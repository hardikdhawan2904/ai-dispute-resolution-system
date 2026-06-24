"""
Workflow Orchestration Agent — ReAct pipeline nodes.

call_model      : invoke LLM (pre-computed tool results already in messages)
should_continue : route to 'tools' if tool calls pending, else to 'finalize'
finalize_node   : parse final JSON, extract audit trail, stamp server-owned
                  fields (tools_used, agent_metadata, metrics,
                  workflow_execution_id, workflow_version)
"""
from __future__ import annotations

import os
import time
import uuid
from typing import Literal

from langchain_core.messages import AIMessage, ToolMessage
from langchain_groq import ChatGroq
from groq import RateLimitError as GroqRateLimitError
from tenacity import retry, retry_if_not_exception_type, stop_after_attempt, wait_exponential

from agents.orchestration_agent.config import get_llm_config, get_agent_tool_names, load_agent_config
from agents.orchestration_agent.state import OrchestrationAgentState
from agents.orchestration_agent.tools import (
    TOOL_REGISTRY,
    _FRAUD_CATEGORIES, _MERCHANT_CATEGORIES,
    _ALWAYS_EVIDENCE_CATEGORIES, _COMPLIANCE_TAGS, _AGENT_ORDER,
)
from utils.helpers import extract_json_from_text, utc_now_iso
from utils.logger import agent_logger, log_workflow_event

# ── LLM + tools + agent identity ─────────────────────────────────────────────
_cfg        = get_llm_config()
_agent_yaml = load_agent_config()["agent"]
_AGENT_NAME = _agent_yaml["full_name"]    # "Workflow Orchestration Agent"
_AGENT_VER  = str(_agent_yaml["version"]) # "1.0.0"
_WF_VERSION = "1.0"

_tools = [TOOL_REGISTRY[name] for name in get_agent_tool_names()]

_llm = ChatGroq(
    model_name=os.environ.get("WOA_MODEL") or os.environ.get("LLM_MODEL") or _cfg["model"],
    temperature=_cfg["temperature"],
    max_tokens=_cfg["max_tokens"],
    api_key=os.environ.get("GROQ_API_KEY"),
)


# ── Nodes ──────────────────────────────────────────────────────────────────────

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(min=2, max=10),
    retry=retry_if_not_exception_type(GroqRateLimitError),
    reraise=True,
)
def call_model(state: OrchestrationAgentState) -> dict:
    """Agent node — tools are pre-computed; single LLM call synthesises the workflow plan."""
    response = _llm.invoke(state["messages"])
    agent_logger.debug("WOA LLM response received")
    return {"messages": [response]}


def should_continue(state: OrchestrationAgentState) -> Literal["tools", "finalize"]:
    last: AIMessage = state["messages"][-1]
    if getattr(last, "tool_calls", None):
        return "tools"
    return "finalize"


