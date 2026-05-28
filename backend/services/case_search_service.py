"""Advanced case search with multiple filter dimensions."""
from typing import Optional, List

from sqlalchemy.orm import Session
from sqlalchemy import desc, or_

from database.models import DisputeCase


def search_cases(
    db: Session,
    query: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    category: Optional[str] = None,
    queue: Optional[str] = None,
    analyst: Optional[str] = None,
    fraud_only: bool = False,
    manual_review_only: bool = False,
    sla_breached_only: bool = False,
    min_amount: Optional[float] = None,
    max_amount: Optional[float] = None,
    skip: int = 0,
    limit: int = 50,
) -> dict:
    q = db.query(DisputeCase)

    # Full-text search across key string fields
    if query:
        pattern = f"%{query}%"
        q = q.filter(or_(
            DisputeCase.case_id.ilike(pattern),
            DisputeCase.customer_id.ilike(pattern),
            DisputeCase.customer_name.ilike(pattern),
            DisputeCase.transaction_id.ilike(pattern),
            DisputeCase.merchant.ilike(pattern),
            DisputeCase.email.ilike(pattern),
        ))

    if status:
        q = q.filter(DisputeCase.status == status)
    if priority:
        q = q.filter(DisputeCase.priority == priority)
    if category:
        q = q.filter(DisputeCase.dispute_category == category)
    if queue:
        q = q.filter(DisputeCase.assigned_queue == queue)
    if analyst:
        q = q.filter(DisputeCase.assigned_analyst == analyst)
    if fraud_only:
        q = q.filter(DisputeCase.fraud_suspicion == True)
    if manual_review_only:
        q = q.filter(DisputeCase.requires_manual_review == True)
    if sla_breached_only:
        q = q.filter(DisputeCase.sla_breached == True)
    if min_amount is not None:
        q = q.filter(DisputeCase.amount >= min_amount)
    if max_amount is not None:
        q = q.filter(DisputeCase.amount <= max_amount)

    total = q.count()
    cases = (
        q.order_by(desc(DisputeCase.priority_score), desc(DisputeCase.created_at))
        .offset(skip)
        .limit(limit)
        .all()
    )
    return {"total": total, "cases": [c.to_dict() for c in cases]}
