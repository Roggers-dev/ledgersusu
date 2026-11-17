from datetime import datetime, timedelta
import hashlib
import io
import os
import sqlite3
import urllib.parse
import openpyxl
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
        font-size: 0.9em;
        line-height: 1.5em;
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
# 2. BULLETPROOF DATABASE & GOVERNANCE FUNCTIONS
# ==========================================
def get_auth_db():
  os.makedirs("secure_data", exist_ok=True)
  db_path = os.path.join("secure_data", "users_registry.db")
  conn = sqlite3.connect(db_path, check_same_thread=False)
  cursor = conn.cursor()
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password_hash TEXT,
            identifier TEXT,
            role TEXT DEFAULT 'collector'
        )
    """)
  conn.commit()
  return conn


# Initialize registry table immediately upon startup
master_conn = get_auth_db()
master_conn.close()


def register_user(username, password_hash, identifier, role="collector"):
  clean_username = username.strip().lower()
  conn = get_auth_db()
  cursor = conn.cursor()
  try:
    cursor.execute(
        """
            INSERT INTO users (username, password_hash, identifier, role)
            VALUES (?, ?, ?, ?)
        """,
        (clean_username, password_hash, identifier.strip().lower(), role),
    )
    conn.commit()
    conn.close()
    return True, "Registration successful!"
  except sqlite3.IntegrityError:
    conn.close()
    return False, "Username already exists. Choose a different username."


def get_user_credentials(username):
  if not username:
    return None
  clean_username = username.strip().lower()
  conn = get_auth_db()
  cursor = conn.cursor()
  cursor.execute(
      "SELECT username, password_hash, identifier, role FROM users WHERE"
      " username = ?",
      (clean_username,),
  )
  row = cursor.fetchone()
  conn.close()
  if row:
    return {
        "username": row[0],
        "password_hash": row[1],
        "identifier": row[2],
        "role": row[3],
    }
  return None


def get_user_db_path(username):
  os.makedirs("secure_data", exist_ok=True)
  clean_username = username.strip().lower()
  return os.path.join("secure_data", f"db_{clean_username}.db")


def init_user_tables(username):
  db_path = get_user_db_path(username)
  conn = sqlite3.connect(db_path, check_same_thread=False)
  cursor = conn.cursor()
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS clients (
            acc_id TEXT PRIMARY KEY,
            full_name TEXT,
            phone_number TEXT,
            location TEXT,
            occupation TEXT,
            registration_date TEXT
        )
    """)
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            transaction_id TEXT PRIMARY KEY,
            timestamp TEXT,
            acc_id TEXT,
            client_name TEXT,
            phone_number TEXT,
            transaction_type TEXT,
            location TEXT,
            amount REAL,
            notes TEXT
        )
    """)
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            log_id TEXT PRIMARY KEY,
            timestamp TEXT,
            record_id TEXT,
            action_type TEXT,
            authorized_by TEXT,
            reason TEXT
        )
    """)
  conn.commit()
  conn.close()


def get_client_records(username):
  init_user_tables(username)
  conn = sqlite3.connect(get_user_db_path(username), check_same_thread=False)
  df = pd.read_sql("SELECT * FROM clients", conn)
  conn.close()
  return df


def save_client_record(
    username, acc_id, full_name, phone_number, location, occupation
):
  init_user_tables(username)
  conn = sqlite3.connect(get_user_db_path(username), check_same_thread=False)
  cursor = conn.cursor()
  cursor.execute(
      """
        INSERT OR REPLACE INTO clients (acc_id, full_name, phone_number, location, occupation, registration_date)
        VALUES (?, ?, ?, ?, ?, ?)
    """,
      (
          acc_id,
          full_name,
          phone_number,
          location,
          occupation,
          datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
      ),
  )
  conn.commit()
  conn.close()


def get_transaction_records(username):
  init_user_tables(username)
  conn = sqlite3.connect(get_user_db_path(username), check_same_thread=False)
  df = pd.read_sql("SELECT * FROM transactions ORDER BY timestamp DESC", conn)
  conn.close()
  return df


