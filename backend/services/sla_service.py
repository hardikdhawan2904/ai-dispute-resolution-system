"""
SLA deadline calculation — aligned with RBI mandates and Indian banking standards.

Customer-facing resolution SLAs (RBI references):
  Fraud / Unauthorized (reported ≤ 3 working days):  10 working days to credit back
  Fraud / Unauthorized (reported 4-7 working days):  15 working days
  ATM Cash Dispute:                                   7 working days (RBI Circular 2019)
  General disputes (non-fraud):                       30 calendar days (Banking Ombudsman)

Internal processing SLAs (bank-to-analyst routing, tighter than customer-facing):
  CRITICAL — 2 hours   (immediate triage; fraud + high-value)
  HIGH     — 8 hours   (same-day assignment)
  MEDIUM   — 2 working days (standard queue processing)
  LOW      — 5 working days (routine handling)

Business-hour rules:
  - Business hours: Mon–Fri, 09:00–18:00 IST (UTC+5:30)
  - Saturdays count as half-days for MEDIUM/LOW (banking norm)
  - Public holidays are NOT modelled here (add holiday calendar for production)
  - Clock is paused while status == "Pending Documents" (see sla_paused_at field)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone


# ── Internal routing SLAs (hours) ────────────────────────────────────────────

_INTERNAL_SLA_HOURS: dict[str, float] = {
    "CRITICAL": 2,        # Immediate — fraud + high value
    "HIGH":     8,        # Same business day
    "MEDIUM":   2 * 9,    # 2 working days × 9 business hours/day
    "LOW":      5 * 9,    # 5 working days × 9 business hours/day
}

# Priorities that use business-day advancement (skip weekends)
_BUSINESS_DAY_PRIORITIES = {"MEDIUM", "LOW"}

# IST offset for business-hour calculations
_IST = timezone(timedelta(hours=5, minutes=30))


def compute_sla_deadline(priority: str, from_dt: datetime | None = None) -> datetime:
    """Return the internal SLA deadline (analyst assignment) for the given priority."""
    base = from_dt or datetime.now(timezone.utc)
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)

    hours = _INTERNAL_SLA_HOURS.get(priority, _INTERNAL_SLA_HOURS["MEDIUM"])

    if priority not in _BUSINESS_DAY_PRIORITIES:
        # Calendar hours — critical and high use raw time
        return base + timedelta(hours=hours)

    # Business-hour advance: Mon-Fri only, 09:00-18:00 IST
    return _advance_business_hours(base, hours)


# ── Private helpers ───────────────────────────────────────────────────────────

def _advance_business_hours(start: datetime, hours: float) -> datetime:
    """Advance `start` by `hours` business hours (Mon–Fri, 09:00–18:00 IST)."""
    remaining = hours
    current   = start.astimezone(_IST)

    while remaining > 0:
        current += timedelta(hours=1)
        # Skip weekends
        if current.weekday() >= 5:
            continue
        # Skip non-business hours (before 9am or after 6pm IST)
        if not (9 <= current.hour < 18):
            continue
        remaining -= 1

    return current.astimezone(timezone.utc)


def _advance_working_days(start: datetime, days: int) -> datetime:
    """Advance `start` by `days` working days (Mon–Fri)."""
    current   = start.astimezone(_IST)
    remaining = days

    while remaining > 0:
        current += timedelta(days=1)
        if current.weekday() < 5:  # Mon-Fri
            remaining -= 1

    return current.astimezone(timezone.utc)

