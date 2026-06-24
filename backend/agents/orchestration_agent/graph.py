"""
Workflow Orchestration Agent graph — ReAct (agent-tools loop) pattern.

Topology:
  agent ──(tool calls?)──► tools ──► agent   (loop)
  agent ──(no tool calls)─► finalize ──► END

Identical topology to Agent 2 (IIA). Tools are pre-run server-side in
run_orchestration_agent; the graph is wired up for future true-ReAct
extension if needed (recursion_limit=4 allows up to 3 extra tool rounds).
"""
from dotenv import load_dotenv
load_dotenv()

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

from agents.orchestration_agent.config import get_entry_point, get_agent_tool_names
from agents.orchestration_agent.state import OrchestrationAgentState
from agents.orchestration_agent.tools import TOOL_REGISTRY
from agents.orchestration_agent.nodes.pipeline import call_model, should_continue, finalize_node


def build_orchestration_graph():
    g = StateGraph(OrchestrationAgentState)

    _tools = [TOOL_REGISTRY[name] for name in get_agent_tool_names()]

    g.add_node("agent",    call_model)
    g.add_node("tools",    ToolNode(_tools, handle_tool_errors=True))
    g.add_node("finalize", finalize_node)

    g.set_entry_point(get_entry_point())   # "agent" from agent.yaml

    g.add_conditional_edges(
        "agent",
        should_continue,
        {"tools": "tools", "finalize": "finalize"},
    )
    g.add_edge("tools",    "agent")
    g.add_edge("finalize", END)

    return g.compile()


orchestration_graph = build_orchestration_graph()

