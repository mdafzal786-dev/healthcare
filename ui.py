import streamlit as st
import pandas as pd
import re
import time
import json
import base64
from random import randint
from io import BytesIO
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.units import inch

import os
import re
from dotenv import load_dotenv

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage

from db import (
    register_patient, get_patient, get_doctor, get_all_doctors,
    get_chat_requests, add_chat_request, update_chat_request_status,
    get_chat_messages, add_chat_message, get_submissions, add_submission,
    get_feedback, add_feedback, get_notifications, mark_notification_read,
    mark_notifications_read_by_request, add_doctor,
    save_otp, get_otp, increment_otp_attempts, delete_otp, send_verification_email,
    check_password,get_doctors_cursor,
    add_chat_attachment, get_chat_attachments,
    add_prescription, get_prescriptions_for_patient,
    get_all_patients, add_notification
)
from utils import (
    PRIMARY_BLUE, SECONDARY_BLUE, NAV_BAR_BG, MOCK_SPECIALTIES,
    logout, set_page_style
)

load_dotenv()



def is_valid_email(email: str) -> bool:
    if not email or not isinstance(email, str):
        return False
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email.strip()))

def is_valid_mobile(mobile: str) -> bool:
    return bool(mobile and mobile.isdigit() and len(mobile) == 10)

# ────────────────────────────────────────────────────────────────
# Gemini setup (unchanged)
# ────────────────────────────────────────────────────────────────

client = None
api_key = os.getenv("GOOGLE_API_KEY")

# Premium Debug (remove after testing)
if st.sidebar.checkbox("🔧 Debug: Show API Key Status"):
    if api_key:
        st.sidebar.success("✅ GOOGLE_API_KEY loaded!")
        st.sidebar.code(f"{api_key[:10]}...{api_key[-6:]}", language="text")
    else:
        st.sidebar.error("❌ No GOOGLE_API_KEY in .env")

if not api_key:
    st.sidebar.error("🚫 GOOGLE_API_KEY missing from .env!")
else:
    api_key = api_key.strip()
    if not api_key.startswith("AIzaSy"):
        st.sidebar.error("🚫 Invalid key format!")
    else:
        try:
            # 2026 STABLE MODEL - gemini-1.5-flash (your 2.5-flash key works here!)
            client = ChatGoogleGenerativeAI(
                model="gemini-2.5-flash",  # 🚀 Most reliable Jan 2026
                temperature=0.1,  # Lower for diagnostic precision
                google_api_key=api_key
            )

            # Ultra-fast test
            test_response = client.invoke([
                SystemMessage(content="Say exactly: READY"),
                HumanMessage(content="Test connection")
            ])

            content = test_response.content
            if isinstance(content, list):
                content = " ".join([str(part.get("text", str(part))) for part in content])
            else:
                content = str(content)

            if "READY" in content.upper():
                st.sidebar.success("🎉 GEMINI 1.5 FLASH CONNECTED! Symptom Checker READY 🚀")
                st.sidebar.caption("Your key: AIzaSyBDBDq2x...leeG6E → Perfect!")
            else:
                st.sidebar.success("✅ Gemini connected (test passed)")

        except Exception as e:
            st.sidebar.error(f"❌ Gemini failed: {str(e)[:100]}...")
            st.sidebar.info("🔄 Fix: pip install --upgrade langchain-google-genai")
            client = None

if 'patient_show_register' not in st.session_state:
    st.session_state.patient_show_register = False

if 'next_request_id' not in st.session_state:
    st.session_state.next_request_id = 1001

if 'next_doc_id' not in st.session_state:
    st.session_state.next_doc_id = f"{randint(200, 999)}"


def show_notifications():
    if 'user_profile' not in st.session_state or not st.session_state.user_profile:
        return

    user_email = st.session_state.user_profile['email']
    role = st.session_state.user_profile.get('role', 'unknown')

    notifications = get_notifications(user_email) or []
    unread = [n for n in notifications if n.get('status') == 'unread']
    unread_count = len(unread)

    # Badge with count
    st.markdown(
        f"""
        <h3 style="margin-bottom:0;">
            Notifications 
            {'<span style="background:#ef4444;color:white;padding:4px 10px;border-radius:12px;font-size:0.9rem;">{unread_count}</span>' if unread_count > 0 else ''}
        </h3>
        """,
        unsafe_allow_html=True
    )

    if not notifications:
        st.info("No notifications at this time.")
        return

    # Show recent first
    for n in sorted(notifications, key=lambda x: x.get('timestamp', ''), reverse=True):
        is_unread = n.get('status') == 'unread'
        style = "background:#1e293b; border-left:4px solid #3b82f6; padding:12px; margin:8px 0; border-radius:8px;" if is_unread else "padding:12px; margin:8px 0; border-radius:8px; opacity:0.85; background:#111827;"

        st.markdown(f'<div style="{style}">', unsafe_allow_html=True)

        st.markdown(f"**{n.get('message', 'No message')}**")
        st.caption(f"{n.get('timestamp', 'N/A')} • {'Unread' if is_unread else 'Read'}")

        if n.get('request_id') and is_unread:
            if st.button("Open Chat", key=f"notif_open_{n['id']}", type="primary"):
                mark_notification_read(n['id'])
                st.session_state.active_chat_request = n['request_id']
                st.session_state.portal_view = "LiveChat"
                st.rerun()

        st.markdown('</div>', unsafe_allow_html=True)

    if unread_count > 0:
        if st.button("Mark All as Read", type="secondary"):
            for n in unread:
                mark_notification_read(n['id'])
            st.rerun()
def draw_post_login_navbar(view_options):
    st.markdown(
        """
        <div style="background-color: #000000; padding: 0px 20px 0 20px; margin: -1rem -1rem 0 -1rem; box-shadow: 0 2px 5px rgba(0, 0, 0, 0.4);">
            <div style="background: linear-gradient(90deg, #10b981, #34d399); height: 5px;"></div>
        </div>
        """, unsafe_allow_html=True
    )
    st.markdown('<div class="post-login-nav" style="margin-top:0;">', unsafe_allow_html=True)

    cols = st.columns(len(view_options) + 1)
    i = 0
    for display_name, internal_key in view_options.items():
        with cols[i]:
            if st.button(display_name, key=f"nav_btn_{internal_key}", type="secondary"):
                if internal_key in ["ViewDoctors", "Dashboard", "RequestChat", "GiveFeedback", "DoctorDetails",
                                    "ViewUsers", "ViewRequests", "AddDoctor", "ViewFeedback", "AssignChat",
                                    "WritePrescription", "MyPrescriptions"]:
                    st.session_state.active_chat_request = None
                if st.session_state.user_profile['role'] == 'admin':
                    st.session_state.admin_view = internal_key
                else:
                    st.session_state.portal_view = internal_key
                st.rerun()
        i += 1

    with cols[-1]:
        if st.button("Logout", key="nav_btn_logout", type="primary"):
            logout()

    st.markdown('</div>', unsafe_allow_html=True)


