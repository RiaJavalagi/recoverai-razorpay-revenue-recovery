from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

class Customer(BaseModel):
    id: str
    name: str
    email: str
    phone: Optional[str] = None
    segment: str = "standard"  # standard, premium, enterprise
    lifetime_value: float = 0.0
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

class Subscription(BaseModel):
    id: str
    customer_id: str
    razorpay_subscription_id: str
    plan_id: str
    amount: float
    status: str = "active"  # active, halted, cancelled, completed
    start_date: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

class Payment(BaseModel):
    id: str
    customer_id: str
    subscription_id: str
    razorpay_payment_id: str
    amount: float
    status: str  # created, authorized, captured, failed
    failure_reason: Optional[str] = None
    attempt_number: int = 1
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

class RecoveryCase(BaseModel):
    id: str
    customer_id: str
    subscription_id: str
    payment_id: str
    amount_at_risk: float
    recovery_probability: Optional[float] = None
    status: str = "OPEN"  # OPEN, IN_PROGRESS, RECOVERED, ESCALATED, STOPPED
    failure_reason: Optional[str] = None
    attempt_count: int = 0
    contact_count: int = 0
    recommended_action: Optional[str] = None
    policy_result: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    closed_at: Optional[str] = None

class Intervention(BaseModel):
    id: Optional[int] = None
    case_id: str
    type: str  # DELAYED_RETRY, PAYMENT_METHOD_UPDATE, PAYMENT_REMINDER, ESCALATE, STOP
    reason: str
    status: str  # PENDING, APPROVED, BLOCKED, EXECUTED, FAILED
    result: Optional[str] = None
    executed_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

class AuditLog(BaseModel):
    id: Optional[int] = None
    case_id: str
    agent: str = "RecoverAI_Agent"
    event: str
    decision: Optional[str] = None
    reason: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
