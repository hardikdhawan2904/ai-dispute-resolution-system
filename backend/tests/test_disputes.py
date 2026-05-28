"""
Integration tests for the BFSI Dispute Resolution Platform.
Run: pytest tests/test_disputes.py -v
"""
import json
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.main import app
from database.database import Base, get_db

# ── Test Database (in-memory SQLite) ──────────────────────────────────────────

TEST_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
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
    response = client.post("/api/disputes/submit", json={"customer_name": "Bad"})
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


def test_synthetic_data_structure():
    """Validate that all synthetic test cases have required fields."""
    data_path = Path(__file__).parent.parent / "synthetic_data" / "sample_disputes.json"
    cases = json.loads(data_path.read_text())
    required_fields = {"customer_name", "customer_id", "email", "phone", "transaction_id",
                       "transaction_type", "merchant", "amount", "currency",
                       "customer_comment", "dispute_reason", "fraud_selected"}
    for case in cases:
        for field in required_fields:
            assert field in case["input"], f"Missing {field} in case: {case['label']}"


def test_submit_dispute_invalid_amount():
    """Negative amount should fail validation."""
    payload = {**SAMPLE_PAYLOAD, "amount": -100}
    response = client.post("/api/disputes/submit", json=payload)
    assert response.status_code == 422


def test_submit_dispute_invalid_email():
    payload = {**SAMPLE_PAYLOAD, "email": "not-an-email"}
    response = client.post("/api/disputes/submit", json=payload)
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