def show_admin_portal():
    user = st.session_state.user_profile
    st.markdown(
        f'<div class="header-bar" style="background: linear-gradient(90deg, #ef4444, #f87171);"><h1>Admin Portal</h1><p>Welcome, {user["name"]} (Admin)</p></div>',
        unsafe_allow_html=True)

    nav_options = {
        "Add Doctor": "AddDoctor",
        "View Doctors": "ViewDoctors",
        "View Users": "ViewUsers",
        "View Feedback": "ViewFeedback",
        "Assign Chat": "AssignChat",
    }
    draw_post_login_navbar(nav_options)

    view = st.session_state.admin_view

    if view == "AddDoctor":
        show_add_doctor_form()
    elif view == "ViewDoctors":
        show_view_doctors_for_portal()
    elif view == "ViewUsers":
        show_view_users()
    elif view == "ViewFeedback":
        show_view_feedback()
    elif view == "AssignChat":
        show_assign_chat_form()
    else:
        st.info("Select an option from the navigation bar above.")


def show_add_doctor_form():
    st.header("Add New Doctor")
    st.markdown("Fill in the details below to register a new doctor in the system.")

    with st.form("add_doctor_form", clear_on_submit=False):
        # Auto-focus on first field
        doc_id = st.text_input(
            "Doctor ID",
            value=st.session_state.next_doc_id,
            help="Unique identifier for the doctor (auto-generated)",
            key="doc_id_input"
        )

        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input("Full Name", key="name_input")
        with col2:
            specialty = st.selectbox("Specialty", [""] + MOCK_SPECIALTIES, key="specialty_input")

        col3, col4 = st.columns(2)
        with col3:
            email = st.text_input("Email Address", key="email_input")
        with col4:
            mobile = st.text_input("Mobile Number (10 digits)", key="mobile_input")

        qualification = st.text_input("Qualifications / Degree", key="qual_input")

        password = st.text_input("Password", type="password", key="pass_input")
        confirm_password = st.text_input("Confirm Password", type="password", key="confirm_pass_input")

        # Real-time validation messages (shown immediately)
        if email and not is_valid_email(email):
            st.warning("Please enter a valid email address", icon="⚠️")
        if mobile and not is_valid_mobile(mobile):
            st.warning("Mobile number must be exactly 10 digits", icon="⚠️")
        if password and len(password) < 8:
            st.warning("Password must be at least 8 characters long", icon="🔑")
        if password and confirm_password and password != confirm_password:
            st.error("Passwords do not match", icon="❌")

        submitted = st.form_submit_button("Add Doctor", type="primary", use_container_width=True)

        if submitted:
            errors = []

            # Required fields check
            required_fields = {
                "Doctor ID": doc_id.strip(),
                "Name": name.strip(),
                "Email": email.strip(),
                "Specialty": specialty.strip(),
                "Qualification": qualification.strip(),
                "Mobile": mobile.strip(),
                "Password": password.strip()
            }
            for field_name, value in required_fields.items():
                if not value:
                    errors.append(f"{field_name} is required.")

            # Specific validations
            if email and not is_valid_email(email):
                errors.append("Invalid email format.")
            if mobile and not is_valid_mobile(mobile):
                errors.append("Mobile number must be exactly 10 digits.")
            if password and len(password) < 8:
                errors.append("Password must be at least 8 characters.")
            if password != confirm_password:
                errors.append("Passwords do not match.")

            if errors:
                for err in errors:
                    st.error(err)
            else:
                with st.spinner("Adding doctor..."):
                    success = add_doctor(
                        email=email.strip().lower(),
                        password=password,
                        name=name.strip(),
                        mobile=mobile.strip() or None,
                        specialty=specialty.strip(),
                        doc_id=doc_id.strip(),
                        qualification=qualification.strip()
                    )

                    if success:
                        st.session_state.next_doc_id = f"D{randint(2000, 9999)}"
                        st.success(f"Doctor **{name}** added successfully! 🎉")
                        st.balloons()  # optional fun feedback
                        # Optional: reset form fields (but keep doc_id new)
                        st.rerun()
                    else:
                        st.error("Failed to add doctor. Email or Doctor ID may already exist.")

