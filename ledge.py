from datetime import datetime
import hashlib
import io
import os
import sqlite3
import urllib.parse
import pandas as pd
import streamlit as st

# ==========================================
# 1. PAGE CONFIGURATION & CUSTOM CSS STYLING
# ==========================================
st.set_page_config(
    page_title="SusuFlow Enterprise",
    page_icon="🔒",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .main {
        background-color: #f4f6f9;
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    }
    .dev-badge {
        background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
        color: white;
        padding: 12px 18px;
        border-radius: 8px;
        text-align: center;
        font-weight: 600;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        margin-top: 15px;
        margin-bottom: 15px;
        letter-spacing: 0.5px;
    }
    .landing-banner {
        background: linear-gradient(135deg, #0f2027, #203a43, #2c5364);
        padding: 40px;
        border-radius: 15px;
        color: white;
        box-shadow: 0 10px 25px rgba(0,0,0,0.2);
        margin-bottom: 25px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ==========================================
# 2. PERSISTENT DATABASE INITIALIZATION
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
            location TEXT,
            work TEXT,
            phone_number TEXT,
            email TEXT,
            zone TEXT,
            role TEXT,
            is_approved INTEGER,
            is_frozen INTEGER DEFAULT 0,
            max_clients INTEGER DEFAULT 50,
            recovery_contact TEXT DEFAULT ''
        )
    """)
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
  cursor.execute(
      "INSERT OR IGNORE INTO app_settings (key, value) VALUES"
      " ('global_client_limit', '5000')"
  )

  for col_sql in [
      "ALTER TABLE users ADD COLUMN is_frozen INTEGER DEFAULT 0",
      "ALTER TABLE users ADD COLUMN max_clients INTEGER DEFAULT 50",
      "ALTER TABLE users ADD COLUMN recovery_contact TEXT DEFAULT ''",
      "ALTER TABLE users ADD COLUMN location TEXT DEFAULT ''",
      "ALTER TABLE users ADD COLUMN work TEXT DEFAULT ''",
      "ALTER TABLE users ADD COLUMN phone_number TEXT DEFAULT ''",
      "ALTER TABLE users ADD COLUMN email TEXT DEFAULT ''",
  ]:
    try:
      cursor.execute(col_sql)
    except sqlite3.OperationalError:
      pass

  conn.commit()
  return conn


auth_conn = init_auth_db()


def register_user(
    username,
    password_hash,
    full_name,
    location,
    work,
    phone_number,
    email,
    zone,
    role="collector",
    recovery_contact="",
):
  cursor = auth_conn.cursor()
  try:
    is_approved = 1 if role == "manager" else 1
    cursor.execute(
        """
            INSERT INTO users (username, password_hash, full_name, location, work, phone_number, email, zone, role, is_approved, is_frozen, max_clients, recovery_contact)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 50, ?)
        """,
        (
            username,
            password_hash,
            full_name,
            location,
            work,
            phone_number,
            email,
            zone,
            role,
            is_approved,
            recovery_contact.strip().lower(),
        ),
    )
    auth_conn.commit()
    return True, "Registration successful!"
  except sqlite3.IntegrityError:
    return False, "Username already exists. Choose a different username."


def get_user_credentials(username):
  cursor = auth_conn.cursor()
  cursor.execute(
      "SELECT username, password_hash, full_name, location, work,"
      " phone_number, email, zone, role, is_approved, is_frozen, max_clients,"
      " recovery_contact FROM users WHERE username = ?",
      (username,),
  )
  row = cursor.fetchone()
  if row:
    return {
        "username": row[0],
        "password_hash": row[1],
        "full_name": row[2],
        "location": row[3],
        "work": row[4],
        "phone_number": row[5],
        "email": row[6],
        "zone": row[7],
        "role": row[8],
        "is_approved": row[9],
        "is_frozen": row[10],
        "max_clients": row[11] if row[11] is not None else 50,
        "recovery_contact": row[12] if row[12] else "",
    }
  return None


def get_all_users_dict():
  cursor = auth_conn.cursor()
  cursor.execute(
      "SELECT username, password_hash, full_name, location, work,"
      " phone_number, email, zone, role, is_approved, is_frozen, max_clients,"
      " recovery_contact FROM users"
  )
  rows = cursor.fetchall()
  users = {}
  for row in rows:
    users[row[0]] = {
        "password_hash": row[1],
        "full_name": row[2],
        "location": row[3],
        "work": row[4],
        "phone_number": row[5],
        "email": row[6],
        "zone": row[7],
        "role": row[8],
        "is_approved": row[9],
        "is_frozen": row[10],
        "max_clients": row[11] if row[11] is not None else 50,
        "recovery_contact": row[12] if row[12] else "",
    }
  return users


def update_collector_quota(username, max_clients, is_frozen):
  cursor = auth_conn.cursor()
  cursor.execute(
      "UPDATE users SET max_clients = ?, is_frozen = ? WHERE username = ?",
      (int(max_clients), int(is_frozen), username),
  )
  auth_conn.commit()


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
            location TEXT,
            work TEXT,
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
            phone_number TEXT,
            transaction_type TEXT,
            location TEXT,
            collector_id TEXT,
            amount REAL,
            notes TEXT,
            is_locked INTEGER DEFAULT 1
        )
    """)
  conn.commit()
  return conn


