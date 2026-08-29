import hmac
import hashlib
import json
import os
from typing import Dict, Any, Tuple, Optional

WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET", "recoverai_test_secret_123")

def verify_webhook_signature(body_bytes: bytes, signature_header: Optional[str]) -> bool:
    """
    Verify Razorpay HMAC-SHA256 signature.
    If using mock secret in test mode without signature header, passes for rapid testing.
    """
    if not signature_header:
        # In mock / dev mode without signature header, allow if secret is mock
        return "test" in WEBHOOK_SECRET.lower() or "mock" in WEBHOOK_SECRET.lower()
    
    try:
        expected_signature = hmac.new(
            key=WEBHOOK_SECRET.encode("utf-8"),
            msg=body_bytes,
            digestmod=hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(expected_signature, signature_header)
    except Exception as e:
        print(f"Signature verification error: {e}")
        return False

def parse_webhook_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract normalized event details from Razorpay webhook JSON.
    """
    event = payload.get("event", "payment.failed")
    payload_data = payload.get("payload", {})
    payment_entity = payload_data.get("payment", {}).get("entity", {})
    subscription_entity = payload_data.get("subscription", {}).get("entity", {})
    
    # Extract details
    payment_id = payment_entity.get("id") or payload.get("payment_id") or f"pay_{os.urandom(4).hex()}"
    subscription_id = (
        payment_entity.get("subscription_id") 
        or subscription_entity.get("id") 
        or payload.get("subscription_id") 
        or f"sub_{os.urandom(4).hex()}"
    )
    customer_id = (
        payment_entity.get("customer_id") 
        or subscription_entity.get("customer_id") 
        or payload.get("customer_id") 
        or f"cust_{os.urandom(4).hex()}"
    )
    
    raw_amount = payment_entity.get("amount") or payload.get("amount") or 299900
    # Convert paise to INR if amount is in paise (e.g. >= 10000 and integer)
    amount_inr = float(raw_amount) / 100.0 if raw_amount > 1000 and isinstance(raw_amount, int) else float(raw_amount)
    
    failure_reason = (
        payment_entity.get("error_description")
        or payment_entity.get("error_reason")
        or payload.get("failure_reason")
        or "Insufficient funds in bank account"
    )
    
    return {
        "event": event,
        "payment_id": payment_id,
        "subscription_id": subscription_id,
        "customer_id": customer_id,
        "amount": amount_inr,
        "failure_reason": failure_reason,
        "customer_email": payment_entity.get("email") or payload.get("email") or f"{customer_id.lower()}@example.com",
        "customer_contact": payment_entity.get("contact") or payload.get("contact")
    }
