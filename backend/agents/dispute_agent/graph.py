"""
Dispute Agent — deterministic sequential pipeline.

Graph topology:
  validate → build_evidence → run_analysis → finalize → END

  validate      : calls validate_dispute_input tool — assigns/confirms case_id
  build_evidence: calls build_evidence_summary tool — formats metadata + document text
  run_analysis  : calls run_dispute_analysis tool — THE ONLY LLM CALL
  finalize      : calls clamp_score + calculate_priority tools — assembles DisputeCase dict
"""
from dotenv import load_dotenv
load_dotenv()

from langgraph.graph import StateGraph, END

from agents.dispute_agent.state import DisputeAgentState
from agents.dispute_agent.nodes.pipeline import (
    validate_node,
    build_evidence_node,
    run_analysis_node,
    finalize_node,
)


def build_dispute_graph():
    g = StateGraph(DisputeAgentState)

    g.add_node("validate",       validate_node)
    g.add_node("build_evidence", build_evidence_node)
    g.add_node("run_analysis",   run_analysis_node)
    g.add_node("finalize",       finalize_node)

    g.set_entry_point("validate")
    g.add_edge("validate",       "build_evidence")
    g.add_edge("build_evidence", "run_analysis")
    g.add_edge("run_analysis",   "finalize")
    g.add_edge("finalize",       END)

    return g.compile()


dispute_graph = build_dispute_graph()
