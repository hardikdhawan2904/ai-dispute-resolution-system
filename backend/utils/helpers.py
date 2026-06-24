"""
Utility helpers for the BFSI Dispute Resolution Platform.
"""
import uuid
import re
import json
from datetime import datetime, timezone
from typing import Any, Optional


def generate_case_id(db=None) -> str:
    """Generate a sequential BFSI case ID — CASE-000527, CASE-000528, …"""
    if db is not None:
        from sqlalchemy import text
        n = db.execute(text("SELECT nextval('dispute_case_seq')")).scalar()
        return f"CASE-{n:06d}"
    # fallback when no db session available (should rarely be hit)
    from sqlalchemy import text, create_engine
    import os
    _engine = create_engine(os.environ["DATABASE_URL"])
    with _engine.connect() as conn:
        n = conn.execute(text("SELECT nextval('dispute_case_seq')")).scalar()
        conn.commit()
    return f"CASE-{n:06d}"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sanitize_amount(amount: Any) -> float:
    """Coerce amount to float, stripping currency symbols."""
    if isinstance(amount, (int, float)):
        return float(amount)
    cleaned = re.sub(r"[^\d.]", "", str(amount))
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def extract_json_from_text(text: str) -> Optional[dict]:
    """
    Robustly extract a JSON object from LLM output that may contain
    surrounding prose, markdown fences, or other noise.
    """
    # 1. Try direct parse
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    # 2. Strip markdown code fences
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except json.JSONDecodeError:
            pass

    # 3. Find first '{' ... last '}'
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass

    return None

