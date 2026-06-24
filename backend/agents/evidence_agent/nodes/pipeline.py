"""
Evidence Intelligence Agent — ReAct pipeline nodes.

call_model      : invoke LLM with all 5 tools bound (via TOOL_REGISTRY + agent.yaml)
should_continue : route to 'tools' if tool calls pending, else to 'finalize'
finalize_node   : parse the LLM's final JSON, extract tool_results from message history,
                  stamp server-owned audit fields (tools_used, agent_metadata, metrics),
                  assemble final_output
"""
from __future__ import annotations

import os
import time
from typing import Literal

from langchain_core.messages import AIMessage, ToolMessage
from langchain_groq import ChatGroq
from groq import RateLimitError as GroqRateLimitError
from tenacity import retry, retry_if_not_exception_type, stop_after_attempt, wait_exponential

from agents.evidence_agent.config import get_llm_config, get_agent_tool_names, load_agent_config
from agents.evidence_agent.state import EvidenceAgentState
from agents.evidence_agent.tools import TOOL_REGISTRY
from utils.helpers import extract_json_from_text, utc_now_iso
from utils.logger import agent_logger, log_workflow_event

# ── LLM + tools + agent identity (all sourced from agent.yaml) ───────────────
_cfg        = get_llm_config()
_agent_yaml = load_agent_config()["agent"]
_AGENT_NAME = _agent_yaml["full_name"]    # "Evidence Intelligence Agent"
_AGENT_VER  = str(_agent_yaml["version"]) # "1.0.0"
_tools = [TOOL_REGISTRY[name] for name in get_agent_tool_names()]

_llm = ChatGroq(
    model_name=os.environ.get("EIA_MODEL") or os.environ.get("LLM_MODEL") or _cfg["model"],
    temperature=_cfg["temperature"],
    max_tokens=_cfg["max_tokens"],
    api_key=os.environ.get("GROQ_API_KEY"),
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _count_fulfilled(tool_results: dict) -> int:
    """Extract fulfilled request count from the completeness tool output string."""
    raw = tool_results.get("evaluate_evidence_completeness", "")
    for line in raw.splitlines():
        if "Fulfilled Requests" in line:
            try:
                return int(line.split(":")[-1].strip())
            except (ValueError, IndexError):
                pass
    return 0


def _build_evidence_summary(
    completeness: int,
    strength: str,
    ev_match,
    missing_docs: list,
    consistency_issues: list,
    investigation_blocked: bool,
    fulfilled_count: int,
    upload_count: int = 0,
) -> list:
    """
    Build evidence_summary bullets deterministically from tool results.
    Never trusts the LLM for this — avoids hallucination of contradictory findings.
    """
    bullets = []

    # Bullet 1 — Agent 1 evidence verdict
    if ev_match is True:
        bullets.append("Agent 1 evidence verdict: submitted documents support the claim.")
    elif ev_match is False:
        bullets.append("Agent 1 evidence verdict: submitted documents do NOT support the claim.")
    else:
        bullets.append("Agent 1 evidence verdict: no documents were submitted — match not assessed.")

    # Bullet 2 — completeness (upload-aware)
    evidence_present = fulfilled_count + upload_count
    if len(missing_docs) == 0 and evidence_present > 0:
        src = f"{fulfilled_count} fulfilled request(s)" if fulfilled_count else f"{upload_count} uploaded file(s)"
        bullets.append(f"All required documents are present ({src}).")
    elif len(missing_docs) == 0:
        bullets.append("No formal document requirements defined for this dispute category.")
    elif upload_count > 0 and ev_match is True:
        bullets.append(
            f"{upload_count} file(s) uploaded and verified by Agent 1. "
            f"{len(missing_docs)} document(s) still required: "
            + ", ".join(missing_docs[:2])
            + ("…" if len(missing_docs) > 2 else ".")
        )
    else:
        bullets.append(
            f"{len(missing_docs)} required document(s) not yet submitted: "
            + ", ".join(missing_docs[:3])
            + ("…" if len(missing_docs) > 3 else ".")
        )

    # Bullet 3 — consistency
    real_issues = [i for i in consistency_issues if "not found" not in i.lower()]
    if real_issues:
        bullets.append(f"Transaction detail inconsistency: {real_issues[0]}")
    elif any("not found" in i.lower() for i in consistency_issues):
        bullets.append("Transaction not found in records — consistency check could not be completed.")
    else:
        bullets.append("No transaction detail inconsistencies found.")

    # Bullet 4 — overall verdict
    if investigation_blocked:
        bullets.append(
            f"Investigation is blocked — {len(missing_docs)} document(s) must be submitted before proceeding."
        )
    elif strength == "HIGH":
        bullets.append("Evidence quality is HIGH — sufficient to proceed with investigation.")
    elif strength == "MEDIUM":
        bullets.append(f"Evidence quality is MEDIUM ({completeness}% complete) — investigation can proceed with caution.")
    else:
        bullets.append(f"Evidence quality is LOW ({completeness}% complete) — additional documentation strongly recommended.")

    return bullets


# ── Nodes ──────────────────────────────────────────────────────────────────────

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(min=2, max=10),
    retry=retry_if_not_exception_type(GroqRateLimitError),
    reraise=True,
)
def call_model(state: EvidenceAgentState) -> dict:
    """Agent node — tools are pre-computed; single LLM call synthesises evidence assessment."""
    response = _llm.invoke(state["messages"])
    agent_logger.debug("EIA LLM response received")
    return {"messages": [response]}


