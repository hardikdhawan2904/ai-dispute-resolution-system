from typing import TypedDict, Optional, List


class DisputeAgentState(TypedDict):
    # ── Input ───────────────────────────────────────────────────────────────────
    dispute_input: dict
    document_texts: List[str]   # extracted text from each uploaded file

    # ── Derived in validate_input ───────────────────────────────────────────────
    case_id: str

    # ── Derived in build_evidence ───────────────────────────────────────────────
    supporting_evidence: str

    # ── Derived in run_llm ─────────────────────────────────────────────────────
    raw_llm_response: str

    # ── Derived in enrich_output ───────────────────────────────────────────────
    final_case: dict

    # ── Error channel ──────────────────────────────────────────────────────────
    error: Optional[str]
