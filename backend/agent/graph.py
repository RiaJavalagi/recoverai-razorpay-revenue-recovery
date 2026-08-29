from langgraph.graph import StateGraph, END
from backend.agent.state import AgentState
from backend.agent.nodes import (
    observe_node,
    diagnose_node,
    predict_node,
    reason_node,
    policy_validation_node,
    execute_node,
    verify_node
)

def create_recovery_graph():
    workflow = StateGraph(AgentState)
    
    # Add nodes
    workflow.add_node("observe", observe_node)
    workflow.add_node("diagnose", diagnose_node)
    workflow.add_node("predict", predict_node)
    workflow.add_node("reason", reason_node)
    workflow.add_node("policy_validate", policy_validation_node)
    workflow.add_node("execute", execute_node)
    workflow.add_node("verify", verify_node)
    
    # Linear edges
    workflow.set_entry_point("observe")
    workflow.add_edge("observe", "diagnose")
    workflow.add_edge("diagnose", "predict")
    workflow.add_edge("predict", "reason")
    workflow.add_edge("reason", "policy_validate")
    workflow.add_edge("policy_validate", "execute")
    workflow.add_edge("execute", "verify")
    workflow.add_edge("verify", END)
    
    return workflow.compile()

# Global compiled agent instance
recovery_agent = create_recovery_graph()
