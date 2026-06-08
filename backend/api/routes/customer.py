"""
Customer portal routes — authenticated customer-only endpoints.
All responses are stripped of internal AI intelligence.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import BankCustomer
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


@router.get("/lookup/transaction/{transaction_id}")
def lookup_transaction(transaction_id: str, db: Session = Depends(get_db)):
    """Public endpoint — returns transaction details for form pre-fill."""
    from database.models import Transaction
    txn = db.query(Transaction).filter(
        Transaction.transaction_id == transaction_id.upper()
    ).first()
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return txn.to_dict()


@router.get("/lookup/{customer_id}")
def lookup_customer(customer_id: str, db: Session = Depends(get_db)):
    """Public endpoint — returns basic customer info for form pre-fill."""
    customer = db.query(BankCustomer).filter(BankCustomer.customer_id == customer_id.upper()).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer.to_dict()


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

    from database.models import Transaction

    # Always resolve customer details from the DB — never trust form-submitted values.
    customer = db.query(BankCustomer).filter(
        BankCustomer.customer_id == payload.customer_id.upper()
    ).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    # Always resolve transaction details from the DB — never trust form-submitted values.
    txn = db.query(Transaction).filter(
        Transaction.transaction_id == payload.transaction_id.upper()
    ).first()
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    if txn.customer_id.upper() != payload.customer_id.upper():
        raise HTTPException(status_code=403, detail="Transaction does not belong to this customer")

    data = payload.model_dump()
    data["customer_name"]     = customer.full_name
    data["email"]             = customer.email
    data["phone"]             = customer.phone
    data["merchant"]          = txn.merchant_name
    data["amount"]            = txn.amount
    data["currency"]          = txn.currency
    data["transaction_type"]  = txn.transaction_type
    data["transaction_date"]  = txn.transaction_date.strftime("%Y-%m-%d") if txn.transaction_date else ""
    data["transaction_time"]  = txn.transaction_date.strftime("%H:%M") if txn.transaction_date else ""

    result = DisputeService.submit_dispute(data, db)

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
