"""
Dispute Understanding Agent — core AI component of the BFSI platform.

Responsibilities:
  - Natural-language complaint understanding
  - Transaction entity extraction
  - Intent classification
  - Fraud indicator detection
  - Structured BFSI JSON generation with reasoning
"""
import os
import json
import time
from typing import Optional
from datetime import datetime, timezone

from dotenv import load_dotenv
load_dotenv()

from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from prompts.dispute_prompts import SYSTEM_PROMPT, DISPUTE_ANALYSIS_PROMPT
from utils.logger import agent_logger, log_workflow_event
from utils.helpers import extract_json_from_text, generate_case_id, utc_now_iso, determine_priority


class DisputeUnderstandingAgent:
    """
    Core AI agent that transforms raw dispute submissions into
    structured BFSI investigation cases using Groq LLM.
    """

    def __init__(self):
        self.llm = ChatGroq(
            model_name=os.getenv("LLM_MODEL", "llama-3.3-70b-versatile"),
            groq_api_key=os.getenv("GROQ_API_KEY"),
            temperature=int(os.getenv("LLM_TEMPERATURE", 0)),
            max_tokens=int(os.getenv("LLM_MAX_TOKENS", 2048)),
        )
        agent_logger.info("DisputeUnderstandingAgent initialized", extra={"agent": "dispute_understanding"})

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    def _invoke_llm(self, messages: list) -> str:
        """Call Groq LLM with automatic retry on transient failures."""
        response = self.llm.invoke(messages)
        return response.content

    def analyze_dispute(self, dispute_input: dict) -> dict:
        """
        Main entry point — analyze a raw dispute form submission.

        Returns a structured dispute case dict ready for database storage
        and downstream workflow nodes.
        """
        case_id = dispute_input.get("case_id") or generate_case_id()
        start_time = time.time()

        log_workflow_event(
            agent_logger,
            event="AGENT_ANALYSIS_START",
            stage="dispute_understanding",
            case_id=case_id,
            customer_id=dispute_input.get("customer_id"),
        )

        # Build the analysis prompt
        prompt_text = DISPUTE_ANALYSIS_PROMPT.format(
            customer_name=dispute_input.get("customer_name", "Unknown"),
            customer_id=dispute_input.get("customer_id", ""),
            email=dispute_input.get("email", ""),
            phone=dispute_input.get("phone", ""),
            transaction_id=dispute_input.get("transaction_id", ""),
            transaction_type=dispute_input.get("transaction_type", ""),
            merchant=dispute_input.get("merchant", ""),
            amount=dispute_input.get("amount", 0),
            currency=dispute_input.get("currency", "INR"),
            transaction_date=dispute_input.get("transaction_date", ""),
            transaction_time=dispute_input.get("transaction_time", ""),
            dispute_reason=dispute_input.get("dispute_reason", ""),
            fraud_selected=dispute_input.get("fraud_selected", False),
            customer_comment=dispute_input.get("customer_comment", ""),
            case_id=case_id,
            created_at=utc_now_iso(),
        )

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=prompt_text),
        ]

        try:
            raw_response = self._invoke_llm(messages)
            elapsed_ms = (time.time() - start_time) * 1000
            agent_logger.info(
                f"LLM responded in {elapsed_ms:.0f}ms",
                extra={"agent": "dispute_understanding", "case_id": case_id},
            )
        except Exception as exc:
            agent_logger.error(f"LLM call failed after retries: {exc}", exc_info=True)
            return self._fallback_case(dispute_input, case_id, error=str(exc))

        # Parse LLM JSON output
        parsed = extract_json_from_text(raw_response)
        if not parsed:
            agent_logger.warning(
                "Failed to parse LLM JSON — using fallback",
                extra={"case_id": case_id, "raw": raw_response[:200]},
            )
            return self._fallback_case(dispute_input, case_id, error="JSON parse failure")

        # Enrich with guaranteed fields
        parsed["case_id"] = case_id
        parsed["customer_id"] = dispute_input.get("customer_id", "")
        parsed.setdefault("status", "Dispute Raised")
        parsed.setdefault("workflow_ready", True)
        parsed.setdefault("created_at", utc_now_iso())

        # Clamp confidence
        parsed["confidence_score"] = max(0.0, min(1.0, float(parsed.get("confidence_score", 0.5))))

        # Fallback priority if missing or invalid
        valid_priorities = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
        if parsed.get("priority") not in valid_priorities:
            parsed["priority"] = determine_priority(
                amount=float(dispute_input.get("amount", 0)),
                fraud_suspicion=parsed.get("fraud_suspicion", False),
                risk_tags=parsed.get("risk_tags", []),
            )

        log_workflow_event(
            agent_logger,
            event="AGENT_ANALYSIS_COMPLETE",
            stage="dispute_understanding",
            case_id=case_id,
            customer_id=dispute_input.get("customer_id"),
            extra={
                "dispute_category": parsed.get("dispute_category"),
                "priority": parsed.get("priority"),
                "confidence_score": parsed.get("confidence_score"),
                "fraud_suspicion": parsed.get("fraud_suspicion"),
                "elapsed_ms": elapsed_ms,
            },
        )

        return parsed

    def _fallback_case(self, dispute_input: dict, case_id: str, error: str = "") -> dict:
        """
        Safe fallback when LLM fails — creates a minimal valid case
        so the dispute is not lost and can be manually reviewed.
        """
        amount = float(dispute_input.get("amount", 0))
        fraud = dispute_input.get("fraud_selected", False)

        return {
            "case_id": case_id,
            "customer_id": dispute_input.get("customer_id", ""),
            "transaction_id": dispute_input.get("transaction_id", ""),
            "transaction_type": dispute_input.get("transaction_type", ""),
            "merchant": dispute_input.get("merchant", ""),
            "amount": amount,
            "currency": dispute_input.get("currency", "INR"),
            "dispute_category": "Other",
            "fraud_suspicion": fraud,
            "customer_intent_summary": (
                "Automated analysis failed — manual review required. "
                f"Customer reported: {dispute_input.get('dispute_reason', 'N/A')}"
            ),
            "priority": determine_priority(amount, fraud, []),
            "confidence_score": 0.1,
            "risk_tags": ["HIGH_PRIORITY_CASE"] if fraud else [],
            "structured_reasoning": (
                f"AI analysis could not be completed due to: {error}. "
                "This case requires manual investigation by the dispute resolution team."
            ),
            "status": "Dispute Raised",
            "workflow_ready": True,
            "created_at": utc_now_iso(),
        }
