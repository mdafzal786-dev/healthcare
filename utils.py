import streamlit as st
import random
import time
import bcrypt
from db import (
    get_patients_cursor, get_doctors_cursor, commit_patients, commit_doctors,
    get_chat_requests, add_chat_request, add_submission, add_chat_message
)

PRIMARY_BLUE = 'rgb(0, 102, 180)'
SECONDARY_BLUE = 'rgb(50, 150, 250)'
NAV_BAR_BG = '#1e1e1e'

MOCK_SPECIALTIES = [
    "Cardiology", "Orthopedics (Bone)", "Pulmonology (Lung)",
    "Nephrology (Kidney)", "Neurology", "Pediatrics"
]

# ----------------------------------------------------------------------
# PAGE STYLE
# ----------------------------------------------------------------------
def set_page_style():
    st.markdown(f"""
    <style>
    .stApp {{
        background-color: #000000;
        font-family: 'Inter', sans-serif;
        color: #ffffff;
    }}
    .header-bar {{
        background: linear-gradient(90deg, {PRIMARY_BLUE}, {SECONDARY_BLUE});
        padding: 20px;
        color: white;
        text-align: left;
        margin: -1rem -1rem 1rem -1rem;
        border-radius: 8px 8px 0 0;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.2);
        display: flex;
        align-items: center;
        gap: 20px;
    }}
    .header-bar img {{
        border-radius: 50%;
        background: #000000;
        padding: 5px;
        height: 80px;
        width: 80px;
    }}
    .header-bar h1 {{
        font-size: 2.5em;
        font-weight: 800;
        letter-spacing: 2px;
        margin: 0;
        flex-grow: 1;
        text-shadow: 1px 1px 3px rgba(0,0,0,0.3);
    }}
    .notification-badge {{
        background-color: #ef4444;
        color: white;
        border-radius: 50%;
        padding: 2px 8px;
        font-size: 0.8em;
        font-weight: bold;
        margin-left: 5px;
        vertical-align: middle;
    }}
    .notification-container {{
        background-color: #000000;
        border-radius: 12px;
        box-shadow: 0 4px 10px rgba(0, 0, 0, 0.1);
        padding: 15px;
        margin-bottom: 20px;
        color: #ffffff;
    }}
    .notification-item {{
        padding: 10px;
        border-bottom: 1px solid #333;
    }}
    .notification-item:last-child {{
        border-bottom: none;
    }}
    .notification-unread {{
        background-color: #1e40af;
        font-weight: bold;
        color: #ffffff;
    }}
    .st-emotion-cache-1ftrux {{
        border-radius: 12px;
        box-shadow: 0 4px 10px rgba(0, 0, 0, 0.05);
        border-top: 5px solid {PRIMARY_BLUE};
        padding: 20px;
        background-color: #000000;
        color: #ffffff;
    }}
    .stButton>button {{
        border-radius: 8px;
        border: none;
        transition: all 0.2s;
    }}
    .st-emotion-cache-nahz7x > button > div > p {{
        font-weight: bold !important;
        font-size: 1.1em !important;
        color: white !important;
        line-height: 1.2 !important;
    }}
    .st-emotion-cache-nahz7x:has(> button > div > p) {{
        width: 150px;
        height: 150px;
        margin: 10px auto;
        border-radius: 50%;
        background: radial-gradient(circle, {SECONDARY_BLUE} 0%, {PRIMARY_BLUE} 100%);
        box-shadow: 0 5px 15px rgba(0, 0, 0, 0.4);
        border: 4px solid #000000;
    }}
    .st-emotion-cache-nahz7x:hover {{
        transform: scale(1.05);
        box-shadow: 0 8px 20px rgba(0, 0, 0, 0.5);
    }}
    .login-container {{
        text-align: center;
        margin-top: 30px;
        background-color: #000000;
        color: #ffffff;
    }}
    .login-container h2 {{
        margin-bottom: 25px;
        color: {PRIMARY_BLUE};
    }}
    .post-login-nav {{
        display: flex;
        justify-content: space-between;
        background-color: {NAV_BAR_BG};
        padding: 10px 20px;
        margin: -1rem -1rem 1rem -1rem;
        box-shadow: 0 2px 5px rgba(0, 0, 0, 0.4);
    }}
    .post-login-nav .stButton > button {{
        background: transparent;
        border: none;
        color: white;
        padding: 8px 15px;
        font-weight: 600;
        cursor: pointer;
        transition: background-color 0.2s;
        border-radius: 4px;
        width: 100%;
    }}
    .post-login-nav .stButton > button:hover {{
        background-color: #333;
    }}
    #nav_btn_logout {{
        background-color: #ef4444;
    }}
    #nav_btn_logout:hover {{
        background-color: #dc2626;
    }}
    .chat-container {{
        background-color: #000000;
        border-radius: 12px;
        box-shadow: 0 4px 10px rgba(0, 0, 0, 0.1);
        padding: 20px;
        color: #ffffff;
    }}
    .chat-messages {{
        height: 400px;
        overflow-y: auto;
        padding: 10px;
        border: 1px solid #333;
        border-radius: 8px;
        margin-bottom: 15px;
        background-color: #1e1e1e;
        color: #ffffff;
    }}
    .chat-message {{
        margin-bottom: 15px;
        padding: 10px;
        border-radius: 8px;
        max-width: 80%;
    }}
    .user-message {{
        background-color: #1e40af;
        margin-left: auto;
        text-align: right;
        color: #ffffff;
    }}
    .doctor-message {{
        background-color: #166534;
        margin-right: auto;
        text-align: left;
        color: #ffffff;
    }}
    .message-sender {{
        font-weight: bold;
        font-size: 0.8em;
        color: #d1d5db;
    }}
    .stDataFrame table thead th {{
        background-color: #4ac1e2 !important;
        color: white !important;
        font-weight: bold !important;
        border-bottom: none !important;
    }}
    .stDataFrame table tbody tr:nth-child(even) {{
        background-color: #333333;
        color: #ffffff;
    }}
    .stDataFrame table tbody tr:hover {{
        background-color: #1e40af !important;
        color: #ffffff !important;
    }}
    </style>
    """, unsafe_allow_html=True)

