from typing import Dict, Any, List
from backend.database import db

def log_case_event(event_dict: Dict[str, Any]):
    """
    Persist structured audit event into database.
    """
    db.insert_audit_log({
        "case_id": event_dict["case_id"],
        "agent": event_dict.get("agent", "RecoverAI_Agent"),
        "event": event_dict["event"],
        "decision": event_dict.get("decision"),
        "reason": event_dict.get("reason"),
        "timestamp": event_dict.get("timestamp")
    })

def get_case_audit_trail(case_id: str) -> List[Dict[str, Any]]:
    return db.get_audit_logs_for_case(case_id)
