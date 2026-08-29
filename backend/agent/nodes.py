import os
import json
from typing import Dict, Any
from datetime import datetime
from backend.agent.state import AgentState
from backend.agent import tools
from backend.policy.rules import PolicyEngine, get_recommended_action_heuristic
from backend.services import audit

def observe_node(state: AgentState) -> Dict[str, Any]:
    customer_id = state["customer_id"]
    ctx = tools.get_customer_context(customer_id)
    
    event = {
        "case_id": state["case_id"],
        "event": "CUSTOMER_CONTEXT_RETRIEVED",
        "decision": f"Retrieved profile for customer {customer_id}",
        "reason": f"LTV: INR {ctx.get('lifetime_value', 0):,.2f}, Successes: {ctx.get('successful_payment_count', 0)}, Failures: {ctx.get('failed_payment_count', 0)}"
    }
    audit.log_case_event(event)
    
    return {
        "customer_context": ctx,
        "audit_events": state.get("audit_events", []) + [event]
    }

def diagnose_node(state: AgentState) -> Dict[str, Any]:
    raw_reason = state.get("raw_failure_reason")
    category = tools.diagnose_failure(raw_reason)
    
    event = {
        "case_id": state["case_id"],
        "event": "FAILURE_DIAGNOSED",
        "decision": category,
        "reason": f"Analyzed raw gateway failure reason: '{raw_reason}' -> Classified as {category}"
    }
    audit.log_case_event(event)
    
    return {
        "failure_category": category,
        "audit_events": state.get("audit_events", []) + [event]
    }

def predict_node(state: AgentState) -> Dict[str, Any]:
    ctx = state.get("customer_context") or {}
    features = {
        "amount": state["amount_at_risk"],
        "failure_reason": state.get("failure_category", "INSUFFICIENT_FUNDS"),
        "attempt_number": state.get("attempt_count", 0) + 1,
        "successful_payment_count": ctx.get("successful_payment_count", 10),
        "failed_payment_count": ctx.get("failed_payment_count", 1),
        "customer_ltv": ctx.get("lifetime_value", 35988.0),
        "subscription_age": ctx.get("subscription_age", 12),
        "payment_method": "card",
        "days_since_last_success": 30,
        "previous_recovery_rate": 0.90
    }
    
    prob = tools.predict_recovery(features)
    
    event = {
        "case_id": state["case_id"],
        "event": "RECOVERY_PROBABILITY_PREDICTED",
        "decision": f"{prob * 100:.1f}%",
        "reason": f"ML Model scored recovery likelihood at {prob:.4f} based on customer history and failure category {state.get('failure_category')}"
    }
    audit.log_case_event(event)
    
    return {
        "recovery_probability": prob,
        "audit_events": state.get("audit_events", []) + [event]
    }

def reason_node(state: AgentState) -> Dict[str, Any]:
    category = state.get("failure_category", "UNKNOWN")
    prob = state.get("recovery_probability", 0.5)
    attempts = state.get("attempt_count", 0)
    contacts = state.get("contact_count", 0)
    ctx = state.get("customer_context") or {}
    ltv = ctx.get("lifetime_value", 0.0)
    
    # Try LLM if configured
    openai_key = os.getenv("OPENAI_API_KEY")
    recommended = None
    reasoning = None
    
    if openai_key and len(openai_key.strip()) > 5:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=openai_key)
            prompt = f"""You are RecoverAI, an expert subscription revenue recovery agent.
Analyze this payment failure and choose the best single action from: [DELAYED_RETRY, PAYMENT_METHOD_UPDATE, PAYMENT_REMINDER, ESCALATE, STOP].

Customer Context:
- LTV: INR {ltv}
- Successful Payments: {ctx.get('successful_payment_count')}
- Failed Payments: {ctx.get('failed_payment_count')}
- Failure Category: {category}
- Recovery Probability: {prob:.2f}
- Attempt Count: {attempts}
- Contact Count: {contacts}

Respond in strict JSON format:
{{"action": "ACTION_NAME", "reasoning": "brief explanation"}}
"""
            response = client.chat.completions.create(
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                response_format={"type": "json_object"}
            )
            parsed = json.loads(response.choices[0].message.content)
            recommended = parsed.get("action")
            reasoning = parsed.get("reasoning")
        except Exception as e:
            print(f"LLM call fallback due to: {e}")
            recommended = None

    if not recommended:
        recommended = get_recommended_action_heuristic(category, attempts, contacts, prob, ltv)
        if recommended == "DELAYED_RETRY":
            reasoning = f"Customer has strong payment history and {category} is typically temporary. A delayed retry has high recovery probability ({prob*100:.1f}%)."
        elif recommended == "PAYMENT_METHOD_UPDATE":
            reasoning = f"Failure {category} indicates credentials/mandate issue. Prompting customer with secure update link."
        elif recommended == "PAYMENT_REMINDER":
            reasoning = f"Sending friendly notification to alert customer before initiating next automatic retry."
        elif recommended == "ESCALATE":
            reasoning = f"Recovery probability is {prob*100:.1f}% or attempt threshold reached. Escalating to human customer success."
        else:
            reasoning = f"Terminating automated attempts to avoid customer fatigue or policy breach."

    event = {
        "case_id": state["case_id"],
        "event": "INTERVENTION_SELECTED",
        "decision": recommended,
        "reason": reasoning
    }
    audit.log_case_event(event)

    return {
        "recommended_action": recommended,
        "reasoning": reasoning,
        "audit_events": state.get("audit_events", []) + [event]
    }