# ----------------------------------------------------------------------
# SESSION INITIALIZATION
# ----------------------------------------------------------------------
def init_session_state():
    defaults = {
        'logged_in': False,
        'user_profile': None,
        'selected_role': 'patient',
        'admin_view': "AddDoctor",
        'portal_view': "Dashboard",
        'next_doc_id': f"{random.randint(200, 999)}",
        'next_request_id': 10001,
        'active_chat_request': None,
        'verify_email': None,
        'nav_view': "Login"
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

    # Auto-increment request ID
    c = get_doctors_cursor()
    c.execute('SELECT MAX(request_id) FROM chat_requests')
    max_id = c.fetchone()[0]
    if max_id:
        st.session_state.next_request_id = max_id + 1

    # Seed admin only if not exists
    c.execute('SELECT COUNT(*) FROM doctors WHERE email = ?', ('admin@app.com',))
    if c.fetchone()[0] == 0:
        from db import add_doctor
        add_doctor(
            email="admin@app.com",
            password=bcrypt.hashpw("admin".encode(), bcrypt.gensalt()).decode(),
            name="System Admin",
            mobile="0000000000",
            specialty="Admin",
            doc_id="000",
            qualification="System"
        )

# ----------------------------------------------------------------------
# LOGOUT
# ----------------------------------------------------------------------
def logout():
    for key in ['logged_in', 'user_profile', 'active_chat_request', 'portal_view', 'admin_view']:
        if key in st.session_state:
            del st.session_state[key]
    st.session_state.selected_role = 'patient'
    st.rerun()