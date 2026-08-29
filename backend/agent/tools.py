import random
from typing import Dict, Any, List, Optional
from datetime import datetime
from backend.database import db
from backend.policy.rules import diagnose_failure_category
from backend.ml.predict import predict_recovery_probability

def get_customer_context(customer_id: str) -> Dict[str, Any]:
    cust = db.get_customer(customer_id)
    if not cust:
        # Default mock customer profile
        return {
            "customer_id": customer_id,
            "name": "Standard Customer",
            "email": f"{customer_id.lower()}@example.com",
            "segment": "standard",
            "lifetime_value": 35988.0,
            "successful_payment_count": 12,
            "failed_payment_count": 1,
            "previous_recoveries": 1,
            "subscription_age": 13
        }
    
    payments = db.get_payments_for_customer(customer_id)
    success_count = sum(1 for p in payments if p.get("status") in ["captured", "authorized", "RECOVERED"])
    failed_count = sum(1 for p in payments if p.get("status") == "failed")
    
    return {
        "customer_id": cust["id"],
        "name": cust["name"],
        "email": cust["email"],
        "segment": cust.get("segment", "standard"),
        "lifetime_value": cust.get("lifetime_value", 0.0),
        "successful_payment_count": max(success_count, 1),
        "failed_payment_count": failed_count,
        "subscription_age": 12
    }

def get_payment_history(customer_id: str) -> List[Dict[str, Any]]:
    return db.get_payments_for_customer(customer_id)

def diagnose_failure(raw_reason: Optional[str]) -> str:
    return diagnose_failure_category(raw_reason)

def predict_recovery(features: Dict[str, Any]) -> float:
    return predict_recovery_probability(features)

def schedule_retry(case_id: str, delay_hours: int = 24) -> Dict[str, Any]:
    return {
        "action": "DELAYED_RETRY",
        "scheduled_delay_hours": delay_hours,
        "message": f"Payment retry scheduled after {delay_hours} hours via Razorpay recurring engine.",
        "status": "SCHEDULED"
    }

def send_payment_reminder(case_id: str, customer_id: str, amount: float) -> Dict[str, Any]:
    return {
        "action": "PAYMENT_REMINDER",
        "recipient": customer_id,
        "amount": amount,
        "message": f"Friendly payment notification and reminder email sent to customer {customer_id}.",
        "status": "DELIVERED"
    }

def request_payment_method_update(case_id: str, customer_id: str) -> Dict[str, Any]:
    return {
        "action": "PAYMENT_METHOD_UPDATE",
        "recipient": customer_id,
        "message": f"Secure Razorpay payment method update link dispatched to customer {customer_id}.",
        "status": "DELIVERED"
    }

def check_payment_status(case_id: str, simulated_success_prob: float = 0.85) -> Dict[str, Any]:
    """
    Simulates outcome verification based on predicted recovery probability.
    """
    # Deterministic or calibrated simulated outcome
    recovered = random.random() < simulated_success_prob
    if recovered:
        return {
            "status": "CAPTURED",
            "recovered": True,
            "message": "Payment captured successfully on retry. Revenue recovered."
        }
    else:
        return {
            "status": "FAILED",
            "recovered": False,
            "message": "Payment retry declined by bank."
        }

def record_intervention(case_id: str, intervention_type: str, reason: str, status: str, result: Optional[str] = None) -> int:
    return db.insert_intervention({
        "case_id": case_id,
        "type": intervention_type,
        "reason": reason,
        "status": status,
        "result": result
    })

def escalate_case(case_id: str, reason: str) -> Dict[str, Any]:
    return {
        "action": "ESCALATE",
        "status": "ESCALATED",
        "reason": reason,
        "message": f"Case {case_id} flagged and escalated to human customer success queue."
    }

def close_case(case_id: str, final_status: str) -> Dict[str, Any]:
    return {
        "case_id": case_id,
        "status": final_status,
        "closed_at": datetime.utcnow().isoformat(),
        "message": f"Recovery workflow terminated with status: {final_status}."
    }