def policy_validation_node(state: AgentState) -> Dict[str, Any]:
    case_dict = {
        "id": state["case_id"],
        "amount_at_risk": state["amount_at_risk"],
        "recovery_probability": state.get("recovery_probability", 0.5),
        "attempt_count": state.get("attempt_count", 0),
        "contact_count": state.get("contact_count", 0),
        "status": state.get("final_status", "OPEN")
    }
    ctx = state.get("customer_context")
    decision = PolicyEngine.evaluate(case_dict, state["recommended_action"], ctx)
    
    event = {
        "case_id": state["case_id"],
        "event": "POLICY_EVALUATION",
        "decision": "APPROVED" if decision.approved else f"BLOCKED -> {decision.action}",
        "reason": decision.reason
    }
    audit.log_case_event(event)
    
    return {
        "policy_approved": decision.approved,
        "policy_reason": decision.reason,
        "recommended_action": decision.action,
        "audit_events": state.get("audit_events", []) + [event]
    }

def execute_node(state: AgentState) -> Dict[str, Any]:
    action = state["recommended_action"]
    case_id = state["case_id"]
    customer_id = state["customer_id"]
    amount = state["amount_at_risk"]
    
    exec_result = None
    new_attempts = state.get("attempt_count", 0)
    new_contacts = state.get("contact_count", 0)
    
    if action == "DELAYED_RETRY":
        new_attempts += 1
        res = tools.schedule_retry(case_id, 24)
        exec_result = res["message"]
        tools.record_intervention(case_id, action, state.get("reasoning", "Retry"), "EXECUTED", exec_result)
    elif action == "PAYMENT_METHOD_UPDATE":
        new_contacts += 1
        res = tools.request_payment_method_update(case_id, customer_id)
        exec_result = res["message"]
        tools.record_intervention(case_id, action, state.get("reasoning", "Update link"), "EXECUTED", exec_result)
    elif action == "PAYMENT_REMINDER":
        new_contacts += 1
        res = tools.send_payment_reminder(case_id, customer_id, amount)
        exec_result = res["message"]
        tools.record_intervention(case_id, action, state.get("reasoning", "Reminder"), "EXECUTED", exec_result)
    elif action == "ESCALATE":
        res = tools.escalate_case(case_id, state.get("reasoning", "Escalation requested"))
        exec_result = res["message"]
        tools.record_intervention(case_id, action, state.get("reasoning", "Escalation"), "EXECUTED", exec_result)
    else:  # STOP
        res = tools.close_case(case_id, "STOPPED")
        exec_result = res["message"]
        tools.record_intervention(case_id, action, state.get("reasoning", "Stopping"), "EXECUTED", exec_result)
        
    event = {
        "case_id": case_id,
        "event": "ACTION_EXECUTED",
        "decision": action,
        "reason": exec_result
    }
    audit.log_case_event(event)
    
    return {
        "attempt_count": new_attempts,
        "contact_count": new_contacts,
        "execution_result": exec_result,
        "audit_events": state.get("audit_events", []) + [event]
    }

def verify_node(state: AgentState) -> Dict[str, Any]:
    action = state["recommended_action"]
    case_id = state["case_id"]
    prob = state.get("recovery_probability", 0.5)
    
    if action == "ESCALATE":
        final_status = "ESCALATED"
        event_decision = "ESCALATED TO HUMAN"
        event_reason = "Case transferred to customer operations team."
    elif action == "STOP":
        final_status = "STOPPED"
        event_decision = "CASE TERMINATED"
        event_reason = "Recovery stopped per policy limits."
    else:
        outcome = tools.check_payment_status(case_id, simulated_success_prob=min(prob + 0.05, 0.95))
        if outcome["recovered"]:
            final_status = "RECOVERED"
            event_decision = f"INR {state['amount_at_risk']:,.2f} RECOVERED"
            event_reason = outcome["message"]
        else:
            final_status = "IN_PROGRESS" if state.get("attempt_count", 0) < 3 else "ESCALATED"
            event_decision = "RETRY FAILED"
            event_reason = outcome["message"]
            
    event = {
        "case_id": case_id,
        "event": "OUTCOME_VERIFIED",
        "decision": event_decision,
        "reason": event_reason
    }
    audit.log_case_event(event)
    
    # Update SQLite state
    tools.db.insert_or_update_case({
        "id": case_id,
        "customer_id": state["customer_id"],
        "subscription_id": state["subscription_id"],
        "payment_id": state["payment_id"],
        "amount_at_risk": state["amount_at_risk"],
        "recovery_probability": prob,
        "status": final_status,
        "failure_reason": state.get("failure_category"),
        "attempt_count": state.get("attempt_count", 0),
        "contact_count": state.get("contact_count", 0),
        "recommended_action": action,
        "policy_result": state.get("policy_reason"),
        "closed_at": datetime.utcnow().isoformat() if final_status in ["RECOVERED", "STOPPED", "ESCALATED"] else None
    })
    
    return {
        "final_status": final_status,
        "audit_events": state.get("audit_events", []) + [event]
    }
