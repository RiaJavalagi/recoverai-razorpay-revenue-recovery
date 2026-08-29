import sqlite3
import os
import threading
from typing import List, Optional, Dict, Any
from datetime import datetime

DATABASE_PATH = os.getenv("DATABASE_PATH", "recoverai.db")
_lock = threading.Lock()

def get_connection():
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with _lock:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS customers (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                phone TEXT,
                segment TEXT DEFAULT 'standard',
                lifetime_value REAL DEFAULT 0.0,
                created_at TEXT NOT NULL
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                id TEXT PRIMARY KEY,
                customer_id TEXT NOT NULL,
                razorpay_subscription_id TEXT NOT NULL,
                plan_id TEXT NOT NULL,
                amount REAL NOT NULL,
                status TEXT DEFAULT 'active',
                start_date TEXT NOT NULL,
                FOREIGN KEY (customer_id) REFERENCES customers(id)
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id TEXT PRIMARY KEY,
                customer_id TEXT NOT NULL,
                subscription_id TEXT NOT NULL,
                razorpay_payment_id TEXT NOT NULL,
                amount REAL NOT NULL,
                status TEXT NOT NULL,
                failure_reason TEXT,
                attempt_number INTEGER DEFAULT 1,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (customer_id) REFERENCES customers(id),
                FOREIGN KEY (subscription_id) REFERENCES subscriptions(id)
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS recovery_cases (
                id TEXT PRIMARY KEY,
                customer_id TEXT NOT NULL,
                subscription_id TEXT NOT NULL,
                payment_id TEXT NOT NULL,
                amount_at_risk REAL NOT NULL,
                recovery_probability REAL,
                status TEXT DEFAULT 'OPEN',
                failure_reason TEXT,
                attempt_count INTEGER DEFAULT 0,
                contact_count INTEGER DEFAULT 0,
                recommended_action TEXT,
                policy_result TEXT,
                created_at TEXT NOT NULL,
                closed_at TEXT,
                FOREIGN KEY (customer_id) REFERENCES customers(id),
                FOREIGN KEY (subscription_id) REFERENCES subscriptions(id),
                FOREIGN KEY (payment_id) REFERENCES payments(id)
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS interventions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id TEXT NOT NULL,
                type TEXT NOT NULL,
                reason TEXT NOT NULL,
                status TEXT NOT NULL,
                result TEXT,
                executed_at TEXT NOT NULL,
                FOREIGN KEY (case_id) REFERENCES recovery_cases(id)
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id TEXT NOT NULL,
                agent TEXT DEFAULT 'RecoverAI_Agent',
                event TEXT NOT NULL,
                decision TEXT,
                reason TEXT,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (case_id) REFERENCES recovery_cases(id)
            )
        """)
        
        conn.commit()
        conn.close()

def insert_customer(cust: dict):
    with _lock:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO customers (id, name, email, phone, segment, lifetime_value, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            cust['id'],
            cust['name'],
            cust['email'],
            cust.get('phone'),
            cust.get('segment', 'standard'),
            cust.get('lifetime_value', 0.0),
            cust.get('created_at') or datetime.utcnow().isoformat()
        ))
        conn.commit()
        conn.close()

def get_customer(customer_id: str) -> Optional[dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM customers WHERE id = ?", (customer_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def insert_subscription(sub: dict):
    with _lock:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO subscriptions (id, customer_id, razorpay_subscription_id, plan_id, amount, status, start_date)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            sub['id'],
            sub['customer_id'],
            sub['razorpay_subscription_id'],
            sub['plan_id'],
            sub['amount'],
            sub.get('status', 'active'),
            sub.get('start_date') or datetime.utcnow().isoformat()
        ))
        conn.commit()
        conn.close()

def get_subscription(subscription_id: str) -> Optional[dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM subscriptions WHERE id = ?", (subscription_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def insert_payment(payment: dict):
    with _lock:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO payments (id, customer_id, subscription_id, razorpay_payment_id, amount, status, failure_reason, attempt_number, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            payment['id'],
            payment['customer_id'],
            payment['subscription_id'],
            payment['razorpay_payment_id'],
            payment['amount'],
            payment['status'],
            payment.get('failure_reason'),
            payment.get('attempt_number', 1),
            payment.get('timestamp') or datetime.utcnow().isoformat()
        ))
        conn.commit()
        conn.close()

def get_payment(payment_id: str) -> Optional[dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM payments WHERE id = ?", (payment_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_payments_for_customer(customer_id: str) -> List[dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM payments WHERE customer_id = ? ORDER BY timestamp DESC", (customer_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def insert_or_update_case(case: dict):
    with _lock:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO recovery_cases (
                id, customer_id, subscription_id, payment_id, amount_at_risk, 
                recovery_probability, status, failure_reason, attempt_count, 
                contact_count, recommended_action, policy_result, created_at, closed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                amount_at_risk=excluded.amount_at_risk,
                recovery_probability=excluded.recovery_probability,
                status=excluded.status,
                failure_reason=excluded.failure_reason,
                attempt_count=excluded.attempt_count,
                contact_count=excluded.contact_count,
                recommended_action=excluded.recommended_action,
                policy_result=excluded.policy_result,
                closed_at=excluded.closed_at
        """, (
            case['id'],
            case['customer_id'],
            case['subscription_id'],
            case['payment_id'],
            case['amount_at_risk'],
            case.get('recovery_probability'),
            case.get('status', 'OPEN'),
            case.get('failure_reason'),
            case.get('attempt_count', 0),
            case.get('contact_count', 0),
            case.get('recommended_action'),
            case.get('policy_result'),
            case.get('created_at') or datetime.utcnow().isoformat(),
            case.get('closed_at')
        ))
        conn.commit()
        conn.close()

