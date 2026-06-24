from typing import Annotated, List, Optional, TypedDict

from langgraph.graph.message import add_messages


class DisputeAgentState(TypedDict):
    messages:            Annotated[list, add_messages]  # full ReAct tool-call / response history
    dispute_input:       dict        # raw submission fields
    document_texts:      List[str]   # OCR-extracted evidence files
    case_id:             str         # assigned before LLM call
    supporting_evidence: str         # formatted fraud-indicator checklist
    document_section:    str         # formatted document block passed to LLM
    final_case:          dict        # parsed + stamped output for DB
    error:               Optional[str]
    # Audit + observability
    tools_used:          List[str]   # ordered list of tool names called during the ReAct loop
    agent_metadata:      dict        # name, version, model, timestamp, duration_ms
    metrics:             dict        # total_duration_ms, llm_calls, tool_calls, retry_count
    agent_start_time:    float       # wall-clock start set in validate_node

