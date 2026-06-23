from typing import Annotated, List, Optional, TypedDict
from langgraph.graph.message import add_messages


class FraudReasoningAgentState(TypedDict):
    messages:            Annotated[list, add_messages]  # ReAct history
    dispute_input:       dict        # raw intake fields
    case_id:             str         # assigned before LLM call
    tool_results:        dict        # pre-computed tool results
    final_output:        dict        # parsed output for DB updates
    error:               Optional[str]
    channel:             str         # DIGITAL | CARD_POS | ATM

    # Audit trail
    tools_used:          List[str]
    agent_metadata:      dict
    metrics:             dict
    agent_start_time:    float
