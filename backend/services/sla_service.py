"""
SLA deadline calculation.

SLAs (business hours):
  CRITICAL  — 4 hours  (calendar time, no weekend pause)
  HIGH      — 24 hours (calendar time)
  MEDIUM    — 3 business days
  LOW       — 5 business days

Business-hour pauses:
  - Weekends are skipped for MEDIUM/LOW
  - Clock is paused while status == "Pending Documents"
"""
from datetime import datetime, timedelta, timezone


_SLA_HOURS = {
    "CRITICAL": 4,
    "HIGH":     24,
    "MEDIUM":   3 * 8,   # 3 business days × 8 h/day
    "LOW":      5 * 8,   # 5 business days × 8 h/day
}

_BUSINESS_DAYS_PRIORITY = {"MEDIUM", "LOW"}


def compute_sla_deadline(priority: str, from_dt: datetime | None = None) -> datetime:
    """Return the SLA deadline datetime for the given priority."""
    base = from_dt or datetime.now(timezone.utc)
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)

    hours = _SLA_HOURS.get(priority, 24)

    if priority not in _BUSINESS_DAYS_PRIORITY:
        # Calendar hours — simple addition
        return base + timedelta(hours=hours)

    # Business-day advance: skip Sat/Sun
    remaining = hours
    current = base
    while remaining > 0:
        current += timedelta(hours=1)
        if current.weekday() < 5:   # Mon-Fri
            remaining -= 1
    return current


def is_sla_breached(deadline: datetime | None) -> bool:
    if deadline is None:
        return False
    now = datetime.now(timezone.utc)
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    return now > deadline


def hours_until_sla(deadline: datetime | None) -> float | None:
    if deadline is None:
        return None
    now = datetime.now(timezone.utc)
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    delta = (deadline - now).total_seconds() / 3600
    return round(delta, 2)