def finalize_node(state: OrchestrationAgentState) -> dict:
    """
    Parse the LLM's final JSON workflow plan.
    Stamp server-owned fields: tools_used, agent_metadata, metrics,
    workflow_execution_id, workflow_version.
    """
    case_input = state.get("case_input") or {}
    case_id    = case_input.get("case_id", "")

    # ── Timing ────────────────────────────────────────────────────────────────
    start_time  = state.get("agent_start_time") or 0.0
    duration_ms = round((time.time() - start_time) * 1000, 1) if start_time else 0.0

    # ── Audit trail ───────────────────────────────────────────────────────────
    messages      = state.get("messages") or []
    tool_results  = dict(state.get("tool_results") or {})
    tools_used    = list(state.get("tools_used") or [])
    llm_call_count = 0
    tool_msg_count = len(tool_results)

    for msg in messages:
        if isinstance(msg, AIMessage):
            llm_call_count += 1
            for tc in (getattr(msg, "tool_calls", None) or []):
                name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", "")
                if name and name not in tools_used:
                    tools_used.append(name)
        elif isinstance(msg, ToolMessage):
            tool_msg_count += 1
            if getattr(msg, "name", None):
                tool_results[msg.name] = msg.content

    metrics = {
        "total_duration_ms": duration_ms,
        "llm_calls":         llm_call_count,
        "tool_calls":        tool_msg_count,
        "retry_count":       0,
    }
    agent_metadata = {
        "agent_name":            _AGENT_NAME,
        "agent_version":         _AGENT_VER,
        "model":                 _cfg["model"],
        "execution_timestamp":   utc_now_iso(),
        "execution_duration_ms": duration_ms,
    }

    # ── Parse LLM final JSON ──────────────────────────────────────────────────
    last   = messages[-1] if messages else None
    raw    = last.content if last and hasattr(last, "content") else ""
    parsed = extract_json_from_text(raw) if raw else None

    if not parsed:
        agent_logger.warning("WOA JSON parse failed — using fallback", extra={"case_id": case_id})
        fb = _fallback_output(case_input, case_id, tools_used, agent_metadata, metrics)
        return {
            "final_output":   fb,
            "tool_results":   tool_results,
            "tools_used":     tools_used,
            "agent_metadata": agent_metadata,
            "metrics":        metrics,
        }

    # ── Stamp server-owned fields — LLM cannot fabricate these ───────────────
    parsed["case_id"]              = case_id
    parsed["created_at"]           = utc_now_iso()
    parsed["tools_used"]           = tools_used
    parsed["agent_metadata"]       = agent_metadata
    parsed["metrics"]              = metrics
    parsed["workflow_execution_id"] = f"WF-{uuid.uuid4().hex[:12].upper()}"
    parsed["workflow_version"]     = _WF_VERSION
    parsed["fallback_mode"]        = False
    parsed["failure_reason"]       = None

    # Defaults for optional fields
    parsed.setdefault("workflow_complexity",            "MEDIUM")
    parsed.setdefault("required_agents",                [])
    parsed.setdefault("workflow_path",                  [])
    parsed.setdefault("next_agent",                     None)
    parsed.setdefault("remaining_agents",               [])
    parsed.setdefault("escalation_required",            False)
    parsed.setdefault("escalation_level",               None)
    parsed.setdefault("manual_review_required",         False)
    parsed.setdefault("estimated_investigation_hours",  2)
    parsed.setdefault("analyst_level",                  "STANDARD")
    parsed.setdefault("workflow_reasoning",             [])
    parsed.setdefault("tool_decisions",                 [])

    # ── Server-side workflow path — tool results are authoritative over LLM ─────
    try:
        inv_plan  = case_input.get("investigation_plan") or {}
        category  = case_input.get("dispute_category") or "Other"
        fraud     = case_input.get("fraud_suspicion") or case_input.get("fraud_selected") or False
        tags      = case_input.get("risk_tags") or []
        ev_match  = case_input.get("evidence_match")

        authoritative: list = []
        if fraud or category in _FRAUD_CATEGORIES:
            authoritative.append("FRAUD_AGENT")
        has_doc_gaps = (
            ev_match is not True
            or (isinstance(inv_plan, dict) and bool(inv_plan.get("required_documents")))
            or category in _ALWAYS_EVIDENCE_CATEGORIES
        )
        if has_doc_gaps:
            authoritative.append("EVIDENCE_AGENT")
        if category in _MERCHANT_CATEGORIES:
            authoritative.append("MERCHANT_AGENT")
        if any(t in _COMPLIANCE_TAGS for t in tags):
            authoritative.append("COMPLIANCE_AGENT")

        seen = set()
        authoritative_path = [a for a in _AGENT_ORDER if a in authoritative and not seen.add(a)]

        if authoritative_path:
            parsed["workflow_path"]   = authoritative_path
            parsed["required_agents"] = authoritative_path
    except Exception as _e:
        agent_logger.warning(f"WOA server-side path validation failed: {_e}")

    # completed_agents — preserve LLM-returned list when valid (it may have read
    # prior tool results correctly); default to []. Auto-mark FRAUD_AGENT complete
    # when fraud_reasoning_brief already exists from a prior run.
    if not isinstance(parsed.get("completed_agents"), list):
        parsed["completed_agents"] = []
    else:
        parsed["completed_agents"] = list(parsed["completed_agents"])

    if case_input.get("fraud_reasoning_brief") and "FRAUD_AGENT" not in parsed["completed_agents"]:
        parsed["completed_agents"].append("FRAUD_AGENT")

    # workflow_status — server-stamped deterministically from execution state.
    # LLM's WAITING is honoured (signals a blocking dependency it detected);
    # all other values are overwritten by the server.
    _next      = parsed.get("next_agent")
    _completed = parsed.get("completed_agents") or []
    _escalate  = parsed.get("escalation_required", False)
    _llm_status = parsed.get("workflow_status", "")

    if _llm_status == "WAITING":
        pass  # blocking dependency detected by LLM — preserve
    elif _next is None:
        parsed["workflow_status"] = "ESCALATED" if _escalate else "COMPLETED"
    elif _completed:
        parsed["workflow_status"] = "IN_PROGRESS"
    else:
        parsed["workflow_status"] = "READY"

    log_workflow_event(
        agent_logger,
        event="WOA_ORCHESTRATION_COMPLETE",
        stage="workflow_orchestration",
        case_id=case_id,
        extra={
            "workflow_complexity":  parsed.get("workflow_complexity"),
            "required_agents":      parsed.get("required_agents"),
            "next_agent":           parsed.get("next_agent"),
            "escalation_required":  parsed.get("escalation_required"),
            "duration_ms":          duration_ms,
        },
    )

    return {
        "final_output":   parsed,
        "tool_results":   tool_results,
        "tools_used":     tools_used,
        "agent_metadata": agent_metadata,
        "metrics":        metrics,
    }


