"""
Agent 2 — IIA (Investigation Intelligence Agent)

Receives Agent 1's classification output.
Calls 5 investigative tools autonomously via ReAct loop.
Returns a structured investigation plan for the human analyst.

Wiring (identical pattern to Agent 1):
  agent.yaml      → agent_tools names
  config.py       → get_agent_tool_names() reads YAML
  tools.py        → TOOL_REGISTRY[name] = callable
  pipeline.py     → TOOL_REGISTRY[name] for name in names → bind_tools
  graph.py        → TOOL_REGISTRY[name] for name in names → ToolNode
  here            → investigation_graph.invoke({messages: [...], ...})
"""
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage

from agents.investigation_agent.graph import investigation_graph
from agents.investigation_agent.state import InvestigationAgentState
from agents.investigation_agent.tools import _active_case_id
from prompts.investigation_prompts import SYSTEM_PROMPT as _SYSTEM_PROMPT
from utils.pii_masking import mask_id, mask_free_text

_MERCHANT_CATS = {"Merchant Dispute", "Refund Not Received", "Product Not Received", "Subscription Abuse"}


def _run_tools_parallel(a1: dict, active_case_id: str) -> tuple:
    """Run all 5 IIA tools in parallel threads. Returns (results: dict, tools_used: list)."""
    from agents.investigation_agent.tools import (
        lookup_customer_history, check_merchant_risk, find_duplicate_transaction,
        lookup_related_cases, recommend_documents,
    )
    cat        = a1.get("dispute_category", "Other")
    fraud      = a1.get("fraud_suspicion", False)
    risk_tags  = a1.get("risk_tags") or []
    merchant   = (a1.get("merchant") or "")[:50]

    task_defs = {
        "lookup_customer_history": (
            lookup_customer_history, {"customer_id": a1.get("customer_id", "")}
        ),
        "check_merchant_risk": (
            check_merchant_risk, {"merchant_name": merchant}
        ),
        "find_duplicate_transaction": (
            find_duplicate_transaction, {
                "transaction_id": a1.get("transaction_id", ""),
                "customer_id":    a1.get("customer_id", ""),
                "amount":         float(a1.get("amount", 0)),
                "merchant":       merchant[:30],
            }
        ),
        "lookup_related_cases": (
            lookup_related_cases, {
                "dispute_category": cat,
                "merchant": merchant if cat in _MERCHANT_CATS else "",
            }
        ),
        "recommend_documents": (
            recommend_documents, {
                "dispute_category": cat,
                "fraud_suspicion":  fraud,
                "risk_tags":        ", ".join(risk_tags) if risk_tags else "None",
            }
        ),
    }

    def _run_one(name: str, tool_fn, args: dict) -> tuple:
        tok = _active_case_id.set(active_case_id)
        try:
            return name, tool_fn.invoke(args)
        except Exception as exc:
            return name, f"{name.upper()}\n  Error: Tool execution failed — {exc}"
        finally:
            _active_case_id.reset(tok)

    results: dict = {}
    with ThreadPoolExecutor(max_workers=5) as ex:
        futures = {
            ex.submit(_run_one, name, fn, args): name
            for name, (fn, args) in task_defs.items()
        }
        for fut in as_completed(futures):
            name, result = fut.result()
            results[name] = result

    tools_used = list(results.keys())
    return results, tools_used


def run_investigation_agent(agent1_output: dict) -> dict:
    """
    Entry point called by dispute_service / workflow after Agent 1 completes.
    Invokes the ReAct investigation graph and returns the final investigation plan.
    """
    active_case_id = agent1_output.get("case_id", "")
    # Pre-compute all 5 tools in parallel (eliminates ReAct sequential LLM round-trips)
    token = _active_case_id.set(active_case_id)
    try:
        pre_tool_results, pre_tools_used = _run_tools_parallel(agent1_output, active_case_id)
    finally:
        _active_case_id.reset(token)

    token = _active_case_id.set(active_case_id)
    try:
        initial: InvestigationAgentState = {
            "messages": [
                SystemMessage(content=_SYSTEM_PROMPT),
                HumanMessage(content=_build_human_message(agent1_output, pre_tool_results)),
            ],
            "agent1_output":          agent1_output,
            "tool_results":           pre_tool_results,   # pre-stamped for finalize_node
            "investigation_findings": {},
            "final_output":           {},
            "error":                  None,
            "tools_used":             pre_tools_used,     # pre-stamped for finalize_node
            "agent_metadata":         {},
            "metrics":                {},
            "agent_start_time":       time.time(),
        }
        result = investigation_graph.invoke(initial, config={"recursion_limit": 4})
    finally:
        _active_case_id.reset(token)
    return result["final_output"]


def _build_human_message(a1: dict, tool_results: dict) -> str:
    risk_tags = a1.get("risk_tags") or []
    tags_str  = ", ".join(risk_tags) if risk_tags else "None"

    _TOOL_ORDER = [
        "lookup_customer_history", "check_merchant_risk", "find_duplicate_transaction",
        "lookup_related_cases", "recommend_documents",
    ]
    tool_section = "\n\n## PRE-COMPUTED TOOL RESULTS\n(All tools executed — synthesise and produce JSON now)\n"
    for name in _TOOL_ORDER:
        if name in tool_results:
            tool_section += f"\n### {name}\n{tool_results[name]}\n"

    masked_intent = mask_free_text(a1.get("customer_intent_summary", "N/A"))

    return (
        "## Agent 1 Classification Output\n"
        f"Case ID              : {mask_id(a1.get('case_id', 'N/A'))}\n"
        f"Customer ID          : {mask_id(a1.get('customer_id', 'N/A'))}\n"
        f"Transaction ID       : {mask_id(a1.get('transaction_id', 'N/A'), prefix_chars=8)}\n"
        f"Merchant             : {a1.get('merchant', 'N/A')}\n"
        f"Amount               : {a1.get('currency', 'INR')} {a1.get('amount', 0)}\n"
        f"Dispute Category     : {a1.get('dispute_category', 'N/A')}\n"
        f"Fraud Suspicion      : {a1.get('fraud_suspicion', False)}\n"
        f"Confidence Score     : {a1.get('confidence_score', 0.0)}\n"
        f"Risk Tags            : {tags_str}\n"
        f"Customer Intent      : {masked_intent}\n"
        + tool_section
    )
