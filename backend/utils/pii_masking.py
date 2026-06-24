"""
PII masking utilities — single source of truth for all masking before data reaches any LLM.

Functions:
  mask_name(name)              'Deepak Ghosh'  → 'D.G.'
  mask_id(value, prefix_chars) 'CUST-00001'    → 'CUST-0**'
  mask_document(text)          strips account numbers, cards, IFSC from OCR text
  mask_free_text(text)         strips email, phone, PAN, Aadhaar, account, card, IFSC
                               from any free-text field (e.g. customer_comment)
"""
from __future__ import annotations

import re
from typing import List, Tuple


# ── Structured field maskers ──────────────────────────────────────────────────

def mask_name(name: str) -> str:
    """'Deepak Ghosh' → 'D.G.'"""
    if not name or name == "N/A":
        return name
    parts = name.strip().split()
    return ".".join(p[0].upper() for p in parts if p) + "."


def mask_id(value: str, prefix_chars: int = 6) -> str:
    """'CUST-00001' → 'CUST-0**'  |  'CASE-000529' → 'CASE-00**'"""
    if not value or value == "N/A":
        return value
    return value[:prefix_chars] + "**"


def mask_document(text: str) -> str:
    """Strip sensitive numbers from OCR / document text."""
    text = re.sub(r'\b\d{9,18}\b',              '[ACCOUNT-MASKED]', text)
    text = re.sub(r'\b[A-Z]{4}0[A-Z0-9]{6}\b', '[IFSC-MASKED]',    text)
    text = re.sub(r'\b(?:\d[ -]?){15}\d\b',     '[CARD-MASKED]',    text)
    return text


# ── Free-text PII patterns (order matters — most-specific first) ──────────────

_PATTERNS: List[Tuple[re.Pattern, str]] = [
    # Aadhaar: 12 digits in groups of 4 (e.g. 1234 5678 9012)
    (re.compile(r'\b\d{4}\s\d{4}\s\d{4}\b'),                                    "[AADHAAR-MASKED]"),
    # PAN card: AAAAA9999A
    (re.compile(r'\b[A-Z]{5}[0-9]{4}[A-Z]\b'),                                  "[PAN-MASKED]"),
    # Card numbers: 16 digits possibly separated by spaces or dashes
    (re.compile(r'\b(?:\d[ -]?){15}\d\b'),                                       "[CARD-MASKED]"),
    # IFSC codes: ABCD0123456
    (re.compile(r'\b[A-Z]{4}0[A-Z0-9]{6}\b'),                                   "[IFSC-MASKED]"),
    # Bank account numbers: 9–18 standalone digits
    (re.compile(r'\b\d{9,18}\b'),                                                "[ACCOUNT-MASKED]"),
    # Email addresses
    (re.compile(r'\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b'),      "[EMAIL-MASKED]"),
    # Indian mobile: optional +91 or 0 prefix then 10 digits starting with 6-9
    (re.compile(r'(?<!\d)(?:\+91[\s\-]?|0)?[6-9]\d{9}(?!\d)'),                 "[PHONE-MASKED]"),
]


def mask_free_text(text: str) -> str:
    """Apply all PII patterns to a free-text string and return the redacted version."""
    if not text:
        return text
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text

