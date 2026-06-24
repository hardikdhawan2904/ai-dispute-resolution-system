"""
Smart document type matching — maps uploaded files to requested document types
using filename keywords and OCR text content signals.
"""
from __future__ import annotations
import re
from typing import Optional


# ── Keyword maps ───────────────────────────────────────────────────────────────
# Each entry: (list_of_keywords_in_filename_or_ocr, canonical_fragment_to_match)
# The canonical fragment is matched against DocumentRequest.document_type (case-insensitive contains)

_FILENAME_RULES: list[tuple[list[str], str]] = [
    (["bank_statement", "account_statement", "statement"],          "bank statement"),
    (["police_fir", "fir", "police_complaint", "police"],           "police fir"),
    (["merchant_comm", "merchant_communication", "chat", "email_", "sms"], "merchant communication"),
    (["refund_confirm", "refund"],                                   "refund confirmation"),
    (["otp_receipt", "otp"],                                        "otp"),
    (["kyc", "aadhaar", "pan_card", "identity"],                    "identity"),
    (["cancellation", "order_cancel", "cancel_confirm"],            "cancellation"),
    (["payment_confirm", "payment_receipt"],                        "payment confirmation"),
    (["photos", "product_photo", "product_image"],                  "photos"),
    (["source_of_funds", "fund_source"],                            "source of funds"),
    (["invoice", "purchase_receipt"],                               "invoice"),
    (["transaction_receipt", "txn_receipt"],                        "transaction"),
    (["complaint_letter", "complaint"],                             "complaint"),
    (["medical", "hospital", "prescription"],                       "medical"),
    (["insurance"],                                                 "insurance"),
]

_OCR_RULES: list[tuple[list[str], str]] = [
    (["first information report", "police station", "fir no", "complaint no"],  "police fir"),
    (["bank statement", "account statement", "opening balance", "closing balance", "transaction history"], "bank statement"),
    (["one time password", "otp for", "do not share this otp", "transaction otp"],  "otp"),
    (["refund of", "amount reversed", "amount credited back", "refund processed"], "refund confirmation"),
    (["aadhaar", "unique identification authority", "uid"],         "identity"),
    (["order cancelled", "cancellation confirmed", "your order has been cancelled"], "cancellation"),
    (["payment received", "payment confirmation", "amount debited", "debited from your account"], "payment confirmation"),
    (["merchant communication", "email from merchant", "chat with"],  "merchant communication"),
    (["source of funds", "income declaration"],                     "source of funds"),
    (["invoice no", "bill no", "gst invoice"],                      "invoice"),
]


def _normalise(text: str) -> str:
    """Lowercase, strip non-alphanumeric to spaces for robust matching."""
    return re.sub(r'[^a-z0-9]+', ' ', text.lower()).strip()


def match_document_type(
    filename: str,
    ocr_text: str,
    pending_types: list[str],
) -> Optional[str]:
    """
    Return the best matching document_type from pending_types given the
    uploaded filename and its OCR-extracted text content.

    Returns None if no confident match found (caller falls back to sequential).
    """
    if not pending_types:
        return None

    fname = _normalise(filename)
    content = _normalise(ocr_text or "")

    # Score each pending type
    scores: dict[str, float] = {t: 0.0 for t in pending_types}

    # ── Filename keyword scoring ───────────────────────────────────────────────
    for keywords, canonical in _FILENAME_RULES:
        if any(kw in fname for kw in keywords):
            for doc_type in pending_types:
                if canonical in _normalise(doc_type):
                    scores[doc_type] += 2.0   # filename match is strong

    # ── OCR content keyword scoring ───────────────────────────────────────────
    for phrases, canonical in _OCR_RULES:
        if any(ph in content for ph in phrases):
            for doc_type in pending_types:
                if canonical in _normalise(doc_type):
                    scores[doc_type] += 3.0   # OCR content match is strongest

    # ── Direct word overlap between filename tokens and doc type ──────────────
    fname_tokens = set(fname.split())
    for doc_type in pending_types:
        type_tokens = set(_normalise(doc_type).split())
        overlap = len(fname_tokens & type_tokens)
        scores[doc_type] += overlap * 0.5

    # Pick best score if above threshold
    best_type = max(scores, key=lambda t: scores[t])
    if scores[best_type] >= 1.5:
        return best_type

    return None   # no confident match

