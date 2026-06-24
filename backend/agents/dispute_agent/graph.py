"""
Dispute Understanding Agent graph — ReAct (agent-tools loop) pattern.

Topology:
  validate → build_evidence → agent ──(tool calls?)──► tools ──► agent   (loop)
                                     └──(no tool calls)─► finalize ──► END

Pre-processing (validate, build_evidence) is deterministic.
The ReAct loop starts at 'agent': the LLM decides which understanding tools to call,
uses their results to reason, then produces the final classification JSON.
"""
from dotenv import load_dotenv
load_dotenv()

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

from agents.dispute_agent.config import get_entry_point, get_agent_tool_names
from agents.dispute_agent.state import DisputeAgentState
from agents.dispute_agent.tools import TOOL_REGISTRY
from agents.dispute_agent.nodes.pipeline import (
    validate_node,
    build_evidence_node,
    call_model,
    should_continue,
    finalize_node,
)


def build_dispute_graph():
    g = StateGraph(DisputeAgentState)

    # Resolve callables from TOOL_REGISTRY using names declared in agent.yaml
    _tools = [TOOL_REGISTRY[name] for name in get_agent_tool_names()]

    g.add_node("validate",       validate_node)
    g.add_node("build_evidence", build_evidence_node)
    g.add_node("agent",          call_model)
    g.add_node("tools",          ToolNode(_tools))
    g.add_node("finalize",       finalize_node)

    g.set_entry_point(get_entry_point())   # "validate" from agent.yaml

    g.add_edge("validate",       "build_evidence")
    g.add_edge("build_evidence", "agent")

    # Conditional: loop back through tools or exit to finalize
    g.add_conditional_edges(
        "agent",
        should_continue,
        {"tools": "tools", "finalize": "finalize"},
    )
    g.add_edge("tools",    "agent")     # tool results feed back into agent
    g.add_edge("finalize", END)

    return g.compile()


dispute_graph = build_dispute_graph()