def save_transaction_record(
    username,
    tx_id,
    timestamp,
    acc_id,
    client_name,
    phone_number,
    tx_type,
    location,
    amount,
    notes,
):
  init_user_tables(username)
  conn = sqlite3.connect(get_user_db_path(username), check_same_thread=False)
  cursor = conn.cursor()
  cursor.execute(
      """
        INSERT INTO transactions (transaction_id, timestamp, acc_id, client_name, phone_number, transaction_type, location, amount, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
      (
          tx_id,
          timestamp,
          acc_id,
          client_name,
          phone_number,
          tx_type,
          location,
          amount,
          notes,
      ),
  )
  conn.commit()
  conn.close()


def log_audit_action(username, record_id, action_type, authorized_by, reason):
  init_user_tables(username)
  conn = sqlite3.connect(get_user_db_path(username), check_same_thread=False)
  cursor = conn.cursor()
  log_id = f"LOG-{datetime.now().strftime('%Y%m%d%H%M%S')}"
  cursor.execute(
      """
        INSERT INTO audit_log (log_id, timestamp, record_id, action_type, authorized_by, reason)
        VALUES (?, ?, ?, ?, ?, ?)
    """,
      (
          log_id,
          datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
          record_id,
          action_type,
          authorized_by,
          reason,
      ),
  )
  conn.commit()
  conn.close()


def get_audit_logs(username):
  init_user_tables(username)
  conn = sqlite3.connect(get_user_db_path(username), check_same_thread=False)
  df = pd.read_sql("SELECT * FROM audit_log ORDER BY timestamp DESC", conn)
  conn.close()
  return df


# Seed default accounts securely on boot
try:
  if not get_user_credentials("collector1"):
    register_user(
        "collector1",
        hashlib.sha256("password123".encode()).hexdigest(),
        "0542470810",
        role="collector",
    )
  if not get_user_credentials("admin"):
    register_user(
        "admin",
        hashlib.sha256("admin123".encode()).hexdigest(),
        "koffieroggers@gmail.com",
        role="manager",
    )
except Exception:
  pass


# ==========================================
# 3. SESSION STATE INITIALIZATION
# ==========================================
if "auth_user" not in st.session_state:
  st.session_state.auth_user = None
if "last_receipt" not in st.session_state:
  st.session_state.last_receipt = None


# ==========================================
# 4. AUTHENTICATION (LOGIN & SIGN UP)
# ==========================================
if not st.session_state.auth_user:
  col_landing, col_auth = st.columns([1.2, 1])

  with col_landing:
    st.markdown(
        """
        <div class="landing-banner">
            <h1 style="color: #ffffff; margin-bottom: 10px;">🏛️ SusuFlow Enterprise</h1>
            <p style="font-size: 1.1em; color: #d0d7de;">Secure micro-finance platform with 24-hour edit lockout, admin override audit trails, and protected exports.</p>
            <hr style="border-color: rgba(255,255,255,0.2);">
            <ul style="list-style-type: none; padding-left: 0; line-height: 2.2em; font-size: 1.05em;">
                <li>🔒 <b>24-Hour Edit Protection:</b> Records lock automatically after 24 hours.</li>
                <li>🛡️ <b>Admin Privileges:</b> Critical overrides require admin authorization & reasons.</li>
                <li>📊 <b>Protected Excel Reports:</b> Data exports with worksheet protection.</li>
            </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )

  with col_auth:
    st.sidebar.markdown("### 🔐 Portal Authentication")
    auth_mode = st.sidebar.radio(
        "Select Action", ["Log In", "Sign Up (New Account)"]
    )

    if auth_mode == "Log In":
      st.sidebar.subheader("Operator Login")
      login_user = st.sidebar.text_input("Username").strip().lower()
      login_pass = st.sidebar.text_input("Password", type="password")

      if st.sidebar.button("Log In", use_container_width=True):
        if not login_user:
          st.sidebar.error("❌ Please enter a username.")
        else:
          user_data = get_user_credentials(login_user)
          if user_data:
            entered_hash = hashlib.sha256(login_pass.encode()).hexdigest()
            if entered_hash == user_data["password_hash"]:
              st.session_state.auth_user = user_data["username"]
              st.rerun()
            else:
              st.sidebar.error("❌ Incorrect password.")
          else:
            st.sidebar.error("❌ Username not found.")

    else:
      st.sidebar.subheader("📝 Sign Up")
      reg_user = st.sidebar.text_input("Choose Username").strip().lower()
      reg_pass = st.sidebar.text_input("Choose Password", type="password")
      reg_identifier = st.sidebar.text_input(
          "Phone Number or Email"
      ).strip()
      reg_role = st.sidebar.selectbox(
          "Account Role", ["collector", "manager"]
      )

      if st.sidebar.button("Register & Login", use_container_width=True):
        if not reg_user or not reg_pass or not reg_identifier:
          st.sidebar.error(
              "❌ Please fill in Username, Password, and Phone Number/Email."
          )
        else:
          pass_hash = hashlib.sha256(reg_pass.encode()).hexdigest()
          success, msg = register_user(
              reg_user, pass_hash, reg_identifier, role=reg_role
          )
          if success:
            st.session_state.auth_user = reg_user
            st.rerun()
          else:
            st.sidebar.error(f"❌ {msg}")

    st.sidebar.markdown(
        """
        <div class="dev-badge">
            👨‍💻 Developer: rog3rs<br>
            📞 0542470810<br>
            📧 koffieroggers@gmail.com
        </div>
        """,
        unsafe_allow_html=True,
    )
  st.stop()


