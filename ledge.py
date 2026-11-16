from datetime import datetime
import hashlib
import io
import os
import sqlite3
import pandas as pd
import streamlit as st

# ==========================================
# 1. PAGE CONFIGURATION
# ==========================================
st.set_page_config(
    page_title="SusuFlow Enterprise",
    page_icon="🔒",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ==========================================
# 2. DYNAMIC USER MANAGEMENT & ISOLATED DATABASES
# ==========================================
def init_auth_db():
  os.makedirs("secure_data", exist_ok=True)
  conn = sqlite3.connect(
      os.path.join("secure_data", "users_registry.db"), check_same_thread=False
  )
  cursor = conn.cursor()
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password_hash TEXT,
            full_name TEXT,
            zone TEXT,
            role TEXT,
            is_approved INTEGER,
            allow_edit INTEGER
        )
    """)
  conn.commit()
  return conn


auth_conn = init_auth_db()


def register_user(username, password_hash, full_name, zone, role="collector"):
  cursor = auth_conn.cursor()
  try:
    is_approved = 1 if role == "manager" else 0
    cursor.execute(
        """
            INSERT INTO users (username, password_hash, full_name, zone, role, is_approved, allow_edit)
            VALUES (?, ?, ?, ?, ?, ?, 0)
        """,
        (username, password_hash, full_name, zone, role, is_approved),
    )
    auth_conn.commit()
    return True, "Registration successful!"
  except sqlite3.IntegrityError:
    return False, "Username already exists. Choose a different username."


def get_user_credentials(username):
  cursor = auth_conn.cursor()
  cursor.execute(
      "SELECT username, password_hash, full_name, zone, role, is_approved,"
      " allow_edit FROM users WHERE username = ?",
      (username,),
  )
  row = cursor.fetchone()
  if row:
    return {
        "username": row[0],
        "password_hash": row[1],
        "full_name": row[2],
        "zone": row[3],
        "role": row[4],
        "is_approved": row[5],
        "allow_edit": row[6],
    }
  return None


def get_all_users_dict():
  cursor = auth_conn.cursor()
  cursor.execute(
      "SELECT username, password_hash, full_name, zone, role, is_approved,"
      " allow_edit FROM users"
  )
  rows = cursor.fetchall()
  users = {}
  for row in rows:
    users[row[0]] = {
        "password_hash": row[1],
        "full_name": row[2],
        "zone": row[3],
        "role": row[4],
        "is_approved": row[5],
        "allow_edit": row[6],
    }
  return users


def update_user_privileges(username, is_approved, allow_edit):
  cursor = auth_conn.cursor()
  cursor.execute(
      """
        UPDATE users SET is_approved = ?, allow_edit = ? WHERE username = ?
    """,
      (1 if is_approved else 0, 1 if allow_edit else 0, username),
  )
  auth_conn.commit()


# Ensure default Master Admin exists on first run (Username: rog3rs_admin, Password: admin123)
default_admin_hash = hashlib.sha256("admin123".encode()).hexdigest()
if not get_user_credentials("rog3rs_admin"):
  register_user(
      "rog3rs_admin",
      default_admin_hash,
      "Koffie Rogers (Master Admin)",
      "All Agency Zones",
      role="manager",
  )
  update_user_privileges("rog3rs_admin", is_approved=True, allow_edit=True)


def get_user_db_path(username):
  os.makedirs("secure_data", exist_ok=True)
  if username == "rog3rs_admin":
    return os.path.join("secure_data", "master_agency.db")
  else:
    return os.path.join("secure_data", f"db_{username}.db")


def init_user_db(db_path):
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
            notes TEXT,
            is_locked INTEGER DEFAULT 1
        )
    """)
  conn.commit()
  return conn


# ==========================================
# 3. SUBSCRIPTION PERIOD LOGIC
# ==========================================
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
      return False, "License status is inactive."
    if today < start_date:
      return False, f"Subscription period not started (Starts: {start_str})"
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
  )
  st.info(f"**Details:** {sub_message}")
  st.stop()


