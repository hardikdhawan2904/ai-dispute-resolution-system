import os
from dotenv import load_dotenv
import psycopg2
import json
import random
from datetime import datetime, timedelta

load_dotenv()

print("Connecting to database...")
db_url = os.environ.get("DATABASE_URL")
conn = psycopg2.connect(db_url)
cur = conn.cursor()

try:
    print("Clearing existing dispute cases and logs...")
    cur.execute("DELETE FROM audit_logs;")
    cur.execute("DELETE FROM workflow_states;")
    cur.execute("DELETE FROM case_notes;")
    cur.execute("DELETE FROM document_requests;")
    cur.execute("DELETE FROM dispute_cases;")
    conn.commit()
    print("Existing dispute tables cleared.")

    # Fetch 10 random customer-transaction pairs
    print("Fetching active customers and transactions from database...")
    cur.execute(
        """
        SELECT c.customer_id, c.full_name, c.email, c.phone, c.joining_date,
               t.transaction_id, t.transaction_type, t.merchant_name, t.amount, t.location, t.device_id
        FROM bank_customers c
        JOIN transactions t ON c.customer_id = t.customer_id
        ORDER BY RANDOM()
        LIMIT 10;
        """
    )
    pairs = cur.fetchall()

    if len(pairs) < 10:
        print("Warning: Found fewer than 10 matches, fetching individual rows...")
        cur.execute("SELECT customer_id, full_name, email, phone, joining_date FROM bank_customers LIMIT 10;")
        customers = cur.fetchall()
        cur.execute("SELECT transaction_id, transaction_type, merchant_name, amount, location, device_id FROM transactions LIMIT 10;")
        txns = cur.fetchall()
        pairs = []
        for i in range(min(len(customers), len(txns))):
            pairs.append(customers[i] + txns[i])

    queues = ["FRAUD_OPS", "ATM_INVESTIGATION", "CHARGEBACK_TEAM", "COMPLIANCE_REVIEW", "HIGH_PRIORITY", "GENERAL"]
    categories = ["Unauthorized Transaction", "Duplicate Transaction", "Refund Not Received", "Product Not Received", "Subscription Abuse", "ATM Cash Issue"]
    comments = [
        "I was charged twice for a single order of electronics. Please refund the duplicate transaction.",
        "I did not authorize this UPI transaction. I received no OTP and my phone was locked.",
        "Returned the items last week but merchant has not issued the refund. Order ID attached.",
        "ATM did not dispense the cash but the money was deducted from my savings account.",
        "Unrecognized credit card charge. I have not ordered from this website before.",
        "Recurring subscription charged after I cancelled it 2 months ago. Help!",
        "Double debit on card transaction. Merchant terminal showed connection error."
    ]

    print("Seeding 10 Dispute Cases...")
    for idx, row in enumerate(pairs):
        cust_id, cust_name, email, phone, join_date, txn_id, txn_type, merchant, amount, location, device_id = row
        
        case_id = f"CASE-{idx + 1:06}"
        dispute_cat = random.choice(categories)
        fraud = "Fraud" in dispute_cat or "Unauthorized" in dispute_cat or idx % 3 == 0
        comment = comments[idx % len(comments)]
        
        # Define varying trust scenarios
        if idx % 3 == 0:  # High threat/suspicious
            trust_score = 0.35
            risk_score = 0.75
            id_verif = "SUSPICIOUS"
            name_match = False
            device_risk = "HIGH"
            recognized_device = False
            friendly_fraud = "MEDIUM"
            velocity_breach = True
            reasoning = [
                "Name match validation failed between customer input and bank database records.",
                "Transaction originated from an unrecognized device ID with high risk classification.",
                "Multiple dispute submissions detected within a short time window (velocity breach)."
            ]
            summary = "Suspicious activity detected. Customer ID and profile name mismatch coupled with unrecognized device and transactional velocity alert."
            priority = "HIGH"
            priority_score = 85.0
            risk_tags = ["DEVICE_MISMATCH", "VELOCITY_BREACH", "SUSPICIOUS_BEHAVIOR"]
            assigned_queue = "FRAUD_OPS"
        elif idx % 3 == 1:  # Low trust/failed verification
            trust_score = 0.15
            risk_score = 0.90
            id_verif = "FAILED"
            name_match = False
            device_risk = "HIGH"
            recognized_device = False
            friendly_fraud = "HIGH"
            velocity_breach = True
            reasoning = [
                "KYC verification checks failed. Neither registered name nor email corresponds to bank database records.",
                "Unrecognized and unverified device fingerprint used for transaction access.",
                "High history of friendly fraud flags registered on this customer profile."
            ]
            summary = "KYC checks failed. Device risk is critical and prior logs suggest significant friendly fraud probability."
            priority = "CRITICAL"
            priority_score = 95.0
            risk_tags = ["POSSIBLE_FRAUD", "SUSPICIOUS_BEHAVIOR", "VELOCITY_BREACH"]
            assigned_queue = "FRAUD_OPS"
        else:  # High trust/verified customer
            trust_score = 0.95
            risk_score = 0.05
            id_verif = "VERIFIED"
            name_match = True
            device_risk = "LOW"
            recognized_device = True
            friendly_fraud = "LOW"
            velocity_breach = False
            reasoning = [
                "KYC check successfully matches full name, email, and phone registered in the system.",
                "Device ID matches recognized customer profile history.",
                "No prior dispute abuse or anomalous velocity behaviors detected."
            ]
            summary = "Trusted profile. Customer identity and device fingerprint verified successfully. Standard dispute routing recommended."
            priority = "LOW" if amount < 5000 else "MEDIUM"
            priority_score = 40.0 if amount < 5000 else 60.0
            risk_tags = ["OTP_VERIFIED"]
            assigned_queue = "ATM_INVESTIGATION" if "ATM" in dispute_cat else "CHARGEBACK_TEAM"

        trust_intel = {
            "case_id": case_id,
            "user_trust_score": trust_score,
            "behavioral_risk_score": risk_score,
            "identity_verification": id_verif,
            "kyc_checks": {
                "name_match": name_match,
                "contact_match": True,
                "join_date": str(join_date) if join_date else "N/A"
            },
            "device_fingerprint": {
                "recognized_device": recognized_device,
                "location_consistent": True,
                "device_risk": device_risk
            },
            "dispute_behavior": {
                "prior_dispute_count": random.randint(0, 2) if id_verif == "VERIFIED" else random.randint(3, 8),
                "velocity_breach_detected": velocity_breach,
                "friendly_fraud_risk": friendly_fraud
            },
            "trust_reasoning": reasoning,
            "trust_summary": summary,
            "tools_used": ["verify_kyc_match", "evaluate_device_fingerprint", "analyze_behavioral_patterns"],
            "agent_metadata": {
                "name": "ITIA",
                "version": "1.0.0",
                "model": "llama-3.1-8b-instant",
                "timestamp": (datetime.now() - timedelta(hours=idx)).isoformat(),
                "duration_ms": 780.0
            },
            "metrics": {
                "total_duration_ms": 780.0,
                "llm_calls": 1,
                "tool_calls": 3,
                "retry_count": 0
            }
        }

        # Create basic investigation plan
        investigation_plan = {
            "case_id": case_id,
            "recommended_queue": assigned_queue,
            "queue_confidence": 0.90,
            "investigation_complexity": "HIGH" if priority in ["HIGH", "CRITICAL"] else "MEDIUM",
            "manual_review_required": priority in ["HIGH", "CRITICAL"],
            "customer_risk_profile": {
                "previous_disputes": trust_intel["dispute_behavior"]["prior_dispute_count"],
                "risk_level": "HIGH" if trust_score < 0.5 else "LOW",
                "assessment": summary
            },
            "merchant_risk_profile": {
                "merchant_risk": "LOW",
                "prior_complaints": 2,
                "fraud_rate": 0.01,
                "assessment": "Merchant profile is stable."
            },
            "required_documents": ["Bank statement", "Merchant transaction slip"],
            "recommended_steps": ["Verify customer credentials", "Review device access history"],
            "investigation_summary": f"Investigation initiated on Category {dispute_cat} for {cust_name}.",
            "confidence_score": 0.85
        }

        # Create basic workflow plan
        workflow_plan = {
            "case_id": case_id,
            "workflow_complexity": "HIGH" if priority in ["HIGH", "CRITICAL"] else "MEDIUM",
            "required_agents": ["FRAUD_AGENT", "EVIDENCE_AGENT"] if fraud else ["EVIDENCE_AGENT"],
            "workflow_path": ["FRAUD_AGENT", "EVIDENCE_AGENT"] if fraud else ["EVIDENCE_AGENT"],
            "workflow_status": "IN_PROGRESS",
            "next_agent": "FRAUD_AGENT" if fraud else "EVIDENCE_AGENT",
            "remaining_agents": ["EVIDENCE_AGENT"] if fraud else [],
            "completed_agents": [],
            "escalation_required": priority == "CRITICAL",
            "escalation_level": "CRITICAL" if priority == "CRITICAL" else None,
            "manual_review_required": priority in ["HIGH", "CRITICAL"],
            "estimated_investigation_hours": 4,
            "analyst_level": "SENIOR" if priority in ["HIGH", "CRITICAL"] else "STANDARD",
            "workflow_reasoning": [f"High priority route initialized based on dispute analysis for {case_id}."]
        }

        created_at_dt = datetime.now() - timedelta(days=idx, hours=random.randint(1, 10))
        sla_deadline_dt = created_at_dt + timedelta(days=7)

        cur.execute(
            """
            INSERT INTO dispute_cases (
                case_id, customer_id, customer_name, email, phone, transaction_id, 
                transaction_type, merchant, amount, currency, transaction_date, transaction_time,
                customer_comment, dispute_reason, fraud_selected, dispute_category,
                fraud_suspicion, customer_intent_summary, priority, confidence_score,
                risk_tags, structured_reasoning, status, workflow_ready, current_stage,
                assigned_queue, assigned_analyst, priority_score, sla_deadline, sla_breached,
                requires_manual_review, manual_review_reason, trust_intelligence,
                user_trust_score, behavioral_risk_score, identity_status,
                investigation_plan, workflow_plan, created_at, updated_at
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW()
            );
            """,
            (
                case_id,
                cust_id,
                cust_name,
                email,
                phone,
                txn_id,
                txn_type,
                merchant,
                amount,
                "INR",
                created_at_dt.strftime("%Y-%m-%d"),
                created_at_dt.strftime("%H:%M"),
                comment,
                dispute_cat,
                fraud,
                dispute_cat,
                fraud,
                f"Customer disputes {txn_type} transaction due to: {dispute_cat}.",
                priority,
                0.85,
                json.dumps(risk_tags),
                f"Initial intake complete. Identity verification status is {id_verif}. Trust score recalculated to {trust_score}.",
                "Under Investigation" if idx % 2 == 0 else "Dispute Raised",
                True,
                "agent3_complete",
                assigned_queue,
                "analyst_01" if idx % 2 == 0 else None,
                priority_score,
                sla_deadline_dt,
                False,
                priority in ["HIGH", "CRITICAL"],
                summary if priority in ["HIGH", "CRITICAL"] else None,
                json.dumps(trust_intel),
                trust_score,
                risk_score,
                id_verif,
                json.dumps(investigation_plan),
                json.dumps(workflow_plan),
                created_at_dt
            )
        )

        # Seed initial audit log for the case
        cur.execute(
            """
            INSERT INTO audit_logs (case_id, event_type, stage, actor, message, created_at)
            VALUES (%s, %s, %s, %s, %s, %s);
            """,
            (
                case_id,
                "CASE_CREATED",
                "intake",
                "customer_portal",
                "Dispute case created from portal submission",
                created_at_dt
            )
        )
        cur.execute(
            """
            INSERT INTO audit_logs (case_id, event_type, stage, actor, message, created_at)
            VALUES (%s, %s, %s, %s, %s, %s);
            """,
            (
                case_id,
                "ITIA_TRUST_EVALUATION_COMPLETE",
                "identity_trust",
                "ITIA",
                f"Identity trust scoring completed: Identity={id_verif}, Trust={trust_score}",
                created_at_dt + timedelta(seconds=2)
            )
        )

    conn.commit()
    print("10 Dispute Cases Seeded Successfully.")

except Exception as err:
    conn.rollback()
    print(f"Error occurred: {err}")
finally:
    cur.close()
    conn.close()
    print("Database connection closed.")