# ==========================================
# 5. DASHBOARD & GOVERNANCE HANDLING
# ==========================================
current_user_id = st.session_state.auth_user
user_creds = get_user_credentials(current_user_id)
user_role = user_creds["role"] if user_creds else "collector"
user_db_path = get_user_db_path(current_user_id)

# Sidebar Workspace Info
st.sidebar.markdown(
    f"### 👤 Operator: {current_user_id} ({user_role.upper()})"
)
st.sidebar.info(
    f"📂 **Active Partition:**\n`secure_data/{os.path.basename(user_db_path)}`"
)

if st.sidebar.button("Log Out", use_container_width=True):
  st.session_state.auth_user = None
  st.rerun()

st.sidebar.markdown(
    """
    <div class="dev-badge">
        👨‍💻 Developer: rog3rs<br>
        📞 0542470810<br>
        📧 koffieroggers@gmail.com
    </div>
    """,
    unsafe_allow_html=True,
)

# Header
head_col1, head_col2 = st.columns([3, 1])
with head_col1:
  st.title("💼 SusuFlow Enterprise Command Centre")
  st.markdown(
      "*Permanent Storage • 24-Hour Edit Lockout • Admin Audit Governance*"
  )
with head_col2:
  st.markdown(
      "<div style='text-align: right; padding-top: 10px; font-size: 0.85em;"
      " color: #333; background: #fff; padding: 8px 12px; border-radius: 6px;"
      " border: 1px solid #ddd;'><b>Developer:</b> rog3rs<br><b>Phone:</b>"
      " 0542470810<br><b>Email:</b> koffieroggers@gmail.com</div>",
      unsafe_allow_html=True,
  )
st.markdown("---")

tab1, tab2, tab3, tab4 = st.tabs([
    "👥 Client Registration",
    "📥 Transactions & 24hr Lock",
    "📊 Dashboard & Protected Export",
    "🛡️ Admin Governance & Audit",
])

# --- TAB 1: CLIENT REGISTRATION ---
with tab1:
  st.markdown("### Register Client")
  with st.form("client_reg_form", clear_on_submit=True):
    col1, col2 = st.columns(2)
    with col1:
      acc_id = st.text_input(
          "ACC ID", value=f"ACC-{datetime.now().strftime('%H%M%S')}"
      )
      full_name = st.text_input("Full Name")
      phone_number = st.text_input("Phone Number")
    with col2:
      location = st.text_input("Location")
      occupation = st.text_input("Occupation / Work")

    submit_client = st.form_submit_button(
        "Save Client Record", use_container_width=True
    )
    if submit_client:
      if not full_name or not phone_number or not acc_id:
        st.error(
            "❌ Please provide ACC ID, Full Name, and Phone Number."
        )
      else:
        save_client_record(
            current_user_id,
            acc_id,
            full_name,
            phone_number,
            location,
            occupation,
        )
        st.success(
            f"✅ Client **{full_name}** ({acc_id}) successfully registered!"
        )
        st.rerun()

  st.markdown("---")
  st.markdown("#### 📋 Registered Clients Directory")
  df_clients = get_client_records(current_user_id)
  if df_clients.empty:
    st.info("ℹ️ No clients registered yet.")
  else:
    st.dataframe(df_clients, use_container_width=True)
    
    from datetime import datetime, timedelta
