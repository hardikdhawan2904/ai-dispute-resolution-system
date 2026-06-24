"""CCA LangGraph — validate → generate → deliver → END."""
from langgraph.graph import StateGraph, END

from agents.communication_agent.state import CommunicationAgentState
from agents.communication_agent.nodes.pipeline import validate_node, generate_node, deliver_node


def _build_graph() -> StateGraph:
    g = StateGraph(CommunicationAgentState)
    g.add_node("validate", validate_node)
    g.add_node("generate", generate_node)
    g.add_node("deliver",  deliver_node)

    g.set_entry_point("validate")
    g.add_edge("validate", "generate")
    g.add_edge("generate", "deliver")
    g.add_edge("deliver",  END)

    return g.compile()


communication_graph = _build_graph()