# ── Fallback ───────────────────────────────────────────────────────────────────

def _fallback_output(
    case_input: dict,
    case_id: str,
    tools_used: list,
    agent_metadata: dict,
    metrics: dict,
) -> dict:
    """Deterministic safe workflow plan when LLM output cannot be parsed."""
    fraud    = case_input.get("fraud_suspicion") or case_input.get("fraud_selected") or False
    amount   = float(case_input.get("amount") or 0)
    category = case_input.get("dispute_category") or "Other"

    from agents.orchestration_agent.tools import (
        _FRAUD_CATEGORIES, _MERCHANT_CATEGORIES, _COMPLIANCE_TAGS,
        _ANALYST_LEVEL, _BASE_HOURS,
    )

    required = []
    if fraud or category in _FRAUD_CATEGORIES:
        required.append("FRAUD_AGENT")
    if category in _MERCHANT_CATEGORIES:
        required.append("MERCHANT_AGENT")
    if any(t in _COMPLIANCE_TAGS for t in (case_input.get("risk_tags") or [])):
        required.append("COMPLIANCE_AGENT")

    if (fraud and amount > 50_000):
        complexity = "CRITICAL"
    elif fraud or amount > 50_000:
        complexity = "HIGH"
    else:
        complexity = "MEDIUM"

    base_hours  = _BASE_HOURS.get(complexity, 2)
    total_hours = base_hours + len(required)
    analyst_lvl = _ANALYST_LEVEL.get(complexity, "STANDARD")

    escalation_required = complexity in ("HIGH", "CRITICAL")
    escalation_level    = complexity if escalation_required else None

    next_agent     = required[0] if required else None
    remaining      = required[1:] if required else []

    return {
        "case_id":                      case_id,
        "workflow_complexity":           complexity,
        "required_agents":              required,
        "workflow_path":                required,
        "workflow_status":              "ESCALATED" if (escalation_required and next_agent is None) else ("COMPLETED" if next_agent is None else "READY"),
        "next_agent":                   next_agent,
        "remaining_agents":             remaining,
        "completed_agents":             [],
        "escalation_required":          escalation_required,
        "escalation_level":             escalation_level,
        "manual_review_required":       True,
        "estimated_investigation_hours": total_hours,
        "analyst_level":                analyst_lvl,
        "workflow_reasoning": [
            "Automated orchestration failed — LLM output could not be parsed.",
            f"Fallback routing applied for category '{category}' and fraud={fraud}.",
            "Manual review is mandatory.",
        ],
        "tool_decisions": [],
        "tools_used":     tools_used,
        "agent_metadata": agent_metadata,
        "metrics":        metrics,
        "workflow_execution_id": f"WF-FALLBACK-{uuid.uuid4().hex[:8].upper()}",
        "workflow_version":     _WF_VERSION,
        "fallback_mode":        True,
        "failure_reason":       "LLM_OUTPUT_PARSE_FAILURE",
        "created_at":           utc_now_iso(),
    }

