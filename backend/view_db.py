"""Quick database viewer — run from backend dir with .venv active."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from database.database import SessionLocal
from database.models import DisputeCase, AuditLog, WorkflowState, CaseNote, DocumentRequest

db = SessionLocal()

cases = db.query(DisputeCase).all()
print(f"\n=== dispute_cases ({len(cases)} rows) ===")
for c in cases[:5]:
    print(f"  {c.case_id} | {c.status} | {c.priority} | {c.amount} {c.currency} | {c.customer_id}")

logs = db.query(AuditLog).all()
print(f"\n=== audit_logs ({len(logs)} rows) ===")
for l in logs[:5]:
    msg = (l.message or "")[:60]
    print(f"  {l.case_id} | {l.action} | {l.actor} | {msg}")

states = db.query(WorkflowState).all()
print(f"\n=== workflow_states ({len(states)} rows) ===")
for s in states[:5]:
    print(f"  {s.case_id} | {s.current_node} | {s.status}")

notes = db.query(CaseNote).all()
print(f"\n=== case_notes ({len(notes)} rows) ===")
for n in notes[:5]:
    print(f"  {n.case_id} | {n.author} | {n.is_internal} | {n.content[:60]}")

docs = db.query(DocumentRequest).all()
print(f"\n=== document_requests ({len(docs)} rows) ===")
for d in docs[:5]:
    print(f"  {d.case_id} | {d.document_type} | fulfilled={d.fulfilled}")

db.close()
print("\nDone.")
