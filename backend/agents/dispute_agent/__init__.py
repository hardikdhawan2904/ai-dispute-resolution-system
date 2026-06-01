"""
ARIA entry point.

run_dispute_agent builds the initial message list (SystemMessage + HumanMessage)
and invokes the LangGraph ReAct loop. The LLM calls all 4 tools autonomously —
validate_dispute_input, build_evidence_summary, calculate_priority, clamp_score —
in whatever order it decides, then produces the final JSON.
"""
import json
from typing import List, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from agents.dispute_agent.graph import dispute_graph
from agents.dispute_agent.state import DisputeAgentState

_SYSTEM_PROMPT = """\
You are ARIA (Automated Resolution Intelligence Agent), a Senior AI Dispute Analyst at a BFSI bank.

## Your task
Analyze the customer dispute submission below and produce a structured investigation brief.

## Workflow — call tools in this order
1. Call validate_dispute_input with customer_id (and existing_case_id if present) → get case_id.
2. Call build_evidence_summary with the transaction_metadata JSON string → get fraud-indicator checklist.
3. Reason over all information: dispute details, evidence checklist, and any uploaded documents.
4. Call calculate_priority with the amount, fraud_suspicion, and risk_tags you determined → get validated priority.
5. Call clamp_score with your confidence_score → get the clamped value to use in output.
6. Respond with ONLY a single valid JSON object — no markdown, no prose, no code fences.

## Output JSON schema
{
  "transaction_type":        "UPI | NEFT | IMPS | Card | ATM | etc.",
  "merchant":                "merchant or payee name",
  "amount":                  0.0,
  "currency":                "INR",
  "dispute_category":        "Unauthorized Transaction | Duplicate Transaction | Refund Not Received | Product Not Received | Subscription Abuse | ATM Cash Issue | Merchant Dispute | Friendly Fraud | Other",
  "fraud_suspicion":         true,
  "customer_intent_summary": "2-3 sentence plain-language summary of the customer claim",
  "priority":                "CRITICAL | HIGH | MEDIUM | LOW",
  "confidence_score":        0.85,
  "risk_tags":               ["TAG_ONE", "TAG_TWO"],
  "structured_reasoning":    "3-5 sentence audit trail explaining the classification",
  "evidence_match":          true,
  "evidence_match_note":     "1-2 sentence note on document relevance"
}

## Priority rules
- CRITICAL : fraud_suspicion=true AND amount > 50000, OR identity theft indicators
- HIGH     : fraud_suspicion=true OR amount > 50000 OR multiple high-risk tags
- MEDIUM   : moderate-confidence dispute, amounts 10000–50000, refund/product issues
- LOW      : minor merchant disputes, low amounts, clear resolution path

## Constraints
- Factual analysis only — no legal or financial advice
- Never fabricate transaction details not present in the input
- Return ONLY valid parseable JSON
- Express uncertainty via confidence_score — never suppress it\
"""


def run_dispute_agent(dispute_input: dict, document_texts: Optional[List[str]] = None) -> dict:
    """
    Entry point called by dispute_service / ops routes.
    The LLM calls all 4 tools autonomously via the ReAct loop.
    Returns the fully structured case dict ready for DB storage.
    """
    docs = document_texts or []
    initial: DisputeAgentState = {
        "messages": [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=_build_human_message(dispute_input, docs)),
        ],
        "dispute_input":  dispute_input,
        "document_texts": docs,
        "final_case":     {},
        "error":          None,
    }
    result = dispute_graph.invoke(initial)
    return result["final_case"]


def _build_human_message(d: dict, doc_texts: list) -> str:
    lines = [
        "## Dispute Submission",
        f"Customer ID    : {d.get('customer_id', 'N/A')}",
        f"Customer Name  : {d.get('customer_name', 'N/A')}",
        f"Transaction ID : {d.get('transaction_id', 'N/A')}",
        f"Type           : {d.get('transaction_type', 'N/A')}",
        f"Merchant       : {d.get('merchant', 'N/A')}",
        f"Amount         : {d.get('currency', 'INR')} {d.get('amount', 0)}",
        f"Date / Time    : {d.get('transaction_date', 'N/A')} {d.get('transaction_time', '')}".rstrip(),
        f"Dispute Reason : {d.get('dispute_reason', 'N/A')}",
        f"Fraud Selected : {d.get('fraud_selected', False)}",
        f"Customer Note  : {d.get('customer_comment') or 'None'}",
        "",
        "## Transaction Metadata",
        json.dumps(d.get("transaction_metadata") or {}, indent=2),
    ]

    if doc_texts:
        lines.append("\n## Uploaded Documents")
        for i, text in enumerate(doc_texts, 1):
            if text.strip():
                body = text[:3000] + ("..." if len(text) > 3000 else "")
                lines.append(f"\nDocument {i}:\n{body}")

    lines.append(
        "\nFollow the workflow: validate_dispute_input → build_evidence_summary → "
        "calculate_priority → clamp_score → final JSON."
    )
    return "\n".join(lines)
