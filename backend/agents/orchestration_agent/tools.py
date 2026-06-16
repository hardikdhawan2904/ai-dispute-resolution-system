"""
Workflow Orchestration Agent tools — 6 deterministic tools that read from DB.

Each tool:
  - is decorated with @tool (docstring becomes LLM JSON schema)
  - opens its own DB session and closes it on exit
  - returns a human-readable string the LLM cites in its reasoning
  - never calls external APIs or the LLM — purely deterministic

All 6 tools are pre-run server-side before LLM invocation (same pattern as
Agent 2). The LLM receives pre-computed results and synthesises the final
workflow plan — it does not call tools at runtime.

Routing rules (complete):
  Unauthorized Transaction / fraud_suspicion / Friendly Fraud  → FRAUD_AGENT
  Duplicate Transaction / Merchant Dispute /
    Refund Not Received / Product Not Received /
    Subscription Abuse                                          → MERCHANT_AGENT
  Evidence missing / evidence_match=false /
    required_documents present                                  → EVIDENCE_AGENT
  ATM Cash Issue / Other (always)                              → EVIDENCE_AGENT
  VELOCITY_BREACH / SUSPICIOUS_BEHAVIOR /
    MERCHANT_BLACKLISTED / regulatory tags                      → COMPLIANCE_AGENT
"""
from langchain_core.tools import tool

from services.routing_rules import COMPLIANCE_AGENT_TAGS as _COMPLIANCE_TAGS_BASE
from utils.logger import agent_logger

# ── Routing tables ────────────────────────────────────────────────────────────

_FRAUD_CATEGORIES = {"Unauthorized Transaction", "Friendly Fraud"}

_MERCHANT_CATEGORIES = {
    "Merchant Dispute", "Refund Not Received",
    "Product Not Received", "Subscription Abuse",
    "Duplicate Transaction",  # Merchant must confirm/deny the duplicate charge
    "Friendly Fraud",         # Merchant must provide delivery/authorisation proof
}

# Categories that always require Evidence Verification regardless of uploads
_ALWAYS_EVIDENCE_CATEGORIES = {
    "ATM Cash Issue",  # ATM records, bank footage, cash count reports always needed
    "Friendly Fraud",  # Counter-evidence against customer's claim always needed
    "Other",           # Catch-all — evidence review always required
}

# Tags that trigger COMPLIANCE_AGENT — imported from shared routing_rules.
_COMPLIANCE_TAGS = _COMPLIANCE_TAGS_BASE


_COMPLEXITY_WEIGHTS = {
    "CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1,
}

_ANALYST_LEVEL = {
    "LOW": "JUNIOR", "MEDIUM": "STANDARD", "HIGH": "SENIOR", "CRITICAL": "LEAD",
}

_BASE_HOURS = {
    "LOW": 1, "MEDIUM": 2, "HIGH": 4, "CRITICAL": 8,
}

_AGENT_ORDER = ["FRAUD_AGENT", "EVIDENCE_AGENT", "MERCHANT_AGENT", "COMPLIANCE_AGENT"]


def _read_case(case_id: str):
    """Read case fields needed for orchestration from dispute_cases."""
    from database.database import SessionLocal
    from database.models import DisputeCase

    db = SessionLocal()
    try:
        case = db.query(DisputeCase).filter(DisputeCase.case_id == case_id).first()
        if not case:
            return None
        return {
            "case_id":                  case.case_id,
            "amount":                   case.amount or 0.0,
            "dispute_category":         case.dispute_category or "Other",
            "fraud_suspicion":          case.fraud_suspicion or False,
            "fraud_selected":           case.fraud_selected or False,
            "risk_tags":                case.risk_tags or [],
            "priority":                 case.priority or "MEDIUM",
            "confidence_score":         case.confidence_score or 0.0,
            "evidence_match":           case.evidence_match,
            "investigation_plan":       case.investigation_plan or {},
            "workflow_plan":            case.workflow_plan if hasattr(case, "workflow_plan") else None,
            "requires_manual_review":   case.requires_manual_review or False,
            "fraud_reasoning_brief":    case.fraud_reasoning_brief if hasattr(case, "fraud_reasoning_brief") else None,
        }
    finally:
        db.close()


# ── Tool 1 — Case complexity ──────────────────────────────────────────────────