import hashlib
import io
import os
import sqlite3
import urllib.parse
import openpyxl
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
        font-size: 0.9em;
        line-height: 1.5em;
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
# 2. BULLETPROOF DATABASE & GOVERNANCE FUNCTIONS
# ==========================================
def get_auth_db():
  os.makedirs("secure_data", exist_ok=True)
  db_path = os.path.join("secure_data", "users_registry.db")
  conn = sqlite3.connect(db_path, check_same_thread=False)
  cursor = conn.cursor()
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password_hash TEXT,
            identifier TEXT,
            role TEXT DEFAULT 'collector'
        )
    """)
  conn.commit()
  return conn


# Initialize registry table immediately upon startup
master_conn = get_auth_db()
master_conn.close()


def register_user(username, password_hash, identifier, role="collector"):
  clean_username = username.strip().lower()
  conn = get_auth_db()
  cursor = conn.cursor()
  try:
    cursor.execute(
        """
            INSERT INTO users (username, password_hash, identifier, role)
            VALUES (?, ?, ?, ?)
        """,
        (clean_username, password_hash, identifier.strip().lower(), role),
    )
    conn.commit()
    conn.close()
    return True, "Registration successful!"
  except sqlite3.IntegrityError:
    conn.close()
    return False, "Username already exists. Choose a different username."


def get_user_credentials(username):
  if not username:
    return None
  clean_username = username.strip().lower()
  conn = get_auth_db()
  cursor = conn.cursor()
  cursor.execute(
      "SELECT username, password_hash, identifier, role FROM users WHERE"
      " username = ?",
      (clean_username,),
  )
  row = cursor.fetchone()
  conn.close()
  if row:
    return {
        "username": row[0],
        "password_hash": row[1],
        "identifier": row[2],
        "role": row[3],
    }
  return None


def get_user_db_path(username):
  os.makedirs("secure_data", exist_ok=True)
  clean_username = username.strip().lower()
  return os.path.join("secure_data", f"db_{clean_username}.db")


def init_user_tables(username):
  db_path = get_user_db_path(username)
  conn = sqlite3.connect(db_path, check_same_thread=False)
  cursor = conn.cursor()
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS clients (
            acc_id TEXT PRIMARY KEY,
            full_name TEXT,
            phone_number TEXT,
            location TEXT,
            occupation TEXT,
            registration_date TEXT
        )
    """)
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            transaction_id TEXT PRIMARY KEY,
            timestamp TEXT,
            acc_id TEXT,
            client_name TEXT,
            phone_number TEXT,
            transaction_type TEXT,
            location TEXT,
            amount REAL,
            notes TEXT
        )
    """)
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            log_id TEXT PRIMARY KEY,
            timestamp TEXT,
            record_id TEXT,
            action_type TEXT,
            authorized_by TEXT,
            reason TEXT
        )
    """)
  conn.commit()
  conn.close()


def get_client_records(username):
  init_user_tables(username)
  conn = sqlite3.connect(get_user_db_path(username), check_same_thread=False)
  df = pd.read_sql("SELECT * FROM clients", conn)
  conn.close()
  return df


def save_client_record(
    username, acc_id, full_name, phone_number, location, occupation
):
  init_user_tables(username)
  conn = sqlite3.connect(get_user_db_path(username), check_same_thread=False)
  cursor = conn.cursor()
  cursor.execute(
      """
        INSERT OR REPLACE INTO clients (acc_id, full_name, phone_number, location, occupation, registration_date)
        VALUES (?, ?, ?, ?, ?, ?)
    """,
      (
          acc_id,
          full_name,
          phone_number,
          location,
          occupation,
          datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
      ),
  )
  conn.commit()
  conn.close()


def get_transaction_records(username):
  init_user_tables(username)
  conn = sqlite3.connect(get_user_db_path(username), check_same_thread=False)
  df = pd.read_sql("SELECT * FROM transactions ORDER BY timestamp DESC", conn)
  conn.close()
  return df


