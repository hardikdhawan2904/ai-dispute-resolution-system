from typing import Annotated, List, Optional, TypedDict

from langgraph.graph.message import add_messages


class InvestigationAgentState(TypedDict):
    messages:                Annotated[list, add_messages]  # full ReAct tool-call / response history
    agent1_output:           dict   # structured classification output from Agent 1 (read-only)
    tool_results:            dict   # accumulated tool call results keyed by tool name (audit)
    investigation_findings:  dict   # intermediate structured findings built during the loop
    final_output:            dict   # final investigation plan returned to the caller
    error:                   Optional[str]
    # Audit + observability (Changes 2, 5, 6)
    tools_used:              List[str]  # ordered unique list of tool names called during the ReAct loop
    agent_metadata:          dict       # agent identity: name, version, model, timestamp, duration_ms
    metrics:                 dict       # total_duration_ms, llm_calls, tool_calls, retry_count
    agent_start_time:        float      # wall-clock start set in run_investigation_agent before graph invoke