def show_login_page():
    if 'nav_view' not in st.session_state:
        st.session_state.nav_view = "Home"
    if 'verify_email' not in st.session_state:
        st.session_state.verify_email = None

    st.markdown(
        """
        <style>
        /* Global */
        .nav-container {background: linear-gradient(90deg, #1d4ed8, #3b82f6); padding: 15px 20px; margin: -1rem -1rem 1rem -1rem; display: flex; justify-content: center; gap: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.2);}
        .nav-button {background: transparent; color: white; font-weight: 500; padding: 8px 16px; border: none; border-radius: 20px; cursor: pointer; transition:0.3s;}
        .nav-button.active {background: #4ac1e2; font-weight: bold;}
        .header-bar {display: flex; align-items: center; gap: 15px; margin-bottom: 20px; padding: 20px; background: #111827; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.3);}
        .login-container {padding: 30px; background: #1f2937; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.4); color: white; max-width: 500px; margin: 0 auto;}
        .otp-input {width: 50px; height: 50px; text-align: center; font-size: 1.5em; margin: 0 5px; border-radius: 8px; border: 1px solid #4b5563;}

        /* Home Page */
        .hero {background: linear-gradient(135deg, #0ea5e9, #3b82f6); color: white; padding: 60px 20px; border-radius: 16px; text-align: center; margin: 20px 0;}
        .feature-card {background:#1f2937; padding:25px; border-radius:12px; box-shadow:0 4px 15px rgba(0,0,0,0.3); text-align:center; transition:0.3s; height:100%;}
        .feature-card:hover {transform:translateY(-8px); box-shadow:0 12px 25px rgba(0,0,0,0.4);}
        .stats-card {background:#10b981; color:white; padding:20px; border-radius:12px; text-align:center; font-weight:bold; font-size:1.1rem;}
        .team-card {background:#1f2937; padding:20px; border-radius:12px; text-align:center; box-shadow:0 4px 12px rgba(0,0,0,0.3);}
        .team-card img {width:120px; height:120px; border-radius:50%; object-fit:cover; margin-bottom:15px; border:4px solid #10b981;}
        .contact-form {background:#1f2937; padding:30px; border-radius:12px; box-shadow:0 4px 15px rgba(0,0,0,0.3);}
        .footer {background:#111827; color:#9ca3af; padding:40px 20px; margin-top:60px; font-size:0.95rem;}
        .footer a {color:#60a5fa; text-decoration:none; margin:0 12px;}
        .footer a:hover {text-decoration:underline;}
        </style>
        """, unsafe_allow_html=True
    )

    col_logo, col_title = st.columns([1, 5])
    with col_logo:
        try:
            st.image("assets/Logo1.png", width=80)
        except Exception as e:
            st.image("https://via.placeholder.com/80?text=Logo", width=80)
    with col_title:
        st.markdown(
            """
            <div style="line-height:1.2;">
                <h1 style="margin-bottom:4px; color:#0ea5e9;">
                    🏥 E-Healthcare System
                </h1>
                <span style="font-size:1.05em; color:#9ca3af;">
                    Digital Access Portal
                </span>
            </div>
            """,
            unsafe_allow_html=True
        )

    st.markdown('<div class="nav-container">', unsafe_allow_html=True)
    nav_cols = st.columns(4)
    nav_options = ["Home", "About Us", "Contact Us", "Login"]
    for i, option in enumerate(nav_options):
        with nav_cols[i]:
            is_active = st.session_state.nav_view == option
            if st.button(option, key=f"nav_{option.lower()}", type="primary" if is_active else "secondary"):
                st.session_state.nav_view = option
                st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    if st.session_state.nav_view == "Home":
        st.markdown("""
        <div class="hero">
            <h1>Healthcare, Reimagined</h1>
            <p style="font-size:1.3rem; max-width:800px; margin:0 auto;">
                AI-powered symptom checker • Live doctor chat • Secure & private
            </p>
        </div>
        """, unsafe_allow_html=True)

        col1, col2 = st.columns([2, 1])
        with col1:
            st.markdown("""
            <h2 style="color:#0ea5e9;">Your Health, Our Priority</h2>
            <p style="color:#e5e7eb; font-size:1.1rem;">
                Get instant health insights using advanced AI, connect with verified specialists in real-time, and manage your health securely — all in one platform.
            </p>
            <ul style="color:#d1d5db; font-size:1rem;">
                <li>AI Symptom Checker with 95% accuracy</li>
                <li>Live chat with doctors in under 2 minutes</li>
                <li>End-to-end encrypted patient data</li>
                <li>Available 24/7 on web and mobile</li>
            </ul>
            """, unsafe_allow_html=True)
        with col2:
            st.image("assets/Logo1.png", use_container_width=True)

        st.markdown("---")
        st.markdown("<h2 style='text-align:center; color:#0ea5e9;'>Why Choose E-Healthcare?</h2>",
                    unsafe_allow_html=True)
        cols = st.columns(3)
        features = [
            ("AI Symptom Checker", "Get instant diagnosis suggestions using cutting-edge AI.", "🧠"),
            ("Live Doctor Chat", "Connect with verified specialists via secure real-time chat.", "💬"),
            ("Secure & Private", "Your data is encrypted and HIPAA-compliant.", "🔒")
        ]
        for col, (title, desc, icon) in zip(cols, features):
            with col:
                st.markdown(f"""
                <div class="feature-card">
                    <h3 style="color:#10b981;">{icon} {title}</h3>
                    <p style="color:#d1d5db;">{desc}</p>
                </div>
                """, unsafe_allow_html=True)

        st.markdown("---")
        st.markdown("<h2 style='text-align:center; color:#0ea5e9;'>Trusted by Thousands</h2>", unsafe_allow_html=True)
        stats_cols = st.columns(4)
        stats = [("50K+", "Active Patients"), ("200+", "Verified Doctors"), ("4.9", "Average Rating"),
                 ("24/7", "Support")]
        for col, (num, label) in zip(stats_cols, stats):
            with col:
                st.markdown(f"""
                <div class="stats-card">
                    <h3>{num}</h3>
                    <p>{label}</p>
                </div>
                """, unsafe_allow_html=True)

        st.markdown("---")
        st.markdown("<h2 style='text-align:center; color:#0ea5e9;'>Ready to Get Started?</h2>", unsafe_allow_html=True)
        c1, c2, c3 = st.columns([1, 1, 1])
        with c2:
            if st.button("Login Now", type="primary", use_container_width=True):
                st.session_state.nav_view = "Login"
                st.rerun()

    elif st.session_state.nav_view == "About Us":
        st.markdown("<h1 style='text-align:center; color:#0ea5e9;'>About E-Healthcare</h1>", unsafe_allow_html=True)
        st.markdown("---")

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("""
            <h3>Our Mission</h3>
            <p style="color:#e5e7eb;">
                To democratize healthcare by providing instant, accurate, and secure access to medical expertise using AI and real-time communication.
            </p>
            """, unsafe_allow_html=True)
        with col2:
            st.markdown("""
            <h3>Our Vision</h3>
            <p style="color:#e5e7eb;">
                A world where quality healthcare is accessible to everyone, anytime, anywhere.
            </p>
            """, unsafe_allow_html=True)

        st.markdown("---")
        st.markdown("<h2 style='text-align:center; color:#0ea5e9;'>Our Core Values</h2>", unsafe_allow_html=True)
        vals = st.columns(3)
        values = [
            ("Trust", "We prioritize patient privacy and data security."),
            ("Innovation", "Leveraging AI to improve healthcare delivery."),
            ("Accessibility", "Healthcare for all, without barriers.")
        ]
        for col, (title, desc) in zip(vals, values):
            with col:
                st.markdown(f"""
                <div style="background:#1f2937; padding:20px; border-radius:12px; text-align:center;">
                    <h4 style="color:#10b981;">{title}</h4>
                    <p style="color:#d1d5db; font-size:0.95rem;">{desc}</p>
                </div>
                """, unsafe_allow_html=True)

        st.markdown("---")
        st.markdown("<h2 style='text-align:center; color:#0ea5e9;'>Meet Our Team</h2>", unsafe_allow_html=True)

        team_cols = st.columns(3)
        team = [
            ("Dr. Md Afzal", "Chief Medical Officer", "assets/Profile.jpg"),
            ("Dr. Arshad Ali", "Head of AI Research", "assets/Profile.jpg"),
            ("Dr. Ajaj Ahmad", "Lead Developer", "assets/Profile.jpg")
        ]

        for col, (name, role, img_path) in zip(team_cols, team):
            with col:
                try:
                    st.image(img_path, width=120, use_container_width=False)
                except:
                    st.image("https://via.placeholder.com/120?text=No+Image", width=120)

                st.markdown(f"""
                <div style="text-align:center; margin-top:10px;">
                    <h4 style="color:#0ea5e9; margin:5px 0;">{name}</h4>
                    <p style="color:#9ca3af; font-size:0.9rem; margin:0;">{role}</p>
                </div>
                """, unsafe_allow_html=True)

    elif st.session_state.nav_view == "Contact Us":
        st.markdown("<h1 style='text-align:center; color:#0ea5e9;'>Get in Touch</h1>", unsafe_allow_html=True)
        st.markdown("---")

        col1, col2 = st.columns([1, 1])
        with col1:
            st.markdown("""
            <div class="contact-form">
                <h3>Send us a Message</h3>
                <form>
                    <input type="text" placeholder="Your Name" style="width:100%; padding:12px; margin:10px 0; border-radius:8px; border:1px solid #4b5563; background:#111827; color:white;">
                    <input type="email" placeholder="Your Email" style="width:100%; padding:12px; margin:10px 0; border-radius:8px; border:1px solid #4b5563; background:#111827; color:white;">
                    <textarea placeholder="Your Message" style="width:100%; height:120px; padding:12px; margin:10px 0; border-radius:8px; border:1px solid #4b5563; background:#111827; color:white;"></textarea>
                    <button type="submit" style="background:#10b981; color:white; padding:12px 24px; border:none; border-radius:8px; cursor:pointer; font-weight:bold;">Send Message</button>
                </form>
            </div>
            """, unsafe_allow_html=True)
        with col2:
            st.markdown("""
            <h3>Contact Information</h3>
            <p><strong>Email:</strong> support@ehealthcare.com</p>
            <p><strong>Phone:</strong> +91 72600 23491</p>
            <p><strong>Address:</strong> 123 Health Street, Mumbai, India</p>
            <p><strong>Hours:</strong> 24/7 Support</p>
            """, unsafe_allow_html=True)

    elif st.session_state.nav_view == "Login":
        st.markdown("<h1 style='text-align:center; color:#0ea5e9;'>Welcome Back</h1>", unsafe_allow_html=True)
        if st.session_state.verify_email:
            show_verification_page()
        else:
            show_login_options()

    st.markdown("---")
    st.markdown("""
    <div class="footer">
        <div style="max-width:1200px; margin:0 auto; text-align:center;">
            <p><strong>E-Healthcare System</strong> © 2025. All rights reserved.</p>
            <p>
                <a href="#">Privacy Policy</a> • 
                <a href="#">Terms of Service</a> • 
                <a href="#">Help Center</a>
            </p>
            <p style="margin-top:15px;">
                <a href="#">Facebook</a> • 
                <a href="#">Twitter</a> • 
                <a href="#">LinkedIn</a>
            </p>
        </div>
    </div>
    """, unsafe_allow_html=True)

