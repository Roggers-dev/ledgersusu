import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import hashlib
import hmac
from datetime import datetime
import io
import os
import urllib.parse

# ==============================================================================
# 1. PAGE CONFIG & MOBILE-FIRST UI STYLING
# ==============================================================================
st.set_page_config(
    page_title="SusuFlow Enterprise | Multi-Collector Command Centre",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
    .stApp { background-color: #0f172a; color: #f8fafc; }
    .metric-card {
        background-color: #1e293b;
        border-left: 4px solid #10b981;
        padding: 16px;
        border-radius: 8px;
        margin-bottom: 12px;
    }
    .metric-title { font-size: 0.85rem; color: #94a3b8; text-transform: uppercase; }
    .metric-value { font-size: 1.55rem; font-weight: 700; color: #f8fafc; }
    .whatsapp-btn {
        background-color: #25d366;
        color: white !important;
        padding: 10px 18px;
        border-radius: 8px;
        text-decoration: none;
        font-weight: bold;
        display: inline-block;
        margin-top: 8px;
    }
    .role-badge {
        background-color: #1e3a8a;
        color: #93c5fd;
        padding: 4px 12px;
        border-radius: 12px;
        font-size: 0.85rem;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 2. HIGH-CAPACITY DATA STORAGE ENGINE (50 COLLECTORS, 2500+ CLIENT CAPACITY)
# ==============================================================================
MEMBERS_FILE = "susuflow_enterprise_members.csv"
TXNS_FILE = "susuflow_enterprise_transactions.csv"

MEMBER_COLS = [
    "Collector_ID", "Member_ID", "Full_Name", "Zone",
    "Daily_Rate_GHS", "Total_Saved_GHS", "Active_Loan_GHS", "Missed_Days", "Phone"
]
TXN_COLS = [
    "Collector_ID", "Date", "Member_ID", "Member_Name",
    "Type", "Amount_GHS", "Commission_GHS", "Net_Balance_Impact"
]

def load_data():
    if os.path.exists(MEMBERS_FILE):
        m_df = pd.read_csv(MEMBERS_FILE, dtype={"Collector_ID": str, "Member_ID": str, "Phone": str})
    else:
        first_names = ["Kwame", "Abena", "Yaw", "Efua", "Kofi", "Akosua", "Kojo", "Ama", "Kwabena", "Adwoa", "Esi", "Kwaku", "Yaa", "Kofi", "Afia"]
        last_names = ["Mensah", "Osei", "Boateng", "Sutherland", "Annan", "Adoma", "Frimpong", "Serwaa", "Appiah", "Danso", "Owusu", "Buadoo", "Asare", "Pomaa", "Duah"]
        zones = ["Central Market", "Lorry Station", "Enchi Main", "Zongo Junction", "New Town", "Station Road", "Commercial Area", "North Sector"]

        seed_members = []
        client_counter = 1
        
        for c in range(1, 51):
            collector_id = f"collector_{c:02d}"
            for cl in range(1, 51):
                member_id = f"SF-{client_counter:04d}"
                name = f"{first_names[(c + cl) % len(first_names)]} {last_names[(c * cl) % len(last_names)]}"
                zone = zones[(c + cl) % len(zones)]
                rate = float([10, 20, 30, 50, 100][(c + cl) % 5])
                saved = rate * float(((cl * 3) % 25) + 5)
                loan = float(rate * 10) if cl % 10 == 0 else 0.0
                missed = int(cl % 4 if cl % 7 == 0 else 0)
                phone = f"23324{client_counter:07d}"

                seed_members.append({
                    "Collector_ID": collector_id,
                    "Member_ID": member_id,
                    "Full_Name": name,
                    "Zone": zone,
                    "Daily_Rate_GHS": rate,
                    "Total_Saved_GHS": saved,
                    "Active_Loan_GHS": loan,
                    "Missed_Days": missed,
                    "Phone": phone
                })
                client_counter += 1

        m_df = pd.DataFrame(seed_members)
        
        seed_txns = []
        for m in seed_members[:200]:
            seed_txns.append({
                "Collector_ID": m["Collector_ID"],
                "Date": str(datetime.today().date()),
                "Member_ID": m["Member_ID"],
                "Member_Name": m["Full_Name"],
                "Type": "Deposit",
                "Amount_GHS": m["Daily_Rate_GHS"],
                "Commission_GHS": 0.0,
                "Net_Balance_Impact": m["Daily_Rate_GHS"]
            })
        t_df = pd.DataFrame(seed_txns)
        
        m_df.to_csv(MEMBERS_FILE, index=False)
        t_df.to_csv(TXNS_FILE, index=False)

    if os.path.exists(TXNS_FILE):
        t_df = pd.read_csv(TXNS_FILE, dtype={"Collector_ID": str, "Date": str, "Member_ID": str})
    else:
        t_df = pd.DataFrame(columns=TXN_COLS)

    for col in ["Daily_Rate_GHS", "Total_Saved_GHS", "Active_Loan_GHS"]:
        if col in m_df.columns:
            m_df[col] = pd.to_numeric(m_df[col], errors="coerce").fillna(0.0)
    if "Missed_Days" in m_df.columns:
        m_df["Missed_Days"] = pd.to_numeric(m_df["Missed_Days"], errors="coerce").fillna(0).astype(int)

    for col in ["Amount_GHS", "Commission_GHS", "Net_Balance_Impact"]:
        if col in t_df.columns:
            t_df[col] = pd.to_numeric(t_df[col], errors="coerce").fillna(0.0)
    if "Date" in t_df.columns:
        t_df["Date"] = t_df["Date"].astype(str)

    return m_df, t_df

def save_data(m_df: pd.DataFrame, t_df: pd.DataFrame):
    m_df.to_csv(MEMBERS_FILE, index=False)
    t_df.to_csv(TXNS_FILE, index=False)

# ==============================================================================
# 3. HELPER FUNCTIONS: AUTHENTICATION & DIRECTORY GENERATION
# ==============================================================================
def get_user_directory() -> dict:
    try:
        users = dict(st.secrets["users"])
        return users
    except Exception:
        default_hash = hashlib.sha256("test".encode()).hexdigest()
        fallback = {
            "rog3rs_admin": {
                "password_hash": default_hash,
                "role": "manager",
                "full_name": "Koffie Rogers (Master Admin)",
                "zone": "All Agency Zones"
            }
        }
        for i in range(1, 51):
            cid = f"collector_{i:02d}"
            fallback[cid] = {
                "password_hash": default_hash,
                "role": "collector",
                "full_name": f"Field Agent {i:02d}",
                "zone": f"Market Zone {i}"
            }
        return fallback

def authenticate_user(username: str, password: str):
    users = get_user_directory()
    uname = username.strip()
    if uname in users:
        expected_hash = users[uname]["password_hash"]
        input_hash = hashlib.sha256(password.encode()).hexdigest()
        if hmac.compare_digest(input_hash, expected_hash):
            return uname, users[uname]
    return None, None

if "auth_user" not in st.session_state:
    st.session_state.auth_user = None
    st.session_state.user_info = None

if not st.session_state.auth_user:
    st.markdown("## 🔐 SusuFlow Enterprise Login")
    st.caption("50-Collector Micro-Savings & Credit Risk Platform | Built by ROG3RS")
    
import hashlib

# 1. Load users function (handles Master Admin and all 50 collectors)
def load_users():
    users = {}
    try:
        if "users" in st.secrets:
            for uid, data in st.secrets["users"].items():
                users[uid] = dict(data)
    except Exception:
        pass
        
    default_hash = hashlib.sha256("test".encode()).hexdigest()
    if "rog3rs_admin" not in users:
        users["rog3rs_admin"] = {
            "password_hash": default_hash,
            "role": "manager",
            "full_name": "Koffie Rogers (Master Admin)",
            "zone": "All Agency Zones"
        }
    
    for i in range(1, 51):
        uid = f"collector_{i:02d}"
        if uid not in users:
            users[uid] = {
                "password_hash": default_hash,
                "role": "collector",
                "full_name": f"Field Agent {i:02d}",
                "zone": f"Market Zone {i}"
            }
    return users

# 2. Initialize users_dict so it is globally available for the selectbox
users_dict = load_users()
    
    # Ensure users_dict is loaded first
users_dict = load_users()

st.sidebar.markdown("### 🔐 SusuFlow Enterprise Login")

# Clean, professional operator selector dropdown
selected_user_id = st.sidebar.selectbox(
    "Select Operator ID",
    options=list(users_dict.keys()),
    format_func=lambda x: f"{x} - {users_dict[x].get('full_name', x)}"
)

# Completely blank password input box (masked securely)
entered_password = st.sidebar.text_input(
    "Security PIN / Password", 
    type="password", 
    value=""  # Ensures no default text is pre-filled
)

login_button = st.sidebar.button("Authorize Access")
    
    
"""   #users_dict = get_user_directory()
       with st.form("multi_login_form"):
           selected_login_id = st.selectbox(
               "Select Operator Account",
               options=list(users_dict.keys()),
               format_func=lambda x: f"{users_dict[x]['full_name']} ({x})"
           )
           pass_in = st.text_input("Operator Security PIN / Password", type="password", placeholder="Default test pass: test")
           if st.form_submit_button("Unlock Workspace", use_container_width=True):
               uid, info = authenticate_user(selected_login_id, pass_in)
               if uid:
                   st.session_state.auth_user = uid
                   st.session_state.user_info = info
                   st.session_state.last_txn = None
                   st.rerun()
               else:
                   st.error("❌ Invalid password for selected operator.")
       st.stop() """
  

# ==============================================================================
# 4. LOAD & PARTITION DATA BY COLLECTOR_ID
# ==============================================================================
all_members_df, all_txns_df = load_data()
current_uid = st.session_state.auth_user
current_role = st.session_state.user_info["role"]
current_name = st.session_state.user_info["full_name"]
current_zone = st.session_state.user_info["zone"]

if current_role == "manager":
    active_members = all_members_df.copy()
    active_txns = all_txns_df.copy()
else:
    active_members = all_members_df[all_members_df["Collector_ID"] == current_uid].copy()
    active_txns = all_txns_df[all_txns_df["Collector_ID"] == current_uid].copy()

# ==============================================================================
# 5. TOP HEADER & METRICS
# ==============================================================================
col_head, col_logout = st.columns([4, 1])
with col_head:
    st.title("💰 SusuFlow Command Centre")
    st.markdown(
        f'<span class="role-badge">👤 {current_name} | Role: {current_role.upper()} | Zone: {current_zone}</span>',
        unsafe_allow_html=True
    )
with col_logout:
    if st.button("🔒 Lock & Switch", use_container_width=True):
        st.session_state.auth_user = None
        st.session_state.user_info = None
        st.session_state.last_txn = None
        st.rerun()

st.write("")

tot_deposits = float(active_members["Total_Saved_GHS"].sum()) if not active_members.empty else 0.0
tot_loans = float(active_members["Active_Loan_GHS"].sum()) if not active_members.empty else 0.0
tot_commission = float(active_txns["Commission_GHS"].sum()) if not active_txns.empty else 0.0
client_count = len(active_members)

k1, k2, k3, k4 = st.columns(4)
k1.markdown(f'<div class="metric-card"><div class="metric-title">Portfolio Savings</div><div class="metric-value">GHS {tot_deposits:,.2f}</div></div>', unsafe_allow_html=True)
k2.markdown(f'<div class="metric-card" style="border-color:#38bdf8;"><div class="metric-title">Active Loans</div><div class="metric-value">GHS {tot_loans:,.2f}</div></div>', unsafe_allow_html=True)
k3.markdown(f'<div class="metric-card" style="border-color:#f59e0b;"><div class="metric-title">Commission Earned</div><div class="metric-value">GHS {tot_commission:,.2f}</div></div>', unsafe_allow_html=True)
k4.markdown(f'<div class="metric-card" style="border-color:#a855f7;"><div class="metric-title">Registered Clients</div><div class="metric-value">{client_count}</div></div>', unsafe_allow_html=True)

st.divider()


# ==============================================================================
# 6. NAVIGATION TABS
# ==============================================================================
if current_role == "manager":
    tab_mgr, tab_collect, tab_risk, tab_members, tab_reports = st.tabs([
        "🏢 Master Agency Overview (50 Collectors)",
        "💵 Daily Collection & WhatsApp",
        "🛡️ Loan Risk Engine",
        "👥 Client Directory",
        "📊 Audit & Exports"
    ])
else:
    tab_collect, tab_risk, tab_members, tab_reports = st.tabs([
        "💵 Daily Collection & WhatsApp",
        "🛡️ Loan Risk Engine",
        "👥 My Clients",
        "📊 My Ledger & Export"
    ])

# MANAGER OVERVIEW TAB
if current_role == "manager":
    with tab_mgr:
        st.subheader("🏢 Agency-Wide Performance Across All 50 Field Collectors")
        if all_members_df.empty:
            st.info("No records found.")
        else:
            perf_df = (
                all_members_df.groupby("Collector_ID", as_index=False)
                .agg(
                    Clients=pd.NamedAgg(column="Member_ID", aggfunc="count"),
                    Total_Savings_GHS=pd.NamedAgg(column="Total_Saved_GHS", aggfunc="sum"),
                    Active_Loans_GHS=pd.NamedAgg(column="Active_Loan_GHS", aggfunc="sum")
                )
            )
            if not all_txns_df.empty:
                comm_df = (
                    all_txns_df.groupby("Collector_ID", as_index=False)
                    .agg(Commission_GHS=pd.NamedAgg(column="Commission_GHS", aggfunc="sum"))
                )
                perf_df = pd.merge(perf_df, comm_df, on="Collector_ID", how="left").fillna(0.0)
            else:
                perf_df["Commission_GHS"] = 0.0

            st.dataframe(perf_df, use_container_width=True, hide_index=True)
            
            fig_mgr = px.bar(
                perf_df, x="Collector_ID", y=["Total_Savings_GHS", "Active_Loans_GHS"],
                barmode="group", title="Savings vs. Loan Exposure by Collector",
                color_discrete_map={"Total_Savings_GHS": "#10b981", "Active_Loans_GHS": "#38bdf8"}
            )
            fig_mgr.update_layout(paper_bgcolor="#1e293b", plot_bgcolor="#1e293b", font_color="#f8fafc")
            st.plotly_chart(fig_mgr, use_container_width=True)

# TAB 1: COLLECTION & WHATSAPP
with tab_collect:
    c_form, c_receipt = st.columns([1, 1])
    
    with c_form:
        st.subheader("Record Daily Transaction")
        if active_members.empty:
            st.warning("No clients registered under your account.")
        else:
            with st.form("txn_form", clear_on_submit=True):
                client_options = active_members["Member_ID"] + " - " + active_members["Full_Name"]
                selected_choice = st.selectbox("Select Client", client_options.tolist())
                selected_mid = selected_choice.split(" - ")[0]
                
                client_row = active_members[active_members["Member_ID"] == selected_mid].iloc[0]
                default_rate = float(client_row["Daily_Rate_GHS"])
                
                txn_type = st.selectbox("Transaction Type", ["Deposit", "Withdrawal (31-Day Cycle)", "Loan Repayment"])
                amount_in = st.number_input("Amount (GHS)", min_value=1.0, value=max(1.0, default_rate), step=5.0)
                txn_date = st.date_input("Transaction Date", value=datetime.today())
                apply_commission = st.checkbox("Deduct 1-Day Collector Commission", value=(txn_type == "Withdrawal (31-Day Cycle)"))
                
                if st.form_submit_button("✅ Post & Generate WhatsApp Receipt", use_container_width=True):
                    comm_fee = default_rate if apply_commission else 0.0
                    net_amount = amount_in - comm_fee if txn_type == "Withdrawal (31-Day Cycle)" else amount_in
                    
                    m_idx = all_members_df[all_members_df["Member_ID"] == selected_mid].index[0]
                    curr_bal = float(all_members_df.at[m_idx, "Total_Saved_GHS"])
                    
                    if txn_type == "Deposit":
                        new_bal = curr_bal + amount_in
                        all_members_df.at[m_idx, "Total_Saved_GHS"] = new_bal
                    elif txn_type == "Withdrawal (31-Day Cycle)":
                        new_bal = max(0.0, curr_bal - amount_in)
                        all_members_df.at[m_idx, "Total_Saved_GHS"] = new_bal
                    elif txn_type == "Loan Repayment":
                        new_bal = curr_bal
                        curr_loan = float(all_members_df.at[m_idx, "Active_Loan_GHS"])
                        all_members_df.at[m_idx, "Active_Loan_GHS"] = max(0.0, curr_loan - amount_in)
                    
                    owner_cid = str(all_members_df.at[m_idx, "Collector_ID"])
                    new_txn = pd.DataFrame([{
                        "Collector_ID": owner_cid,
                        "Date": str(txn_date),
                        "Member_ID": selected_mid,
                        "Member_Name": client_row["Full_Name"],
                        "Type": txn_type,
                        "Amount_GHS": float(amount_in),
                        "Commission_GHS": float(comm_fee),
                        "Net_Balance_Impact": float(net_amount)
                    }])
                    all_txns_df = pd.concat([all_txns_df, new_txn], ignore_index=True)
                    save_data(all_members_df, all_txns_df)
                    
                    st.session_state.last_txn = {
                        "name": client_row["Full_Name"],
                        "mid": selected_mid,
                        "phone": str(client_row["Phone"]),
                        "type": txn_type,
                        "amount": amount_in,
                        "commission": comm_fee,
                        "balance": new_bal,
                        "date": str(txn_date),
                        "collector": current_name
                    }
                    st.rerun()

    with c_receipt:
        st.subheader("📱 Instant WhatsApp Receipt")
        if st.session_state.get("last_txn"):
            t = st.session_state.last_txn
            receipt_text = (
                f"*SUSUFLOW OFFICIAL RECEIPT*\n"
                f"--------------------------------\n"
                f"🆔 *Acct ID:* {t['mid']}\n"
                f"👤 *Client:* {t['name']}\n"
                f"📅 *Date:* {t['date']}\n"
                f"📝 *Type:* {t['type']}\n"
                f"💵 *Amount:* GHS {t['amount']:,.2f}\n"
            )
            if t['commission'] > 0:
                receipt_text += f"⚙️ *Commission:* GHS {t['commission']:,.2f}\n"
            receipt_text += (
                f"💰 *Total Savings Balance:* GHS {t['balance']:,.2f}\n"
                f"👮 *Collector:* {t['collector']}\n"
                f"--------------------------------\n"
                f"Thank you for saving with us!"
            )
            st.code(receipt_text, language="text")
            encoded_msg = urllib.parse.quote(receipt_text)
            wa_url = f"https://wa.me/{t['phone']}?text={encoded_msg}"
            st.markdown(f'<a href="{wa_url}" target="_blank" class="whatsapp-btn">💬 Send Receipt via WhatsApp</a>', unsafe_allow_html=True)
        else:
            st.info("Post a transaction to generate a WhatsApp receipt.")

# TAB 2: RISK ENGINE
with tab_risk:
    st.subheader("🛡️ Automated Loan Risk & Eligibility Engine")
    if active_members.empty:
        st.info("No clients available.")
    else:
        risk_df = active_members.copy()
        risk_df["Max_Eligible_Loan_GHS"] = ((risk_df["Total_Saved_GHS"] * 1.5) - (risk_df["Missed_Days"] * 25.0)).clip(lower=0.0)
        
        def classify_risk(row):
            if row["Missed_Days"] >= 5 or row["Active_Loan_GHS"] > row["Total_Saved_GHS"]:
                return "HIGH RISK (Decline)"
            elif row["Missed_Days"] >= 2 or row["Active_Loan_GHS"] > 0:
                return "MEDIUM RISK (Guarantor Req.)"
            else:
                return "LOW RISK (Pre-Approved)"
                
        risk_df["Credit_Status"] = risk_df.apply(classify_risk, axis=1)
        st.dataframe(
            risk_df[["Member_ID", "Full_Name", "Zone", "Total_Saved_GHS", "Active_Loan_GHS", "Missed_Days", "Max_Eligible_Loan_GHS", "Credit_Status"]],
            use_container_width=True,
            hide_index=True
        )

# TAB 3: CLIENT REGISTRY
with tab_members:
    st.subheader("👥 Register New Susu Client")
    with st.form("new_member_form", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        m_name = c1.text_input("Client Full Name")
        m_zone = c2.text_input("Market Zone", value=current_zone if current_role == "collector" else "Central Market")
        m_rate = c3.number_input("Agreed Daily Rate (GHS)", min_value=1.0, value=20.0, step=5.0)
        m_phone = st.text_input("WhatsApp Number (Format: 233244XXXXXX)", placeholder="233244112233")
        
        assigned_cid = current_uid
        if current_role == "manager":
            users_dict = get_user_directory()
            collector_keys = [k for k, v in users_dict.items() if v["role"] == "collector"]
            assigned_cid = st.selectbox("Assign to Field Collector", collector_keys)
            
        if st.form_submit_button("➕ Register Client"):
            if m_name.strip():
                next_num = 101 + len(all_members_df)
                new_id = f"SF-{next_num}"
                new_member = pd.DataFrame([{
                    "Collector_ID": assigned_cid,
                    "Member_ID": new_id,
                    "Full_Name": m_name.strip(),
                    "Zone": m_zone.strip(),
                    "Daily_Rate_GHS": float(m_rate),
                    "Total_Saved_GHS": 0.0,
                    "Active_Loan_GHS": 0.0,
                    "Missed_Days": 0,
                    "Phone": m_phone.strip()
                }])
                all_members_df = pd.concat([all_members_df, new_member], ignore_index=True)
                save_data(all_members_df, all_txns_df)
                st.success(f"✅ Registered under ID **{new_id}**!")
                st.rerun()
            else:
                st.warning("Please enter client name.")

    st.markdown("### Client Directory")
    st.dataframe(active_members, use_container_width=True, hide_index=True)

# TAB 4: AUDIT & EXPORT
with tab_reports:
    st.subheader("📊 Audit-Ready Ledger & Excel Export")
    if active_txns.empty:
        st.info("No transactions recorded.")
    else:
        st.dataframe(active_txns.sort_values(by="Date", ascending=False), use_container_width=True, hide_index=True)
        
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        active_members.to_excel(writer, sheet_name="Client_Balances", index=False)
        active_txns.to_excel(writer, sheet_name="Transaction_Ledger", index=False)
        
    st.download_button(
        label="📥 Download Audit Report (.xlsx)",
        data=buffer.getvalue(),
        file_name=f"SusuFlow_{current_uid}_{datetime.today().strftime('%Y_%m_%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )