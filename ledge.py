from datetime import datetime
import hashlib
import os
import sqlite3
import pandas as pd
import streamlit as st

# ==========================================
# 1. PAGE CONFIGURATION
# ==========================================
st.set_page_config(
    page_title="SusuFlow Enterprise",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ==========================================
# 2. ISOLATED DATABASE MANAGEMENT PER USER
# ==========================================
def get_user_db_path(username):
  """Returns a dedicated, isolated database filename for each user/collector."""
  # Master admin gets a consolidated view or management database, collectors get isolated files
  if username == "rog3rs_admin":
    return "master_agency.db"
  else:
    return f"db_{username}.db"


def init_db(db_path):
  conn = sqlite3.connect(db_path, check_same_thread=False)
  cursor = conn.cursor()

  cursor.execute("""
        CREATE TABLE IF NOT EXISTS clients (
            client_id TEXT PRIMARY KEY,
            full_name TEXT,
            phone_number TEXT,
            market_zone TEXT,
            registration_date TEXT,
            registered_by TEXT
        )
    """)

  cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            transaction_id TEXT PRIMARY KEY,
            timestamp TEXT,
            client_id TEXT,
            client_name TEXT,
            collector_id TEXT,
            frequency TEXT,
            amount REAL,
            notes TEXT
        )
    """)
  conn.commit()
  return conn


# Master Access Control DB (Shared only for manager approvals)
def init_master_access_db():
  conn = sqlite3.connect("master_access.db", check_same_thread=False)
  cursor = conn.cursor()
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS collector_access (
            collector_id TEXT PRIMARY KEY,
            is_approved INTEGER
        )
    """)
  conn.commit()
  return conn


master_access_conn = init_master_access_db()


def get_collector_approval(collector_id, default_val=False):
  cursor = master_access_conn.cursor()
  cursor.execute(
      "SELECT is_approved FROM collector_access WHERE collector_id = ?",
      (collector_id,),
  )
  row = cursor.fetchone()
  if row is None:
    return 1 if default_val else 0
  return row[0]


def set_collector_approval(collector_id, status):
  cursor = master_access_conn.cursor()
  cursor.execute(
      """
        INSERT OR REPLACE INTO collector_access (collector_id, is_approved)
        VALUES (?, ?)
    """,
      (collector_id, 1 if status else 0),
  )
  master_access_conn.commit()


# ==========================================
# 3. USER DIRECTORY & SUBSCRIPTION LOGIC
# ==========================================
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
        "zone": "All Agency Zones",
    }

  for i in range(1, 51):
    uid = f"collector_{i:02d}"
    if uid not in users:
      users[uid] = {
          "password_hash": default_hash,
          "role": "collector",
          "full_name": f"Field Agent {i:02d}",
          "zone": f"Market Zone {i}",
      }
  return users


users_dict = load_users()


def check_subscription_period():
  try:
    sub_config = st.secrets.get("subscription", {})
    status = sub_config.get("status", "active")
    start_str = sub_config.get("start_date", "2026-01-01")
    expiry_str = sub_config.get("expiry_date", "2026-12-31")

    start_date = datetime.strptime(start_str, "%Y-%m-%d").date()
    expiry_date = datetime.strptime(expiry_str, "%Y-%m-%d").date()
    today = datetime.now().date()

    if status != "active":
      return False, "License status is marked as inactive."
    if today < start_date:
      return False, f"Subscription period has not started yet (Starts: {start_str})"
    if today > expiry_date:
      return False, f"Subscription period expired on {expiry_str}"

    return True, expiry_str
  except Exception:
    return True, "2026-12-31"


# ==========================================
# 4. SESSION STATE INITIALIZATION
# ==========================================
if "auth_user" not in st.session_state:
  st.session_state.auth_user = None
if "user_info" not in st.session_state:
  st.session_state.user_info = None
if "last_receipt" not in st.session_state:
  st.session_state.last_receipt = None


# ==========================================
# 5. SUBSCRIPTION PERIOD ENFORCEMENT GATE
# ==========================================
is_active, sub_message = check_subscription_period()
if not is_active:
  st.error("⚠️ **SaaS Subscription License Expired / Inactive**")
  st.warning(
      "The licensed operational period for SusuFlow Enterprise has concluded."
      " Live field operations and database posting are locked."
  )
  st.info(
      f"**Reason / Expiry Details:** {sub_message}\n\nTo renew your agency"
      " subscription package, please contact system administration."
  )
  st.stop()
  
  
  # ==========================================