def show_login_options():
    st.markdown('<div class="login-container">', unsafe_allow_html=True)
    st.markdown("<h2 style='text-align:center; color:#0ea5e9;'>Login Access</h2>", unsafe_allow_html=True)
    st.markdown("---")

    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("Patient Login", use_container_width=True):
            st.session_state.selected_role = 'patient'
            st.session_state.patient_show_register = False
    with col2:
        if st.button("Doctor Login", use_container_width=True):
            st.session_state.selected_role = 'doctor'
    with col3:
        if st.button("Admin Login", use_container_width=True):
            st.session_state.selected_role = 'admin'

    role = st.session_state.get("selected_role", "patient")
    st.info(f"Selected: **{role.upper()}**")

    if role == "patient":
        if st.session_state.patient_show_register:
            with st.form("patient_register_form"):
                st.subheader("Patient Registration")

                col1, col2 = st.columns([3, 2])
                with col1:
                    name = st.text_input("Full Name *")
                with col2:
                    mobile = st.text_input("Phone Number (10 digits) *")

                email = st.text_input("Email *")

                col3, col4 = st.columns(2)
                with col3:
                    password = st.text_input("Password *", type="password")
                with col4:
                    confirm = st.text_input("Confirm Password *", type="password")

                # Real-time feedback
                if email and not is_valid_email(email):
                    st.warning("Please enter a valid email", icon="⚠️")
                if mobile and not is_valid_mobile(mobile):
                    st.warning("Mobile must be 10 digits", icon="📱")
                if password and len(password) < 8:
                    st.warning("Password too short (min 8 chars)", icon="🔑")
                if password and confirm and password != confirm:
                    st.error("Passwords do not match", icon="❌")

                col_reg, col_back = st.columns(2)
                with col_reg:
                    register_btn = st.form_submit_button("Register")
                with col_back:
                    if st.form_submit_button("Back to Login"):
                        st.session_state.patient_show_register = False
                        st.rerun()

                if register_btn:
                    errors = []
                    # ... keep your existing validation ...

                    if errors:
                        st.error("\n".join(errors))
                    else:
                        if register_patient(email, password, name, mobile):
                            # Directly log the user in — no OTP/email needed
                            user = get_patient(email)
                            if user:
                                st.session_state.logged_in = True
                                st.session_state.user_profile = user
                                st.session_state.portal_view = "Dashboard"
                                st.success(f"Registration successful! Welcome, {user['name']} 🎉")
                                st.rerun()
                            else:
                                st.error("Registration succeeded but couldn't fetch user profile.")
                        else:
                            st.warning("This email is already registered. Please log in.")

        else:
            with st.form("patient_login_form"):
                st.subheader("Patient Login")
                email = st.text_input("Email")
                password = st.text_input("Password", type="password")

                col1, col2 = st.columns(2)
                with col1:
                    login_btn = st.form_submit_button("Login")
                with col2:
                    if st.form_submit_button("Register"):
                        st.session_state.patient_show_register = True
                        st.rerun()

                if login_btn:
                    if not email or not password:
                        st.error("Email and password are required.")
                    elif not is_valid_email(email):
                        st.error("Invalid email format.")
                    else:
                        user = get_patient(email)
                        if user and check_password(password, user["password"]):
                            st.session_state.logged_in = True
                            st.session_state.user_profile = user
                            st.session_state.portal_view = "Dashboard"
                            st.rerun()
                        else:
                            st.error("Invalid credentials.")

    elif role == "doctor":
        with st.form("doctor_form"):
            st.subheader("Doctor Login")
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            if st.form_submit_button("Login"):
                if not email or not password:
                    st.error("Email and password are required.")
                elif not is_valid_email(email):
                    st.error("Invalid email format.")
                else:
                    user = get_doctor(email)
                    if user and check_password(password, user["password"]):
                        st.session_state.logged_in = True
                        st.session_state.user_profile = user
                        st.session_state.portal_view = "Dashboard"
                        st.rerun()
                    else:
                        st.error("Invalid credentials.")

    elif role == "admin":
        with st.form("admin_form"):
            st.subheader("Admin Login")
            email = st.text_input("Email", value="admin@app.com")
            password = st.text_input("Password", type="password", value="admin")
            if st.form_submit_button("Login"):
                if email == "admin@app.com" and password == "admin":
                    st.session_state.logged_in = True
                    st.session_state.user_profile = {"email": email, "role": "admin", "name": "System Admin"}
                    st.rerun()
                else:
                    st.error("Invalid admin credentials.")

    st.markdown('</div>', unsafe_allow_html=True)


# ────────────────────────────────────────────────────────────────
# The rest of your original code continues unchanged from here
# (show_doctor_portal, show_patient_portal, chat, prescriptions, etc.)
# ────────────────────────────────────────────────────────────────

def show_doctor_portal():
    user = st.session_state.user_profile
    st.markdown(
        f'<div class="header-bar" style="background: linear-gradient(90deg, #1d4ed8, #3b82f6);"><h1>Doctor Portal</h1><p>Welcome, {user["name"]} (Doctor)</p></div>',
        unsafe_allow_html=True)

    nav_options = {
        "Pending Requests": "Dashboard",
        "Details": "DoctorDetails",
        "View User": "ViewUsers",
        "View Request": "ViewRequests",
        "Write Prescription": "WritePrescription"
    }
    draw_post_login_navbar(nav_options)

    view = st.session_state.portal_view
    if view == "Dashboard":
        show_doctor_dashboard()
    elif view == "LiveChat":
        show_live_chat_interface()
    elif view == "DoctorDetails":
        show_doctor_details()
    elif view == "ViewUsers":
        show_view_users()
    elif view == "ViewRequests":
        show_view_requests()
    elif view == "WritePrescription":
        show_generate_prescription()
    else:
        show_doctor_portal()


