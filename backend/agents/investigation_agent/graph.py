"""
Investigation Intelligence Agent graph — ReAct (agent-tools loop) pattern.

Topology:
  agent ──(tool calls?)──► tools ──► agent   (loop)
  agent ──(no tool calls)─► finalize ──► END

Tools resolved from agent.yaml → TOOL_REGISTRY (same wiring as Agent 1).
"""
from dotenv import load_dotenv
load_dotenv()

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

from agents.investigation_agent.config import get_entry_point, get_agent_tool_names
from agents.investigation_agent.state import InvestigationAgentState
from agents.investigation_agent.tools import TOOL_REGISTRY
from agents.investigation_agent.nodes.pipeline import call_model, should_continue, finalize_node


def build_investigation_graph():
    g = StateGraph(InvestigationAgentState)

    # Resolve callables from TOOL_REGISTRY using names declared in agent.yaml
    _tools = [TOOL_REGISTRY[name] for name in get_agent_tool_names()]

    g.add_node("agent",    call_model)
    # parallel_tool_calls=True on bind_tools lets the LLM batch all calls;
    # ToolNode with max_concurrency runs them concurrently in a thread pool.
    g.add_node("tools",    ToolNode(_tools, handle_tool_errors=True))
    g.add_node("finalize", finalize_node)

    g.set_entry_point(get_entry_point())   # "agent" from agent.yaml

    # Conditional: loop back through tools or exit to finalize
    g.add_conditional_edges(
        "agent",
        should_continue,
        {"tools": "tools", "finalize": "finalize"},
    )
    g.add_edge("tools",    "agent")    # tool results feed back into agent
    g.add_edge("finalize", END)

    return g.compile()


investigation_graph = build_investigation_graph()