# 6. SIDEBAR AUTHENTICATION GATE
# ==========================================
if not st.session_state.auth_user:
  st.sidebar.markdown("### 🔐 SusuFlow Enterprise Login")
  st.sidebar.caption("Isolated Space Per Collector Platform")

  selected_user_id = st.sidebar.selectbox(
      "Select Operator Account",
      options=list(users_dict.keys()),
      format_func=lambda x: f"{x} - {users_dict[x].get('full_name', x)}",
  )

  entered_password = st.sidebar.text_input(
      "Operator Security PIN / Password", type="password", value=""
  )

  if st.sidebar.button("Unlock Workspace", use_container_width=True):
    entered_hash = hashlib.sha256(entered_password.encode()).hexdigest()
    stored_hash = users_dict.get(selected_user_id, {}).get("password_hash", "")

    if entered_hash == stored_hash:
      is_manager = users_dict.get(selected_user_id, {}).get("role") == "manager"
      is_approved = (
          True
          if is_manager
          else bool(get_collector_approval(selected_user_id, default_val=False))
      )

      if not is_manager and not is_approved:
        st.sidebar.error(
            "🚫 Access Pending: Master Admin has not yet authorized this"
            " collector account."
        )
      else:
        st.session_state.auth_user = selected_user_id
        st.session_state.user_info = users_dict[selected_user_id]
        st.rerun()
    else:
      st.sidebar.error("❌ Invalid password for selected operator.")

  st.stop()


# ==========================================
# 7. MAIN APP DASHBOARD & ISOLATED DATA HANDLING
# ==========================================
user_info = st.session_state.get("user_info", {})
current_role = user_info.get("role", "collector") if user_info else "collector"
current_agent_name = (
    user_info.get("full_name", "Field Agent") if user_info else "Field Agent"
)
current_zone = (
    user_info.get("zone", "Market Zone") if user_info else "Market Zone"
)
current_user_id = st.session_state.auth_user

# Connect to THIS specific user's isolated database file
user_db_path = get_user_db_path(current_user_id)
agent_db_conn = init_db(user_db_path)


def get_my_clients():
  return pd.read_sql("SELECT * FROM clients", agent_db_conn)


def save_my_client(client_id, full_name, phone_number, market_zone):
  cursor = agent_db_conn.cursor()
  cursor.execute(
      """
        INSERT OR REPLACE INTO clients (client_id, full_name, phone_number, market_zone, registration_date, registered_by)
        VALUES (?, ?, ?, ?, ?, ?)
    """,
      (
          client_id,
          full_name,
          phone_number,
          market_zone,
          datetime.now().strftime("%Y-%m-%d"),
          current_user_id,
      ),
  )
  agent_db_conn.commit()


def get_my_transactions():
  return pd.read_sql(
      "SELECT * FROM transactions ORDER BY timestamp DESC", agent_db_conn
  )


def save_my_transaction(
    tx_id, timestamp, client_id, client_name, frequency, amount, notes
):
  cursor = agent_db_conn.cursor()
  cursor.execute(
      """
        INSERT INTO transactions (transaction_id, timestamp, client_id, client_name, collector_id, frequency, amount, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """,
      (
          tx_id,
          timestamp,
          client_id,
          client_name,
          current_user_id,
          frequency,
          amount,
          notes,
      ),
  )
  agent_db_conn.commit()


# Sidebar User Info & Logout
st.sidebar.markdown(f"### 👤 Operator: {current_agent_name}")
st.sidebar.info(
    f"Role: **{current_role.upper()}**\n\nZone:"
    f" **{current_zone}**\n\nStorage: **Isolated Cloud Space**"
)
if st.sidebar.button("Log Out Session", use_container_width=True):
  st.session_state.auth_user = None
  st.session_state.user_info = None
  st.session_state.last_receipt = None
  st.rerun()

st.title("💼 SusuFlow Enterprise Command Centre")
st.markdown(
    f"*Secure, Private Collector Workspace (Data Isolated Per Agent)*"
)
st.markdown("---")

# Main Application Tabs
tab_list = [
    "👥 My Client Registration",
    "📥 My Daily / Weekly Transactions",
    "📊 My Loan Qualification Audit",
]
if current_role == "manager":
  tab_list.append("⚙️ Collector Access Control")
  tab_list.append("🏢 Master Agency Overview")

tabs = st.tabs(tab_list)
tab1 = tabs[0]
tab2 = tabs[1]
tab3 = tabs[2]
tab_access = tabs[3] if current_role == "manager" else None
tab_overview = tabs[4] if current_role == "manager" else None