def should_continue(state: EvidenceAgentState) -> Literal["tools", "finalize"]:
    """Conditional edge — tool calls pending → tools node, otherwise → finalize."""
    last: AIMessage = state["messages"][-1]
    if getattr(last, "tool_calls", None):
        return "tools"
    return "finalize"


def finalize_node(state: EvidenceAgentState) -> dict:
    """
    Parse the LLM's final JSON evidence assessment.
    Extracts audit trail from message history.
    Stamps server-owned fields: tools_used, agent_metadata, metrics.
    Assembles final_output.
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
        agent_logger.warning("EIA JSON parse failed — using fallback", extra={"case_id": case_id})
        fb = _fallback_output(case_input, case_id, tools_used, agent_metadata, metrics)
        return {
            "final_output":   fb,
            "tool_results":   tool_results,
            "tools_used":     tools_used,
            "agent_metadata": agent_metadata,
            "metrics":        metrics,
        }

    # ── Stamp server-owned fields — LLM cannot fabricate these ───────────────
    parsed["case_id"]       = case_id
    parsed["created_at"]    = utc_now_iso()
    parsed["tools_used"]    = tools_used
    parsed["agent_metadata"] = agent_metadata
    parsed["metrics"]       = metrics
    parsed["fallback_mode"] = False
    parsed["failure_reason"] = None

    # Defaults for optional LLM-generated fields
    parsed.setdefault("evidence_completeness",         50)
    parsed.setdefault("evidence_strength",             "MEDIUM")
    parsed.setdefault("evidence_strength_score",       0.50)
    parsed.setdefault("evidence_consistent",           True)
    parsed.setdefault("consistency_issues",            [])
    parsed.setdefault("missing_documents",             [])
    parsed.setdefault("recommended_document_requests", [])
    parsed.setdefault("investigation_blocked",         False)
    parsed.setdefault("manual_evidence_review",        False)
    parsed.setdefault("tool_decisions",                [])

    # Sanitise numeric fields
    try:
        parsed["evidence_completeness"] = int(parsed["evidence_completeness"])
    except (TypeError, ValueError):
        parsed["evidence_completeness"] = 50

    try:
        parsed["evidence_strength_score"] = float(parsed["evidence_strength_score"])
    except (TypeError, ValueError):
        parsed["evidence_strength_score"] = 0.50

    # ── Server-stamp evidence_strength / score / completeness from tool output ─
    # Tool 4 (assess_evidence_strength) computes these deterministically.
    # Always override LLM values to prevent hallucinated strength/score.
    _es_raw = tool_results.get("assess_evidence_strength", "")
    if _es_raw:
        for _line in _es_raw.splitlines():
            _s = _line.strip()
            if _s.startswith("Strength") and "Score" not in _s and ":" in _s:
                _v = _s.split(":", 1)[1].strip()
                if _v in ("HIGH", "MEDIUM", "LOW"):
                    parsed["evidence_strength"] = _v
            elif _s.startswith("Strength Score") and ":" in _s:
                try:
                    parsed["evidence_strength_score"] = round(
                        float(_s.split(":", 1)[1].strip()), 2
                    )
                except (ValueError, IndexError):
                    pass

    _ec_raw = tool_results.get("evaluate_evidence_completeness", "")
    if _ec_raw:
        for _line in _ec_raw.splitlines():
            _s = _line.strip()
            if _s.startswith("Completeness Score") and ":" in _s:
                try:
                    # Format: "Completeness Score       : 75% (customer docs only)"
                    parsed["evidence_completeness"] = int(
                        _s.split(":", 1)[1].strip().split("%")[0].strip()
                    )
                except (ValueError, IndexError):
                    pass
                break

    # ── Server-stamp fields that must be internally consistent ────────────────
    # evidence_consistent: true only when there are no actual issues.
    real_issues = [
        i for i in (parsed.get("consistency_issues") or [])
        if "not found" not in i.lower()
    ]
    parsed["evidence_consistent"] = len(real_issues) == 0

    # investigation_blocked: recompute from hard signals — never trust LLM for this.
    strength     = parsed.get("evidence_strength", "MEDIUM")
    ev_match     = case_input.get("evidence_match")
    completeness = parsed["evidence_completeness"]

    from agents.evidence_agent.tools import _count_uploads, _split_docs
    upload_count = _count_uploads(case_input.get("case_id", ""))

    # ── Server-stamp missing_documents and recommended_document_requests ──────
    # The LLM frequently lists docs as missing even when uploads already cover them.
    # Recompute from the same upload-credit logic used in the tools so the output
    # is always consistent with evidence_completeness and investigation_blocked.
    inv_plan      = case_input.get("investigation_plan") or {}
    all_required  = inv_plan.get("required_documents", []) if isinstance(inv_plan, dict) else []
    customer_docs, bank_docs = _split_docs(all_required)

    # Replicate Tools 1 & 2 logic: formal requests + upload credits
    from database.database import SessionLocal
    from database.models import DocumentRequest as _DR
    _db = SessionLocal()
    try:
        _reqs = _db.query(_DR).filter(_DR.case_id == case_id).all()
        fulfilled_types = {r.document_type.lower() for r in _reqs if r.fulfilled}
    except Exception:
        fulfilled_types = set()
    finally:
        _db.close()

    def _is_fulfilled_req(doc: str) -> bool:
        d = doc.lower()
        return any(d in ft or ft in d for ft in fulfilled_types)

    req_without = [d for d in customer_docs if not _is_fulfilled_req(d)]
    upload_credits = min(upload_count, len(req_without)) if ev_match is True else 0
    missing_docs = req_without[upload_credits:]  # authoritative missing list

    parsed["missing_documents"] = missing_docs
    # Recommended requests = missing customer docs not already pending
    _pending_types = set()
    _db2 = SessionLocal()
    try:
        _pending = _db2.query(_DR).filter(_DR.case_id == case_id, _DR.fulfilled == False).all()
        _pending_types = {r.document_type.lower() for r in _pending}
    except Exception:
        pass
    finally:
        _db2.close()

    parsed["recommended_document_requests"] = [
        d for d in missing_docs
        if not any(d.lower() in p or p in d.lower() for p in _pending_types)
    ]

    # Bank-obtainable docs — server-stamped, informational only.
    # These are obtained by the bank/merchant internally; they do NOT affect
    # completeness, strength, or investigation_blocked.
    parsed["bank_pending_documents"] = bank_docs

    # Cap strength at MEDIUM when customer docs are still outstanding —
    # HIGH strength with missing docs is contradictory from an analyst perspective.
    _customer_docs_missing = [
        d for d in missing_docs
        if d not in (parsed.get("bank_pending_documents") or [])
    ]
    if _customer_docs_missing and strength == "HIGH":
        strength = "MEDIUM"
        parsed["evidence_strength"] = "MEDIUM"

    parsed["investigation_blocked"] = (
        (ev_match is False and len(missing_docs) > 0)
        or (strength == "LOW" and len(missing_docs) > 0 and upload_count == 0)
        or (completeness < 25 and upload_count == 0 and ev_match is not True)
    )

    parsed["manual_evidence_review"] = (
        parsed["investigation_blocked"]
        or strength == "LOW"
        or len(_customer_docs_missing) > 0
    )

    parsed["review_recommendation"] = (
        "Additional documentation required before investigation can proceed."
        if (parsed["investigation_blocked"] or len(_customer_docs_missing) > 0)
        else "Evidence is sufficient to continue the investigation."
    )

    # ── Server-stamp evidence_summary ─────────────────────────────────────────
    parsed["evidence_summary"] = _build_evidence_summary(
        completeness    = parsed["evidence_completeness"],
        strength        = parsed["evidence_strength"],
        ev_match        = ev_match,
        missing_docs    = missing_docs,
        consistency_issues = parsed.get("consistency_issues") or [],
        investigation_blocked = parsed["investigation_blocked"],
        fulfilled_count = _count_fulfilled(tool_results),
        upload_count    = upload_count,
    )

    log_workflow_event(
        agent_logger,
        event="EIA_EVIDENCE_ASSESSMENT_COMPLETE",
        stage="evidence_intelligence",
        case_id=case_id,
        customer_id=case_input.get("customer_id"),
        extra={
            "evidence_completeness":  parsed.get("evidence_completeness"),
            "evidence_strength":      parsed.get("evidence_strength"),
            "investigation_blocked":  parsed.get("investigation_blocked"),
            "missing_docs_count":     len(parsed.get("missing_documents", [])),
            "tools_used":             tools_used,
            "duration_ms":            duration_ms,
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
    """Deterministic safe evidence assessment when LLM output cannot be parsed."""
    ev_match  = case_input.get("evidence_match")
    category  = case_input.get("dispute_category", "Other")
    inv_plan  = case_input.get("investigation_plan") or {}
    req_docs  = inv_plan.get("required_documents", []) if isinstance(inv_plan, dict) else []

    if ev_match is True:
        strength       = "MEDIUM"
        strength_score = 0.60
        completeness   = 70
        blocked        = False
        summary = [
            "Agent 1 evidence verdict indicates documents support the claim.",
            f"Formal document checklist has {len(req_docs)} required item(s) — manual verification required.",
            "Automated evidence assessment failed — fallback applied.",
        ]
    elif ev_match is False:
        strength       = "LOW"
        strength_score = 0.30
        completeness   = 30
        blocked        = True
        summary = [
            "Agent 1 evidence verdict: submitted documents do NOT support the claim.",
            "Investigation is blocked pending additional documentation.",
            "Automated evidence assessment failed — fallback applied.",
        ]
    else:
        strength       = "LOW"
        strength_score = 0.35
        completeness   = 40
        blocked        = len(req_docs) > 0
        summary = [
            "No documents submitted with this dispute — evidence cannot be assessed.",
            f"{len(req_docs)} document(s) required per investigation plan.",
            "Automated evidence assessment failed — fallback applied.",
        ]

    from agents.evidence_agent.tools import _split_docs
    customer_fb, bank_fb = _split_docs(req_docs)

    return {
        "case_id":                      case_id,
        "evidence_completeness":        completeness,
        "evidence_strength":            strength,
        "evidence_strength_score":      strength_score,
        "evidence_consistent":          ev_match is not False,
        "consistency_issues":           [] if ev_match is not False else [
            "Agent 1 evidence mismatch — documents do not support the claimed transaction"
        ],
        "missing_documents":            customer_fb,
        "recommended_document_requests": customer_fb[:3] if customer_fb else [],
        "bank_pending_documents":       bank_fb,
        "investigation_blocked":        blocked,
        "evidence_summary":             summary,
        "review_recommendation": (
            "Additional documentation required before investigation can proceed."
            if blocked else
            "Evidence review completed using fallback — manual analyst verification required."
        ),
        "manual_evidence_review":       True,
        "tool_decisions":               [],
        "tools_used":                   tools_used,
        "agent_metadata":               agent_metadata,
        "metrics":                      metrics,
        "fallback_mode":                True,
        "failure_reason":               "LLM_OUTPUT_PARSE_FAILURE",
        "created_at":                   utc_now_iso(),
    }

