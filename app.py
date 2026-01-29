import streamlit as st
import time
from db import (
    get_chat_requests, mark_notifications_read_by_request,
    add_chat_request, get_patient, get_doctor
)
from ui import (
    show_login_page, show_patient_portal,
    show_doctor_portal, show_admin_portal
)
from utils import set_page_style, init_session_state


def main():

    set_page_style()
    init_session_state()

    query_params = st.query_params


    if 'view' in query_params and query_params['view'] == 'LiveChat' and 'req_id' in query_params:
        try:
            req_id = int(query_params['req_id'])
            if st.session_state.logged_in:
                user = st.session_state.user_profile
                req = next((r for r in get_chat_requests() if r['request_id'] == req_id), None)
                if req and req['status'] != 'Closed':
                    if req['patient_email'] == user.get('email') or req['doctor_email'] == user.get('email'):
                        st.session_state.active_chat_request = req_id
                        st.session_state.portal_view = "LiveChat"
                        mark_notifications_read_by_request(req_id, user['email'])
                        st.query_params.clear()
                        st.rerun()
        except (ValueError, KeyError):
            st.warning("Invalid chat request ID.")
            st.query_params.clear()

    # 2. Admin: Assign Chat via URL
    elif ('assign_chat' in query_params and
          'patient_email' in query_params and
          'doctor_email' in query_params):

        if (st.session_state.logged_in and
                st.session_state.user_profile['role'] == 'admin' and
                st.session_state.user_profile['email'] == 'admin@app.com'):

            p_email = query_params['patient_email']
            d_email = query_params['doctor_email']

            patient = get_patient(p_email)
            doctor = get_doctor(d_email)

            if patient and doctor:
                new_req = {
                    "request_id": st.session_state.next_request_id,
                    "patient_email": p_email,
                    "doctor_email": d_email,
                    "specialty": doctor['specialty'],
                    "doctor_name": doctor['name'],
                    "doctor_id": doctor['doc_id'],
                    "qualification": doctor['qualification'],
                    "query": f"Admin-initiated consultation between {patient['name']} and Dr. {doctor['name']}",
                    "status": "Accepted",
                    "patient_name": patient['name'],
                    "patient_id": patient['patient_id'],
                    "flag": "N",
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                }
                add_chat_request(new_req)
                st.session_state.next_request_id += 1
                st.query_params.clear()
                st.success(f"Chat #{new_req['request_id']} created.")
                st.rerun()
            else:
                st.error("Invalid patient or doctor.")
                st.query_params.clear()


    if st.session_state.logged_in:
        user = st.session_state.user_profile
        role = user['role']


        st.markdown(
            f"""
            <div class="header-bar">
                <h1>E-Healthcare System</h1>
                <p>Logged in as <strong>{user['name']}</strong> ({role.title()})</p>
            </div>
            """,
            unsafe_allow_html=True
        )

        # Route by role
        if role == 'admin' and user['email'] == 'admin@app.com':
            show_admin_portal()
        elif role == 'doctor':
            show_doctor_portal()
        elif role == 'patient':
            show_patient_portal()
        else:
            st.error("Unauthorized role.")
            st.session_state.logged_in = False
            st.rerun()

    else:
        show_login_page()


if __name__ == "__main__":
    main()