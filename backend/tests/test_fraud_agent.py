import sys
import os
from datetime import datetime, timezone, timedelta

# Add parent directory to sys.path so we can import from backend
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

import unittest
from sqlalchemy.orm import Session
from database.database import SessionLocal, init_db
from database.models import DisputeCase, BankCustomer, Transaction, AuditLog, WorkflowState
from agents.fraud_reasoning_agent import run_fraud_reasoning_agent
from workflows.dispute_workflow import run_dispute_workflow
from services.dispute_service import DisputeService


class TestFraudReasoningAgent(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        # 1. Trigger the database migrations and make sure tables are initialized
        init_db()
        cls.db = SessionLocal()
        
    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def setUp(self):
        # Clean up any residual test data from previous runs
        self._cleanup_test_data()

        # 2. Pre-seed database rows for a mock customer and historical transactions
        # We need:
        # - A test customer: CUST_FRAUD_TEST
        # - A test transaction under dispute: TXN_FRAUD_TEST_CURRENT (large amount, off-hours, location mismatch)
        # - Other transactions in the last 24h (for velocity breach)
        # - A transaction within 4 hours at a different location (for geovelocity breach)
        # - Historical transactions of smaller amount (for spending deviation outlier)
        
        # We define our current time for testing dynamically as the system time to align with DB default created_at
        self.current_time = datetime(2026, 6, 12, 23, 30, 0, tzinfo=timezone.utc)

        self.customer = BankCustomer(
            customer_id="CUST_FRAUD_TEST",
            full_name="Fraud Test Customer",
            email="fraud.test@example.com",
            phone="+91-9999999999",
            joining_date=self.current_time.date() - timedelta(days=100)
        )
        self.db.add(self.customer)
        
        # Current transaction under dispute
        self.current_txn = Transaction(
            transaction_id="TXN_FRAUD_TEST_CURRENT",
            customer_id="CUST_FRAUD_TEST",
            merchant_id="MERCH_001",
            merchant_name="HighEnd Electronics",
            amount=25000.0,  # Spend deviation outlier (> 3x average)
            currency="INR",
            transaction_type="UPI",
            transaction_date=self.current_time,
            status="Success",
            location="Bangalore",
            device_id="DEV_NEW_123",
            is_disputed=True
        )
        self.db.add(self.current_txn)
        
        # Velocity Breach: Seed 3 other transactions in the last 24 hours (total 4 in 24 hours)
        self.db.add(Transaction(
            transaction_id="TXN_VEL_1",
            customer_id="CUST_FRAUD_TEST",
            merchant_name="Coffee Shop",
            amount=150.0,
            transaction_type="UPI",
            transaction_date=self.current_time - timedelta(hours=2),
            status="Success",
            location="Mumbai",
            device_id="DEV_OLD_999"
        ))
        
        # Geovelocity Breach: Seed a transaction at a different location within 4 hours
        # TXN_VEL_2 is 3 hours before current_txn, but location is "Delhi"
        self.db.add(Transaction(
            transaction_id="TXN_VEL_2",
            customer_id="CUST_FRAUD_TEST",
            merchant_name="Delhi Airport",
            amount=2500.0,
            transaction_type="UPI",
            transaction_date=self.current_time - timedelta(hours=3),
            status="Success",
            location="Delhi",  # Different from Mumbai
            device_id="DEV_OLD_999"
        ))
        
        self.db.add(Transaction(
            transaction_id="TXN_VEL_3",
            customer_id="CUST_FRAUD_TEST",
            merchant_name="Grocery Store",
            amount=800.0,
            transaction_type="UPI",
            transaction_date=self.current_time - timedelta(hours=10),
            status="Success",
            location="Mumbai",
            device_id="DEV_OLD_999"
        ))
        
        # Spending deviation: Seed some historical transactions of ~1000 INR
        # Average is around 1000 INR. Current is 25000 INR. Standard deviation is small.
        historical_amounts = [950.0, 1050.0, 980.0, 1020.0, 1000.0]
        for i, amt in enumerate(historical_amounts):
            self.db.add(Transaction(
                transaction_id=f"TXN_HIST_{i}",
                customer_id="CUST_FRAUD_TEST",
                merchant_name="Regular Merchant",
                amount=amt,
                transaction_type="UPI",
                transaction_date=self.current_time - timedelta(days=2 + i),
                status="Success",
                location="Mumbai",
                device_id="DEV_OLD_999"
            ))
            
        self.db.commit()

    def tearDown(self):
        self._cleanup_test_data()

    def _cleanup_test_data(self):
        # Delete case notes, audit logs, workflow states, dispute cases, transactions, and customers
        case_ids = ["CASE_FRAUD_TEST_123"]
        self.db.query(AuditLog).filter(AuditLog.case_id.in_(case_ids)).delete(synchronize_session=False)
        self.db.query(WorkflowState).filter(WorkflowState.case_id.in_(case_ids)).delete(synchronize_session=False)
        self.db.query(DisputeCase).filter(DisputeCase.case_id.in_(case_ids)).delete(synchronize_session=False)
        self.db.query(Transaction).filter(Transaction.customer_id == "CUST_FRAUD_TEST").delete(synchronize_session=False)
        self.db.query(BankCustomer).filter(BankCustomer.customer_id == "CUST_FRAUD_TEST").delete(synchronize_session=False)
        self.db.commit()

    def test_fraud_agent_standalone(self):
        """Test run_fraud_reasoning_agent standalone against database case."""
        # 3. Create a mock dispute case in the DB representing the intake state
        case = DisputeCase(
            case_id="CASE_FRAUD_TEST_123",
            customer_id="CUST_FRAUD_TEST",
            customer_name="Fraud Test Customer",
            email="fraud.test@example.com",
            phone="+91-9999999999",
            transaction_id="TXN_FRAUD_TEST_CURRENT",
            transaction_type="UPI",
            merchant="HighEnd Electronics",
            amount=25000.0,
            currency="INR",
            transaction_date=self.current_time.strftime("%Y-%m-%d"),
            transaction_time="23:30",
            dispute_reason="Unauthorized Transaction",
            fraud_selected=True,
            status="Dispute Raised",
            created_at=self.current_time,
            # Mock trust intelligence with unrecognized device and mismatching location
            trust_intelligence={
                "device_fingerprint": {
                    "recognized_device": False,
                    "location_consistent": False,
                    "device_risk": "HIGH"
                }
            },
            transaction_metadata={
                "transaction_location": "Bangalore"
            }
        )
        self.db.add(case)
        self.db.commit()

        # Run standalone fraud agent
        print("\n--- Running run_fraud_reasoning_agent standalone ---")
        brief = run_fraud_reasoning_agent({}, case_id="CASE_FRAUD_TEST_123")
        
        # 4. Assert response schema and contents
        import json
        print("Agent Output Brief JSON:")
        print(json.dumps(brief, indent=2, ensure_ascii=True))
        self.assertIsNotNone(brief)
        self.assertEqual(brief["case_id"], "CASE_FRAUD_TEST_123")
        self.assertIn("fraud_probability", brief)
        self.assertIn("fraud_risk_level", brief)
        self.assertIn("anomaly_detection", brief)
        self.assertIn("device_location_risk", brief)
        self.assertIn("spending_history_analysis", brief)
        self.assertIn("fraud_reasoning", brief)
        self.assertIn("fraud_summary", brief)
        self.assertIn("user_trust_score", brief)
        self.assertIn("behavioral_risk_score", brief)
        self.assertIn("identity_verification", brief)
        self.assertIn("kyc_checks", brief)
        self.assertIn("device_fingerprint", brief)
        self.assertIn("dispute_behavior", brief)
        self.assertIn("trust_reasoning", brief)
        self.assertIn("trust_summary", brief)

        # 5. Assert that the server-side calibration overrides function correctly.
        # Scoring rules:
        # - Outlier spend (+0.20): average ~1000, current 25000 -> Yes (+0.20)
        # - Off-hours txn (+0.15): 23:30 -> Yes (+0.15)
        # - Velocity breach (+0.30): 4 transactions in 24 hours (limit is >=3) -> Yes (+0.30)
        # - Geovelocity breach (+0.25): Mumbai and Delhi within 3 hours -> Yes (+0.25)
        # - Unrecognized device (+0.30): Mocked as False -> Yes (+0.30)
        # - Location mismatch (+0.20): Mocked as False -> Yes (+0.20)
        # Sum: 0.20 + 0.15 + 0.30 + 0.25 + 0.30 + 0.20 = 1.40 -> Clamped to 1.0.
        # This matches >= 0.75 which is CRITICAL.
        self.assertEqual(brief["fraud_probability"], 1.0)
        self.assertEqual(brief["fraud_risk_level"], "CRITICAL")
        self.assertTrue(brief["anomaly_detection"]["amount_anomaly"])
        self.assertTrue(brief["anomaly_detection"]["time_anomaly"])
        self.assertTrue(brief["anomaly_detection"]["velocity_anomaly"])
        self.assertTrue(brief["device_location_risk"]["unrecognized_device"])
        self.assertTrue(brief["device_location_risk"]["location_mismatch"])
        self.assertEqual(brief["user_trust_score"], 0.50)
        self.assertEqual(brief["behavioral_risk_score"], 0.50)
        self.assertEqual(brief["identity_verification"], "VERIFIED")

    def test_full_workflow_integration(self):
        """Test running the entire run_dispute_workflow and verify DB outputs."""
        dispute_input = {
            "_preset_case_id": "CASE_FRAUD_TEST_123",
            "_document_count": 2,
            "customer_id": "CUST_FRAUD_TEST",
            "customer_name": "Fraud Test Customer",
            "email": "fraud.test@example.com",
            "phone": "+91-9999999999",
            "transaction_id": "TXN_FRAUD_TEST_CURRENT",
            "transaction_type": "UPI",
            "merchant": "HighEnd Electronics",
            "amount": 25000.0,
            "currency": "INR",
            "transaction_date": self.current_time.strftime("%Y-%m-%d"),
            "transaction_time": "23:30",
            "customer_comment": "I did not make this transaction. It is not my signature or authorization.",
            "dispute_reason": "Unauthorized Transaction",
            "fraud_selected": True,
            "transaction_metadata": {
                "transaction_location": "Bangalore"
            }
        }

        # Submit the dispute through the DisputeService (simulating intake -> workflow -> database save)
        print("\n--- Submitting dispute via DisputeService.submit_dispute ---")
        res = DisputeService.submit_dispute(
            dispute_input, 
            self.db, 
            document_texts=["[BankStatement.pdf]\nSome statement text", "[FIR.pdf]\nSome FIR file"]
        )
        self.assertTrue(res["success"])
        
        # Refresh the case from DB and verify all fields are saved correctly
        case = self.db.query(DisputeCase).filter(DisputeCase.case_id == "CASE_FRAUD_TEST_123").first()
        self.assertIsNotNone(case)
        
        print("\n--- DB UPDATES AFTER FULL PIPELINE ---")
        print(f"Status: {case.status}")
        print(f"Dispute Category: {case.dispute_category}")
        print(f"Priority: {case.priority}")
        print(f"Confidence Score: {case.confidence_score}")
        print(f"User Trust Score: {case.user_trust_score}")
        print(f"Behavioral Risk Score: {case.behavioral_risk_score}")
        print(f"Identity Status: {case.identity_status}")
        print(f"Fraud Probability: {case.fraud_probability}")
        print(f"Fraud Risk Level: {case.fraud_risk_level}")
        print(f"Orchestration workflow plan next: {case.workflow_plan.get('next_agent') if case.workflow_plan else None}")
        
        # Verify the database has the fields populated
        self.assertIn(case.identity_status, ["VERIFIED", "SUSPICIOUS", "FAILED"])
        self.assertEqual(case.fraud_risk_level, "CRITICAL")
        self.assertEqual(case.fraud_probability, 1.0)
        self.assertIsNotNone(case.fraud_reasoning_brief)
        self.assertIsNotNone(case.trust_intelligence)
        self.assertIsNotNone(case.investigation_plan)
        self.assertIsNotNone(case.workflow_plan)


if __name__ == "__main__":
    unittest.main()
