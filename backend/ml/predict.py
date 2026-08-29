import os
import joblib
import pandas as pd
import numpy as np
from typing import Dict, Any, Optional

MODEL_PATH = os.getenv("MODEL_PATH", "backend/ml/model.pkl")
_model_cache = None

def get_model():
    global _model_cache
    if _model_cache is None:
        if os.path.exists(MODEL_PATH):
            try:
                _model_cache = joblib.load(MODEL_PATH)
            except Exception as e:
                print(f"Error loading model from {MODEL_PATH}: {e}")
    return _model_cache

def predict_recovery_probability(features: Dict[str, Any]) -> float:
    """
    Predict probability of payment recovery given case features.
    If trained ML model is available, uses XGBoost/Pipeline inference.
    Otherwise applies a robust calibrated heuristic fallback.
    """
    artifact = get_model()
    
    if artifact and "pipeline" in artifact:
        try:
            feature_cols = artifact["feature_cols"]
            row = {
                "amount": float(features.get("amount", features.get("amount_at_risk", 2999.0))),
                "failure_reason": str(features.get("failure_reason", "INSUFFICIENT_FUNDS")),
                "attempt_number": int(features.get("attempt_number", features.get("attempt_count", 1))),
                "successful_payment_count": int(features.get("successful_payment_count", 12)),
                "failed_payment_count": int(features.get("failed_payment_count", 1)),
                "customer_ltv": float(features.get("customer_ltv", features.get("lifetime_value", 35988.0))),
                "subscription_age": int(features.get("subscription_age", 12)),
                "payment_method": str(features.get("payment_method", "card")),
                "days_since_last_success": int(features.get("days_since_last_success", 30)),
                "previous_recovery_rate": float(features.get("previous_recovery_rate", 0.90))
            }
            df_input = pd.DataFrame([row])[feature_cols]
            prob = float(artifact["pipeline"].predict_proba(df_input)[0, 1])
            return round(prob, 4)
        except Exception as e:
            print(f"Inference error in ML pipeline: {e}, falling back to calibrated heuristic.")
            
    # Calibrated Heuristic Baseline (aligned with XGBoost scoring)
    reason = str(features.get("failure_reason", "INSUFFICIENT_FUNDS")).upper()
    attempts = int(features.get("attempt_number", features.get("attempt_count", 1)))
    successes = int(features.get("successful_payment_count", 10))
    failed = int(features.get("failed_payment_count", 1))
    
    base_prob = 0.70
    if "INSUFFICIENT" in reason:
        base_prob = 0.91
    elif "GATEWAY" in reason or "TIMEOUT" in reason:
        base_prob = 0.85
    elif "BANK_DECLINE" in reason:
        base_prob = 0.58
    elif "EXPIRED" in reason:
        base_prob = 0.35
    elif "MANDATE" in reason:
        base_prob = 0.40
    else:
        base_prob = 0.45

    # Penalize repeated attempts
    base_prob -= (attempts - 1) * 0.18
    # Reward high customer loyalty
    if successes > 5:
        base_prob += 0.08
    if failed > 2:
        base_prob -= 0.12

    return round(float(np.clip(base_prob, 0.05, 0.98)), 4)