# ==========================================
# 6. SIDEBAR AUTHENTICATION & SIGN-UP GATE
# ==========================================
if not st.session_state.auth_user:
  st.sidebar.markdown("### 🔐 SusuFlow Enterprise Portal")
  auth_mode = st.sidebar.radio(
      "Select Action", ["Log In", "Sign Up (New Account)"]
  )

  if auth_mode == "Log In":
    st.sidebar.subheader("Operator Login")
    login_user = st.sidebar.text_input("Username").strip()
    login_pass = st.sidebar.text_input("Password", type="password")

    if st.sidebar.button("Log In to My Workspace", use_container_width=True):
      user_data = get_user_credentials(login_user)
      if user_data:
        entered_hash = hashlib.sha256(login_pass.encode()).hexdigest()
        if entered_hash == user_data["password_hash"]:
          is_manager = user_data["role"] == "manager"
          is_approved = bool(user_data["is_approved"])

          if not is_manager and not is_approved:
            st.sidebar.error(
                "🚫 Access Pending: Master Admin has not yet authorized your"
                " account."
            )
          else:
            st.session_state.auth_user = user_data["username"]
            st.session_state.user_info = user_data
            st.session_state.last_receipt = None
            st.rerun()
        else:
          st.sidebar.error("❌ Incorrect password.")
      else:
        st.sidebar.error(
            "❌ Username not found. Please sign up for a new account."
        )

  else:
    st.sidebar.subheader("Create New Account")
    new_user = st.sidebar.text_input("Choose Username").strip()
    new_pass = st.sidebar.text_input("Choose Password", type="password")
    new_name = st.sidebar.text_input("Full Name").strip()
    new_zone = st.sidebar.text_input(
        "Assigned Market Zone", value="Market Zone 1"
    ).strip()

    if st.sidebar.button("Register Account", use_container_width=True):
      if not new_user or not new_pass or not new_name:
        st.sidebar.error("❌ Please fill in all required fields.")
      else:
        pass_hash = hashlib.sha256(new_pass.encode()).hexdigest()
        success, msg = register_user(
            new_user, pass_hash, new_name, new_zone, role="collector"
        )
        if success:
          st.sidebar.success(
              "✅ Account created successfully! Please wait for Master Admin"
              " approval before logging in."
          )
        else:
          st.sidebar.error(f"❌ {msg}")

  st.stop()


# ==========================================
# 7. MAIN APP DASHBOARD & ISOLATED DATA HANDLING
# ==========================================
current_user_id = st.session_state.auth_user
fresh_user_data = get_user_credentials(current_user_id)

current_role = fresh_user_data.get("role", "collector")
current_agent_name = fresh_user_data.get("full_name", "Field Agent")
current_zone = fresh_user_data.get("zone", "Market Zone")
user_allow_edit = (
    1 if current_role == "manager" else fresh_user_data.get("allow_edit", 0)
)

user_db_path = get_user_db_path(current_user_id)
agent_db_conn = init_user_db(user_db_path)


# --- DATABASE HELPER FUNCTIONS (DEFINED BEFORE TABS) ---
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
        INSERT INTO transactions (transaction_id, timestamp, client_id, client_name, collector_id, frequency, amount, notes, is_locked)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
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
  
  def update_my_transaction(tx_id, frequency, amount, notes):
  cursor = agent_db_conn.cursor()
  cursor.execute(
      """
        UPDATE transactions SET frequency = ?, amount = ?, notes = ? WHERE transaction_id = ?
    """,
      (frequency, amount, notes, tx_id),
  )
  agent_db_conn.commit()


# Sidebar Info & Logout
st.sidebar.markdown(f"### 👤 Operator: {current_agent_name}")
edit_status_badge = (
    "🔓 Edit Rights Granted" if user_allow_edit else "🔒 Locked (No Edit)"
)
st.sidebar.info(
    f"Role: **{current_role.upper()}**\n\nZone:"
    f" **{current_zone}**\n\nPrivilege: **{edit_status_badge}**"
)
if st.sidebar.button("Log Out Session", use_container_width=True):
  st.session_state.auth_user = None
  st.session_state.user_info = None
  st.session_state.last_receipt = None
  st.rerun()

st.title("💼 SusuFlow Enterprise Command Centre")
st.markdown("*Strictly Isolated Private Collector Workspace*")
st.markdown("---")

# Main Application Tabs
tab_list = [
    "👥 Client Registration",
    "📥 Daily/Weekly Transactions & Receipts",
    "📊 Loan Qualification Audit",
]
if current_role == "manager":
  tab_list.append("⚙️ Collector Access & Edit Control")
  tab_list.append("🏢 Master Agency Overview")

tabs = st.tabs(tab_list)
tab1 = tabs[0]
tab2 = tabs[1]
tab3 = tabs[2]
tab_access = tabs[3] if current_role == "manager" else None
tab_overview = tabs[4] if current_role == "manager" else None