@tool
def evaluate_case_complexity(case_id: str) -> str:
    """Evaluate the orchestration complexity of a dispute case by reading its
    amount, category, fraud signals, risk tags, and Agent 2's investigation
    complexity from the database. Returns LOW, MEDIUM, HIGH, or CRITICAL with
    a list of contributing factors. Call this first — complexity drives all
    downstream routing decisions."""
    try:
        c = _read_case(case_id)
        if not c:
            return f"COMPLEXITY\n  Error: Case {case_id} not found\n  Complexity: MEDIUM (default)"

        signals = []
        score = 0

        # Agent 2 investigation complexity is the strongest signal
        inv_plan = c["investigation_plan"]
        inv_complexity = (inv_plan.get("investigation_complexity") or "MEDIUM") if isinstance(inv_plan, dict) else "MEDIUM"
        score += _COMPLEXITY_WEIGHTS.get(inv_complexity, 2)
        signals.append(f"Agent 2 investigation complexity: {inv_complexity}")

        # Amount tier
        amount = float(c["amount"])
        if amount > 500_000:
            score += 2
            signals.append(f"Very high-value transaction: ₹{amount:,.0f}")
        elif amount > 50_000:
            score += 1
            signals.append(f"High-value transaction: ₹{amount:,.0f}")

        # Fraud signals
        if c["fraud_suspicion"] and c["fraud_selected"]:
            score += 2
            signals.append("Fraud confirmed by both AI and customer")
        elif c["fraud_suspicion"] or c["fraud_selected"]:
            score += 1
            signals.append("Fraud indicator present")

        # High-risk tags
        high_risk = [t for t in c["risk_tags"] if t in _COMPLIANCE_TAGS | {"POSSIBLE_FRAUD", "MERCHANT_BLACKLISTED"}]
        if high_risk:
            score += len(high_risk)
            signals.append(f"High-risk tags: {', '.join(high_risk)}")

        # Map score to complexity.
        # Agent 2 MEDIUM contributes score=2 — threshold aligned so that a MEDIUM
        # Agent 2 assessment without additional signals stays MEDIUM (not LOW).
        if score >= 7:
            complexity = "CRITICAL"
        elif score >= 4:
            complexity = "HIGH"
        elif score >= 2:
            complexity = "MEDIUM"
        else:
            complexity = "LOW"

        factors = "\n".join(f"    + {s}" for s in signals)
        return (
            f"COMPLEXITY ASSESSMENT\n"
            f"  Case ID              : {case_id}\n"
            f"  Complexity           : {complexity}\n"
            f"  Score                : {score}\n"
            f"  Contributing Factors :\n{factors}"
        )
    except Exception as exc:
        agent_logger.warning(f"evaluate_case_complexity failed: {exc}")
        return f"COMPLEXITY ASSESSMENT\n  Error: {exc}\n  Complexity: MEDIUM (default)"


# ── Tool 2 — Required agents ──────────────────────────────────────────────────

@tool
def determine_required_agents(case_id: str) -> str:
    """Identify which specialist agents must be activated for this dispute case
    by checking dispute category, fraud indicators, evidence gaps, and risk tags
    against the routing rule table. Returns the required agent identifiers.
    Routing rules: Unauthorized/Fraud → FRAUD_AGENT; Merchant/Refund/Product/
    Subscription → MERCHANT_AGENT; Missing evidence → EVIDENCE_AGENT;
    Velocity/Suspicious/Blacklist tags → COMPLIANCE_AGENT."""
    try:
        c = _read_case(case_id)
        if not c:
            return f"REQUIRED AGENTS\n  Error: Case {case_id} not found\n  Required Agents: []"

        required = []
        reasons  = []

        category = c["dispute_category"]

        # FRAUD_AGENT
        if c["fraud_suspicion"] or c["fraud_selected"] or category in _FRAUD_CATEGORIES:
            required.append("FRAUD_AGENT")
            reasons.append(f"FRAUD_AGENT: category={category}, fraud_suspicion={c['fraud_suspicion']}")

        # EVIDENCE_AGENT
        inv_plan = c["investigation_plan"]
        has_doc_gaps = (
            c["evidence_match"] is not True
            or (isinstance(inv_plan, dict) and bool(inv_plan.get("required_documents")))
            or category in _ALWAYS_EVIDENCE_CATEGORIES
        )
        if has_doc_gaps:
            required.append("EVIDENCE_AGENT")
            reasons.append(f"EVIDENCE_AGENT: category={category}, evidence_match={c['evidence_match']}, required_documents present")

        # MERCHANT_AGENT
        if category in _MERCHANT_CATEGORIES:
            required.append("MERCHANT_AGENT")
            reasons.append(f"MERCHANT_AGENT: category={category}")

        # COMPLIANCE_AGENT
        compliance_triggers = [t for t in c["risk_tags"] if t in _COMPLIANCE_TAGS]
        if compliance_triggers:
            required.append("COMPLIANCE_AGENT")
            reasons.append(f"COMPLIANCE_AGENT: risk_tags={compliance_triggers}")

        reasons_str = "\n".join(f"    • {r}" for r in reasons) if reasons else "    • No specialist agents required"
        return (
            f"REQUIRED AGENTS\n"
            f"  Case ID         : {case_id}\n"
            f"  Required Agents : {required or ['None']}\n"
            f"  Routing Reasons :\n{reasons_str}"
        )
    except Exception as exc:
        agent_logger.warning(f"determine_required_agents failed: {exc}")
        return f"REQUIRED AGENTS\n  Error: {exc}\n  Required Agents: []"