def save_transaction_record(
    username,
    tx_id,
    timestamp,
    acc_id,
    client_name,
    phone_number,
    tx_type,
    location,
    amount,
    notes,
):
  init_user_tables(username)
  conn = sqlite3.connect(get_user_db_path(username), check_same_thread=False)
  cursor = conn.cursor()
  cursor.execute(
      """
        INSERT INTO transactions (transaction_id, timestamp, acc_id, client_name, phone_number, transaction_type, location, amount, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
      (
          tx_id,
          timestamp,
          acc_id,
          client_name,
          phone_number,
          tx_type,
          location,
          amount,
          notes,
      ),
  )
  conn.commit()
  conn.close()


def log_audit_action(username, record_id, action_type, authorized_by, reason):
  init_user_tables(username)
  conn = sqlite3.connect(get_user_db_path(username), check_same_thread=False)
  cursor = conn.cursor()
  log_id = f"LOG-{datetime.now().strftime('%Y%m%d%H%M%S')}"
  cursor.execute(
      """
        INSERT INTO audit_log (log_id, timestamp, record_id, action_type, authorized_by, reason)
        VALUES (?, ?, ?, ?, ?, ?)
    """,
      (
          log_id,
          datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
          record_id,
          action_type,
          authorized_by,
          reason,
      ),
  )
  conn.commit()
  conn.close()


def get_audit_logs(username):
  init_user_tables(username)
  conn = sqlite3.connect(get_user_db_path(username), check_same_thread=False)
  df = pd.read_sql("SELECT * FROM audit_log ORDER BY timestamp DESC", conn)
  conn.close()
  return df


# Seed default accounts securely on boot
try:
  if not get_user_credentials("collector1"):
    register_user(
        "collector1",
        hashlib.sha256("password123".encode()).hexdigest(),
        "0542470810",
        role="collector",
    )
  if not get_user_credentials("admin"):
    register_user(
        "admin",
        hashlib.sha256("admin123".encode()).hexdigest(),
        "koffieroggers@gmail.com",
        role="manager",
    )
except Exception:
  pass


# ==========================================
# 3. SESSION STATE INITIALIZATION
# ==========================================
if "auth_user" not in st.session_state:
  st.session_state.auth_user = None
if "last_receipt" not in st.session_state:
  st.session_state.last_receipt = None


# ==========================================
# 4. AUTHENTICATION (LOGIN & SIGN UP)
# ==========================================
if not st.session_state.auth_user:
  col_landing, col_auth = st.columns([1.2, 1])

  with col_landing:
    st.markdown(
        """
        <div class="landing-banner">
            <h1 style="color: #ffffff; margin-bottom: 10px;">🏛️ SusuFlow Enterprise</h1>
            <p style="font-size: 1.1em; color: #d0d7de;">Secure micro-finance platform with 24-hour edit lockout, admin override audit trails, and protected exports.</p>
            <hr style="border-color: rgba(255,255,255,0.2);">
            <ul style="list-style-type: none; padding-left: 0; line-height: 2.2em; font-size: 1.05em;">
                <li>🔒 <b>24-Hour Edit Protection:</b> Records lock automatically after 24 hours.</li>
                <li>🛡️ <b>Admin Privileges:</b> Critical overrides require admin authorization & reasons.</li>
                <li>📊 <b>Protected Excel Reports:</b> Data exports with worksheet protection.</li>
            </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )

  with col_auth:
    st.sidebar.markdown("### 🔐 Portal Authentication")
    auth_mode = st.sidebar.radio(
        "Select Action", ["Log In", "Sign Up (New Account)"]
    )

    if auth_mode == "Log In":
      st.sidebar.subheader("Operator Login")
      login_user = st.sidebar.text_input("Username").strip().lower()
      login_pass = st.sidebar.text_input("Password", type="password")

      if st.sidebar.button("Log In", use_container_width=True):
        if not login_user:
          st.sidebar.error("❌ Please enter a username.")
        else:
          user_data = get_user_credentials(login_user)
          if user_data:
            entered_hash = hashlib.sha256(login_pass.encode()).hexdigest()
            if entered_hash == user_data["password_hash"]:
              st.session_state.auth_user = user_data["username"]
              st.rerun()
            else:
              st.sidebar.error("❌ Incorrect password.")
          else:
            st.sidebar.error("❌ Username not found.")

    else:
      st.sidebar.subheader("📝 Sign Up")
      reg_user = st.sidebar.text_input("Choose Username").strip().lower()
      reg_pass = st.sidebar.text_input("Choose Password", type="password")
      reg_identifier = st.sidebar.text_input(
          "Phone Number or Email"
      ).strip()
      reg_role = st.sidebar.selectbox(
          "Account Role", ["collector", "manager"]
      )

      if st.sidebar.button("Register & Login", use_container_width=True):
        if not reg_user or not reg_pass or not reg_identifier:
          st.sidebar.error(
              "❌ Please fill in Username, Password, and Phone Number/Email."
          )
        else:
          pass_hash = hashlib.sha256(reg_pass.encode()).hexdigest()
          success, msg = register_user(
              reg_user, pass_hash, reg_identifier, role=reg_role
          )
          if success:
            st.session_state.auth_user = reg_user
            st.rerun()
          else:
            st.sidebar.error(f"❌ {msg}")

    st.sidebar.markdown(
        """
        <div class="dev-badge">
            👨‍💻 Developer: rog3rs<br>
            📞 0542470810<br>
            📧 koffieroggers@gmail.com
        </div>
        """,
        unsafe_allow_html=True,
    )
  st.stop()


