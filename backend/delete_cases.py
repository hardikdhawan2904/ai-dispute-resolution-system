import sys
sys.path.insert(0, ".")
from database.database import SessionLocal
from database.models import DisputeCase, AuditLog, WorkflowState, CaseNote, DocumentRequest

IDS = ["CASE-20260529054950-B93B2018"]
db = SessionLocal()
for m in [AuditLog, WorkflowState, CaseNote, DocumentRequest]:
    n = db.query(m).filter(m.case_id.in_(IDS)).delete(synchronize_session=False)
    print(f"Deleted {n} from {m.__tablename__}")
n = db.query(DisputeCase).filter(DisputeCase.case_id.in_(IDS)).delete(synchronize_session=False)
print(f"Deleted {n} from dispute_cases")
db.commit()
db.close()
print("Done.")
