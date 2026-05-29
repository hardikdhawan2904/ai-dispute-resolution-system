import sys, json
sys.path.insert(0, ".")
from database.database import SessionLocal
from database.models import DisputeCase, AuditLog

db = SessionLocal()

cases = [
    {
        "case_id":               "CASE-20260526183524-C5B08138",
        "customer_id":           "CUST-00101",
        "customer_name":         "Priya Sharma",
        "email":                 "priya.sharma@gmail.com",
        "phone":                 "+91 9876543210",
        "transaction_id":        "UPI20260526183500001",
        "transaction_type":      "UPI",
        "merchant":              "Unknown Merchant - Delhi",
        "amount":                45000.0,
        "currency":              "INR",
        "transaction_date":      "2026-05-26",
        "transaction_time":      "00:05",
        "dispute_reason":        "Unauthorized UPI transfer",
        "fraud_selected":        True,
        "customer_comment":      "Unauthorized transaction",
        "dispute_category":      "Unauthorized Transaction",
        "fraud_suspicion":       True,
        "customer_intent_summary": "Customer reports unauthorized UPI transaction to unknown merchant in Delhi.",
        "priority":              "HIGH",
        "confidence_score":      0.1,
        "risk_tags":             ["POSSIBLE_FRAUD", "HIGH_VALUE_TRANSACTION"],
        "structured_reasoning":  "Unauthorized transaction to unknown merchant flagged as fraud.",
        "status":                "Dispute Raised",
        "workflow_ready":        True,
        "created_at":            "2026-05-26T18:35:24+00:00",
        "assigned_queue":        "FRAUD_OPS",
        "priority_score":        45.0,
    },
    {
        "case_id":               "CASE-20260526183829-B705FFFE",
        "customer_id":           "CUST-00101",
        "customer_name":         "Priya Sharma",
        "email":                 "priya.sharma@gmail.com",
        "phone":                 "+91 9876543210",
        "transaction_id":        "UPI20260526183800002",
        "transaction_type":      "UPI",
        "merchant":              "Unknown Merchant - Delhi",
        "amount":                45000.0,
        "currency":              "INR",
        "transaction_date":      "2026-05-26",
        "transaction_time":      "00:08",
        "dispute_reason":        "Unauthorized UPI transfer",
        "fraud_selected":        True,
        "customer_comment":      "Unauthorized transaction",
        "dispute_category":      "Unauthorized Transaction",
        "fraud_suspicion":       True,
        "customer_intent_summary": "Customer reports unauthorized UPI transaction to unknown merchant in Delhi.",
        "priority":              "HIGH",
        "confidence_score":      0.1,
        "risk_tags":             ["POSSIBLE_FRAUD", "HIGH_VALUE_TRANSACTION"],
        "structured_reasoning":  "Unauthorized transaction to unknown merchant flagged as fraud.",
        "status":                "Dispute Raised",
        "workflow_ready":        True,
        "created_at":            "2026-05-26T18:38:29+00:00",
        "assigned_queue":        "FRAUD_OPS",
        "priority_score":        45.0,
    },
    {
        "case_id":               "CASE-20260529054950-B93B2018",
        "customer_id":           "CUST-00132",
        "customer_name":         "Viraj Balakrishnan",
        "email":                 "vb@gmail.com",
        "phone":                 "+91 9876543210",
        "transaction_id":        "TXN-CC-20260501-5519",
        "transaction_type":      "UPI",
        "merchant":              "Netflix India",
        "amount":                45000.0,
        "currency":              "INR",
        "transaction_date":      "2026-05-14",
        "transaction_time":      "02:22",
        "dispute_reason":        "Unauthorized UPI transfer",
        "fraud_selected":        False,
        "customer_comment":      "money was debited",
        "dispute_category":      "Unauthorized Transaction",
        "fraud_suspicion":       True,
        "customer_intent_summary": "Customer reports money was debited without authorization via UPI to Netflix India.",
        "priority":              "HIGH",
        "confidence_score":      0.7,
        "risk_tags":             ["POSSIBLE_FRAUD", "HIGH_VALUE_TRANSACTION"],
        "structured_reasoning":  "High value UPI transaction disputed as unauthorized.",
        "status":                "Dispute Raised",
        "workflow_ready":        True,
        "created_at":            "2026-05-29T05:49:50+00:00",
        "assigned_queue":        "FRAUD_OPS",
        "priority_score":        45.0,
    },
]

for c in cases:
    existing = db.query(DisputeCase).filter(DisputeCase.case_id == c["case_id"]).first()
    if existing:
        print(f"Already exists: {c['case_id']}")
        continue
    row = DisputeCase(**c)
    db.add(row)
    db.flush()
    log = AuditLog(
        case_id=c["case_id"],
        event_type="CASE_CREATED",
        stage="structured_output",
        actor="system",
        message=f"Case restored. Category: {c['dispute_category']}",
        payload=json.dumps({"confidence_score": c["confidence_score"]}),
    )
    db.add(log)
    print(f"Restored: {c['case_id']}")

db.commit()
db.close()
print("Done.")