# --- TAB 1: CLIENT REGISTRATION ---
with tab1:
  st.markdown("### Register New Susu Client (Private Space)")
  df_my_clients = get_my_clients()
  registered_count = len(df_my_clients)
  max_allowed = 40

  st.metric(
      "Your Personal Client Quota",
      f"{registered_count} / {max_allowed} Clients Registered",
  )

  if current_role == "collector" and registered_count >= max_allowed:
    st.error(
        "🚫 **Quota Reached:** You have reached your individual limit of 40"
        " clients."
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
          "Register Client", use_container_width=True
      )

      if submit_client:
        if not c_name or not c_phone:
          st.error("❌ Please provide both client name and phone number.")
        else:
          save_my_client(c_id, c_name, c_phone, c_zone)
          st.success(
              f"✅ Client **{c_name}** successfully registered with ID"
              f" **{c_id}**!"
          )
          st.rerun()

  st.markdown("#### Your Registered Clients Directory")
  if df_my_clients.empty:
    st.info(
        "ℹ️ No clients registered in your private space yet. Your records are"
        " completely clean and private to you."
    )
  else:
    st.dataframe(df_my_clients, use_container_width=True)

# --- TAB 2: TRANSACTIONS & EXPORTS ---
with tab2:
  st.markdown("### Record Contributions & Protected Exports")
  df_my_clients = get_my_clients()

  if df_my_clients.empty:
    st.warning("⚠️ Please register at least one client first.")
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
        notes = st.text_input("Remarks / Notes", value="Regular Deposit")

      submit_tx = st.form_submit_button(
          "Post Contribution & Lock Entry", use_container_width=True
      )

      if submit_tx:
        if amount <= 0:
          st.error("❌ Amount must be greater than zero.")
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
              " Entry is now locked."
          )

  if st.session_state.last_receipt:
    r = st.session_state.last_receipt
    st.markdown("---")
    st.markdown("### 🖨️ Official Instant Transaction Receipt")
    st.markdown(
        f"""
        <div style="background-color: #f8f9fa; padding: 20px; border-radius: 10px; border: 2px dashed #0e1117; color: #000;">
            <h3 style="text-align: center; margin-bottom: 0;">🏛️ SUSUFLOW ENTERPRISE</h3>
            <p style="text-align: center; font-size: 0.9em; color: #555;">Official Locked Collection Receipt</p>
            <hr style="border: 0.5px solid #ccc;">
            <p><b>Transaction ID:</b> {r['Transaction ID']}</p>
            <p><b>Date & Time:</b> {r['Timestamp']}</p>
            <p><b>Client ID:</b> {r['Client ID']} | <b>Name:</b> {r['Client Name']}</p>
            <p><b>Contribution Type:</b> {r['Frequency']}</p>
            <p><b>Amount Deposited:</b> <span style="font-size: 1.2em; color: green;"><b>GHS {r['Amount (GHS)']:,.2f}</b></span></p>
            <p><b>Field Collector:</b> {r['Collector ID']} ({current_agent_name})</p>
            <p><b>Remarks:</b> {r['Notes']}</p>
            <hr style="border: 0.5px solid #ccc;">
            <p style="text-align: center; font-size: 0.8em; color: #777;">Locked in isolated database partition.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

  st.markdown("#### 📝 Transaction Ledger & Edit Management")
  df_tx = get_my_transactions()

  if df_tx.empty:
    st.info("ℹ️ No transactions recorded yet in your private workspace.")
  else:
    if not user_allow_edit:
      st.info(
          "🔒 **Edit Protection Active:** Entries are locked. You cannot modify"
          " past transactions unless Master Admin grants you edit access."
      )
      st.dataframe(df_tx, use_container_width=True)
    else:
      st.warning(
          "🔓 **Edit Access Granted:** You are permitted to modify existing"
          " transaction records."
      )
      selected_tx_to_edit = st.selectbox(
          "Select Transaction ID to Edit",
          options=df_tx["transaction_id"].tolist(),
      )

      if selected_tx_to_edit:
        current_row = df_tx.loc[
            df_tx["transaction_id"] == selected_tx_to_edit
        ].iloc[0]
        with st.form("edit_tx_form"):
          edit_freq = st.selectbox(
              "Edit Frequency",
              ["Daily Contribution", "Weekly Deposit"],
              index=(
                  0 if current_row["frequency"] == "Daily Contribution" else 1
              ),
          )
          edit_amount = st.number_input(
              "Edit Amount (GHS)",
              value=float(current_row["amount"]),
              format="%.2f",
          )
          edit_notes = st.text_input("Edit Remarks", value=current_row["notes"])

          update_btn = st.form_submit_button(
              "Save Changes to Transaction Record"
          )
          if update_btn:
            update_my_transaction(
                selected_tx_to_edit, edit_freq, edit_amount, edit_notes
            )
            st.success(
                f"✅ Transaction {selected_tx_to_edit} successfully updated!"
            )
            st.rerun()

      st.dataframe(df_tx, use_container_width=True)

    st.markdown("#### 📥 Secure Export Options")
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
      df_tx.to_excel(writer, index=False, sheet_name="Ledger")
    excel_data = output.getvalue()

    st.download_button(
        label="📥 Download Protected Ledger (Excel .xlsx)",
        data=excel_data,
        file_name=f"SusuFlow_Ledger_{current_user_id}_{datetime.now().strftime('%Y-%m-%d')}.xlsx",
        mime=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
    )

# --- TAB 3: LOAN QUALIFICATION AUDIT ---
with tab3:
  st.markdown("### 💳 Loan Qualification Tracker")
  df_my_clients = get_my_clients()
  df_tx = get_my_transactions()

  if df_my_clients.empty:
    st.info("ℹ️ No client data available.")
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
    ]] = merged_summary["Amount (GHS)"].apply(
        lambda x: pd.Series(evaluate_loan(x))
    )

    st.dataframe(merged_summary, use_container_width=True)

# --- TAB 4: COLLECTOR ACCESS & EDIT CONTROL (MANAGER ONLY) ---
if tab_access:
  with tab_access:
    st.markdown("### ⚙️ Collector Authorization & Edit Privilege Control")
    users_dict = get_all_users_dict()
    collector_items = [
        (uid, data)
        for uid, data in users_dict.items()
        if data.get("role") == "collector"
    ]

    if not collector_items:
      st.info("ℹ️ No registered collector accounts found yet.")
    else:
      col_ctrl1, col_ctrl2 = st.columns([2, 1])
      with col_ctrl1:
        target_collector = st.selectbox(
            "Select Field Agent Account",
            options=[item[0] for item in collector_items],
            format_func=lambda x: f"{x} - {users_dict[x].get('full_name')} ({users_dict[x].get('zone')})",
        )

      cur_app = users_dict[target_collector].get("is_approved", 0)
      cur_edit = users_dict[target_collector].get("allow_edit", 0)

      with col_ctrl2:
        st.markdown(
            f"**Status:** {'🟢 Authorized' if cur_app else '🔴 Locked'}\n\n**Edit"
            f" Permission:** {'🔓 Allowed' if cur_edit else '🔒 Restricted'}"
        )

      action_col1, action_col2, action_col3 = st.columns(3)
      with action_col1:
        if st.button("✅ Authorize Agent", use_container_width=True):
          update_user_privileges(
              target_collector, is_approved=True, allow_edit=cur_edit
          )
          st.success(f"Agent {target_collector} authorized!")
          st.rerun()
      with action_col2:
        if st.button("🔓 Grant Edit Access", use_container_width=True):
          update_user_privileges(
              target_collector, is_approved=cur_app, allow_edit=True
          )
          st.success(f"Edit privileges granted to {target_collector}!")
          st.rerun()
      with action_col3:
        if st.button("🔒 Revoke Edit Access", use_container_width=True):
          update_user_privileges(
              target_collector, is_approved=cur_app, allow_edit=False
          )
          st.warning(f"Edit privileges revoked for {target_collector}.")
          st.rerun()

      st.markdown("#### Full Roster Authorization & Privilege Status")
      status_df = pd.DataFrame([
          {
              "Username": uid,
              "Full Name": data.get("full_name"),
              "Zone": data.get("zone"),
              "Login Status": (
                  "Authorized" if data.get("is_approved") else "Locked"
              ),
              "Edit Rights": (
                  "Allowed" if data.get("allow_edit") else "Restricted"
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
    users_dict = get_all_users_dict()
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
    m1.metric("Total Agency Clients", f"{len(master_clients_df)} Registered")
    total_vol = master_tx_df["amount"].sum() if not master_tx_df.empty else 0.0
    m2.metric("Total Agency Inflow", f"GHS {total_vol:,.2f}")
    m3.metric("Subscription Window", "Active (2026)")

    st.markdown("#### Aggregated Agency Transaction Inflows")
    if not master_tx_df.empty:
      freq_chart = (
          master_tx_df.groupby("frequency")["amount"].sum().reset_index()
      )
      st.bar_chart(freq_chart.set_index("frequency"))
      st.markdown("#### Complete Master Client Directory")
      st.dataframe(master_clients_df, use_container_width=True)
    else:
      st.info("ℹ️ No transactions recorded across agent workspaces yet.")