# ── Tool 3 — Workflow path ────────────────────────────────────────────────────

@tool
def recommend_workflow_path(case_id: str) -> str:
    """Build an ordered execution sequence for the required specialist agents,
    respecting dependency rules. FRAUD_AGENT always runs first when present
    (fraud classification informs all other agents). EVIDENCE_AGENT runs before
    MERCHANT_AGENT and COMPLIANCE_AGENT so they have complete evidence context.
    Returns the ordered workflow path and dependency mapping."""
    try:
        c = _read_case(case_id)
        if not c:
            return f"WORKFLOW PATH\n  Error: Case {case_id} not found\n  Workflow Path: []"

        category = c["dispute_category"]
        required = []

        if c["fraud_suspicion"] or c["fraud_selected"] or category in _FRAUD_CATEGORIES:
            required.append("FRAUD_AGENT")

        inv_plan = c["investigation_plan"]
        has_doc_gaps = (
            c["evidence_match"] is not True
            or (isinstance(inv_plan, dict) and bool(inv_plan.get("required_documents")))
            or category in _ALWAYS_EVIDENCE_CATEGORIES
        )
        if has_doc_gaps:
            required.append("EVIDENCE_AGENT")

        if category in _MERCHANT_CATEGORIES:
            required.append("MERCHANT_AGENT")

        compliance_triggers = [t for t in c["risk_tags"] if t in _COMPLIANCE_TAGS]
        if compliance_triggers:
            required.append("COMPLIANCE_AGENT")

        # Enforce canonical order (dedup preserving order)
        seen = set()
        path = [a for a in _AGENT_ORDER if a in required and not seen.add(a)]

        deps = {
            "FRAUD_AGENT":      [],
            "EVIDENCE_AGENT":   ["FRAUD_AGENT"] if "FRAUD_AGENT" in path else [],
            "MERCHANT_AGENT":   ["EVIDENCE_AGENT"] if "EVIDENCE_AGENT" in path else [],
            "COMPLIANCE_AGENT": ["FRAUD_AGENT"] if "FRAUD_AGENT" in path else [],
        }
        active_deps = {k: v for k, v in deps.items() if k in path}
        dep_str = "\n".join(f"    {k}: depends on {v}" for k, v in active_deps.items()) if active_deps else "    None"

        return (
            f"WORKFLOW PATH\n"
            f"  Case ID       : {case_id}\n"
            f"  Workflow Path : {path}\n"
            f"  Step Count    : {len(path)}\n"
            f"  Dependencies  :\n{dep_str}"
        )
    except Exception as exc:
        agent_logger.warning(f"recommend_workflow_path failed: {exc}")
        return f"WORKFLOW PATH\n  Error: {exc}\n  Workflow Path: []"


# ── Tool 4 — Escalation ───────────────────────────────────────────────────────

