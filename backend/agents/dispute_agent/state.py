from typing import TypedDict, Optional, List


class DisputeAgentState(TypedDict):
    dispute_input: dict
    document_texts: List[str]
    case_id: str
    supporting_evidence: str
    document_section: str
    raw_llm_response: str
    final_case: dict
    error: Optional[str]
