"""
Customer portal routes — authenticated customer-only endpoints.
All responses are stripped of internal AI intelligence.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database.database import get_db
from services.dispute_service import DisputeService
from schemas.dispute_schemas import DisputeSubmissionRequest
from schemas.customer_schemas import (
    CustomerDisputeResponse,
    CustomerDisputeSubmissionResponse,
    to_customer_response,
)
from auth.auth import Role
from auth.dependencies import get_current_user
from utils.logger import api_logger

router = APIRouter(prefix="/api/customer", tags=["Customer Portal"])


def _require_customer(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] != Role.CUSTOMER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Customer access only")
    return user


@router.post("/disputes/submit", response_model=CustomerDisputeSubmissionResponse, status_code=201)
def customer_submit_dispute(
    payload: DisputeSubmissionRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(_require_customer),
):
    """Customer raises a new dispute — they receive only a safe confirmation."""
    api_logger.info("Customer dispute submission", extra={"customer_id": user.get("customer_id")})

    result = DisputeService.submit_dispute(payload.model_dump(), db)

    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "Dispute submission failed validation", "errors": result["errors"]},
        )

    safe = to_customer_response(result["final_case"])
    return CustomerDisputeSubmissionResponse(
        success=True,
        case_id=result["case_id"],
        message="Your dispute has been submitted successfully. We will review it and contact you within 7 business days.",
        dispute_case=safe,
    )


@router.get("/disputes", response_model=list[CustomerDisputeResponse])
def customer_list_disputes(
    db: Session = Depends(get_db),
    user: dict = Depends(_require_customer),
):
    """Customer views only their own disputes, with safe status labels."""
    customer_id = user.get("customer_id")
    result = DisputeService.list_cases(db, skip=0, limit=100)
    own_cases = [c for c in result["cases"] if c.get("customer_id") == customer_id]
    return [to_customer_response(c) for c in own_cases]


@router.get("/disputes/{case_id}", response_model=CustomerDisputeResponse)
def customer_get_dispute(
    case_id: str,
    db: Session = Depends(get_db),
    user: dict = Depends(_require_customer),
):
    """Customer tracks a specific dispute by case ID."""
    case = DisputeService.get_case(case_id, db)
    if not case:
        raise HTTPException(status_code=404, detail="Dispute not found")

    if case.get("customer_id") != user.get("customer_id"):
        raise HTTPException(status_code=403, detail="Access denied — this dispute does not belong to your account")

    return to_customer_response(case)
