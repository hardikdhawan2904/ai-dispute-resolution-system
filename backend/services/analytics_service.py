"""
Operations analytics — queue-level and time-based metrics.
"""
from datetime import datetime, timedelta, timezone
from typing import List

from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from database.models import DisputeCase, AuditLog


def get_ops_analytics(db: Session) -> dict:
    now = datetime.now(timezone.utc)
    last_7d = now - timedelta(days=7)
    last_30d = now - timedelta(days=30)

    total = db.query(DisputeCase).count()
    open_cases = db.query(DisputeCase).filter(
        DisputeCase.status.in_(["Dispute Raised", "Under Investigation", "Pending Documents", "Escalated"])
    ).count()
    fraud = db.query(DisputeCase).filter(DisputeCase.fraud_suspicion == True).count()
    critical = db.query(DisputeCase).filter(DisputeCase.priority == "CRITICAL").count()
    sla_breached = db.query(DisputeCase).filter(DisputeCase.sla_breached == True).count()
    manual_review = db.query(DisputeCase).filter(DisputeCase.requires_manual_review == True).count()

    # Cases by queue
    queue_rows = (
        db.query(DisputeCase.assigned_queue, func.count())
        .group_by(DisputeCase.assigned_queue)
        .all()
    )
    by_queue = {(r[0] or "UNASSIGNED"): r[1] for r in queue_rows}

    # Cases by status
    status_rows = (
        db.query(DisputeCase.status, func.count())
        .group_by(DisputeCase.status)
        .all()
    )
    by_status = {r[0]: r[1] for r in status_rows if r[0]}

    # Cases by priority
    pri_rows = (
        db.query(DisputeCase.priority, func.count())
        .group_by(DisputeCase.priority)
        .all()
    )
    by_priority = {r[0]: r[1] for r in pri_rows if r[0]}

    # Cases by category
    cat_rows = (
        db.query(DisputeCase.dispute_category, func.count())
        .group_by(DisputeCase.dispute_category)
        .all()
    )
    by_category = {r[0]: r[1] for r in cat_rows if r[0]}

    # New cases in last 7 days
    new_7d = db.query(DisputeCase).filter(DisputeCase.created_at >= last_7d).count()
    new_30d = db.query(DisputeCase).filter(DisputeCase.created_at >= last_30d).count()

    # Average confidence score
    avg_conf = db.query(func.avg(DisputeCase.confidence_score)).scalar() or 0.0

    # Resolution rate (Resolved + Rejected + Closed vs total)
    resolved = db.query(DisputeCase).filter(
        DisputeCase.status.in_(["Resolved", "Rejected", "Closed"])
    ).count()
    resolution_rate = round(resolved / total * 100, 1) if total else 0.0

    # ── Agent 4 — EIA evidence metrics ───────────────────────────────────────
    # Cases where EIA is required but not yet run (EVIDENCE_AGENT is next_agent)
    all_open = db.query(DisputeCase).filter(
        DisputeCase.status.in_(["Dispute Raised", "Under Investigation"])
    ).all()

    evidence_pending = 0
    evidence_completed = 0
    blocked_investigations = 0
    completeness_values: List[float] = []

    for case in all_open:
        wf = case.workflow_plan or {}
        ea = case.evidence_assessment or {}

        if isinstance(wf, dict):
            next_agent  = wf.get("next_agent")
            req_agents  = wf.get("required_agents") or []
            comp_agents = wf.get("completed_agents") or []

            if "EVIDENCE_AGENT" in req_agents:
                if "EVIDENCE_AGENT" in comp_agents or isinstance(ea, dict) and ea:
                    evidence_completed += 1
                else:
                    evidence_pending += 1

        if isinstance(ea, dict) and ea:
            if ea.get("investigation_blocked"):
                blocked_investigations += 1
            comp = ea.get("evidence_completeness")
            if isinstance(comp, (int, float)) and comp > 0:
                completeness_values.append(float(comp))

    avg_evidence_completeness = round(
        sum(completeness_values) / len(completeness_values), 1
    ) if completeness_values else 0.0

    return {
        "total_cases": total,
        "open_cases": open_cases,
        "fraud_cases": fraud,
        "critical_cases": critical,
        "sla_breached_cases": sla_breached,
        "manual_review_cases": manual_review,
        "resolved_cases": resolved,
        "resolution_rate": resolution_rate,
        "new_cases_7d": new_7d,
        "new_cases_30d": new_30d,
        "avg_confidence_score": round(float(avg_conf), 3),
        "by_queue": by_queue,
        "by_status": by_status,
        "by_priority": by_priority,
        "by_category": by_category,
        # Agent 4 — EIA evidence metrics
        "evidence_reviews_pending":    evidence_pending,
        "evidence_reviews_completed":  evidence_completed,
        "blocked_investigations":      blocked_investigations,
        "avg_evidence_completeness":   avg_evidence_completeness,
    }
