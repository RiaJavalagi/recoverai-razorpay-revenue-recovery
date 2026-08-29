import sys
import os
# Ensure project root is on sys.path regardless of execution directory
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
from datetime import datetime

# Page configuration
st.set_page_config(
    page_title="RecoverAI - Revenue Recovery Agent",
    page_icon="??",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS styling
st.markdown("""
<style>
    .metric-card {
        background: linear-gradient(135deg, #1e293b, #0f172a);
        padding: 1.2rem;
        border-radius: 12px;
        border: 1px solid #334155;
        color: white;
    }
    .timeline-item {
        border-left: 3px solid #3b82f6;
        padding-left: 1rem;
        margin-bottom: 1rem;
    }
    .badge-success { background-color: #059669; color: white; padding: 4px 8px; border-radius: 6px; font-weight: bold; }
    .badge-warning { background-color: #d97706; color: white; padding: 4px 8px; border-radius: 6px; font-weight: bold; }
    .badge-danger { background-color: #dc2626; color: white; padding: 4px 8px; border-radius: 6px; font-weight: bold; }
    .badge-info { background-color: #2563eb; color: white; padding: 4px 8px; border-radius: 6px; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# Direct DB / Backend fallback helper
from backend.database import db
from backend.services.recovery import handle_payment_failure_event, run_batch_simulation
from backend.services.audit import get_case_audit_trail

db.init_db()

# Sidebar Navigation
st.sidebar.title(" RecoverAI")
st.sidebar.caption("Agentic AI for Subscription Revenue Recovery")
st.sidebar.markdown("---")
page = st.sidebar.radio(
    "Navigation",
    [" Executive Overview", " Case Explorer & Timeline", " Batch Simulation & Benchmark", " Live Failure Simulator"]
)

st.sidebar.markdown("---")
st.sidebar.info("""
**Connected Platform:** Razorpay Test Mode  
**Architecture:** LangGraph + XGBoost + Policy Engine  
**Storage:** SQLite Thread-Safe Engine
""")

# -------------------------------------------------------------
# 1. Executive Overview
# -------------------------------------------------------------
if page == " Executive Overview":
    st.title(" Executive Recovery Dashboard")
    st.caption("Real-time revenue recovery metrics, active case lifecycle, and policy compliance.")
    
    metrics = db.get_dashboard_metrics()
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric(
            label="Revenue At Risk",
            value=f"{metrics['revenue_at_risk']:,.2f}",
            help="Total value of all failed subscription payments ingested"
        )
    with col2:
        st.metric(
            label="Revenue Recovered",
            value=f"{metrics['revenue_recovered']:,.2f}",
            delta=f"{metrics['recovery_rate']:.1f}% Recovery Rate",
            help="Total revenue successfully recovered by RecoverAI"
        )
    with col3:
        st.metric(
            label="Total Recovery Cases",
            value=f"{metrics['total_cases']:,}",
            help="Total cases handled by the recovery agent"
        )
    with col4:
        st.metric(
            label="Intervention Success Rate",
            value=f"{metrics['intervention_success_rate']:.1f}%",
            delta=f"{metrics['successful_interventions']} / {metrics['total_interventions']} successful",
            help="Percentage of interventions that directly recovered revenue"
        )
        
    st.markdown("---")
    
    # Charts Section
    c1, c2 = st.columns([1, 1])
    
    cases = db.get_all_cases(limit=500)
    if cases:
        df_cases = pd.DataFrame(cases)
        with c1:
            st.subheader("Case Status Breakdown")
            status_counts = df_cases['status'].value_counts().reset_index()
            status_counts.columns = ['Status', 'Count']
            
            fig_pie = px.pie(
                status_counts, 
                values='Count', 
                names='Status',
                hole=0.45,
                color='Status',
                color_discrete_map={
                    'RECOVERED': '#10b981',
                    'OPEN': '#3b82f6',
                    'IN_PROGRESS': '#f59e0b',
                    'ESCALATED': '#8b5cf6',
                    'STOPPED': '#ef4444'
                }
            )
            fig_pie.update_layout(margin=dict(t=10, b=10, l=10, r=10))
            st.plotly_chart(fig_pie, use_container_width=True)
            
        with c2:
            st.subheader("Recovery by Failure Category")
            if 'failure_reason' in df_cases.columns:
                cat_summary = df_cases.groupby('failure_reason')['amount_at_risk'].agg(['sum', 'count']).reset_index()
                cat_summary.columns = ['Failure Category', 'Amount at Risk', 'Cases']
                fig_bar = px.bar(
                    cat_summary,
                    x='Failure Category',
                    y='Amount at Risk',
                    color='Amount at Risk',
                    color_continuous_scale='Blues',
                    text_auto='.2s'
                )
                fig_bar.update_layout(margin=dict(t=10, b=10, l=10, r=10))
                st.plotly_chart(fig_bar, use_container_width=True)
    else:
        st.info("No recovery cases in database yet. Try running the Batch Simulation or Live Failure Simulator!")

    # Recent cases table
    st.subheader("Recent Recovery Cases")
    if cases:
        display_df = pd.DataFrame(cases)[['id', 'customer_id', 'amount_at_risk', 'failure_reason', 'recommended_action', 'status', 'created_at']]
        display_df.columns = ['Case ID', 'Customer ID', 'Amount (INR)', 'Failure Category', 'Recommended Action', 'Status', 'Created At']
        st.dataframe(display_df, use_container_width=True)

# -------------------------------------------------------------
# 2. Case Explorer & Live Timeline
# -------------------------------------------------------------
elif page == " Case Explorer & Timeline":
    st.title(" Case Explorer & Agent Timeline")
    st.caption("Inspect individual recovery cases with full explainability, ML attribution, and step-by-step audit logs.")
    
    cases = db.get_all_cases(limit=100)
    if not cases:
        st.warning("No cases found. Create one via Live Simulator or Batch Simulation.")
    else:
        case_options = [f"{c['id']} | Customer: {c['customer_id']} | {c['amount_at_risk']:,.2f} | {c['status']}" for c in cases]
        selected_option = st.selectbox("Select Recovery Case:", case_options)
        selected_case_id = selected_option.split(" | ")[0]
        
        case_data = db.get_case(selected_case_id)
        cust_data = db.get_customer(case_data['customer_id'])
        timeline = get_case_audit_trail(selected_case_id)
        interventions = db.get_interventions_for_case(selected_case_id)
        
        col_a, col_b, col_c, col_d = st.columns(4)
        with col_a:
            st.markdown(f"**Amount At Risk:** {case_data['amount_at_risk']:,.2f}")
            st.markdown(f"**Current Status:** `{case_data['status']}`")
        with col_b:
            st.markdown(f"**Customer:** {cust_data['name'] if cust_data else case_data['customer_id']}")
            st.markdown(f"**Customer LTV:** {cust_data.get('lifetime_value', 0):,.2f}" if cust_data else "N/A")
        with col_c:
            prob = case_data.get('recovery_probability') or 0.0
            st.markdown(f"**Recovery Probability:** `{prob * 100:.1f}%`")
            st.markdown(f"**Failure Category:** `{case_data.get('failure_reason', 'UNKNOWN')}`")
        with col_d:
            st.markdown(f"**Agent Action:** `{case_data.get('recommended_action', 'N/A')}`")
            st.markdown(f"**Policy Decision:** `{case_data.get('policy_result', 'APPROVED')}`")
            
        st.markdown("---")
        st.subheader("Agent Decision & Execution Timeline")
        
        if not timeline:
            st.info("No timeline events recorded.")
        else:
            for idx, event in enumerate(timeline):
                event_name = event['event']
                decision = event.get('decision') or ""
                reason = event.get('reason') or ""
                ts = event.get('timestamp') or ""
                
                icon = "??"
                if "FAILED" in event_name: icon = ""
                elif "CONTEXT" in event_name: icon = ""
                elif "DIAGNOSED" in event_name: icon = ""
                elif "PROBABILITY" in event_name: icon = ""
                elif "INTERVENTION" in event_name: icon = ""
                elif "POLICY" in event_name: icon = ""
                elif "EXECUTED" in event_name: icon = ""
                elif "OUTCOME" in event_name: icon = "" if "RECOVERED" in decision else ""
                
                with st.expander(f"{icon} Step {idx+1}: {event_name.replace('_', ' ')} — {decision}", expanded=True):
                    st.markdown(f"**Timestamp:** `{ts}`")
                    if reason:
                        st.markdown(f"**Agent Explanation / Context:** {reason}")

# -------------------------------------------------------------
# 3. Batch Simulation & Benchmark
# -------------------------------------------------------------
elif page == " Batch Simulation & Benchmark":
    st.title(" Batch Simulation & Strategy Benchmark")
    st.markdown("""
    Evaluate RecoverAI across a large batch of failed payments (**1,000 cases**) and benchmark against conventional industry strategies:
    1. **Baseline 1: No Recovery** (Zero proactive interventions)
    2. **Baseline 2: Fixed Rule Strategy** (Generic blind retries without diagnosis or policy guardrails)
    3. **RecoverAI Agent** (XGBoost ML probability + Context-Aware Reasoning + Deterministic Policy Engine)
    """)
    
    col1, col2 = st.columns([1, 3])
    with col1:
        num_sim_cases = st.number_input("Number of Simulated Cases", min_value=100, max_value=5000, value=1000, step=100)
        run_sim = st.button(" Run Batch Simulation", type="primary")
        
    if run_sim or "sim_results" in st.session_state:
        if run_sim:
            with st.spinner("Simulating payment lifecycle and agent decisions across 1,000 cases..."):
                st.session_state["sim_results"] = run_batch_simulation(num_sim_cases)
                
        res = st.session_state["sim_results"]
        s = res["strategies"]
        
        st.success(f"Simulation completed for {res['cases_processed']:,} failed subscription payments!")
        
        # Summary KPI Cards
        k1, k2, k3 = st.columns(3)
        with k1:
            st.metric("Revenue At Risk", f"{res['revenue_at_risk']:,.2f}")
        with k2:
            st.metric("RecoverAI Recovered Revenue", f"{s['recoverai_agent']['revenue_recovered']:,.2f}", f"{s['recoverai_agent']['recovery_rate']:.1f}% Recovery Rate")
        with k3:
            st.metric("Revenue Uplift vs Fixed Retries", f"+{res['uplift_vs_fixed_rule']:.1f}%", help="Incremental revenue generated by AI agent over standard rule retry")
            
        # Comparison Table
        st.subheader("Strategy Performance Benchmark")
        table_data = [
            {
                "Strategy": s["no_recovery"]["name"],
                "Recovered (INR)": f"{s['no_recovery']['revenue_recovered']:,.2f}",
                "Recovery Rate": f"{s['no_recovery']['recovery_rate']:.1f}%",
                "Successful Recoveries": s["no_recovery"]["successful_recoveries"],
                "Total Interventions": s["no_recovery"]["interventions"]
            },
            {
                "Strategy": s["fixed_rule"]["name"],
                "Recovered (INR)": f"{s['fixed_rule']['revenue_recovered']:,.2f}",
                "Recovery Rate": f"{s['fixed_rule']['recovery_rate']:.1f}%",
                "Successful Recoveries": s["fixed_rule"]["successful_recoveries"],
                "Total Interventions": s["fixed_rule"]["interventions"]
            },
            {
                "Strategy": s["recoverai_agent"]["name"],
                "Recovered (INR)": f"{s['recoverai_agent']['revenue_recovered']:,.2f}",
                "Recovery Rate": f"{s['recoverai_agent']['recovery_rate']:.1f}%",
                "Successful Recoveries": s["recoverai_agent"]["successful_recoveries"],
                "Total Interventions": s["recoverai_agent"]["interventions"]
            }
        ]
        st.table(pd.DataFrame(table_data))
        
        # Plotly Benchmark Chart
        fig = go.Figure()
        fig.add_trace(go.Bar(
            name='Revenue Recovered (INR)',
            x=['No Recovery', 'Fixed Rule Retry', 'RecoverAI Agent'],
            y=[s['no_recovery']['revenue_recovered'], s['fixed_rule']['revenue_recovered'], s['recoverai_agent']['revenue_recovered']],
            marker_color=['#94a3b8', '#f59e0b', '#10b981'],
            text=[f"{s['no_recovery']['revenue_recovered']:,.0f}", f"{s['fixed_rule']['revenue_recovered']:,.0f}", f"{s['recoverai_agent']['revenue_recovered']:,.0f}"],
            textposition='auto',
        ))
        fig.update_layout(
            title="Total Revenue Recovered Across 1,000 Failed Payments",
            yaxis_title="Recovered Revenue (INR)",
            template="plotly_dark",
            height=400
        )
        st.plotly_chart(fig, use_container_width=True)

# -------------------------------------------------------------
# 4. Live Failure Simulator
# -------------------------------------------------------------
elif page == " Live Failure Simulator":
    st.title(" Live Payment Failure Simulator")
    st.caption("Simulate a Razorpay subscription payment failure event to trigger the live LangGraph recovery agent.")
    
    with st.form("simulate_payment_form"):
        col1, col2 = st.columns(2)
        with col1:
            customer_name = st.text_input("Customer Name", value="Rahul Sharma")
            customer_email = st.text_input("Customer Email", value="rahul.sharma@example.com")
            subscription_amount = st.selectbox("Subscription Tier (INR)", [499.0, 999.0, 1999.0, 2999.0, 4999.0, 9999.0, 24999.0], index=3)
        with col2:
            failure_reason = st.selectbox(
                "Payment Failure Reason",
                [
                    "Insufficient funds in bank account",
                    "Card expired / card expired on file",
                    "Bank decline / generic decline by issuer",
                    "Gateway timeout / temporary bank network error",
                    "Recurring mandate authorization failed"
                ]
            )
            customer_id = st.text_input("Customer ID", value=f"CUST_{datetime.utcnow().strftime('%M%S')}")
            
        submitted = st.form_submit_button(" Ingest Payment Failure Event", type="primary")
        
    if submitted:
        with st.spinner("Processing event via Razorpay webhook layer & LangGraph recovery agent..."):
            event_payload = {
                "customer_id": customer_id,
                "customer_name": customer_name,
                "customer_email": customer_email,
                "subscription_id": f"sub_{datetime.utcnow().strftime('%H%M%S')}",
                "payment_id": f"pay_{datetime.utcnow().strftime('%H%M%S')}",
                "amount": subscription_amount,
                "failure_reason": failure_reason
            }
            res = handle_payment_failure_event(event_payload)
            
            st.success(f"Event Ingested! Case `{res['case_id']}` processed with result: **{res['final_status']}**")
            
            # Step by step execution cards
            st.subheader("Live Agent Workflow Execution")
            for idx, event in enumerate(res["timeline"]):
                st.markdown(f"""
                <div class="timeline-item">
                    <strong>Step {idx+1}: {event['event']}</strong><br/>
                    <span style="color:#94a3b8;">{event.get('decision', '')}</span> — <em>{event.get('reason', '')}</em>
                </div>
                """, unsafe_allow_html=True)