# --- TAB 1: CLIENT REGISTRATION (ISOLATED TO AGENT'S DATABASE) ---
with tab1:
  st.markdown("### Register New Susu Client (Private to You)")

  df_my_clients = get_my_clients()
  registered_count = len(df_my_clients)
  max_allowed = 40  # Maximum cap per collector

  st.metric(
      "Your Personal Client Quota",
      f"{registered_count} / {max_allowed} Clients Registered",
  )

  if current_role == "collector" and registered_count >= max_allowed:
    st.error(
        "🚫 **Quota Reached:** You have reached your individual limit of 40"
        " clients in your private workspace."
    )
  else:
    with st.form("client_reg_form", clear_on_submit=True):
      col1, col2 = st.columns(2)
      with col1:
        c_name = st.text_input("Client Full Name")
        c_phone = st.text_input("Phone Number / Mobile Money Number")
      with col2:
        c_zone = st.text_input("Market Zone / Location", value=current_zone)
        c_id = st.text_input(
            "Client Account ID (e.g., ACC-001)",
            value=f"ACC-{datetime.now().strftime('%H%M%S')}",
        )

      submit_client = st.form_submit_button(
          "Register Client to My Private Space", use_container_width=True
      )

      if submit_client:
        if not c_name or not c_phone:
          st.error("❌ Please provide both client name and phone number.")
        else:
          if len(get_my_clients()) >= max_allowed:
            st.error("❌ Quota limit reached. Registration blocked.")
          else:
            save_my_client(c_id, c_name, c_phone, c_zone)
            st.success(
                f"✅ Client **{c_name}** successfully registered in your private"
                f" space with ID **{c_id}**!"
            )
            st.rerun()

  st.markdown("#### Your Private Registered Clients Directory")
  if df_my_clients.empty:
    st.info(
        "ℹ️ No clients registered in your private space yet. Your records are"
        " completely hidden from other collectors."
    )
  else:
    st.dataframe(df_my_clients, use_container_width=True)

