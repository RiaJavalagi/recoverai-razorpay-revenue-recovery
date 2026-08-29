import os
import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
import xgboost as xgb

def generate_synthetic_data(num_samples: int = 50000, seed: int = 42) -> pd.DataFrame:
    np.random.seed(seed)
    
    # Customer features
    customer_ids = [f"C{np.random.randint(1000, 9999)}" for _ in range(num_samples)]
    subscription_age_months = np.random.exponential(scale=12, size=num_samples).astype(int) + 1
    
    # Payment amounts (mimicking standard SaaS tiers: 499, 999, 1999, 2999, 4999, 9999, 24999)
    tier_choices = np.array([499, 999, 1999, 2999, 4999, 9999, 24999])
    tier_probs = np.array([0.25, 0.30, 0.20, 0.12, 0.08, 0.04, 0.01])
    amounts = np.random.choice(tier_choices, size=num_samples, p=tier_probs)
    
    # Historical counts
    successful_counts = np.clip(np.random.poisson(lam=subscription_age_months * 0.9), 0, 60)
    failed_counts = np.clip(np.random.poisson(lam=0.5, size=num_samples), 0, 10)
    customer_ltvs = (successful_counts * amounts).astype(float)
    
    # Failure reasons & Payment methods
    failure_reasons = np.random.choice(
        ["INSUFFICIENT_FUNDS", "EXPIRED_CARD", "BANK_DECLINE", "GATEWAY_ERROR", "MANDATE_FAILURE", "UNKNOWN"],
        size=num_samples,
        p=[0.42, 0.18, 0.15, 0.12, 0.08, 0.05]
    )
    
    payment_methods = np.random.choice(
        ["card", "upi", "netbanking", "nach_mandate"],
        size=num_samples,
        p=[0.50, 0.30, 0.12, 0.08]
    )
    
    attempt_numbers = np.random.choice([1, 2, 3, 4], size=num_samples, p=[0.60, 0.25, 0.10, 0.05])
    days_since_last_success = np.clip(np.random.exponential(scale=28, size=num_samples).astype(int), 1, 180)
    previous_recovery_rate = np.where(
        failed_counts > 0, 
        np.clip(np.random.beta(a=4, b=2, size=num_samples), 0.0, 1.0),
        1.0
    )

    # Realistic Ground Truth Probability Equation
    # Success history & low attempts increase recovery; expired cards / excessive attempts decrease recovery
    logit = (
        0.8 * (successful_counts / (successful_counts + failed_counts + 1.0))
        - 0.5 * (attempt_numbers - 1)
        + 0.6 * (failure_reasons == "INSUFFICIENT_FUNDS")
        - 1.2 * (failure_reasons == "EXPIRED_CARD")
        + 0.5 * (failure_reasons == "GATEWAY_ERROR")
        - 0.3 * (failure_reasons == "BANK_DECLINE")
        - 0.4 * (failure_reasons == "MANDATE_FAILURE")
        + 0.3 * np.log1p(customer_ltvs / 1000.0)
        - 0.01 * days_since_last_success
        + 0.4 * previous_recovery_rate
        - 0.2
    )
    
    true_prob = 1.0 / (1.0 + np.exp(-logit))
    recovered = (np.random.uniform(0, 1, size=num_samples) < true_prob).astype(int)
    
    df = pd.DataFrame({
        "payment_id": [f"pay_{i:06d}" for i in range(num_samples)],
        "customer_id": customer_ids,
        "amount": amounts,
        "failure_reason": failure_reasons,
        "attempt_number": attempt_numbers,
        "successful_payment_count": successful_counts,
        "failed_payment_count": failed_counts,
        "customer_ltv": customer_ltvs,
        "subscription_age": subscription_age_months,
        "payment_method": payment_methods,
        "days_since_last_success": days_since_last_success,
        "previous_recovery_rate": np.round(previous_recovery_rate, 2),
        "recovered": recovered
    })
    
    return df