def show_doctor_dashboard():
    show_notifications()

    try:
        doc = st.session_state.user_profile
        st.markdown(
            f'''
            <h2 style="color:#0ea5e9; text-align:center; margin-bottom:0;">Pending Requests</h2>
            <p style="text-align:center; margin-top:5px; font-size:1rem; color:#e5e7eb;">
                Requests for Dr. {doc.get("name", "Unknown")} ({doc.get("specialty", "N/A")}).
            </p>
            ''',
            unsafe_allow_html=True
        )
        st.markdown("---")
    except Exception as e:
        st.error(f"Profile error: {e}")
        return

    try:
        my_email = doc.get("email", "")
        if not my_email:
            st.error("Doctor email not found.")
            return

        all_requests = get_chat_requests() or []
        pending = [
            r for r in all_requests
            if r.get("doctor_email") == my_email and r.get("status") == "Pending"
        ]
    except Exception as e:
        st.error(f"Failed to load requests: {e}")
        return

    if not pending:
        st.success("No pending requests at this time.")
        return

    query_params = st.query_params
    if "accept_request" in query_params:
        req_id = query_params["accept_request"]
        try:
            if update_chat_request_status(req_id, "Accepted"):
                st.session_state.active_chat_request = req_id
                st.session_state.portal_view = "LiveChat"
                st.success(f"Request {req_id} accepted! Starting chat...")
            else:
                st.error("Failed to accept request.")
        except Exception as e:
            st.error(f"Accept error: {e}")
        finally:
            st.query_params.clear()
            st.rerun()

    data = []
    for r in pending:
        data.append({
            "RId": r.get('request_id', 'N/A'),
            "PId": r.get('patient_id', 'N/A'),
            "PName": r.get('patient_name', 'N/A'),
            "DId": r.get('doctor_id', 'N/A'),
            "DName": f"{r.get('doctor_name', 'N/A')} ({r.get('specialty', '')})",
            "Flag": r.get('flag', 'N'),
            "Email": r.get('patient_email', 'N/A')
        })

    df = pd.DataFrame(data)

    st.markdown("#### Pending Chat Requests")
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "DName": st.column_config.TextColumn("Doctor (Specialty)", width="medium"),
            "Email": st.column_config.TextColumn("Patient Email", width="large"),
        }
    )

    st.caption("Click an 'Accept' button below to start a live chat session.")

    st.markdown("---")
    st.subheader("Accept a Request")

    cols = st.columns(3)
    for idx, r in enumerate(pending):
        with cols[idx % 3]:
            st.markdown(f"**{r.get('patient_name', 'N/A')}**  \nRequest ID: `{r.get('request_id')}`")
            if st.button("Accept & Start Chat", key=f"accept_btn_{r.get('request_id')}", type="primary",
                         use_container_width=True):
                try:
                    update_chat_request_status(r.get('request_id'), "Accepted")
                    st.session_state.active_chat_request = r.get('request_id')
                    st.session_state.portal_view = "LiveChat"
                    st.success(f"Chat started with {r.get('patient_name', '')}!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to accept: {e}")

    st.markdown("---")
    st.subheader("Patient Details")

    for r in pending:
        with st.expander(f"Request ID: {r.get('request_id', 'N/A')} — {r.get('patient_name', 'N/A')}"):
            col1, col2 = st.columns(2)
            with col1:
                st.write("**Patient ID**", r.get('patient_id', 'N/A'))
                st.write("**Name**", r.get('patient_name', 'N/A'))
                st.write("**Email**", r.get('patient_email', 'N/A'))
                st.write("**Mobile**", r.get('patient_mobile', 'N/A') or "Not provided")
            with col2:
                st.write("**Specialty**", r.get('specialty', 'N/A'))
                st.write("**Doctor**", r.get('doctor_name', 'N/A'))
                st.write("**Timestamp**", r.get('timestamp', 'N/A'))

            st.markdown("**Query / Concern:**")
            st.info(r.get('query', 'No query provided.'))


def show_generate_prescription():
    rid = st.session_state.get('active_chat_request')
    if not rid:
        st.warning("No active chat selected. Please go to Live Chat first.")
        return

    req = next((r for r in get_chat_requests() if r['request_id'] == rid), None)
    if not req:
        st.error("Chat request not found.")
        return

    patient_name = req['patient_name']
    patient_email = req['patient_email']

    st.subheader(f"Generate Prescription for {patient_name} (Chat #{rid})")

    with st.form("prescription_form"):
        st.info("Add medicines one by one")

        if 'prescription_meds' not in st.session_state:
            st.session_state.prescription_meds = []

        col1, col2, col3, col4 = st.columns([3, 2, 2, 1])
        with col1:
            med_name = st.text_input("Medicine Name", key="med_name_input")
        with col2:
            dosage = st.text_input("Dosage (e.g., 1 tab twice daily)", key="dosage_input")
        with col3:
            duration = st.text_input("Duration (e.g., 5 days)", key="duration_input")
        with col4:
            add_med = st.form_submit_button("Add")

        if add_med:
            if med_name.strip():
                st.session_state.prescription_meds.append({
                    "name": med_name.strip(),
                    "dosage": dosage.strip(),
                    "duration": duration.strip()
                })
                st.success(f"Added: {med_name}")
                st.rerun()
            else:
                st.error("Medicine name is required.")

        if st.session_state.prescription_meds:
            st.markdown("### Current Medicines")
            for i, med in enumerate(st.session_state.prescription_meds):
                st.markdown(f"**{i + 1}.** {med['name']} — {med['dosage']} — {med['duration']}")
                if st.button("Remove", key=f"remove_med_{i}"):
                    st.session_state.prescription_meds.pop(i)
                    st.rerun()

        advice = st.text_area("Additional Advice / Notes", height=100)

        col_save, col_clear = st.columns([1, 1])
        with col_save:
            save = st.form_submit_button("Save & Send Prescription", type="primary")
        with col_clear:
            clear = st.form_submit_button("Clear All")

        if save:
            if not st.session_state.prescription_meds:
                st.error("Add at least one medicine.")
            else:
                add_prescription(
                    request_id=rid,
                    patient_email=patient_email,
                    doctor_email=st.session_state.user_profile['email'],
                    doctor_name=st.session_state.user_profile['name'],
                    patient_name=patient_name,
                    medicines=st.session_state.prescription_meds,
                    advice=advice.strip()
                )
                st.success("Prescription saved and sent to patient!")
                st.session_state.prescription_meds = []
                st.rerun()

        if clear:
            st.session_state.prescription_meds = []
            st.rerun()


def show_doctor_details():
    u = st.session_state.user_profile
    st.header("Profile")
    st.metric("Name", u.get('name', 'N/A'))
    st.metric("Specialty", u.get('specialty', 'N/A'))
    st.metric("ID", u.get('doc_id', 'N/A'))


