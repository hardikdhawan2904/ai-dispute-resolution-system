"""
Evidence Intelligence Agent graph — ReAct (agent-tools loop) pattern.

Topology:
  agent ──(tool calls?)──► tools ──► agent   (loop)
  agent ──(no tool calls)─► finalize ──► END

Identical topology to Agent 2 (IIA) and Agent 3 (WOA). Tools are pre-run
server-side in run_evidence_agent; the graph is wired for future true-ReAct
extension if needed (recursion_limit=4 allows up to 3 extra tool rounds).
"""
from dotenv import load_dotenv
load_dotenv()

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

from agents.evidence_agent.config import get_entry_point, get_agent_tool_names
from agents.evidence_agent.state import EvidenceAgentState
from agents.evidence_agent.tools import TOOL_REGISTRY
from agents.evidence_agent.nodes.pipeline import call_model, should_continue, finalize_node


def build_evidence_graph():
    g = StateGraph(EvidenceAgentState)

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


evidence_graph = build_evidence_graph()

