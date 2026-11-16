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


# Page Configuration for Professional SaaS Look
st.set_page_config(
    page_title="SusuFlow Enterprise",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded",
)


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


# 2. SaaS Subscription & License Check Gate
def check_subscription_status():
  try:
    sub_config = st.secrets.get("subscription", {})
    status = sub_config.get("status", "active")
    expiry_str = sub_config.get("expiry_date", "2026-12-31")
    expiry_date = datetime.strptime(expiry_str, "%Y-%m-%d").date()
    if status != "active" or datetime.now().date() > expiry_date:
      return False, expiry_str
  except Exception:
    pass
  return True, None

# 3. Initialize Session State Safely
if "auth_user" not in st.session_state:
  st.session_state.auth_user = None
if "user_info" not in st.session_state:
  st.session_state.user_info = None

# 4. Clean Sidebar Login Screen (Zero plain-text hints)
if not st.session_state.auth_user:
  st.sidebar.markdown("### 🔐 SusuFlow Enterprise Login")
  st.sidebar.caption("50-Collector Micro-Savings & Credit Risk Platform")

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
      st.session_state.auth_user = selected_user_id
      st.session_state.user_info = users_dict[selected_user_id]
      st.rerun()
    else:
      st.sidebar.error("❌ Invalid password for selected operator.")

  st.stop()  # Halts execution so unauthenticated users cannot access core modules
  
  # 5. Enforce Subscription Gate Post-Login
is_subscribed, expiry_date = check_subscription_status()
if not is_subscribed:
  st.error("⚠️ **Subscription Expired / License Suspended**")
  st.warning(
      "The software license for this agency has expired. Live operations are"
      " temporarily locked."
  )
  st.info(
      f"To restore full access, please contact your administrator. (Expired On:"
      f" {expiry_date})"
  )
  st.stop()

# 6. Safe Role & User Information Access (Guaranteed non-None)
user_info = st.session_state.get("user_info", {})
current_role = user_info.get("role", "collector") if user_info else "collector"
current_agent_name = (
    user_info.get("full_name", "Field Agent") if user_info else "Field Agent"
)
current_zone = (
    user_info.get("zone", "Market Zone") if user_info else "Market Zone"
)

# Main App Header Dashboard preview for verified session
st.title("💼 SusuFlow Enterprise Command Centre")
st.success(
    f"Logged in as: **{current_agent_name}** | Role: **{current_role.upper()}**"
    f" | Zone: **{current_zone}**")