def show_view_requests():
    st.header("All Chat Requests")
    requests = get_chat_requests()
    if not requests:
        st.info("No chat requests found.")
        return

    data = []
    for r in requests:
        status_color = {
            "Pending": "#f59e0b",
            "Accepted": "#10b981",
            "Closed": "#ef4444"
        }.get(r.get('status', ''), "#6b7280")

        data.append({
            "ID": r.get('request_id', 'N/A'),
            "Patient": r.get('patient_name', 'N/A'),
            "Doctor": r.get('doctor_name', 'N/A'),
            "Specialty": r.get('specialty', 'N/A'),
            "Query": (r.get('query', '')[:50] + "..." if len(r.get('query', '')) > 50 else r.get('query', '')),
            "Status": f"<span style='color:{status_color}; font-weight:bold;'>{r.get('status', 'N/A')}</span>",
            "Time": r.get('timestamp', 'N/A')
        })

    df = pd.DataFrame(data)
    st.markdown(df.to_html(escape=False, index=False), unsafe_allow_html=True)


def show_patient_portal():
    user = st.session_state.user_profile
    show_notifications()

    st.markdown(
        f'<div class="header-bar" style="background: linear-gradient(90deg, #10b981, #34d399);"><h1>Patient Portal</h1><p>Welcome, {user["name"]} (Patient)</p></div>',
        unsafe_allow_html=True)

    nav_options = {
        "Dashboard": "Dashboard",
        "My Chats": "MyChats",               # ← This is the key missing piece
        "Request Chat": "RequestChat",
        "View Doctors": "ViewDoctors",
        "My Prescriptions": "MyPrescriptions",
        "Give Feedback": "GiveFeedback"
    }
    draw_post_login_navbar(nav_options)

    view = st.session_state.portal_view

    if view == "Dashboard":
        show_patient_symptom_checker()

    elif view == "MyChats":
        st.subheader("My Active Conversations")

        email = user['email']
        c = get_doctors_cursor()
        c.execute("""
            SELECT request_id, doctor_name, specialty, timestamp
            FROM chat_requests
            WHERE patient_email = ? AND status = 'Accepted'
            ORDER BY timestamp DESC
        """, (email,))
        chats = c.fetchall()

        if not chats:
            st.info("No active chats yet.")
            st.caption("When a doctor accepts your request, it will appear here.")
            if st.button("Request New Chat", type="primary"):
                st.session_state.portal_view = "RequestChat"
                st.rerun()
        else:
            for chat in chats:
                rid, doc_name, specialty, ts = chat
                col1, col2 = st.columns([4,1])
                with col1:
                    st.markdown(f"**Dr. {doc_name}** — {specialty}")
                    st.caption(f"Started: {ts}")
                with col2:
                    if st.button("Open Chat", key=f"pat_open_{rid}", type="primary"):
                        st.session_state.active_chat_request = rid
                        st.session_state.portal_view = "LiveChat"
                        st.rerun()
                st.markdown("---")

    elif view == "LiveChat":
        show_live_chat_interface()

    elif view == "RequestChat":
        show_request_chat_form()

    elif view == "ViewDoctors":
        show_view_doctors_for_portal()

    elif view == "MyPrescriptions":
        show_patient_prescriptions()

    elif view == "GiveFeedback":
        show_feedback_form()

    else:
        st.info("Select an option from the navigation bar.")


def is_valid_symptom(text):
    """
    Checks if the input looks like a valid symptom description.
    Rejects empty strings, numbers-only, or meaningless symbols.
    """
    text = text.strip()
    if not text:
        return False

    # Remove spaces and check if mostly numbers or symbols
    letters_only = re.sub(r'[^A-Za-z]', '', text)
    if len(letters_only) < 3:  # too short to be meaningful
        return False

    # Reject repetitive meaningless characters like 'aaaa', 'xxxx'
    if all(c * len(text.replace(" ", "")) == text.replace(" ", "") for c in set(text.replace(" ", ""))):
        return False

    return True

def show_patient_symptom_checker():
    st.subheader("AI-Powered Symptom Checker (Powered by Google Gemini)")

    if client is None:
        st.error("AI Symptom Checker is currently unavailable — Google API key not configured or invalid.")
        st.info("Set GOOGLE_API_KEY in your .env file.")
        return

    st.info("Describe your symptoms in detail. Gemini will recommend the most suitable medical specialty.")

    if "last_recommended_specialty" not in st.session_state:
        st.session_state.last_recommended_specialty = None

    with st.form("symptom_form", clear_on_submit=False):
        sym = st.text_area(
            "Describe your symptoms",
            placeholder="Example: I have severe headache for 3 days, nausea, sensitivity to light, and neck stiffness...",
            height=200,
            key="symptom_input_area"
        )

        disclaimer = st.checkbox(
            "I understand this is NOT a medical diagnosis and is for informational purposes only.",
            value=False
        )

        analyze_btn = st.form_submit_button("Analyze with Gemini AI", type="primary")

        if analyze_btn:
            if not is_valid_symptom(sym):
                st.error("Please enter a **valid symptom description**. Avoid empty input, random numbers, or meaningless characters.")
            elif not disclaimer:
                st.warning("Please acknowledge the disclaimer.")
            else:
                with st.spinner("Analyzing symptoms using Google Gemini..."):
                    try:
                        messages = [
                            SystemMessage(content="""
You are an expert medical triage assistant.
Analyze symptoms and recommend ONE specialty only.
Detect emergencies.
Never diagnose or prescribe.

Respond exactly in this format:

SPECIALTY: [One specialty]
URGENCY: [Low / Moderate / High / Emergency]
RECOMMENDATION: [1-2 sentences, simple language]
EMERGENCY_ADVICE: [Strong warning if needed, else "None"]
                            """),
                            HumanMessage(content=f"Symptoms: {sym}")
                        ]

                        response = client.invoke(messages)
                        result = response.content

                        if isinstance(result, list):
                            result = " ".join(
                                [str(part.get("text", str(part))) for part in result if isinstance(part, dict)])
                        elif not isinstance(result, str):
                            result = str(result)

                        result = result.strip()

                        parsed = {
                            "SPECIALTY": "General Physician",
                            "URGENCY": "Low",
                            "RECOMMENDATION": "Please consult a doctor.",
                            "EMERGENCY_ADVICE": "None"
                        }
                        for line in result.split('\n'):
                            if ':' in line:
                                k, v = line.split(':', 1)
                                key = k.strip().upper()
                                if key in parsed:
                                    parsed[key] = v.strip()

                        specialty = parsed["SPECIALTY"]
                        urgency = parsed["URGENCY"]
                        recommendation = parsed["RECOMMENDATION"]
                        emergency_advice = parsed["EMERGENCY_ADVICE"]

                        st.session_state.last_recommended_specialty = specialty

                        add_submission({
                            "date": time.strftime("%Y-%m-%d %H:%M:%S"),
                            "symptoms": sym,
                            "prediction": specialty,
                            "advice": recommendation,
                            "urgency": urgency,
                            "patient_email": st.session_state.user_profile['email']
                        })

                        st.markdown("---")
                        if urgency == "Emergency":
                            st.error("EMERGENCY DETECTED")
                            if emergency_advice != "None":
                                st.warning(emergency_advice)
                            st.error("Seek immediate medical help.")
                        elif urgency == "High":
                            st.warning("High urgency — consult urgently.")
                        elif urgency == "Moderate":
                            st.info("Moderate — consult soon.")
                        else:
                            st.success("Low urgency.")

                        st.markdown(f"### Recommended Specialty: **{specialty}**")
                        st.info(f"**Why:** {recommendation}")

                        st.caption("This AI analysis is informational only. Always consult a qualified doctor.")

                    except Exception as e:
                        st.error("AI analysis failed. Please try again later.")
                        st.caption(f"Error: {str(e)}")

    if st.session_state.last_recommended_specialty:
        if st.button(f"Request Chat with {st.session_state.last_recommended_specialty} Doctor",
                     type="primary", use_container_width=True):
            st.session_state.portal_view = "RequestChat"
            st.session_state.selected_specialty = st.session_state.last_recommended_specialty
            st.rerun()