def revenue_weighted_recovery_score(y_true, y_pred, amounts):
    # Weighted revenue recovered: sum of true positives * amount / sum of all true recoverables * amount
    recovered_value = np.sum(amounts * (y_true == 1) * (y_pred == 1))
    total_recoverable_value = np.sum(amounts * (y_true == 1))
    return (recovered_value / total_recoverable_value) if total_recoverable_value > 0 else 0.0

def train_models():
    print("Generating 50,000 synthetic payment recovery records...")
    df = generate_synthetic_data(50000)
    
    os.makedirs("data", exist_ok=True)
    os.makedirs("backend/ml", exist_ok=True)
    df.to_csv("data/sample_payments.csv", index=False)
    print("Saved sample dataset to data/sample_payments.csv")
    
    feature_cols = [
        "amount", "failure_reason", "attempt_number", "successful_payment_count",
        "failed_payment_count", "customer_ltv", "subscription_age", "payment_method",
        "days_since_last_success", "previous_recovery_rate"
    ]
    
    X = df[feature_cols]
    y = df["recovered"]
    amounts = df["amount"].values
    
    X_train, X_test, y_train, y_test, amounts_train, amounts_test = train_test_split(
        X, y, amounts, test_size=0.2, random_state=42, stratify=y
    )
    
    categorical_features = ["failure_reason", "payment_method"]
    numeric_features = [c for c in feature_cols if c not in categorical_features]
    
    preprocessor = ColumnTransformer(
        transformers=[
            ("num", StandardScaler(), numeric_features),
            ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), categorical_features)
        ]
    )
    
    models = {
        "Logistic Regression": LogisticRegression(max_iter=1000, random_state=42),
        "Random Forest": RandomForestClassifier(n_estimators=100, max_depth=10, random_state=42, n_jobs=-1),
        "XGBoost": xgb.XGBClassifier(
            n_estimators=150,
            learning_rate=0.08,
            max_depth=5,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            eval_metric="logloss"
        )
    }
    
    results = {}
    best_model_name = "XGBoost"
    best_pipeline = None
    best_f1 = -1.0
    
    print("\n--- Model Benchmark & Evaluation ---")
    for name, clf in models.items():
        pipeline = Pipeline(steps=[("preprocessor", preprocessor), ("classifier", clf)])
        pipeline.fit(X_train, y_train)
        
        y_pred = pipeline.predict(X_test)
        y_prob = pipeline.predict_proba(X_test)[:, 1]
        
        acc = accuracy_score(y_test, y_pred)
        prec = precision_score(y_test, y_pred)
        rec = recall_score(y_test, y_pred)
        f1 = f1_score(y_test, y_pred)
        roc = roc_auc_score(y_test, y_prob)
        rev_weighted = revenue_weighted_recovery_score(y_test.values, y_pred, amounts_test)
        
        results[name] = {
            "Accuracy": acc,
            "Precision": prec,
            "Recall": rec,
            "F1": f1,
            "ROC-AUC": roc,
            "Revenue-Weighted Recovery": rev_weighted
        }
        
        print(f"[{name}]")
        print(f"  Accuracy: {acc:.4f} | Precision: {prec:.4f} | Recall: {rec:.4f} | F1: {f1:.4f} | ROC-AUC: {roc:.4f}")
        print(f"  Revenue-Weighted Recovery Score: {rev_weighted:.4f}")
        
        if f1 > best_f1:
            best_f1 = f1
            best_model_name = name
            best_pipeline = pipeline

    model_artifact = {
        "pipeline": best_pipeline,
        "feature_cols": feature_cols,
        "categorical_features": categorical_features,
        "numeric_features": numeric_features,
        "metrics": results,
        "best_model_name": best_model_name
    }
    
    joblib.dump(model_artifact, "backend/ml/model.pkl")
    print(f"\nBest Model: {best_model_name} (F1: {best_f1:.4f}) saved to backend/ml/model.pkl")
    return results

if __name__ == "__main__":
    train_models()
