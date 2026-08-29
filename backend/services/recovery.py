import os
import uuid
import random
import numpy as np
from datetime import datetime
from typing import Dict, Any, List, Optional
from backend.database import db
from backend.agent.graph import recovery_agent
from backend.services import audit
from backend.policy.rules import (
    diagnose_failure_category, 
    PolicyEngine,
    INSUFFICIENT_FUNDS, 
    EXPIRED_CARD, 
    BANK_DECLINE, 
    GATEWAY_ERROR, 
    MANDATE_FAILURE, 
    UNKNOWN,
    DELAYED_RETRY,
    PAYMENT_METHOD_UPDATE,
    PAYMENT_REMINDER,
    ESCALATE,
    STOP
)
from backend.ml.predict import predict_recovery_probability

def handle_payment_failure_event(event_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Core ingestion pipeline: Webhook/Event -> DB Registration -> Recovery Case -> Agent Execution.
    """
    customer_id = event_data["customer_id"]
    subscription_id = event_data["subscription_id"]
    payment_id = event_data["payment_id"]
    amount = float(event_data["amount"])
    raw_reason = event_data.get("failure_reason", "Payment failed")
    
    # 1. Upsert Customer
    existing_cust = db.get_customer(customer_id)
    if not existing_cust:
        db.insert_customer({
            "id": customer_id,
            "name": event_data.get("customer_name") or f"Customer {customer_id[-4:]}",
            "email": event_data.get("customer_email") or f"{customer_id.lower()}@example.com",
            "phone": event_data.get("customer_contact"),
            "segment": "standard",
            "lifetime_value": amount * 12.0
        })
        
    # 2. Upsert Subscription
    db.insert_subscription({
        "id": subscription_id,
        "customer_id": customer_id,
        "razorpay_subscription_id": f"sub_rzp_{subscription_id[-6:]}",
        "plan_id": "plan_monthly_pro",
        "amount": amount,
        "status": "active"
    })
    
    # 3. Insert Failed Payment
    db.insert_payment({
        "id": payment_id,
        "customer_id": customer_id,
        "subscription_id": subscription_id,
        "razorpay_payment_id": f"pay_rzp_{payment_id[-6:]}",
        "amount": amount,
        "status": "failed",
        "failure_reason": raw_reason,
        "attempt_number": 1
    })
    
    # 4. Create Recovery Case
    case_id = f"RC-{uuid.uuid4().hex[:8].upper()}"
    db.insert_or_update_case({
        "id": case_id,
        "customer_id": customer_id,
        "subscription_id": subscription_id,
        "payment_id": payment_id,
        "amount_at_risk": amount,
        "status": "OPEN",
        "failure_reason": raw_reason,
        "attempt_count": 0,
        "contact_count": 0
    })
    
    # Log initial failure event
    audit.log_case_event({
        "case_id": case_id,
        "event": "PAYMENT_FAILED",
        "decision": f"Revenue At Risk: INR {amount:,.2f}",
        "reason": f"Payment {payment_id} failed: {raw_reason}"
    })
    
    # 5. Trigger Agentic Recovery Workflow
    initial_state = {
        "case_id": case_id,
        "customer_id": customer_id,
        "subscription_id": subscription_id,
        "payment_id": payment_id,
        "amount_at_risk": amount,
        "raw_failure_reason": raw_reason,
        "attempt_count": 0,
        "contact_count": 0,
        "previous_interventions": [],
        "audit_events": []
    }
    
    final_state = recovery_agent.invoke(initial_state)
    case_details = db.get_case(case_id)
    case_timeline = audit.get_case_audit_trail(case_id)
    interventions = db.get_interventions_for_case(case_id)
    
    return {
        "case_id": case_id,
        "customer_id": customer_id,
        "amount_at_risk": amount,
        "final_status": final_state.get("final_status"),
        "recommended_action": final_state.get("recommended_action"),
        "recovery_probability": final_state.get("recovery_probability"),
        "execution_result": final_state.get("execution_result"),
        "case": case_details,
        "timeline": case_timeline,
        "interventions": interventions
    }

def run_batch_simulation(num_cases: int = 1000) -> Dict[str, Any]:
    """
    Runs full batch simulation comparing 3 strategies:
    1. Baseline 1: No Recovery
    2. Baseline 2: Fixed Retry Strategy
    3. RecoverAI Intelligent Agent
    """
    np.random.seed(101)
    
    tier_choices = [499, 999, 1999, 2999, 4999, 9999, 24999]
    tier_probs = [0.25, 0.30, 0.20, 0.12, 0.08, 0.04, 0.01]
    
    reasons = [INSUFFICIENT_FUNDS, EXPIRED_CARD, BANK_DECLINE, GATEWAY_ERROR, MANDATE_FAILURE, UNKNOWN]
    reason_probs = [0.42, 0.18, 0.15, 0.12, 0.08, 0.05]
    
    simulated_cases = []
    
    # Generate batch
    for i in range(num_cases):
        amount = float(np.random.choice(tier_choices, p=tier_probs))
        reason = str(np.random.choice(reasons, p=reason_probs))
        ltv = amount * np.random.randint(6, 36)
        success_hist = np.random.randint(4, 24)
        fail_hist = np.random.randint(0, 3)
        
        simulated_cases.append({
            "id": f"SIM-{i+1:04d}",
            "amount": amount,
            "failure_reason": reason,
            "ltv": ltv,
            "success_hist": success_hist,
            "fail_hist": fail_hist
        })
        
    total_risk = sum(c["amount"] for c in simulated_cases)
    
    # Strategy 1: No Recovery
    s1_recovered = 0.0
    s1_count = 0
    
    # Strategy 2: Fixed Retry (blind retry on all failures without diagnosis/policy)
    s2_recovered = 0.0
    s2_count = 0
    s2_interventions = num_cases
    for c in simulated_cases:
        # Fixed retry only succeeds well for temporary balance/gateway (e.g. 50% chance), fails for expired/mandate
        if c["failure_reason"] in [INSUFFICIENT_FUNDS, GATEWAY_ERROR]:
            if random.random() < 0.52:
                s2_recovered += c["amount"]
                s2_count += 1
        elif c["failure_reason"] == BANK_DECLINE:
            if random.random() < 0.20:
                s2_recovered += c["amount"]
                s2_count += 1
        # Expired card & Mandate failure 0% success on blind retry
        
    # Strategy 3: RecoverAI Agent (ML + Diagnosis + Policy + Tailored Actions)
    s3_recovered = 0.0
    s3_count = 0
    s3_escalated = 0
    s3_stopped = 0
    s3_interventions = 0
    
    for c in simulated_cases:
        prob = predict_recovery_probability({
            "amount": c["amount"],
            "failure_reason": c["failure_reason"],
            "attempt_number": 1,
            "successful_payment_count": c["success_hist"],
            "failed_payment_count": c["fail_hist"],
            "customer_ltv": c["ltv"]
        })
        
        # Policy & Intervention
        if prob < 0.20:
            s3_escalated += 1
            continue
            
        if c["failure_reason"] == EXPIRED_CARD:
            # Payment method update notification (high conversion 65%)
            s3_interventions += 1
            if random.random() < 0.65:
                s3_recovered += c["amount"]
                s3_count += 1
            else:
                s3_escalated += 1
        elif c["failure_reason"] == MANDATE_FAILURE:
            s3_interventions += 1
            if random.random() < 0.55:
                s3_recovered += c["amount"]
                s3_count += 1
            else:
                s3_escalated += 1
        elif c["failure_reason"] == INSUFFICIENT_FUNDS:
            s3_interventions += 1
            if random.random() < (prob * 0.95):
                s3_recovered += c["amount"]
                s3_count += 1
            else:
                s3_interventions += 1  # 2nd attempt
                if random.random() < 0.40:
                    s3_recovered += c["amount"]
                    s3_count += 1
                else:
                    s3_stopped += 1
        elif c["failure_reason"] == GATEWAY_ERROR:
            s3_interventions += 1
            if random.random() < 0.88:
                s3_recovered += c["amount"]
                s3_count += 1
            else:
                s3_escalated += 1
        elif c["failure_reason"] == BANK_DECLINE:
            s3_interventions += 1
            if random.random() < 0.48:
                s3_recovered += c["amount"]
                s3_count += 1
            else:
                s3_escalated += 1
        else:
            s3_escalated += 1

    return {
        "cases_processed": num_cases,
        "revenue_at_risk": round(total_risk, 2),
        "strategies": {
            "no_recovery": {
                "name": "Baseline 1: No Recovery",
                "revenue_recovered": round(s1_recovered, 2),
                "recovery_rate": 0.0,
                "successful_recoveries": 0,
                "interventions": 0
            },
            "fixed_rule": {
                "name": "Baseline 2: Fixed Rule Retry",
                "revenue_recovered": round(s2_recovered, 2),
                "recovery_rate": round((s2_recovered / total_risk) * 100.0, 2),
                "successful_recoveries": s2_count,
                "interventions": s2_interventions
            },
            "recoverai_agent": {
                "name": "RecoverAI Agent (ML + Policy + Personalized)",
                "revenue_recovered": round(s3_recovered, 2),
                "recovery_rate": round((s3_recovered / total_risk) * 100.0, 2),
                "successful_recoveries": s3_count,
                "interventions": s3_interventions,
                "escalated": s3_escalated,
                "policy_stopped": s3_stopped
            }
        },
        "uplift_vs_fixed_rule": round(((s3_recovered - s2_recovered) / s2_recovered) * 100.0, 2) if s2_recovered > 0 else 0.0
    }