def show_request_chat_form():
    st.subheader("Request Chat with Doctor")

    pre_selected = st.session_state.get('selected_specialty', "--")
    if pre_selected != "--":
        st.success(f"Gemini recommends: **{pre_selected}**")

    with st.form("request_chat_form"):
        specialty_index = MOCK_SPECIALTIES.index(pre_selected) + 1 if pre_selected in MOCK_SPECIALTIES else 0
        specialty = st.selectbox("Specialty", ["--"] + MOCK_SPECIALTIES, index=specialty_index)

        if 'selected_specialty' in st.session_state and specialty != "--":
            del st.session_state.selected_specialty

        docs = [d for d in get_all_doctors() if d.get('specialty') == specialty]
        if specialty == "--" or not docs:
            st.info("Select specialty to view doctors.")
            doc = "No doctors available"
        else:
            doctor_options = [f"{d.get('name')} ({d.get('doc_id')})" for d in docs]
            doc = st.selectbox("Select Doctor", doctor_options)

        query = st.text_area("Describe your concern", height=120)

        submitted = st.form_submit_button("Submit Request")
        if submitted:
            if specialty == "--":
                st.error("Select specialty.")
            elif "No doctors" in doc:
                st.error("No doctor available.")
            elif not query.strip():
                st.error("Describe your concern.")
            else:
                doc_id = doc.split(' (')[1][:-1]
                d = next(x for x in docs if x['doc_id'] == doc_id)
                req = {
                    "request_id": st.session_state.next_request_id,
                    "patient_email": st.session_state.user_profile['email'],
                    "patient_name": st.session_state.user_profile['name'],
                    "patient_id": "P" + st.session_state.user_profile.get('mobile', '')[-6:],
                    "doctor_email": d['email'],
                    "doctor_name": d['name'],
                    "doctor_id": d['doc_id'],
                    "qualification": d.get('qualification', ''),
                    "specialty": specialty,
                    "query": query,
                    "status": "Pending",
                    "flag": "N",
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                }
                add_chat_request(req)
                st.session_state.next_request_id += 1
                st.success("Request sent!")
                st.rerun()


def show_patient_prescriptions():
    st.subheader("My Prescriptions")
    prescriptions = get_prescriptions_for_patient(st.session_state.user_profile['email'])

    if not prescriptions:
        st.info("No prescriptions yet.")
        return

    for pres in prescriptions:
        with st.expander(
                f"Prescription from Dr. {pres['doctor_name']} — {pres['timestamp']} (Chat #{pres['request_id']})"):
            st.write("**Medicines:**")
            for i, med in enumerate(pres['medicines']):
                st.markdown(f"{i + 1}. **{med['name']}** — {med['dosage']} — {med['duration']}")

            if pres['advice']:
                st.markdown("**Doctor's Advice:**")
                st.info(pres['advice'])

            if st.button("Download as PDF", key=f"pdf_btn_{pres['id']}"):
                pdf_buffer = generate_prescription_pdf(pres, st.session_state.user_profile['name'])
                b64 = base64.b64encode(pdf_buffer.getvalue()).decode()
                filename = f"Prescription_Chat{pres['request_id']}_{pres['timestamp'][:10].replace('-', '')}.pdf"
                href = f'<a href="data:application/pdf;base64,{b64}" download="{filename}">Click here to download</a>'
                st.markdown(href, unsafe_allow_html=True)


def generate_prescription_pdf(prescription, patient_name):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=inch, bottomMargin=inch, leftMargin=inch, rightMargin=inch)
    styles = getSampleStyleSheet()
    story = []

    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=28, alignment=1, spaceAfter=30,
                                 textColor=colors.HexColor('#0066cc'))
    story.append(Paragraph("Medical Prescription", title_style))
    story.append(Spacer(1, 20))

    header_data = [
        ["Patient Name:", patient_name],
        ["Prescribed by:", f"Dr. {prescription['doctor_name']}"],
        ["Date:", prescription['timestamp'].split(' ')[0]],
        ["Chat Reference:", f"#{prescription['request_id']}"]
    ]
    header_table = Table(header_data, colWidths=[2 * inch, 4 * inch])
    header_table.setStyle(TableStyle([('GRID', (0, 0), (-1, -1), 1, colors.lightgrey)]))
    story.append(header_table)
    story.append(Spacer(1, 30))

    med_data = [["No.", "Medicine", "Dosage", "Duration"]]
    for i, med in enumerate(prescription['medicines']):
        med_data.append([str(i + 1), med['name'], med['dosage'], med['duration']])
    med_table = Table(med_data, colWidths=[0.6 * inch, 2.8 * inch, 2 * inch, 1.6 * inch])
    med_table.setStyle(TableStyle([('GRID', (0, 0), (-1, -1), 1, colors.black)]))
    story.append(med_table)

    if prescription['advice']:
        story.append(Spacer(1, 40))
        story.append(Paragraph("<b>Additional Advice:</b>", styles['Heading3']))
        story.append(Paragraph(prescription['advice'], styles['Normal']))

    doc.build(story)
    buffer.seek(0)
    return buffer