def get_case(case_id: str) -> Optional[dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM recovery_cases WHERE id = ?", (case_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_all_cases(limit: int = 500) -> List[dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM recovery_cases ORDER BY created_at DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def insert_intervention(intervention: dict) -> int:
    with _lock:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO interventions (case_id, type, reason, status, result, executed_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            intervention['case_id'],
            intervention['type'],
            intervention['reason'],
            intervention['status'],
            intervention.get('result'),
            intervention.get('executed_at') or datetime.utcnow().isoformat()
        ))
        inserted_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return inserted_id

def get_interventions_for_case(case_id: str) -> List[dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM interventions WHERE case_id = ? ORDER BY executed_at ASC", (case_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def insert_audit_log(log: dict):
    with _lock:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO audit_logs (case_id, agent, event, decision, reason, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            log['case_id'],
            log.get('agent', 'RecoverAI_Agent'),
            log['event'],
            log.get('decision'),
            log.get('reason'),
            log.get('timestamp') or datetime.utcnow().isoformat()
        ))
        conn.commit()
        conn.close()

def get_audit_logs_for_case(case_id: str) -> List[dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM audit_logs WHERE case_id = ? ORDER BY timestamp ASC", (case_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_all_audit_logs(limit: int = 500) -> List[dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_dashboard_metrics() -> dict:
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*), COALESCE(SUM(amount_at_risk), 0) FROM recovery_cases")
    total_cases, total_at_risk = cursor.fetchone()
    
    cursor.execute("SELECT COUNT(*), COALESCE(SUM(amount_at_risk), 0) FROM recovery_cases WHERE status = 'RECOVERED'")
    recovered_cases, total_recovered = cursor.fetchone()
    
    cursor.execute("SELECT COUNT(*) FROM recovery_cases WHERE status = 'OPEN' OR status = 'IN_PROGRESS'")
    active_cases = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM recovery_cases WHERE status = 'ESCALATED'")
    escalated_cases = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM recovery_cases WHERE status = 'STOPPED'")
    stopped_cases = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM interventions")
    total_interventions = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM interventions WHERE result LIKE '%success%' OR result LIKE '%Recovered%'")
    successful_interventions = cursor.fetchone()[0]
    
    conn.close()
    
    recovery_rate = (total_recovered / total_at_risk * 100.0) if total_at_risk > 0 else 0.0
    intervention_success_rate = (successful_interventions / total_interventions * 100.0) if total_interventions > 0 else 0.0
    
    return {
        'total_cases': total_cases,
        'revenue_at_risk': round(total_at_risk, 2),
        'revenue_recovered': round(total_recovered, 2),
        'recovery_rate': round(recovery_rate, 2),
        'active_cases': active_cases,
        'recovered_cases': recovered_cases,
        'escalated_cases': escalated_cases,
        'stopped_cases': stopped_cases,
        'total_interventions': total_interventions,
        'successful_interventions': successful_interventions,
        'intervention_success_rate': round(intervention_success_rate, 2)
    }
