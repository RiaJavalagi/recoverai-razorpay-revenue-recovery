from typing import Dict, Any, Optional
from pydantic import BaseModel

# Failure Categories
INSUFFICIENT_FUNDS = "INSUFFICIENT_FUNDS"
EXPIRED_CARD = "EXPIRED_CARD"
BANK_DECLINE = "BANK_DECLINE"
GATEWAY_ERROR = "GATEWAY_ERROR"
MANDATE_FAILURE = "MANDATE_FAILURE"
UNKNOWN = "UNKNOWN"

# Intervention Types
DELAYED_RETRY = "DELAYED_RETRY"
PAYMENT_METHOD_UPDATE = "PAYMENT_METHOD_UPDATE"
PAYMENT_REMINDER = "PAYMENT_REMINDER"
ESCALATE = "ESCALATE"
STOP = "STOP"

# Policy Thresholds & Limits
MAX_RETRIES = 3
MAX_CUSTOMER_CONTACTS = 2
MIN_RETRY_INTERVAL_HOURS = 12
LOW_PROBABILITY_THRESHOLD = 0.20
HIGH_VALUE_THRESHOLD = 25000.0

class PolicyDecision(BaseModel):
    approved: bool
    reason: str
    action: str
    requires_escalation: bool = False
    requires_stop: bool = False

def diagnose_failure_category(raw_reason: Optional[str]) -> str:
    if not raw_reason:
        return UNKNOWN
    
    text = raw_reason.upper()
    if any(k in text for k in ["INSUFFICIENT", "BALANCE", "FUNDS", "LOW_BALANCE"]):
        return INSUFFICIENT_FUNDS
    elif any(k in text for k in ["EXPIRED", "CARD_EXPIRED", "EXPIRY"]):
        return EXPIRED_CARD
    elif any(k in text for k in ["DECLINE", "BANK_DECLINE", "ISSUER", "DO_NOT_HONOR"]):
        return BANK_DECLINE
    elif any(k in text for k in ["GATEWAY", "TIMEOUT", "NETWORK", "SYSTEM_ERROR", "TEMPORARY"]):
        return GATEWAY_ERROR
    elif any(k in text for k in ["MANDATE", "RECURRING_AUTH", "PRE_AUTH", "SI_FAILED"]):
        return MANDATE_FAILURE
    else:
        return UNKNOWN

def get_recommended_action_heuristic(
    failure_category: str, 
    attempt_count: int, 
    contact_count: int, 
    recovery_prob: float, 
    customer_ltv: float = 0.0
) -> str:
    # Check stopping / escalation bounds first
    if recovery_prob < LOW_PROBABILITY_THRESHOLD:
        return ESCALATE
    if attempt_count >= MAX_RETRIES:
        return ESCALATE if customer_ltv >= HIGH_VALUE_THRESHOLD else STOP
        
    if failure_category == INSUFFICIENT_FUNDS:
        return DELAYED_RETRY if attempt_count < 2 else PAYMENT_REMINDER
    elif failure_category == EXPIRED_CARD:
        return PAYMENT_METHOD_UPDATE if contact_count < MAX_CUSTOMER_CONTACTS else ESCALATE
    elif failure_category == BANK_DECLINE:
        return PAYMENT_REMINDER if contact_count < MAX_CUSTOMER_CONTACTS else DELAYED_RETRY
    elif failure_category == GATEWAY_ERROR:
        return DELAYED_RETRY
    elif failure_category == MANDATE_FAILURE:
        return PAYMENT_METHOD_UPDATE if contact_count < MAX_CUSTOMER_CONTACTS else ESCALATE
    else:
        return ESCALATE if recovery_prob < 0.40 else DELAYED_RETRY

class PolicyEngine:
    @staticmethod
    def evaluate(
        case: Dict[str, Any], 
        proposed_action: str, 
        customer: Optional[Dict[str, Any]] = None
    ) -> PolicyDecision:
        status = case.get("status", "OPEN")
        attempt_count = case.get("attempt_count", 0)
        contact_count = case.get("contact_count", 0)
        recovery_prob = case.get("recovery_probability") or 0.50
        amount_at_risk = case.get("amount_at_risk", 0.0)
        ltv = customer.get("lifetime_value", 0.0) if customer else 0.0

        # Rule 1: Immediate Stop if case already recovered
        if status == "RECOVERED":
            return PolicyDecision(
                approved=False,
                reason="Case is already marked as RECOVERED. Automated interventions terminated.",
                action=STOP,
                requires_stop=True
            )

        # Rule 2: Customer opted out check
        if customer and customer.get("segment") == "opted_out":
            return PolicyDecision(
                approved=False,
                reason="Customer has opted out of automated communications.",
                action=STOP,
                requires_stop=True
            )

        # Rule 3: Very low recovery probability
        if recovery_prob < LOW_PROBABILITY_THRESHOLD and proposed_action not in [ESCALATE, STOP]:
            return PolicyDecision(
                approved=False,
                reason=f"Recovery probability ({recovery_prob:.2f}) is below safe autonomous threshold ({LOW_PROBABILITY_THRESHOLD}). Auto-escalating to human support.",
                action=ESCALATE,
                requires_escalation=True
            )

        # Rule 4: Action is ESCALATE
        if proposed_action == ESCALATE:
            return PolicyDecision(
                approved=True,
                reason="Human escalation requested and approved within safety guidelines.",
                action=ESCALATE,
                requires_escalation=True
            )

        # Rule 5: Action is STOP
        if proposed_action == STOP:
            return PolicyDecision(
                approved=True,
                reason="Recovery termination requested and approved.",
                action=STOP,
                requires_stop=True
            )

        # Rule 6: Max Retry limits
        if proposed_action == DELAYED_RETRY:
            if attempt_count >= MAX_RETRIES:
                if ltv >= HIGH_VALUE_THRESHOLD or amount_at_risk > 10000:
                    return PolicyDecision(
                        approved=False,
                        reason=f"Maximum retries ({MAX_RETRIES}) reached for high-value account. Escalating to human agent.",
                        action=ESCALATE,
                        requires_escalation=True
                    )
                return PolicyDecision(
                    approved=False,
                    reason=f"Maximum retries ({MAX_RETRIES}) reached. Halting automated retry workflow.",
                    action=STOP,
                    requires_stop=True
                )
            return PolicyDecision(
                approved=True,
                reason=f"Retry attempt {attempt_count + 1} of {MAX_RETRIES} is within permitted policy limits.",
                action=DELAYED_RETRY
            )

        # Rule 7: Max Customer Contact limits
        if proposed_action in [PAYMENT_METHOD_UPDATE, PAYMENT_REMINDER]:
            if contact_count >= MAX_CUSTOMER_CONTACTS:
                return PolicyDecision(
                    approved=False,
                    reason=f"Maximum customer contacts ({MAX_CUSTOMER_CONTACTS}) exceeded to prevent spam/fatigue. Escalating to human support.",
                    action=ESCALATE,
                    requires_escalation=True
                )
            return PolicyDecision(
                approved=True,
                reason=f"Communication attempt {contact_count + 1} of {MAX_CUSTOMER_CONTACTS} is compliant with customer contact policy.",
                action=proposed_action
            )

        # Default fallback
        return PolicyDecision(
            approved=True,
            reason="Action passed default policy evaluation.",
            action=proposed_action
        )
