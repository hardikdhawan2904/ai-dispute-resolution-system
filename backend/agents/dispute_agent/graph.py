"""
Dispute Agent graph — ReAct (agent-tools loop) pattern.

Topology (mirrors agent.yaml → langgraph → pipeline):
  agent ──(tool calls?)──► tools ──► agent   (loop)
  agent ──(no tool calls)─► finalize ──► END
"""
from dotenv import load_dotenv
load_dotenv()

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

from agents.dispute_agent.config import get_entry_point
from agents.dispute_agent.state import DisputeAgentState
from agents.dispute_agent.tools import TOOLS
from agents.dispute_agent.nodes.pipeline import call_model, should_continue, finalize_node


def build_dispute_graph():
    g = StateGraph(DisputeAgentState)

    g.add_node("agent",    call_model)
    g.add_node("tools",    ToolNode(TOOLS))
    g.add_node("finalize", finalize_node)

    g.set_entry_point(get_entry_point())  # "agent" from agent.yaml

    # Conditional: loop back through tools or exit to finalize
    g.add_conditional_edges(
        "agent",
        should_continue,
        {"tools": "tools", "finalize": "finalize"},
    )
    g.add_edge("tools",    "agent")   # tool results feed back into agent
    g.add_edge("finalize", END)

    return g.compile()


dispute_graph = build_dispute_graph()