@tool
def assess_escalation_need(case_id: str) -> str:
    """Assess whether this dispute case requires escalation and at what level
    by checking fraud indicators, transaction amount, priority, risk tags, and
    Agent 2's investigation complexity. CRITICAL: fraud + amount > ₹50,000 or
    CRITICAL complexity. HIGH: fraud alone or amount > ₹5,00,000 or CRITICAL
    tags. MEDIUM: amount > ₹50,000 or HIGH complexity. Returns escalation_required
    boolean, escalation_level, and the specific triggers."""
    try:
        c = _read_case(case_id)
        if not c:
            return f"ESCALATION\n  Error: Case {case_id} not found\n  Escalation Required: false"

        inv_plan = c["investigation_plan"]
        inv_complexity = (inv_plan.get("investigation_complexity") or "MEDIUM") if isinstance(inv_plan, dict) else "MEDIUM"
        amount = float(c["amount"])
        fraud  = c["fraud_suspicion"] or c["fraud_selected"]
        tags   = c["risk_tags"]
        critical_tags = [t for t in tags if t in {"POSSIBLE_FRAUD", "MERCHANT_BLACKLISTED"} | _COMPLIANCE_TAGS]

        triggers = []

        if (fraud and amount > 50_000) or inv_complexity == "CRITICAL":
            level = "CRITICAL"
            if fraud and amount > 50_000:
                triggers.append(f"Fraud confirmed + high-value ₹{amount:,.0f}")
            if inv_complexity == "CRITICAL":
                triggers.append("Agent 2 rated investigation complexity CRITICAL")

        elif fraud or amount > 500_000 or critical_tags:
            level = "HIGH"
            if fraud:
                triggers.append("Fraud indicator present")
            if amount > 500_000:
                triggers.append(f"Very high-value transaction ₹{amount:,.0f}")
            if critical_tags:
                triggers.append(f"Critical risk tags: {', '.join(critical_tags)}")

        elif amount > 50_000 or inv_complexity == "HIGH":
            level = "MEDIUM"
            if amount > 50_000:
                triggers.append(f"High-value transaction ₹{amount:,.0f}")
            if inv_complexity == "HIGH":
                triggers.append("Agent 2 rated investigation complexity HIGH")

        else:
            level = None

        required     = level is not None
        triggers_str = "\n".join(f"    • {t}" for t in triggers) if triggers else "    • No escalation triggers"

        return (
            f"ESCALATION ASSESSMENT\n"
            f"  Case ID              : {case_id}\n"
            f"  Escalation Required  : {required}\n"
            f"  Escalation Level     : {level or 'None'}\n"
            f"  Triggers             :\n{triggers_str}"
        )
    except Exception as exc:
        agent_logger.warning(f"assess_escalation_need failed: {exc}")
        return f"ESCALATION ASSESSMENT\n  Error: {exc}\n  Escalation Required: false"


# ── Tool 5 — Workload estimate ────────────────────────────────────────────────

@tool
def estimate_workload(case_id: str) -> str:
    """Estimate total investigation effort in hours and required analyst seniority
    level for this dispute case. Base hours come from complexity level; each
    required specialist agent adds one additional hour. Analyst level is driven
    by the highest complexity signal. Returns estimated_hours integer and
    analyst_level (JUNIOR | STANDARD | SENIOR | LEAD)."""
    try:
        c = _read_case(case_id)
        if not c:
            return f"WORKLOAD ESTIMATE\n  Error: Case {case_id} not found\n  Estimated Hours: 2\n  Analyst Level: STANDARD"

        inv_plan = c["investigation_plan"]
        inv_complexity = (inv_plan.get("investigation_complexity") or "MEDIUM") if isinstance(inv_plan, dict) else "MEDIUM"
        amount = float(c["amount"])
        fraud  = c["fraud_suspicion"] or c["fraud_selected"]
        tags   = c["risk_tags"]

        # Derive orchestration complexity (mirrors tool 1 logic without DB re-read)
        score = _COMPLEXITY_WEIGHTS.get(inv_complexity, 2)
        if amount > 500_000:
            score += 2
        elif amount > 50_000:
            score += 1
        if fraud:
            score += 1
        compliance_hits = [t for t in tags if t in _COMPLIANCE_TAGS]
        score += len(compliance_hits)

        if score >= 7:
            complexity = "CRITICAL"
        elif score >= 4:
            complexity = "HIGH"
        elif score >= 2:
            complexity = "MEDIUM"
        else:
            complexity = "LOW"

        # Count required agents
        required_count = 0
        if fraud or c["dispute_category"] in _FRAUD_CATEGORIES:
            required_count += 1
        has_doc_gaps = (
            c["evidence_match"] is not True
            or (isinstance(inv_plan, dict) and bool(inv_plan.get("required_documents")))
            or c["dispute_category"] in _ALWAYS_EVIDENCE_CATEGORIES
        )
        if has_doc_gaps:
            required_count += 1
        if c["dispute_category"] in _MERCHANT_CATEGORIES:
            required_count += 1
        if compliance_hits:
            required_count += 1

        base_hours = _BASE_HOURS.get(complexity, 2)
        total_hours = base_hours + required_count
        analyst_level = _ANALYST_LEVEL.get(complexity, "STANDARD")

        return (
            f"WORKLOAD ESTIMATE\n"
            f"  Case ID              : {case_id}\n"
            f"  Orchestration Complexity : {complexity}\n"
            f"  Base Hours           : {base_hours}\n"
            f"  Specialist Agents    : {required_count} (+ {required_count}h)\n"
            f"  Total Estimated Hours: {total_hours}\n"
            f"  Analyst Level        : {analyst_level}"
        )
    except Exception as exc:
        agent_logger.warning(f"estimate_workload failed: {exc}")
        return f"WORKLOAD ESTIMATE\n  Error: {exc}\n  Estimated Hours: 2\n  Analyst Level: STANDARD"