# Ensure default Master Admin exists on first run
default_admin_hash = hashlib.sha256("admin123".encode()).hexdigest()
if not get_user_credentials("rog3rs_admin"):
  register_user(
      "rog3rs_admin",
      default_admin_hash,
      "Koffie Rogers (Master Admin)",
      "Accra",
      "System Administrator",
      "0542470810",
      "admin@susuflow.com",
      "All Agency Zones",
      role="manager",
      recovery_contact="0542470810",
  )


# ==========================================
# 3. SESSION STATE INITIALIZATION
# ==========================================
if "auth_user" not in st.session_state:
  st.session_state.auth_user = None
if "last_receipt" not in st.session_state:
  st.session_state.last_receipt = None


# ==========================================
# 4. AUTHENTICATION & REGISTRATION
# ==========================================
if not st.session_state.auth_user:
  col_landing, col_auth = st.columns([1.2, 1])

  with col_landing:
    st.markdown(
        """
        <div class="landing-banner">
            <h1 style="color: #ffffff; margin-bottom: 10px;">🏛️ SusuFlow Enterprise</h1>
            <p style="font-size: 1.1em; color: #d0d7de;">Secure micro-finance management platform with permanent SQLite database storage and admin quota regulation.</p>
            <hr style="border-color: rgba(255,255,255,0.2);">
            <ul style="list-style-type: none; padding-left: 0; line-height: 2.2em; font-size: 1.05em;">
                <li>👤 <b>Detailed Profiles:</b> Full Name, Location, Work, Phone, & Email.</li>
                <li>⚙️ <b>Admin Quota Control:</b> Regulate client registration caps per collector.</li>
                <li>🗂️ <b>Permanent Storage:</b> All data is safely saved on disk and never lost.</li>
                <li>📥 <b>Neat Receipts:</b> Instant dispatch via WhatsApp.</li>
            </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )

  with col_auth:
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
            if user_data.get("is_frozen", 0) == 1:
              st.sidebar.error("🚫 Account is frozen by Master Admin.")
            else:
              st.session_state.auth_user = user_data["username"]
              st.rerun()
          else:
            st.sidebar.error("❌ Incorrect password.")
        else:
          st.sidebar.error("❌ Username not found.")

    else:
      st.sidebar.subheader("📝 Register New Account")
      reg_user = st.sidebar.text_input("Choose Username").strip()
      reg_pass = st.sidebar.text_input("Choose Password", type="password")
      reg_name = st.sidebar.text_input("1. Full Name").strip()
      reg_loc = st.sidebar.text_input("2. Location").strip()
      reg_work = st.sidebar.text_input("3. Work").strip()
      reg_phone = st.sidebar.text_input("4. Phone Number").strip()
      reg_email = st.sidebar.text_input("5. Email (Optional)").strip()
      reg_zone = st.sidebar.text_input(
          "Assigned Market Zone", value="Market Zone 1"
      ).strip()

      if st.sidebar.button("Register & Access Workspace", use_container_width=True):
        if not reg_user or not reg_pass or not reg_name or not reg_phone:
          st.sidebar.error(
              "❌ Please fill in required fields (Username, Password, Full"
              " Name, Phone Number)."
          )
        else:
          pass_hash = hashlib.sha256(reg_pass.encode()).hexdigest()
          success, msg = register_user(
              reg_user,
              pass_hash,
              reg_name,
              reg_loc,
              reg_work,
              reg_phone,
              reg_email,
              reg_zone,
              role="collector",
              recovery_contact=reg_phone,
          )
          if success:
            st.session_state.auth_user = reg_user
            st.rerun()
          else:
            st.sidebar.error(f"❌ {msg}")

    st.sidebar.markdown(
        """
        <div class="dev-badge">
            👨‍💻 Developer: rog3rs<br>📞 0542470810
        </div>
        """,
        unsafe_allow_html=True,
    )
  st.stop()


# ==========================================
# 5. DASHBOARD & PERSISTENT DATA HANDLING
# ==========================================
current_user_id = st.session_state.auth_user
fresh_user_data = get_user_credentials(current_user_id)

current_role = fresh_user_data.get("role", "collector")
current_agent_name = fresh_user_data.get("full_name", "Field Agent")
current_zone = fresh_user_data.get("zone", "Market Zone")
max_allowed_clients = fresh_user_data.get("max_clients", 50)

user_db_path = get_user_db_path(current_user_id)
agent_db_conn = init_user_db(user_db_path)


def get_my_clients():
  return pd.read_sql("SELECT * FROM clients", agent_db_conn)


def save_my_client(client_id, full_name, phone_number, location, work, zone):
  cursor = agent_db_conn.cursor()
  cursor.execute(
      """
        INSERT OR REPLACE INTO clients (client_id, full_name, phone_number, location, work, market_zone, registration_date, registered_by)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """,
      (
          client_id,
          full_name,
          phone_number,
          location,
          work,
          zone,
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
    tx_id,
    timestamp,
    client_id,
    client_name,
    phone_number,
    tx_type,
    location,
    amount,
    notes,
):
  cursor = agent_db_conn.cursor()
  cursor.execute(
      """
        INSERT INTO transactions (transaction_id, timestamp, client_id, client_name, phone_number, transaction_type, location, collector_id, amount, notes, is_locked)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
    """,
      (
          tx_id,
          timestamp,
          client_id,
          client_name,
          phone_number,
          tx_type,
          location,
          current_user_id,
          amount,
          notes,
      ),
  )
  agent_db_conn.commit()


# Sidebar Workspace Info
st.sidebar.markdown(f"### 👤 Operator: {current_agent_name}")
st.sidebar.info(
    f"Role: **{current_role.upper()}**\n\nClient Quota Limit:"
    f" **{max_allowed_clients}**\n\nDatabase:\n`secure_data/{os.path.basename(user_db_path)}`"
)

if st.sidebar.button("Log Out Session", use_container_width=True):
  st.session_state.auth_user = None
  st.rerun()

st.sidebar.markdown(
    """
    <div class="dev-badge">
        👨‍💻 Developer: rog3rs<br>📞 0542470810
    </div>
    """,
    unsafe_allow_html=True,
)

# Header
head_col1, head_col2 = st.columns([3, 1])
with head_col1:
  st.title("💼 SusuFlow Enterprise Command Centre")
  st.markdown("*Persistent Local SQLite Storage & Admin Quota Management*")
with head_col2:
  st.markdown(
      "<div style='text-align: right; padding-top: 15px; font-size: 0.9em;"
      " color: #333; background: #fff; padding: 8px 12px; border-radius: 6px;"
      " border: 1px solid #ddd;'><b>Developer:</b> rog3rs<br><b>Contact:</b>"
      " 0542470810</div>",
      unsafe_allow_html=True,
  )
st.markdown("---")

tab_list = [
    "👥 Client Registration & Directory",
    "📥 Transaction Recording & Receipts",
    "📊 Persistent Records Auditor",
]
if current_role == "manager":
  tab_list.append("⚙️ Master Admin & Collector Oversight")

tabs = st.tabs(tab_list)
tab1 = tabs[0]
tab2 = tabs[1]
tab3 = tabs[2]
tab_admin = tabs[3] if current_role == "manager" else None

# --- TAB 1: CLIENT REGISTRATION ---
with tab1:
  st.markdown("### Register New Client Account (Persistent Storage)")
  df_clients_check = get_my_clients()
  current_registered_count = len(df_clients_check)

  st.metric(
      "Your Client Registration Quota",
      f"{current_registered_count} / {max_allowed_clients} Clients Registered",
  )

  if current_role == "collector" and current_registered_count >= max_allowed_clients:
    st.error(
        f"🚫 **Quota Reached:** You have reached your assigned maximum limit"
        f" of {max_allowed_clients} clients. Contact Master Admin to increase"
        " your quota."
    )
  else:
    with st.form("client_reg_form", clear_on_submit=True):
      col1, col2 = st.columns(2)
      with col1:
        c_name = st.text_input("1. Full Name / Account Name")
        c_loc = st.text_input("2. Location")
        c_work = st.text_input("3. Work / Occupation")
      with col2:
        c_phone = st.text_input("4. Phone Number")
        c_email = st.text_input("5. Email (Optional)")
        c_zone = st.text_input("Market Zone", value=current_zone)

      c_id = st.text_input(
          "Client ID", value=f"ACC-{datetime.now().strftime('%H%M%S')}"
      )

      submit_client = st.form_submit_button(
          "Save Client Record Permanently", use_container_width=True
      )
      if submit_client:
        if not c_name or not c_phone:
          st.error("❌ Please provide Client Name and Phone Number.")
        else:
          save_my_client(c_id, c_name, c_phone, c_loc, c_work, c_zone)
          st.success(
              f"✅ Client **{c_name}** successfully registered and saved!"
          )
          st.rerun()

  st.markdown("---")
  st.markdown("#### 📋 Saved Client Directory (Persistent)")
  if df_clients_check.empty:
    st.info("ℹ️ No clients registered yet. Records saved here remain intact.")
  else:
    st.dataframe(df_clients_check, use_container_width=True)
    
    # --- TAB 2: TRANSACTION RECORDING & RECEIPTS ---
with tab2:
  st.markdown("### Record Transaction & Generate Neat Receipt")
  df_clients = get_my_clients()

  if df_clients.empty:
    st.warning("⚠️ Please register a client in Tab 1 first.")
  else:
    with st.form("tx_form", clear_on_submit=True):
      col1, col2 = st.columns(2)
      with col1:
        client_options = df_clients["client_id"].tolist()
        selected_client_id = st.selectbox(
            "Select Client ID",
            options=client_options,
            format_func=lambda x: f"{x} - {df_clients.loc[df_clients['client_id'] == x, 'full_name'].values[0]}",
        )
        tx_type = st.selectbox(
            "Type of Transaction",
            [
                "Daily Contribution",
                "Weekly Deposit",
                "Loan Disbursement",
                "Withdrawal",
            ],
        )
        amount = st.number_input("Amount (GHS)", min_value=0.0, format="%.2f")
      with col2:
        tx_loc = st.text_input(
            "Transaction Location",
            value=df_clients.loc[
                df_clients["client_id"] == selected_client_id, "location"
            ].values[0]
            if not df_clients.empty
            else "",
        )
        notes = st.text_input("Remarks / Notes", value="Standard Entry")

      submit_tx = st.form_submit_button(
          "Record Transaction Permanently", use_container_width=True
      )

      if submit_tx:
        if amount <= 0:
          st.error("❌ Amount must be greater than zero.")
        else:
          c_row = df_clients.loc[
              df_clients["client_id"] == selected_client_id
          ].iloc[0]
          tx_id = f"TXN-{datetime.now().strftime('%Y%m%d%H%M%S')}"
          tx_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

          save_my_transaction(
              tx_id,
              tx_time,
              selected_client_id,
              c_row["full_name"],
              c_row["phone_number"],
              tx_type,
              tx_loc,
              amount,
              notes,
          )

          st.session_state.last_receipt = {
              "Transaction ID": tx_id,
              "Automated Date": tx_time,
              "Client ID": selected_client_id,
              "Account Name": c_row["full_name"],
              "Phone Number": c_row["phone_number"],
              "Location": tx_loc,
              "Transaction Type": tx_type,
              "Amount (GHS)": amount,
              "Notes": notes,
          }
          st.success("✅ Transaction recorded and saved permanently!")

  if st.session_state.last_receipt:
    r = st.session_state.last_receipt
    st.markdown("---")
    st.markdown("### 🖨️ Organised & Neat Transaction Receipt")
    receipt_text = (
        f"🏛️ *SUSUFLOW ENTERPRISE RECEIPT*\n"
        f"----------------------------------------\n"
        f"Tx ID: {r['Transaction ID']}\n"
        f"Automated Date: {r['Automated Date']}\n"
        f"Client ID: {r['Client ID']}\n"
        f"Account Name: {r['Account Name']}\n"
        f"Phone Number: {r['Phone Number']}\n"
        f"Location: {r['Location']}\n"
        f"Transaction Type: {r['Transaction Type']}\n"
        f"Amount: GHS {r['Amount (GHS)']:,.2f}\n"
        f"Remarks: {r['Notes']}\n"
        f"----------------------------------------\n"
        f"Status: PERMANENTLY SAVED & SECURED"
    )

    st.markdown(
        f"""
        <div style="background-color: #ffffff; padding: 25px; border-radius: 12px; border: 2px solid #1e3c72; color: #000; box-shadow: 0 4px 15px rgba(0,0,0,0.05);">
            <h3 style="text-align: center; color: #1e3c72; margin-bottom: 0;">🏛️ SUSUFLOW ENTERPRISE</h3>
            <p style="text-align: center; font-size: 0.9em; color: #555;">Official Verified Transaction Receipt</p>
            <hr style="border: 0.5px solid #ddd;">
            <p><b>Transaction ID:</b> {r['Transaction ID']}</p>
            <p><b>Automated Date & Time:</b> {r['Automated Date']}</p>
            <p><b>Client ID:</b> {r['Client ID']} | <b>Account Name:</b> {r['Account Name']}</p>
            <p><b>Phone Number:</b> {r['Phone Number']} | <b>Location:</b> {r['Location']}</p>
            <p><b>Transaction Type:</b> {r['Transaction Type']}</p>
            <p><b>Amount:</b> <span style="font-size: 1.2em; color: #2e7d32;"><b>GHS {r['Amount (GHS)']:,.2f}</b></span></p>
            <p><b>Remarks:</b> {r['Notes']}</p>
            <hr style="border: 0.5px solid #ddd;">
            <p style="text-align: center; font-size: 0.8em; color: #777;">Permanently stored in SQLite database partition.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    wa_text = urllib.parse.quote(receipt_text)
    clean_ph = "".join(filter(str.isdigit, str(r["Phone Number"])))
    wa_url = (
        f"https://wa.me/{clean_ph}?text={wa_text}"
        if clean_ph
        else f"https://wa.me/?text={wa_text}"
    )
    st.markdown(
        f'<p style="text-align: center; margin-top: 15px;"><a href="{wa_url}"'
        ' target="_blank" style="display:inline-block; background-color:#25D366;'
        ' color:white; padding:10px 25px; border-radius:6px;'
        ' text-decoration:none; font-weight:bold;">💬 Share Neat Receipt via'
        " WhatsApp</a></p>",
        unsafe_allow_html=True,
    )

# --- TAB 3: PERSISTENT RECORDS AUDITOR ---
with tab3:
  st.markdown("### 📊 All Persistent Transaction & Client Records")
  st.caption(
      "All records kept on the app remain stored permanently on disk so data is"
      " never lost."
  )
  df_tx = get_my_transactions()
  if df_tx.empty:
    st.info("ℹ️ No transactions recorded yet.")
  else:
    st.dataframe(df_tx, use_container_width=True)

# --- TAB 4: MASTER ADMIN & COLLECTOR OVERSIGHT (MANAGER ONLY) ---
if tab_admin:
  with tab_admin:
    st.markdown(
        "### ⚙️ Master Admin Dashboard: Collector Oversight & Quota Regulation"
    )
    st.caption(
        "Review all registered collectors, monitor total client registrations,"
        " and regulate client quotas per collector."
    )

    users_dict = get_all_users_dict()
    collector_items = [
        (uid, data)
        for uid, data in users_dict.items()
        if data.get("role") == "collector"
    ]

    if not collector_items:
      st.info("ℹ️ No collector accounts registered yet.")
    else:
      roster_data = []
      for uid, data in collector_items:
        agent_db = get_user_db_path(uid)
        client_count = 0
        if os.path.exists(agent_db):
          try:
            t_conn = sqlite3.connect(agent_db)
            c_df = pd.read_sql("SELECT COUNT(*) FROM clients", t_conn)
            t_conn.close()
            client_count = int(c_df.iloc[0, 0])
          except Exception:
            pass

        roster_data.append({
            "Username": uid,
            "Full Name": data.get("full_name"),
            "Phone": data.get("phone_number"),
            "Zone": data.get("zone"),
            "Clients Registered": client_count,
            "Max Quota Allowed": data.get("max_clients", 50),
            "Status": (
                "❄️ Frozen" if data.get("is_frozen", 0) == 1 else "🟢 Active"
            ),
        })

      roster_df = pd.DataFrame(roster_data)
      st.markdown("#### 📋 Agency Roster & Total Client Registrations")
      st.dataframe(roster_df, use_container_width=True)

      st.markdown("---")
      st.markdown("#### 🎛️ Regulate Collector Quota & Account Status")

      selected_collector = st.selectbox(
          "Select Collector to Regulate",
          options=[item[0] for item in collector_items],
          format_func=lambda x: f"{x} - {users_dict[x].get('full_name')} ({users_dict[x].get('zone')})",
      )

      curr_data = users_dict[selected_collector]
      current_quota = curr_data.get("max_clients", 50)
      is_currently_frozen = bool(curr_data.get("is_frozen", 0))

      with st.form("regulate_form"):
        new_quota = st.number_input(
            "Regulate Maximum Client Quota Limit",
            min_value=1,
            max_value=10000,
            value=int(current_quota),
        )
        freeze_status = st.checkbox(
            "Freeze Account (Block Login / Registration)",
            value=is_currently_frozen,
        )

        submit_regulation = st.form_submit_button(
            "Update Collector Privileges", use_container_width=True
        )
        if submit_regulation:
          update_collector_quota(
              selected_collector, new_quota, 1 if freeze_status else 0
          )
          st.success(
              f"✅ Quota and status for **{selected_collector}** successfully"
              " updated!"
          )
          st.rerun()

st.markdown("---")
st.caption(
    "SusuFlow Enterprise • Developed by rog3rs / 0542470810 • Persistent"
    " Local Storage & Admin Oversight"
)