# --- TAB 2: DAILY / WEEKLY TRANSACTIONS & INSTANT RECEIPT ---
with tab2:
  st.markdown("### Record Daily or Weekly Contributions")
  st.caption(
      "Log regular savings deposits to your private ledger and generate instant"
      " receipts."
  )

  df_my_clients = get_my_clients()

  if df_my_clients.empty:
    st.warning(
        "⚠️ Please register at least one client in your 'Client Registration'"
        " tab before posting transactions."
    )
  else:
    with st.form("tx_form", clear_on_submit=True):
      col1, col2 = st.columns(2)
      with col1:
        client_options = df_my_clients["client_id"].tolist()
        selected_client_id = st.selectbox(
            "Select Client Account",
            options=client_options,
            format_func=lambda x: f"{x} - {df_my_clients.loc[df_my_clients['client_id'] == x, 'full_name'].values[0]}",
        )
        frequency = st.selectbox(
            "Contribution Frequency", ["Daily Contribution", "Weekly Deposit"]
        )
      with col2:
        amount = st.number_input(
            "Amount Deposited (GHS)", min_value=0.0, format="%.2f"
        )
        notes = st.text_input("Remarks / Agent Notes", value="Regular Deposit")

      submit_tx = st.form_submit_button(
          "Post Contribution & Generate Receipt", use_container_width=True
      )

      if submit_tx:
        if amount <= 0:
          st.error("❌ Contribution amount must be greater than zero.")
        else:
          client_name = df_my_clients.loc[
              df_my_clients["client_id"] == selected_client_id, "full_name"
          ].values[0]
          tx_id = f"TXN-{datetime.now().strftime('%Y%m%d%H%M%S')}"
          tx_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

          save_my_transaction(
              tx_id,
              tx_timestamp,
              selected_client_id,
              client_name,
              frequency,
              amount,
              notes,
          )

          st.session_state.last_receipt = {
              "Transaction ID": tx_id,
              "Timestamp": tx_timestamp,
              "Client ID": selected_client_id,
              "Client Name": client_name,
              "Collector ID": current_user_id,
              "Frequency": frequency,
              "Amount (GHS)": amount,
              "Notes": notes,
          }
          st.success(
              f"✅ Recorded GHS {amount:.2f} ({frequency}) for {client_name}!"
          )

  if st.session_state.last_receipt:
    r = st.session_state.last_receipt
    st.markdown("---")
    st.markdown("### 🖨️ Official Instant Transaction Receipt")

    with st.container():
      st.markdown(
          f"""
            <div style="background-color: #f8f9fa; padding: 20px; border-radius: 10px; border: 2px dashed #0e1117; color: #000;">
                <h3 style="text-align: center; margin-bottom: 0;">🏛️ SUSUFLOW ENTERPRISE</h3>
                <p style="text-align: center; font-size: 0.9em; color: #555;">Official Field Collection Receipt</p>
                <hr style="border: 0.5px solid #ccc;">
                <p><b>Transaction ID:</b> {r['Transaction ID']}</p>
                <p><b>Date & Time:</b> {r['Timestamp']}</p>
                <p><b>Client ID:</b> {r['Client ID']} | <b>Name:</b> {r['Client Name']}</p>
                <p><b>Contribution Type:</b> {r['Frequency']}</p>
                <p><b>Amount Deposited:</b> <span style="font-size: 1.2em; color: green;"><b>GHS {r['Amount (GHS)']:,.2f}</b></span></p>
                <p><b>Field Collector:</b> {r['Collector ID']} ({current_agent_name})</p>
                <p><b>Remarks:</b> {r['Notes']}</p>
                <hr style="border: 0.5px solid #ccc;">
                <p style="text-align: center; font-size: 0.8em; color: #777;">Saved securely in your private cloud space.</p>
            </div>
            """,
          unsafe_allow_html=True,
      )

      receipt_text = (
          f"SUSUFLOW ENTERPRISE - OFFICIAL RECEIPT\n"
          f"----------------------------------------\n"
          f"Transaction ID: {r['Transaction ID']}\n"
          f"Date: {r['Timestamp']}\n"
          f"Client: {r['Client Name']} ({r['Client ID']})\n"
          f"Type: {r['Frequency']}\n"
          f"Amount: GHS {r['Amount (GHS)']:,.2f}\n"
          f"Collector: {current_agent_name}\n"
          f"Remarks: {r['Notes']}\n"
          f"----------------------------------------\n"
      )
      st.download_button(
          label="📥 Download Receipt (Text File)",
          data=receipt_text,
          file_name=f"Receipt_{r['Transaction ID']}.txt",
          mime="text/plain",
      )

  st.markdown("#### Your Private Transaction Ledger")
  df_tx = get_my_transactions()
  if df_tx.empty:
    st.info("ℹ️ No transactions recorded in your private space yet.")
  else:
    st.dataframe(df_tx, use_container_width=True)
    csv_bytes = df_tx.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="📥 Download My Ledger (CSV)",
        data=csv_bytes,
        file_name=f"susuflow_private_ledger_{current_user_id}_{datetime.now().strftime('%Y-%m-%d')}.csv",
        mime="text/csv",
    )

# --- TAB 3: LOAN QUALIFICATION & SAVINGS AUDIT ---
with tab3:
  st.markdown("### 💳 Your Clients' Loan Qualification Tracker")
  st.caption(
      "Calculates lifetime savings per client inside your private ledger."
  )

  df_my_clients = get_my_clients()
  df_tx = get_my_transactions()

  if df_my_clients.empty:
    st.info("ℹ️ No client data available for loan qualification assessment.")
  else:
    if not df_tx.empty:
      summary_df = (
          df_tx.groupby(["client_id", "client_name"])["amount"]
          .sum()
          .reset_index()
      )
      summary_df.rename(
          columns={"client_id": "Client ID", "amount": "Amount (GHS)"},
          inplace=True,
      )
    else:
      summary_df = df_my_clients[["client_id", "full_name"]].copy()
      summary_df.rename(
          columns={"client_id": "Client ID", "full_name": "Client Name"},
          inplace=True,
      )
      summary_df["Amount (GHS)"] = 0.0

    df_my_clients.rename(
        columns={
            "client_id": "Client ID",
            "full_name": "Full Name",
            "phone_number": "Phone Number",
            "market_zone": "Market Zone",
        },
        inplace=True,
    )
    merged_summary = pd.merge(
        df_my_clients[["Client ID", "Full Name", "Phone Number", "Market Zone"]],
        summary_df[["Client ID", "Amount (GHS)"]],
        on="Client ID",
        how="left",
    ).fillna({"Amount (GHS)": 0.0})


    def evaluate_loan(savings):
      if savings >= 200.0:
        return "Qualified (Tier 1 - 3x)", savings * 3.0
      elif savings >= 50.0:
        return "Qualified (Tier 2 - 2x)", savings * 2.0
      else:
        return "Pending Savings Target", 0.0


    merged_summary[[
        "Qualification Status",
        "Max Loan Limit (GHS)",
    ]] = merged_summary["Amount (GHS)"].apply(lambda x: pd.Series(evaluate_loan(x)))

    st.dataframe(merged_summary, use_container_width=True)

