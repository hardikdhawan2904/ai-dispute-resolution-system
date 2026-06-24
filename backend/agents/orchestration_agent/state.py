from typing import Annotated, List, Optional, TypedDict

from langgraph.graph.message import add_messages


class OrchestrationAgentState(TypedDict):
    messages:         Annotated[list, add_messages]  # full ReAct tool-call / response history
    case_input:       dict    # combined Agent 1 + Agent 2 data read from DB
    tool_results:     dict    # pre-computed tool results keyed by tool name
    final_output:     dict    # final workflow plan returned to the caller
    error:            Optional[str]
    # Audit + observability
    tools_used:       List[str]  # ordered list of tool names executed
    agent_metadata:   dict       # agent identity, model, version, timestamp, duration_ms
    metrics:          dict       # total_duration_ms, llm_calls, tool_calls, retry_count
    agent_start_time: float      # wall-clock start set in run_orchestration_agent