# ==========================================
# 5. DASHBOARD & GOVERNANCE HANDLING
# ==========================================
current_user_id = st.session_state.auth_user
user_creds = get_user_credentials(current_user_id)
user_role = user_creds["role"] if user_creds else "collector"
user_db_path = get_user_db_path(current_user_id)

# Sidebar Workspace Info
st.sidebar.markdown(
    f"### 👤 Operator: {current_user_id} ({user_role.upper()})"
)
st.sidebar.info(
    f"📂 **Active Partition:**\n`secure_data/{os.path.basename(user_db_path)}`"
)

if st.sidebar.button("Log Out", use_container_width=True):
  st.session_state.auth_user = None
  st.rerun()

st.sidebar.markdown(
    """
    <div class="dev-badge">
        👨‍💻 Developer: rog3rs<br>
        📞 0542470810<br>
        📧 koffieroggers@gmail.com
    </div>
    """,
    unsafe_allow_html=True,
)

# Header
head_col1, head_col2 = st.columns([3, 1])
with head_col1:
  st.title("💼 SusuFlow Enterprise Command Centre")
  st.markdown(
      "*Permanent Storage • 24-Hour Edit Lockout • Admin Audit Governance*"
  )
with head_col2:
  st.markdown(
      "<div style='text-align: right; padding-top: 10px; font-size: 0.85em;"
      " color: #333; background: #fff; padding: 8px 12px; border-radius: 6px;"
      " border: 1px solid #ddd;'><b>Developer:</b> rog3rs<br><b>Phone:</b>"
      " 0542470810<br><b>Email:</b> koffieroggers@gmail.com</div>",
      unsafe_allow_html=True,
  )
st.markdown("---")

tab1, tab2, tab3, tab4 = st.tabs([
    "👥 Client Registration",
    "📥 Transactions & 24hr Lock",
    "📊 Dashboard & Protected Export",
    "🛡️ Admin Governance & Audit",
])

# --- TAB 1: CLIENT REGISTRATION ---
with tab1:
  st.markdown("### Register Client")
  with st.form("client_reg_form", clear_on_submit=True):
    col1, col2 = st.columns(2)
    with col1:
      acc_id = st.text_input(
          "ACC ID", value=f"ACC-{datetime.now().strftime('%H%M%S')}"
      )
      full_name = st.text_input("Full Name")
      phone_number = st.text_input("Phone Number")
    with col2:
      location = st.text_input("Location")
      occupation = st.text_input("Occupation / Work")

    submit_client = st.form_submit_button(
        "Save Client Record", use_container_width=True
    )
    if submit_client:
      if not full_name or not phone_number or not acc_id:
        st.error(
            "❌ Please provide ACC ID, Full Name, and Phone Number."
        )
      else:
        save_client_record(
            current_user_id,
            acc_id,
            full_name,
            phone_number,
            location,
            occupation,
        )
        st.success(
            f"✅ Client **{full_name}** ({acc_id}) successfully registered!"
        )
        st.rerun()

  st.markdown("---")
  st.markdown("#### 📋 Registered Clients Directory")
  df_clients = get_client_records(current_user_id)
  if df_clients.empty:
    st.info("ℹ️ No clients registered yet.")
  else:
    st.dataframe(df_clients, use_container_width=True)