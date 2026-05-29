import os
import time

from dotenv import load_dotenv
load_dotenv()

from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from agents.dispute_agent.state import DisputeAgentState
from prompts.dispute_prompts import SYSTEM_PROMPT, DISPUTE_ANALYSIS_PROMPT
from utils.helpers import utc_now_iso
from utils.logger import agent_logger


def _build_llm() -> ChatGroq:
    return ChatGroq(
        model_name=os.getenv("LLM_MODEL", "llama-3.3-70b-versatile"),
        groq_api_key=os.getenv("GROQ_API_KEY"),
        temperature=int(os.getenv("LLM_TEMPERATURE", 0)),
        max_tokens=int(os.getenv("LLM_MAX_TOKENS", 2048)),
    )


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(Exception),
    reraise=True,
)
def _call_llm(llm: ChatGroq, messages: list) -> str:
    return llm.invoke(messages).content


def run_llm(state: DisputeAgentState) -> dict:
    d = state["dispute_input"]
    case_id = state["case_id"]

    doc_texts = state.get("document_texts") or []
    if doc_texts:
        parts = [f"Document {i+1}:\n{t}" for i, t in enumerate(doc_texts) if t.strip()]
        document_section = "\n\n".join(parts) if parts else "  No documents attached."
    else:
        document_section = "  No documents attached."

    prompt_text = DISPUTE_ANALYSIS_PROMPT.format(
        customer_name=d.get("customer_name", "Unknown"),
        customer_id=d.get("customer_id", ""),
        transaction_type=d.get("transaction_type", ""),
        merchant=d.get("merchant", ""),
        amount=d.get("amount", 0),
        currency=d.get("currency", "INR"),
        transaction_date=d.get("transaction_date", ""),
        transaction_time=d.get("transaction_time", ""),
        dispute_reason=d.get("dispute_reason", ""),
        fraud_selected=d.get("fraud_selected", False),
        customer_comment=d.get("customer_comment", ""),
        supporting_evidence=state["supporting_evidence"],
        document_section=document_section,
        case_id=case_id,
        created_at=utc_now_iso(),
    )

    messages = [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=prompt_text)]

    try:
        start = time.time()
        raw = _call_llm(_build_llm(), messages)
        elapsed_ms = (time.time() - start) * 1000
        agent_logger.info(
            f"LLM responded in {elapsed_ms:.0f}ms",
            extra={"agent": "dispute_understanding", "case_id": case_id},
        )
        return {"raw_llm_response": raw, "error": None}
    except Exception as exc:
        agent_logger.error(f"LLM call failed after retries: {exc}", exc_info=True)
        return {"raw_llm_response": "", "error": str(exc)}