# ── Tool 6 — Next execution step ──────────────────────────────────────────────

@tool
def determine_next_execution_step(case_id: str) -> str:
    """Determine the immediate next specialist agent to execute by comparing the
    planned workflow_path against already-completed agents stored in the existing
    workflow_plan (if any). Returns the next_agent identifier, reason, and any
    blocking_dependencies that must complete first. Returns next_agent=null when
    all specialist agents have completed or none are required. This tool enables
    dynamic step-by-step orchestration as Agent 4+ are built."""
    try:
        c = _read_case(case_id)
        if not c:
            return (
                f"NEXT EXECUTION STEP\n"
                f"  Error: Case {case_id} not found\n"
                f"  Next Agent: null\n"
                f"  Reason: Case not found"
            )

        # Derive workflow path (mirrors tool 3 logic)
        category = c["dispute_category"]
        fraud    = c["fraud_suspicion"] or c["fraud_selected"]
        inv_plan = c["investigation_plan"]
        tags     = c["risk_tags"]

        required = []
        if fraud or category in _FRAUD_CATEGORIES:
            required.append("FRAUD_AGENT")
        has_doc_gaps = (
            c["evidence_match"] is not True
            or (isinstance(inv_plan, dict) and bool(inv_plan.get("required_documents")))
            or category in _ALWAYS_EVIDENCE_CATEGORIES
        )
        if has_doc_gaps:
            required.append("EVIDENCE_AGENT")
        if category in _MERCHANT_CATEGORIES:
            required.append("MERCHANT_AGENT")
        if any(t in _COMPLIANCE_TAGS for t in tags):
            required.append("COMPLIANCE_AGENT")

        seen = set()
        planned_path = [a for a in _AGENT_ORDER if a in required and not seen.add(a)]

        # Read completed agents from existing workflow_plan (if WOA ran before)
        existing_plan = c.get("workflow_plan") or {}
        completed_raw = existing_plan.get("completed_agents", []) if isinstance(existing_plan, dict) else []
        completed = list(completed_raw) if isinstance(completed_raw, (list, tuple)) else []
        if c.get("fraud_reasoning_brief") and "FRAUD_AGENT" not in completed:
            completed.append("FRAUD_AGENT")

        # Dependency map
        deps = {
            "FRAUD_AGENT":      [],
            "EVIDENCE_AGENT":   ["FRAUD_AGENT"] if "FRAUD_AGENT" in planned_path else [],
            "MERCHANT_AGENT":   ["EVIDENCE_AGENT"] if "EVIDENCE_AGENT" in planned_path else [],
            "COMPLIANCE_AGENT": ["FRAUD_AGENT"] if "FRAUD_AGENT" in planned_path else [],
        }

        # Find the first agent whose dependencies are satisfied and is not completed
        next_agent = None
        blocking   = []
        reason     = "All required specialist agents have been completed."

        for agent in planned_path:
            if agent in completed:
                continue
            unmet = [d for d in deps.get(agent, []) if d not in completed]
            if unmet:
                blocking = unmet
                reason = f"{agent} is blocked — waiting for: {unmet}"
                break
            # This agent is ready to run
            next_agent = agent
            remaining  = [a for a in planned_path if a != next_agent and a not in completed]
            reason = f"{next_agent} is the next required specialist agent."
            blocking = []
            break

        if next_agent is None and not blocking:
            remaining = []

        return (
            f"NEXT EXECUTION STEP\n"
            f"  Case ID              : {case_id}\n"
            f"  Planned Path         : {planned_path}\n"
            f"  Completed Agents     : {completed}\n"
            f"  Next Agent           : {next_agent or 'null'}\n"
            f"  Remaining After Next : {remaining if next_agent else []}\n"
            f"  Blocking Deps        : {blocking}\n"
            f"  Reason               : {reason}"
        )
    except Exception as exc:
        agent_logger.warning(f"determine_next_execution_step failed: {exc}")
        return (
            f"NEXT EXECUTION STEP\n"
            f"  Error: {exc}\n"
            f"  Next Agent: null\n"
            f"  Reason: Tool execution failed"
        )


# ── Registry ──────────────────────────────────────────────────────────────────

TOOL_REGISTRY: dict = {
    "evaluate_case_complexity":     evaluate_case_complexity,
    "determine_required_agents":    determine_required_agents,
    "recommend_workflow_path":      recommend_workflow_path,
    "assess_escalation_need":       assess_escalation_need,
    "estimate_workload":            estimate_workload,
    "determine_next_execution_step": determine_next_execution_step,
}