def show_live_chat_interface():
    rid = st.session_state.active_chat_request
    if not rid:
        st.error("No active chat selected.")
        return

    req = next((r for r in get_chat_requests() if r.get('request_id') == rid), None)
    if not req or req.get('status') == 'Closed':
        st.error("This chat is closed.")
        st.session_state.active_chat_request = None
        st.rerun()
        return

    # Show who we are chatting with
    if st.session_state.user_profile['role'] == 'patient':
        interlocutor = req.get('doctor_name', 'Doctor')
    else:
        interlocutor = req.get('patient_name', 'Patient')

    st.markdown(f"### Chat with **{interlocutor}** (Request ID: {rid})")

    messages = get_chat_messages(rid) or []
    attachments = get_chat_attachments(rid) or []

    # Display messages and attachments
    st.markdown('<div class="chat-messages">', unsafe_allow_html=True)

    for m in messages:
        sender_name = m.get('sender', 'Unknown')
        is_user = sender_name == st.session_state.user_profile.get('name')
        cls = "user-message" if is_user else "doctor-message"
        st.markdown(
            f'<div class="chat-message {cls}">'
            f'<div class="message-sender">{sender_name} • {m.get("timestamp", "")}</div>'
            f'<div>{m.get("text", "")}</div>'
            f'</div>',
            unsafe_allow_html=True
        )

    for a in attachments:
        sender_name = a.get('sender', 'Unknown')
        is_user = sender_name == st.session_state.user_profile.get('name')
        cls = "user-message" if is_user else "doctor-message"
        file_path = a['file_path']
        filename = a['filename']
        timestamp = a.get('timestamp', '')

        st.markdown(
            f'<div class="chat-message {cls}">'
            f'<div class="message-sender">{sender_name} • {timestamp}</div>'
            f'<div><strong>Attached:</strong> {filename}</div>',
            unsafe_allow_html=True
        )
        if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
            st.image(file_path, caption=filename, width=300)
        else:
            with open(file_path, "rb") as f:
                st.download_button(f"Download {filename}", f, file_name=filename)

        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)

    # ────────────────────────────────────────────────
    # THE FORM + SEND + NOTIFICATION LOGIC (THIS IS THE ONLY FORM YOU NEED)
    # ────────────────────────────────────────────────
    with st.form("chat_form", clear_on_submit=True):
        col_text, col_file = st.columns([4, 1])
        with col_text:
            msg = st.text_area("Type message...", height=100)
        with col_file:
            uploaded_file = st.file_uploader("Attach", type=['png', 'jpg', 'jpeg', 'pdf', 'txt', 'webp'],
                                             label_visibility="collapsed")

        col_send, col_end = st.columns([2, 3])
        with col_send:
            send_btn = st.form_submit_button("Send", type="primary")
        with col_end:
            end_btn = st.form_submit_button("End Session", type="secondary")

        if send_btn:
            current_message = msg.strip()
            has_content = False

            # Save text message
            if current_message:
                if 'last_sent_message' not in st.session_state or \
                   st.session_state.last_sent_message != current_message:
                    add_chat_message(
                        rid,
                        st.session_state.user_profile['name'],
                        st.session_state.user_profile['role'],
                        current_message
                    )
                    st.session_state.last_sent_message = current_message
                    has_content = True

            # Save attachment
            if uploaded_file:
                os.makedirs("uploads", exist_ok=True)
                safe_name = f"{rid}_{int(time.time())}_{uploaded_file.name.replace(' ', '_')}"
                path = os.path.join("uploads", safe_name)
                with open(path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                add_chat_attachment(
                    rid,
                    uploaded_file.name,
                    path,
                    st.session_state.user_profile['name'],
                    st.session_state.user_profile['role']
                )
                has_content = True

            # If something was sent → notify the other person (doctor or patient)
            if has_content:
                # Find the other person's email
                if st.session_state.user_profile['role'] == 'patient':
                    receiver_email = req['doctor_email']
                    sender_name = st.session_state.user_profile['name']  # patient
                else:
                    receiver_email = req['patient_email']
                    sender_name = st.session_state.user_profile['name']  # doctor

                # Create meaningful notification message
                if current_message:
                    preview = current_message[:70] + "..." if len(current_message) > 70 else current_message
                    notification_text = f"New message from {sender_name} in chat #{rid}: {preview}"
                else:
                    notification_text = f"New attachment from {sender_name} in chat #{rid}: {uploaded_file.name}"

                # Send notification to the other party
                add_notification(
                    receiver_email,
                    notification_text,
                    rid
                )

            if has_content:
                st.rerun()

        if end_btn:
            update_chat_request_status(rid, "Closed")
            st.session_state.active_chat_request = None
            st.success("Session closed.")
            st.rerun()

def show_view_doctors_for_portal():
    docs = get_all_doctors()
    df = pd.DataFrame([{
        "Name": d.get('name', 'N/A'),
        "Specialty": d.get('specialty', 'N/A'),
        "Qualification": d.get('qualification', 'N/A'),
        "ID": d.get('doc_id', 'N/A'),
        "Email": d.get('email', 'N/A')
    } for d in docs])
    st.dataframe(df, use_container_width=True)


def show_feedback_form():
    st.subheader("Give Feedback")
    with st.form("feedback_form"):
        fb = st.text_area("Your feedback")
        if st.form_submit_button("Submit"):
            add_feedback({
                "user_email": st.session_state.user_profile.get('email'),
                "feedback": fb,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            })
            st.success("Thank you!")


def show_view_users():
    st.header("All Patients")

    patients = get_all_patients()

    if not patients:
        st.info("No patients registered yet.")
        return

    df_original = pd.DataFrame(patients)
    df_original = df_original.rename(columns={
        'email': 'Email',
        'name': 'Full Name',
        'mobile': 'Mobile Number'
    })

    df = df_original.copy()
    df = df.reset_index(drop=True)
    df.insert(0, "No.", df.index + 1)

    total_patients = len(df_original)
    st.write(f"**Total Registered Patients: {total_patients}**")

    search_term = st.text_input("🔍 Search by Name, Email, or Mobile", "")

    if search_term:
        mask = (
                df['Full Name'].str.contains(search_term, case=False, na=False) |
                df['Email'].str.contains(search_term, case=False, na=False) |
                df['Mobile Number'].str.contains(search_term, case=False, na=False)
        )
        df = df[mask].copy()
        df = df.reset_index(drop=True)
        df["No."] = df.index + 1
        st.write(f"**Found {len(df)} patient(s) matching your search**")

    if df.empty:
        st.warning("No patients found matching your search criteria.")
        return

    items_per_page = 10
    total_pages = (len(df) + items_per_page - 1) // items_per_page

    col1, col2 = st.columns([1, 4])
    with col1:
        page_number = st.number_input(
            "Page",
            min_value=1,
            max_value=total_pages,
            value=1,
            step=1,
            key="patient_page_number"
        )

    start_idx = (page_number - 1) * items_per_page
    end_idx = min(start_idx + items_per_page, len(df))
    page_df = df.iloc[start_idx:end_idx].copy()
    page_df["No."] = range(start_idx + 1, end_idx + 1)

    st.markdown(f"**Showing patients {start_idx + 1}–{end_idx} of {len(df)}**")

    st.dataframe(
        page_df.drop(columns=["No."]),
        use_container_width=True,
        hide_index=True
    )

    st.markdown("---")
    st.subheader("📥 Download Patient List")

    export_df = df.drop(columns=["No."]) if "No." in df.columns else df

    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        export_df.to_excel(writer, index=False, sheet_name='Patients')

    output.seek(0)
    excel_data = output.getvalue()

    st.download_button(
        label="📄 Download Full List as Excel (.xlsx)",
        data=excel_data,
        file_name=f"Patients_List_{datetime.now().strftime('%Y-%m-%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )

    st.success("Download ready! Click the button above to get the Excel file.")


def show_view_feedback():
    st.header("User Feedback")
    fb = get_feedback()
    if fb:
        df = pd.DataFrame(fb)
        st.dataframe(df)
    else:
        st.info("No feedback yet.")


def show_assign_chat_form():
    st.header("Assign Chat (Admin)")
    st.info("Manual assignment feature coming soon.")


__all__ = [
    'show_login_page', 'show_patient_portal',
    'show_doctor_portal', 'show_admin_portal'
]