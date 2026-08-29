import sys
import os
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import os
import uvicorn
from contextlib import asynccontextmanager
from typing import Dict, Any, Optional, List
from fastapi import FastAPI, Request, HTTPException, Header, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from backend.database import db
from backend.razorpay.webhook import verify_webhook_signature, parse_webhook_payload
from backend.services.recovery import handle_payment_failure_event, run_batch_simulation
from backend.services.audit import get_case_audit_trail
from backend.ml.train import train_models

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB and ensure ML model exists
    print("Initializing RecoverAI Database...")
    db.init_db()
    if not os.path.exists("backend/ml/model.pkl"):
        print("ML model not found. Training initial XGBoost model...")
        train_models()
    print("RecoverAI System Ready.")
    yield

app = FastAPI(
    title="RecoverAI - Subscription Revenue Recovery Agent",
    description="Intelligent, Policy-Bounded Agentic AI Layer for Razorpay Subscription Payment Recovery",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class TriggerCaseRequest(BaseModel):
    customer_id: str
    subscription_id: str
    payment_id: str
    amount: float
    failure_reason: str
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    customer_contact: Optional[str] = None

class SimulationRequest(BaseModel):
    num_cases: int = 1000

@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "service": "RecoverAI Agent Backend",
        "version": "1.0.0",
        "environment": os.getenv("ENVIRONMENT", "development")
    }

@app.post("/webhook/razorpay")
async def razorpay_webhook(
    request: Request,
    x_razorpay_signature: Optional[str] = Header(None)
):
    body_bytes = await request.body()
    is_valid = verify_webhook_signature(body_bytes, x_razorpay_signature)
    
    if not is_valid:
        raise HTTPException(status_code=400, detail="Invalid Razorpay webhook signature")
    
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
        
    parsed = parse_webhook_payload(payload)
    event_type = parsed.get("event")
    
    # Process only payment failures for recovery case initiation
    if "failed" in event_type.lower():
        result = handle_payment_failure_event(parsed)
        return {
            "status": "success",
            "message": "Payment failure ingested. Recovery agent executed.",
            "recovery": result
        }
    
    return {
        "status": "ignored",
        "event": event_type,
        "message": "Event received but did not require recovery workflow."
    }

@app.post("/api/cases/trigger")
def trigger_case(req: TriggerCaseRequest):
    result = handle_payment_failure_event(req.dict())
    return {
        "status": "success",
        "data": result
    }

@app.get("/api/cases")
def list_cases(limit: int = Query(200, ge=1, le=1000)):
    cases = db.get_all_cases(limit=limit)
    return {
        "count": len(cases),
        "cases": cases
    }

@app.get("/api/cases/{case_id}")
def get_case_details(case_id: str):
    case = db.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
    
    timeline = get_case_audit_trail(case_id)
    interventions = db.get_interventions_for_case(case_id)
    customer = db.get_customer(case["customer_id"])
    
    return {
        "case": case,
        "customer": customer,
        "timeline": timeline,
        "interventions": interventions
    }

@app.get("/api/audit-logs")
def list_audit_logs(limit: int = Query(500, ge=1, le=2000)):
    logs = db.get_all_audit_logs(limit=limit)
    return {
        "count": len(logs),
        "logs": logs
    }

@app.get("/api/metrics")
def get_metrics():
    return db.get_dashboard_metrics()

@app.post("/api/simulate")
def run_simulation(req: SimulationRequest):
    results = run_batch_simulation(num_cases=req.num_cases)
    return results

if __name__ == "__main__":
    host = os.getenv("BACKEND_HOST", "127.0.0.1")
    port = int(os.getenv("BACKEND_PORT", 8000))
    uvicorn.run("backend.main:app", host=host, port=port, reload=True)