# --- TAB 4: COLLECTOR ACCESS CONTROL (MANAGER ONLY) ---
if tab_access:
  with tab_access:
    st.markdown("### ⚙️ Field Collector Access & Authorization Control")
    st.caption(
        "Authorize collector accounts before they can access their private"
        " workspaces."
    )

    collector_items = [
        (uid, data)
        for uid, data in users_dict.items()
        if data.get("role") == "collector"
    ]

    col_ctrl1, col_ctrl2 = st.columns([2, 1])
    with col_ctrl1:
      target_collector = st.selectbox(
          "Select Field Agent Account",
          options=[item[0] for item in collector_items],
          format_func=lambda x: f"{x} - {users_dict[x].get('full_name')} ({users_dict[x].get('zone')})",
      )

    current_status = bool(
        get_collector_approval(target_collector, default_val=False)
    )

    with col_ctrl2:
      st.markdown(
          f"**Current State:** {'🟢 Authorized' if current_status else '🔴'
          ' Locked'}"
      )

    action_col1, action_col2 = st.columns(2)
    with action_col1:
      if st.button("✅ Grant Access to Agent", use_container_width=True):
        set_collector_approval(target_collector, True)
        st.success(f"Access granted for {target_collector}!")
        st.rerun()
    with action_col2:
      if st.button("🚫 Revoke Access", use_container_width=True):
        set_collector_approval(target_collector, False)
        st.warning(f"Access revoked for {target_collector}.")
        st.rerun()

    st.markdown("#### Full Roster Authorization Status")
    status_df = pd.DataFrame([
        {
            "Agent ID": uid,
            "Full Name": data.get("full_name"),
            "Zone": data.get("zone"),
            "Access Status": (
                "Authorized"
                if get_collector_approval(uid, default_val=False)
                else "Locked"
            ),
        }
        for uid, data in users_dict.items()
        if data.get("role") == "collector"
    ])
    st.dataframe(status_df, use_container_width=True)

# --- TAB 5: MASTER AGENCY OVERVIEW (MANAGER ONLY) ---
if tab_overview:
  with tab_overview:
    st.markdown("### 🏢 Executive Master Agency Overview")
    st.caption(
        "Aggregates data across all collector private spaces for high-level"
        " auditing and decisions."
    )

    # Collect data from all individual collector databases
    all_agency_clients = []
    all_agency_tx = []

    for uid, data in users_dict.items():
      if data.get("role") == "collector":
        db_path = get_user_db_path(uid)
        if os.path.exists(db_path):
          try:
            temp_conn = sqlite3.connect(db_path)
            c_df = pd.read_sql("SELECT * FROM clients", temp_conn)
            t_df = pd.read_sql("SELECT * FROM transactions", temp_conn)
            temp_conn.close()
            if not c_df.empty:
              all_agency_clients.append(c_df)
            if not t_df.empty:
              all_agency_tx.append(t_df)
          except Exception:
            pass

    master_clients_df = (
        pd.concat(all_agency_clients, ignore_index=True)
        if all_agency_clients
        else pd.DataFrame()
    )
    master_tx_df = (
        pd.concat(all_agency_tx, ignore_index=True)
        if all_agency_tx
        else pd.DataFrame()
    )

    m1, m2, m3 = st.columns(3)
    total_clients_count = len(master_clients_df)
    m1.metric("Total Agency Clients", f"{total_clients_count} Registered")

    active_count = sum(
        1
        for uid in users_dict.keys()
        if users_dict[uid].get("role") == "collector"
        and get_collector_approval(uid, default_val=False)
    )
    m1.metric("Active Authorized Agents", f"{active_count} / 50 Deployed")

    total_vol = (
        master_tx_df["amount"].sum() if not master_tx_df.empty else 0.0
    )
    m2.metric("Total Agency Inflow", f"GHS {total_vol:,.2f}")
    m3.metric("Subscription Window", "Active (2026)")

    st.markdown("#### Aggregated Agency Transaction Inflows")
    if not master_tx_df.empty:
      freq_chart = (
          master_tx_df.groupby("frequency")["amount"].sum().reset_index()
      )
      st.bar_chart(freq_chart.set_index("frequency"))

      st.markdown("#### Complete Master Client Directory (All Agents)")
      st.dataframe(master_clients_df, use_container_width=True)
    else:
      st.info("ℹ️ No transactions recorded across agent workspaces yet.")