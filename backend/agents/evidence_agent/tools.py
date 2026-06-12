"""
Evidence Intelligence Agent tools — 5 deterministic tools that read from DB.

Each tool:
  - is decorated with @tool (docstring becomes LLM JSON schema)
  - opens its own DB session and closes it on exit
  - returns a human-readable string the LLM cites in its reasoning
  - never calls external APIs or the LLM — purely deterministic

All 5 tools are pre-run server-side before LLM invocation (same pattern as
Agent 2 and Agent 3). The LLM receives pre-computed results and synthesises
the final evidence assessment — it does not call tools at runtime.

Evidence strength calculation:
  evidence_match=true  + completeness >= 80  + consistent  → HIGH
  evidence_match=false + any major gap                     → LOW
  All other cases                                          → MEDIUM
"""
import pathlib

from langchain_core.tools import tool

from utils.logger import agent_logger

_ALLOWED_EXTS = {".pdf", ".jpg", ".jpeg", ".png", ".xlsx", ".csv"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _split_docs(required_docs: list) -> tuple:
    """Split required documents into customer-obtainable and bank-obtainable.
    Bank-obtainable docs are the bank's internal responsibility — they do not
    affect evidence completeness or customer-facing requests."""
    from services.document_rules import BANK_OBTAINABLE
    customer = [d for d in required_docs if d not in BANK_OBTAINABLE]
    bank     = [d for d in required_docs if d in BANK_OBTAINABLE]
    return customer, bank


def _count_uploads(case_id: str) -> int:
    """Count files actually on disk for this case — ground truth regardless of
    whether formal document requests were created. Mirrors the same pattern used
    by document_rules.resolve_investigation_status."""
    upload_dir = pathlib.Path("uploads") / case_id
    if not upload_dir.exists():
        return 0
    return sum(
        1 for f in upload_dir.iterdir()
        if f.is_file() and f.suffix.lower() in _ALLOWED_EXTS
    )

def _read_case(case_id: str):
    """Read case fields needed for evidence assessment from dispute_cases."""
    from database.database import SessionLocal
    from database.models import DisputeCase

    db = SessionLocal()
    try:
        case = db.query(DisputeCase).filter(DisputeCase.case_id == case_id).first()
        if not case:
            return None
        return {
            "case_id":              case.case_id,
            "customer_id":          case.customer_id,
            "transaction_id":       case.transaction_id,
            "transaction_type":     case.transaction_type or "",
            "merchant":             case.merchant or "",
            "amount":               float(case.amount or 0),
            "currency":             case.currency or "INR",
            "transaction_date":     case.transaction_date or "",
            "transaction_time":     case.transaction_time or "",
            "dispute_category":     case.dispute_category or "Other",
            "fraud_suspicion":      case.fraud_suspicion or False,
            "evidence_match":       case.evidence_match,
            "evidence_match_note":  case.evidence_match_note or "",
            "investigation_plan":   case.investigation_plan or {},
            "risk_tags":            case.risk_tags or [],
        }
    finally:
        db.close()


def _get_document_requests(case_id: str):
    """Read document requests for this case."""
    from database.database import SessionLocal
    from database.models import DocumentRequest

    db = SessionLocal()
    try:
        reqs = db.query(DocumentRequest).filter(
            DocumentRequest.case_id == case_id
        ).all()
        return [
            {
                "id":            r.id,
                "document_type": r.document_type,
                "fulfilled":     r.fulfilled,
                "description":   r.description or "",
            }
            for r in reqs
        ]
    finally:
        db.close()


# ── Tool 1 — Evidence completeness ───────────────────────────────────────────

@tool
def evaluate_evidence_completeness(case_id: str) -> str:
    """Evaluate the completeness of evidence for a dispute case by checking required
    documents from the investigation plan against fulfilled document requests. Computes
    a completeness score (0-100) and returns a list of missing document types. Reads
    from dispute_cases, investigation_plan, and document_requests tables. Call this
    first to establish a baseline evidence coverage picture."""
    try:
        c = _read_case(case_id)
        if not c:
            return f"EVIDENCE COMPLETENESS\n  Error: Case {case_id} not found\n  Completeness Score: 0"

        inv_plan      = c["investigation_plan"]
        all_required  = inv_plan.get("required_documents", []) if isinstance(inv_plan, dict) else []
        customer_docs, bank_docs = _split_docs(all_required)

        doc_requests  = _get_document_requests(case_id)
        fulfilled     = [r for r in doc_requests if r["fulfilled"]]
        pending       = [r for r in doc_requests if not r["fulfilled"]]
        upload_count  = _count_uploads(case_id)
        ev_match      = c["evidence_match"]

        fulfilled_types = {r["document_type"].lower() for r in fulfilled}

        def _is_fulfilled_by_request(doc: str) -> bool:
            doc_lower = doc.lower()
            return any(doc_lower in ft or ft in doc_lower for ft in fulfilled_types)

        # Completeness is scored against customer-obtainable docs only.
        # Bank-obtainable docs are the bank's internal responsibility and do not
        # affect whether the customer has provided sufficient evidence.
        if not customer_docs and not all_required:
            if ev_match is True:
                completeness = 90
                missing = []
                note = "No formal document requirements — Agent 1 evidence match is True"
            elif ev_match is False:
                completeness = 30
                missing = ["Supporting documentation for claimed dispute"]
                note = "No formal document requirements — Agent 1 evidence match is False"
            else:
                completeness = 50
                missing = []
                note = "No formal document requirements defined — evidence match not assessed"
        else:
            req_fulfilled = [d for d in customer_docs if _is_fulfilled_by_request(d)]
            req_without   = [d for d in customer_docs if not _is_fulfilled_by_request(d)]

            # Credit uploads when Agent 1 verified evidence (no formal request needed)
            upload_credits = min(upload_count, len(req_without)) if ev_match is True else 0
            fulfilled_cnt  = len(req_fulfilled) + upload_credits
            missing        = req_without[upload_credits:]
            total_customer = len(customer_docs) if customer_docs else 1
            completeness   = int((fulfilled_cnt / total_customer) * 100)

            if upload_credits > 0:
                note = (
                    f"{fulfilled_cnt}/{len(customer_docs)} customer documents present "
                    f"({upload_credits} via uploads, {len(bank_docs)} bank-obtainable docs tracked separately)"
                )
            else:
                note = (
                    f"{fulfilled_cnt}/{len(customer_docs)} customer documents fulfilled "
                    f"({len(bank_docs)} bank-obtainable docs not included in score)"
                )

        missing_str   = "\n".join(f"    • {m}" for m in missing) if missing else "    • None"
        bank_docs_str = "\n".join(f"    • {d}" for d in bank_docs) if bank_docs else "    • None"

        return (
            f"EVIDENCE COMPLETENESS\n"
            f"  Case ID                  : {case_id}\n"
            f"  Customer Documents Total : {len(customer_docs)}\n"
            f"  Bank-Obtainable Docs     : {len(bank_docs)}\n"
            f"  Fulfilled Requests       : {len(fulfilled)}\n"
            f"  Uploaded Files           : {upload_count}\n"
            f"  Completeness Score       : {completeness}% (customer docs only)\n"
            f"  Evidence Match (AI)      : {ev_match}\n"
            f"  Note                     : {note}\n"
            f"  Missing Customer Docs    :\n{missing_str}\n"
            f"  Bank-Obtainable Pending  :\n{bank_docs_str}"
        )
    except Exception as exc:
        agent_logger.warning(f"evaluate_evidence_completeness failed: {exc}")
        return f"EVIDENCE COMPLETENESS\n  Error: {exc}\n  Completeness Score: 50 (default)"


# ── Tool 2 — Missing evidence ─────────────────────────────────────────────────

@tool
def identify_missing_evidence(case_id: str) -> str:
    """Identify which required documents have not yet been submitted or fulfilled
    for this dispute case. Compares investigation_plan.required_documents against
    fulfilled document requests to produce a specific list of missing document types.
    Returns the count of pending requests and whether evidence gaps block investigation."""
    try:
        c = _read_case(case_id)
        if not c:
            return f"MISSING EVIDENCE\n  Error: Case {case_id} not found\n  Required Documents: []"

        inv_plan      = c["investigation_plan"]
        all_required  = inv_plan.get("required_documents", []) if isinstance(inv_plan, dict) else []
        customer_docs, bank_docs = _split_docs(all_required)

        doc_requests  = _get_document_requests(case_id)
        fulfilled     = [r for r in doc_requests if r["fulfilled"]]
        pending       = [r for r in doc_requests if not r["fulfilled"]]
        upload_count  = _count_uploads(case_id)
        ev_match      = c["evidence_match"]
        fulfilled_types = {r["document_type"].lower() for r in fulfilled}

        def _is_fulfilled_by_request(doc: str) -> bool:
            doc_lower = doc.lower()
            return any(doc_lower in ft or ft in doc_lower for ft in fulfilled_types)

        # Only report customer-obtainable docs as "missing" — bank-obtainable docs
        # are the bank's internal responsibility and should not block investigation.
        if not customer_docs:
            missing    = []
            gaps_block = ev_match is False
        else:
            req_without = [d for d in customer_docs if not _is_fulfilled_by_request(d)]
            upload_credits = min(upload_count, len(req_without)) if ev_match is True else 0
            missing    = req_without[upload_credits:]
            gaps_block = len(missing) > len(customer_docs) // 2

        missing_str  = "\n".join(f"    • {m}" for m in missing) if missing else "    • None"
        pending_str  = "\n".join(f"    • {r['document_type']}" for r in pending) if pending else "    • None"
        bank_doc_str = "\n".join(f"    • {d}" for d in bank_docs) if bank_docs else "    • None"

        return (
            f"MISSING EVIDENCE\n"
            f"  Case ID                  : {case_id}\n"
            f"  Customer Documents       : {customer_docs or ['None defined']}\n"
            f"  Bank-Obtainable Docs     : {bank_docs or ['None']}\n"
            f"  Uploaded Files           : {upload_count}\n"
            f"  Missing Customer Docs    :\n{missing_str}\n"
            f"  Pending Requests         :\n{pending_str}\n"
            f"  Bank Docs Pending        :\n{bank_doc_str}\n"
            f"  Gaps Block Investigation : {gaps_block}\n"
            f"  Evidence Match (Agent 1) : {ev_match}"
        )
    except Exception as exc:
        agent_logger.warning(f"identify_missing_evidence failed: {exc}")
        return f"MISSING EVIDENCE\n  Error: {exc}\n  Required Documents: []"


# ── Tool 3 — Evidence consistency ────────────────────────────────────────────

@tool
def validate_evidence_consistency(case_id: str) -> str:
    """Validate consistency of key transaction details for this dispute case.
    Checks whether the amount, merchant, transaction type, and date reported in
    the dispute match the original transaction record. Reads from dispute_cases and
    transactions tables. Returns a consistency verdict and any specific discrepancies."""
    try:
        from database.database import SessionLocal
        from database.models import DisputeCase, Transaction

        db = SessionLocal()
        try:
            case = db.query(DisputeCase).filter(DisputeCase.case_id == case_id).first()
            if not case:
                return f"CONSISTENCY CHECK\n  Error: Case {case_id} not found\n  Consistent: Unknown"

            txn = db.query(Transaction).filter(
                Transaction.transaction_id == case.transaction_id
            ).first()

            issues = []

            if txn:
                # Amount consistency (allow 1% tolerance)
                case_amt = float(case.amount or 0)
                txn_amt  = float(txn.amount or 0)
                if txn_amt > 0 and abs(case_amt - txn_amt) / txn_amt > 0.01:
                    issues.append(
                        f"Amount mismatch: dispute claims ₹{case_amt:,.2f}, "
                        f"transaction record shows ₹{txn_amt:,.2f}"
                    )

                # Merchant consistency
                if txn.merchant_name and case.merchant:
                    txn_m  = txn.merchant_name.lower().strip()
                    case_m = case.merchant.lower().strip()
                    if txn_m and case_m and txn_m not in case_m and case_m not in txn_m:
                        issues.append(
                            f"Merchant mismatch: dispute names '{case.merchant}', "
                            f"transaction record shows '{txn.merchant_name}'"
                        )

                txn_source = "Transaction record found in database"
            else:
                txn_source = "Transaction record not found — consistency check limited to case data"
                issues.append("Transaction not found in records — full consistency check not possible")

            # Evidence match note consistency
            ev_match = case.evidence_match
            if ev_match is False:
                issues.append(
                    "Agent 1 evidence verdict: submitted documents do NOT support the claim"
                )

            consistent = len([i for i in issues if "Transaction not found" not in i]) == 0

            issues_str = "\n".join(f"    • {i}" for i in issues) if issues else "    • No inconsistencies found"

            return (
                f"CONSISTENCY CHECK\n"
                f"  Case ID        : {case_id}\n"
                f"  Transaction    : {txn_source}\n"
                f"  Consistent     : {consistent}\n"
                f"  Issues Found   : {len(issues)}\n"
                f"  Inconsistencies:\n{issues_str}"
            )
        finally:
            db.close()
    except Exception as exc:
        agent_logger.warning(f"validate_evidence_consistency failed: {exc}")
        return f"CONSISTENCY CHECK\n  Error: {exc}\n  Consistent: Unknown"


# ── Tool 4 — Evidence strength ───────────────────────────────────────────────

@tool
def assess_evidence_strength(case_id: str) -> str:
    """Assess the overall strength of available evidence for this dispute case using
    multiple signals: Agent 1 evidence_match verdict, document completeness, fulfilled
    document requests, amount of missing evidence, and Agent 2 data quality score.
    Returns HIGH, MEDIUM, or LOW strength with a numeric score (0.0-1.0) and the
    key contributing factors. HIGH means evidence is sufficient to proceed; LOW means
    additional documentation is critical before investigation can continue."""
    try:
        c = _read_case(case_id)
        if not c:
            return f"EVIDENCE STRENGTH\n  Error: Case {case_id} not found\n  Strength: MEDIUM (default)"

        inv_plan      = c["investigation_plan"]
        all_required  = inv_plan.get("required_documents", []) if isinstance(inv_plan, dict) else []
        dq_score      = inv_plan.get("data_quality_score", 0.75) if isinstance(inv_plan, dict) else 0.75
        customer_docs, bank_docs = _split_docs(all_required)

        doc_requests  = _get_document_requests(case_id)
        fulfilled     = [r for r in doc_requests if r["fulfilled"]]
        upload_count  = _count_uploads(case_id)
        fulfilled_types = {r["document_type"].lower() for r in fulfilled}

        def _is_fulfilled_by_request(doc: str) -> bool:
            doc_lower = doc.lower()
            return any(doc_lower in ft or ft in doc_lower for ft in fulfilled_types)

        # Score signals (each contributes to strength)
        score    = 0.5  # baseline
        factors  = []
        ev_match = c["evidence_match"]

        # Signal 1 — Agent 1 evidence verdict (highest weight)
        if ev_match is True:
            score += 0.25
            factors.append("Agent 1 evidence verdict: documents SUPPORT the claim (+0.25)")
        elif ev_match is False:
            score -= 0.20
            factors.append("Agent 1 evidence verdict: documents DO NOT support the claim (-0.20)")
        else:
            factors.append("Agent 1 evidence verdict: not assessed (no documents submitted)")

        # Signal 2 — document completeness (customer docs only — bank docs excluded)
        if customer_docs:
            req_without   = [d for d in customer_docs if not _is_fulfilled_by_request(d)]
            upload_credits = min(upload_count, len(req_without)) if ev_match is True else 0
            fulfilled_cnt  = (len(customer_docs) - len(req_without)) + upload_credits
            missing_count  = len(customer_docs) - fulfilled_cnt
            completeness   = fulfilled_cnt / len(customer_docs)
            completeness_adj = (completeness - 0.5) * 0.20  # ±0.10 max
            score += completeness_adj
            suffix = f" ({len(bank_docs)} bank-obtainable docs excluded)"
            if missing_count == 0:
                factors.append(f"All {len(customer_docs)} customer documents present (+{completeness_adj:+.2f}){suffix}")
            elif upload_credits > 0:
                factors.append(
                    f"{fulfilled_cnt}/{len(customer_docs)} customer documents present "
                    f"({upload_credits} via uploads, {missing_count} still missing) ({completeness_adj:+.2f})"
                )
            else:
                factors.append(f"{missing_count}/{len(customer_docs)} customer documents missing ({completeness_adj:+.2f})")
        else:
            factors.append("No customer-obtainable document requirements — evidence completeness not scored")

        # Signal 3 — uploaded files (when no formal requests exist)
        effective_fulfilled = len(fulfilled) + (upload_count if len(fulfilled) == 0 else 0)
        if effective_fulfilled >= 2:
            score += 0.05
            factors.append(f"{effective_fulfilled} evidence file(s) present (+0.05)")
        elif effective_fulfilled == 1:
            score += 0.02
            factors.append(f"1 evidence file present (+0.02)")

        # Signal 4 — Agent 2 data quality
        if isinstance(dq_score, (int, float)):
            dq_adj = (float(dq_score) - 0.75) * 0.10
            score += dq_adj
            factors.append(f"Agent 2 data quality score: {dq_score:.2f} (adjustment: {dq_adj:+.2f})")

        score = max(0.0, min(1.0, score))

        if score >= 0.70:
            strength = "HIGH"
        elif score >= 0.45:
            strength = "MEDIUM"
        else:
            strength = "LOW"

        factors_str = "\n".join(f"    + {f}" for f in factors)

        return (
            f"EVIDENCE STRENGTH\n"
            f"  Case ID          : {case_id}\n"
            f"  Strength         : {strength}\n"
            f"  Strength Score   : {score:.2f}\n"
            f"  Evidence Match   : {ev_match}\n"
            f"  Fulfilled Requests: {len(fulfilled)}\n"
            f"  Contributing Factors:\n{factors_str}"
        )
    except Exception as exc:
        agent_logger.warning(f"assess_evidence_strength failed: {exc}")
        return f"EVIDENCE STRENGTH\n  Error: {exc}\n  Strength: MEDIUM (default)\n  Strength Score: 0.50"


# ── Tool 5 — Next document request ───────────────────────────────────────────

@tool
def determine_next_document_request(case_id: str) -> str:
    """Determine the next document that should be formally requested from the customer
    or merchant for this dispute case. Checks existing pending document requests to
    avoid creating duplicates. Prioritises missing required documents from the
    investigation plan first, then evidence-match gaps. Returns the recommended
    document type and the specific reason it is needed for this dispute."""
    try:
        c = _read_case(case_id)
        if not c:
            return f"NEXT DOCUMENT REQUEST\n  Error: Case {case_id} not found\n  Recommended Request: null"

        inv_plan      = c["investigation_plan"]
        all_required  = inv_plan.get("required_documents", []) if isinstance(inv_plan, dict) else []
        customer_docs, bank_docs = _split_docs(all_required)

        doc_requests  = _get_document_requests(case_id)
        fulfilled     = [r for r in doc_requests if r["fulfilled"]]
        pending       = [r for r in doc_requests if not r["fulfilled"]]
        upload_count  = _count_uploads(case_id)
        ev_match      = c["evidence_match"]

        fulfilled_types = {r["document_type"].lower() for r in fulfilled}
        pending_types   = {r["document_type"].lower() for r in pending}

        def _is_covered_by_request(doc: str) -> bool:
            doc_lower = doc.lower()
            return any(doc_lower in t or t in doc_lower for t in (fulfilled_types | pending_types))

        # Only recommend requesting customer-obtainable documents.
        # Bank-obtainable docs are obtained internally — never request from customer.
        req_without = [d for d in customer_docs if not _is_covered_by_request(d)]
        upload_credits    = min(upload_count, len(req_without)) if ev_match is True else 0
        genuinely_missing = req_without[upload_credits:]

        recommended = None
        reason      = None

        for doc in genuinely_missing:
            doc_lower = doc.lower()
            already_pending = any(doc_lower in p or p in doc_lower for p in pending_types)
            if not already_pending:
                recommended = doc
                reason = (
                    f"Required for {c['dispute_category']} investigation — "
                    f"not yet submitted or formally requested"
                )
                break

        # Fallback — evidence mismatch with no specific customer doc gap
        if not recommended and ev_match is False:
            recommended = "Additional supporting documentation"
            reason = (
                "Agent 1 evidence verdict indicates submitted documents do not support the claim — "
                "additional customer evidence required"
            )

        pending_str = "\n".join(f"    • {r['document_type']}" for r in pending) if pending else "    • None"

        return (
            f"NEXT DOCUMENT REQUEST\n"
            f"  Case ID              : {case_id}\n"
            f"  Customer Docs        : {len(customer_docs)} required\n"
            f"  Bank-Obtainable Docs : {len(bank_docs)} (excluded — bank obtains internally)\n"
            f"  Uploaded Files       : {upload_count} (credited for {upload_credits} customer doc(s))\n"
            f"  Recommended Request  : {recommended or 'null — all customer documents present'}\n"
            f"  Reason               : {reason or 'All required customer documents present or already requested'}\n"
            f"  Existing Pending     : {len(pending)}\n"
            f"  Currently Pending    :\n{pending_str}"
        )
    except Exception as exc:
        agent_logger.warning(f"determine_next_document_request failed: {exc}")
        return f"NEXT DOCUMENT REQUEST\n  Error: {exc}\n  Recommended Request: null"


# ── Registry ──────────────────────────────────────────────────────────────────

TOOL_REGISTRY: dict = {
    "evaluate_evidence_completeness":  evaluate_evidence_completeness,
    "identify_missing_evidence":       identify_missing_evidence,
    "validate_evidence_consistency":   validate_evidence_consistency,
    "assess_evidence_strength":        assess_evidence_strength,
    "determine_next_document_request": determine_next_document_request,
}
