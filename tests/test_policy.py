import pytest
from backend.policy.rules import (
    PolicyEngine,
    diagnose_failure_category,
    INSUFFICIENT_FUNDS,
    EXPIRED_CARD,
    BANK_DECLINE,
    GATEWAY_ERROR,
    MANDATE_FAILURE,
    DELAYED_RETRY,
    PAYMENT_METHOD_UPDATE,
    PAYMENT_REMINDER,
    ESCALATE,
    STOP,
    MAX_RETRIES,
    MAX_CUSTOMER_CONTACTS
)

def test_diagnose_failure_categories():
    assert diagnose_failure_category("Insufficient balance in card") == INSUFFICIENT_FUNDS
    assert diagnose_failure_category("Card has expired") == EXPIRED_CARD
    assert diagnose_failure_category("Payment declined by issuing bank") == BANK_DECLINE
    assert diagnose_failure_category("Gateway timeout error") == GATEWAY_ERROR
    assert diagnose_failure_category("Recurring mandate failed") == MANDATE_FAILURE
    assert diagnose_failure_category("random error string 123") != INSUFFICIENT_FUNDS

def test_policy_already_recovered():
    case = {"status": "RECOVERED", "attempt_count": 0, "contact_count": 0}
    decision = PolicyEngine.evaluate(case, DELAYED_RETRY)
    assert decision.approved is False
    assert decision.requires_stop is True
    assert decision.action == STOP

def test_policy_opted_out_customer():
    case = {"status": "OPEN", "attempt_count": 0, "contact_count": 0}
    customer = {"segment": "opted_out"}
    decision = PolicyEngine.evaluate(case, DELAYED_RETRY, customer)
    assert decision.approved is False
    assert decision.requires_stop is True

def test_policy_low_probability_escalation():
    case = {"status": "OPEN", "recovery_probability": 0.15, "attempt_count": 0}
    decision = PolicyEngine.evaluate(case, DELAYED_RETRY)
    assert decision.approved is False
    assert decision.requires_escalation is True
    assert decision.action == ESCALATE

def test_policy_max_retries_exceeded():
    case = {"status": "OPEN", "attempt_count": MAX_RETRIES, "recovery_probability": 0.8}
    decision = PolicyEngine.evaluate(case, DELAYED_RETRY)
    assert decision.approved is False
    assert decision.requires_stop is True or decision.requires_escalation is True

def test_policy_max_contacts_exceeded():
    case = {"status": "OPEN", "contact_count": MAX_CUSTOMER_CONTACTS, "recovery_probability": 0.8}
    decision = PolicyEngine.evaluate(case, PAYMENT_METHOD_UPDATE)
    assert decision.approved is False
    assert decision.requires_escalation is True
    assert decision.action == ESCALATE
