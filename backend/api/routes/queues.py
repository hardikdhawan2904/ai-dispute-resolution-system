"""Queue management endpoints."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import DisputeCase
from services.queue_assignment_service import all_queues, QUEUE_DISPLAY

router = APIRouter(prefix="/api/ops/queues", tags=["Ops — Queues"])


@router.get("")
def list_queues(db: Session = Depends(get_db)):
    """Return all queues with case counts."""
    queues = all_queues()
    result = []
    for q in queues:
        queue_name = q["queue"]
        count = db.query(DisputeCase).filter(DisputeCase.assigned_queue == queue_name).count()
        critical = db.query(DisputeCase).filter(
            DisputeCase.assigned_queue == queue_name,
            DisputeCase.priority == "CRITICAL",
        ).count()
        breached = db.query(DisputeCase).filter(
            DisputeCase.assigned_queue == queue_name,
            DisputeCase.sla_breached == True,
        ).count()
        result.append({
            "queue": queue_name,
            "display": q["display"],
            "count": count,
            "critical": critical,
            "sla_breached": breached,
        })
    return {"queues": result}


@router.get("/{queue_name}/cases")
def queue_cases(
    queue_name: str,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """List cases in a specific queue, ordered by priority_score desc."""
    from sqlalchemy import desc
    q = db.query(DisputeCase).filter(DisputeCase.assigned_queue == queue_name)
    total = q.count()
    cases = q.order_by(desc(DisputeCase.priority_score), desc(DisputeCase.created_at)).offset(skip).limit(limit).all()
    return {
        "queue": queue_name,
        "display": QUEUE_DISPLAY.get(queue_name, queue_name),
        "total": total,
        "cases": [c.to_dict() for c in cases],
    }

