"""
Integration tests for the BFSI Dispute Resolution Platform.
Run: pytest tests/test_disputes.py -v
"""
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from api.main import app
from database.database import Base, get_db

# ── Test Database (isolated PostgreSQL schema) ────────────────────────────────

TEST_DATABASE_URL = os.environ["DATABASE_URL"]
engine = create_engine(TEST_DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def setup_db():
    from database import models  # noqa
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


client = TestClient(app)

# ── Sample payload ─────────────────────────────────────────────────────────────

SAMPLE_PAYLOAD = {
    "customer_name": "Test User",
    "customer_id": "TEST-001",
    "email": "test@example.com",
    "phone": "+91-9999999999",
    "transaction_id": "TXN-TEST-001",
    "transaction_type": "UPI",
    "merchant": "Test Merchant",
    "amount": 5000.0,
    "currency": "INR",
    "transaction_date": "2024-03-15",
    "transaction_time": "14:30",
    "customer_comment": "I did not make this transaction. My phone was with me and I never authorized this payment.",
    "dispute_reason": "Unauthorized Transaction",
    "fraud_selected": True,
}


# ── Tests ──────────────────────────────────────────────────────────────────────

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "llm_model" in data


def test_submit_dispute_validation_error():
    """Submission with missing required fields should return 422."""
    import json
    response = client.post("/api/disputes/submit-public", data={"payload": json.dumps({"customer_name": "Bad"})})
    assert response.status_code == 422


def test_list_cases_empty():
    response = client.get("/api/disputes/cases")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["cases"] == []


def test_dashboard_stats_empty():
    response = client.get("/api/disputes/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["total_cases"] == 0
    assert data["open_cases"] == 0


def test_get_nonexistent_case():
    response = client.get("/api/disputes/cases/CASE-FAKE-0000")
    assert response.status_code == 404


def test_submit_dispute_invalid_amount():
    """Negative amount should fail validation."""
    import json
    payload = {**SAMPLE_PAYLOAD, "amount": -100}
    response = client.post("/api/disputes/submit-public", data={"payload": json.dumps(payload)})
    assert response.status_code == 422


def test_submit_dispute_invalid_email():
    import json
    payload = {**SAMPLE_PAYLOAD, "email": "not-an-email"}
    response = client.post("/api/disputes/submit-public", data={"payload": json.dumps(payload)})
    assert response.status_code == 422


def test_schema_output_fields():
    """Verify DisputeSubmissionResponse has all BFSI-required fields."""
    from schemas.dispute_schemas import DisputeCaseResponse
    fields = DisputeCaseResponse.model_fields
    required = ["case_id", "customer_id", "transaction_id", "dispute_category",
                 "fraud_suspicion", "priority", "confidence_score", "risk_tags",
                 "structured_reasoning", "status", "workflow_ready"]
    for field in required:
        assert field in fields, f"Missing field {field} in DisputeCaseResponse"
