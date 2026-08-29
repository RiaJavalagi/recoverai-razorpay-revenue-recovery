from typing import TypedDict, Optional, List, Dict, Any

class AgentState(TypedDict):
    case_id: str
    customer_id: str
    subscription_id: str
    payment_id: str
    amount_at_risk: float
    raw_failure_reason: Optional[str]
    failure_category: Optional[str]
    customer_context: Optional[Dict[str, Any]]
    recovery_probability: Optional[float]
    attempt_count: int
    contact_count: int
    previous_interventions: List[Dict[str, Any]]
    recommended_action: Optional[str]
    reasoning: Optional[str]
    policy_approved: bool
    policy_reason: Optional[str]
    execution_result: Optional[str]
    final_status: str  # OPEN, IN_PROGRESS, RECOVERED, ESCALATED, STOPPED
    audit_events: List[Dict[str, Any]]
