import hmac
import hashlib
import json
import pytest
from backend.razorpay.webhook import verify_webhook_signature, parse_webhook_payload, WEBHOOK_SECRET

def test_webhook_signature_verification():
    body = b'{"event":"payment.failed"}'
    signature = hmac.new(
        key=WEBHOOK_SECRET.encode("utf-8"),
        msg=body,
        digestmod=hashlib.sha256
    ).hexdigest()
    
    assert verify_webhook_signature(body, signature) is True
    assert verify_webhook_signature(body, "invalid_sig_123") is False

def test_parse_webhook_payload():
    payload = {
        "event": "payment.failed",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_test123",
                    "amount": 299900,
                    "customer_id": "cust_test123",
                    "error_description": "Insufficient funds in bank account"
                }
            },
            "subscription": {
                "entity": {
                    "id": "sub_test123"
                }
            }
        }
    }
    
    parsed = parse_webhook_payload(payload)
    assert parsed["payment_id"] == "pay_test123"
    assert parsed["subscription_id"] == "sub_test123"
    assert parsed["amount"] == 2999.0
    assert "Insufficient" in parsed["failure_reason"]
