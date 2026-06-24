"""
Account Intelligence Service — aggregates bank-observed security events
for verified Account Takeover detection. Primary source of truth for ATO signals.
"""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session


def get_ato_events(customer_id: str, transaction_datetime: datetime, db: Session, lookback_days: int = 30) -> list[dict]:
    """Return all security events for customer in the lookback window before the transaction."""
    from database.models import AccountEvent
    if transaction_datetime.tzinfo is None:
        transaction_datetime = transaction_datetime.replace(tzinfo=timezone.utc)
    cutoff = transaction_datetime - timedelta(days=lookback_days)
    try:
        events = (
            db.query(AccountEvent)
            .filter(
                AccountEvent.customer_id == customer_id.upper(),
                AccountEvent.event_timestamp >= cutoff,
                AccountEvent.event_timestamp <= transaction_datetime,
            )
            .order_by(AccountEvent.event_timestamp.desc())
            .all()
        )
        return [e.to_dict() for e in events]
    except Exception:
        return []


def get_device_status(customer_id: str, device_id: str, transaction_datetime: datetime, db: Session) -> dict:
    """Check if the device used is known, trusted, and how old it is."""
    from database.models import CustomerDevice
    if not device_id:
        return {"device_status": "UNKNOWN", "trusted": False, "device_age_hours": None, "found": False}
    if transaction_datetime.tzinfo is None:
        transaction_datetime = transaction_datetime.replace(tzinfo=timezone.utc)
    try:
        device = (
            db.query(CustomerDevice)
            .filter(
                CustomerDevice.customer_id == customer_id.upper(),
                CustomerDevice.device_id == device_id,
            )
            .first()
        )
        if not device:
            return {"device_status": "NEW_DEVICE", "trusted": False, "device_age_hours": None, "found": False}
        age_hours = None
        if device.first_seen:
            fs = device.first_seen
            if fs.tzinfo is None:
                fs = fs.replace(tzinfo=timezone.utc)
            age_hours = round((transaction_datetime - fs).total_seconds() / 3600, 1)
        status = "TRUSTED_DEVICE" if device.trusted else (
            "RECENTLY_REGISTERED" if age_hours is not None and age_hours < 72 else "KNOWN_DEVICE"
        )
        return {"device_status": status, "trusted": device.trusted, "device_age_hours": age_hours, "found": True}
    except Exception:
        return {"device_status": "UNKNOWN", "trusted": False, "device_age_hours": None, "found": False}


def get_beneficiary_status(customer_id: str, beneficiary_name: str, transaction_datetime: datetime, db: Session) -> dict:
    """Check if the payee is a known beneficiary."""
    from database.models import Beneficiary
    name_lower = (beneficiary_name or "").lower().strip()
    if not name_lower:
        return {"known_beneficiary": False, "beneficiary_age_hours": None, "transaction_count": 0}
    if transaction_datetime.tzinfo is None:
        transaction_datetime = transaction_datetime.replace(tzinfo=timezone.utc)
    try:
        bene = (
            db.query(Beneficiary)
            .filter(
                Beneficiary.customer_id == customer_id.upper(),
                Beneficiary.beneficiary_name.ilike(f"%{name_lower}%"),
            )
            .first()
        )
        if not bene:
            return {"known_beneficiary": False, "beneficiary_age_hours": None, "transaction_count": 0}
        age_hours = None
        if bene.created_at:
            ca = bene.created_at
            if ca.tzinfo is None:
                ca = ca.replace(tzinfo=timezone.utc)
            age_hours = round((transaction_datetime - ca).total_seconds() / 3600, 1)
        return {
            "known_beneficiary": True,
            "beneficiary_age_hours": age_hours,
            "transaction_count": bene.transaction_count or 0,
        }
    except Exception:
        return {"known_beneficiary": False, "beneficiary_age_hours": None, "transaction_count": 0}

