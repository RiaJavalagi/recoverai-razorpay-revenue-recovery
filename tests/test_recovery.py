import pytest
from backend.database import db
from backend.services.recovery import handle_payment_failure_event, run_batch_simulation

@pytest.fixture(autouse=True)
def setup_database():
    db.init_db()

def test_handle_insufficient_funds_recovery():
    event = {
        "customer_id": "CUST_TEST_001",
        "customer_name": "Test User",
        "customer_email": "test@example.com",
        "subscription_id": "sub_test_001",
        "payment_id": "pay_test_001",
        "amount": 2999.0,
        "failure_reason": "Insufficient funds in bank account"
    }
    result = handle_payment_failure_event(event)
    assert result["case_id"].startswith("RC-")
    assert result["amount_at_risk"] == 2999.0
    assert result["final_status"] in ["RECOVERED", "IN_PROGRESS", "ESCALATED"]
    assert len(result["timeline"]) >= 5

def test_handle_expired_card_recovery():
    event = {
        "customer_id": "CUST_TEST_002",
        "subscription_id": "sub_test_002",
        "payment_id": "pay_test_002",
        "amount": 4999.0,
        "failure_reason": "Card expired on file"
    }
    result = handle_payment_failure_event(event)
    assert result["case_id"].startswith("RC-")
    assert result["recommended_action"] in ["PAYMENT_METHOD_UPDATE", "ESCALATE"]

def test_batch_simulation():
    sim = run_batch_simulation(100)
    assert sim["cases_processed"] == 100
    assert sim["revenue_at_risk"] > 0
    assert "strategies" in sim
    assert sim["strategies"]["recoverai_agent"]["revenue_recovered"] >= 0
