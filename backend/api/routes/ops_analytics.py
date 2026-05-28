"""Ops analytics endpoint."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database.database import get_db
from services.analytics_service import get_ops_analytics
from schemas.ops_schemas import OpsAnalyticsResponse

router = APIRouter(prefix="/api/ops", tags=["Ops — Analytics"])


@router.get("/analytics", response_model=OpsAnalyticsResponse)
def ops_analytics(db: Session = Depends(get_db)):
    return get_ops_analytics(db)
