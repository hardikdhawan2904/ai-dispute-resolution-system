from typing import List, Optional

from agents.dispute_agent.graph import dispute_graph
from agents.dispute_agent.state import DisputeAgentState


def run_dispute_agent(dispute_input: dict, document_texts: Optional[List[str]] = None) -> dict:
    """
    Entry point — run the dispute understanding pipeline.
    Evidence text is extracted before this call and passed in as document_texts
    so everything goes to the LLM in a single call.

    Returns the structured case dict ready for DB storage.
    """
    initial: DisputeAgentState = {
        "dispute_input":      dispute_input,
        "document_texts":     document_texts or [],
        "case_id":            "",
        "supporting_evidence": "",
        "document_section":   "",
        "raw_llm_response":   "",
        "final_case":         {},
        "error":              None,
    }
    result = dispute_graph.invoke(initial)
    return result["final_case"]
