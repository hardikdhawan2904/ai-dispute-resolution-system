"""
Duplicate dispute detection.

A case is considered a potential duplicate if another open case exists for the
same customer with the same transaction_id (exact) or same amount + merchant
within 24 hours.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from database.models import DisputeCase


_OPEN_STATUSES = {"Dispute Raised", "Under Investigation", "Pending Documents", "Escalated"}


def find_duplicate(
    customer_id: str,
    transaction_id: str,
    amount: float,
    merchant: str,
    db: Session,
    exclude_case_id: str = "",
) -> Optional[str]:
    """
    Returns the case_id of an existing open case that looks like a duplicate,
    or None if no duplicate found.
    """
    query = (
        db.query(DisputeCase)
        .filter(
            DisputeCase.customer_id == customer_id,
            DisputeCase.status.in_(list(_OPEN_STATUSES)),
        )
    )
    if exclude_case_id:
        query = query.filter(DisputeCase.case_id != exclude_case_id)

    candidates = query.all()

    for c in candidates:
        # Exact transaction_id match
        if c.transaction_id == transaction_id:
            return c.case_id

        # Same amount + merchant within 24h
        if c.amount == amount and (c.merchant or "").lower() == merchant.lower():
            created = c.created_at
            if created and created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
            if created and created > cutoff:
                return c.case_id

    return None
