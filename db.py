import sqlite3
import bcrypt
import time
import random
import streamlit as st
import smtplib
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from pathlib import Path

def load_env():
    env_path = Path('.env')
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()

load_env()

def get_patients_conn():
    if 'patients_conn' not in st.session_state:
        st.session_state.patients_conn = sqlite3.connect('patients.db', check_same_thread=False)
    return st.session_state.patients_conn

def get_doctors_conn():
    if 'doctors_conn' not in st.session_state:
        st.session_state.doctors_conn = sqlite3.connect('doctors.db', check_same_thread=False)
    return st.session_state.doctors_conn

def get_patients_cursor(): return get_patients_conn().cursor()
def get_doctors_cursor():  return get_doctors_conn().cursor()

def commit_patients(): get_patients_conn().commit()
def commit_doctors():  get_doctors_conn().commit()

def init_databases():
    pc = get_patients_cursor()
    pc.execute('''
        CREATE TABLE IF NOT EXISTS patients (
            email TEXT PRIMARY KEY,
            password TEXT NOT NULL,
            name TEXT NOT NULL,
            mobile TEXT,
            patient_id TEXT UNIQUE
        )
    ''')
    pc.execute('''
        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            symptoms TEXT,
            prediction TEXT,
            patient_email TEXT
        )
    ''')
    pc.execute('''
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email TEXT,
            feedback TEXT,
            timestamp TEXT
        )
    ''')
    pc.execute('''
        CREATE TABLE IF NOT EXISTS otp_verifications (
            email TEXT PRIMARY KEY,
            otp TEXT NOT NULL,
            created_at TEXT NOT NULL,
            attempts INTEGER DEFAULT 0
        )
    ''')
    commit_patients()

    dc = get_doctors_cursor()
    dc.execute('''
        CREATE TABLE IF NOT EXISTS doctors (
            email TEXT PRIMARY KEY,
            password TEXT NOT NULL,
            name TEXT NOT NULL,
            mobile TEXT,
            specialty TEXT,
            doc_id TEXT UNIQUE,
            qualification TEXT
        )
    ''')
    dc.execute('''
        CREATE TABLE IF NOT EXISTS chat_requests (
            request_id INTEGER PRIMARY KEY,
            patient_email TEXT,
            doctor_email TEXT,
            specialty TEXT,
            doctor_name TEXT,
            doctor_id TEXT,
            qualification TEXT,
            query TEXT,
            status TEXT,
            patient_name TEXT,
            patient_id TEXT,
            flag TEXT,
            timestamp TEXT
        )
    ''')
    dc.execute('''
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id INTEGER,
            sender TEXT,
            role TEXT,
            text TEXT,
            timestamp TEXT
        )
    ''')
    dc.execute('''
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email TEXT,
            message TEXT,
            status TEXT DEFAULT 'unread',
            timestamp TEXT,
            request_id INTEGER
        )
    ''')

    # File attachments table
    dc.execute('''
        CREATE TABLE IF NOT EXISTS chat_attachments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            file_path TEXT NOT NULL,
            sender TEXT NOT NULL,
            role TEXT NOT NULL,
            timestamp TEXT NOT NULL
        )
    ''')

    # Prescriptions table
    dc.execute('''
        CREATE TABLE IF NOT EXISTS prescriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id INTEGER NOT NULL,
            patient_email TEXT NOT NULL,
            doctor_email TEXT NOT NULL,
            doctor_name TEXT NOT NULL,
            patient_name TEXT NOT NULL,
            medicines TEXT NOT NULL,  -- JSON string
            advice TEXT,
            timestamp TEXT NOT NULL
        )
    ''')

    commit_doctors()

if 'db_initialized' not in st.session_state:
    init_databases()
    st.session_state.db_initialized = True

def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def check_password(pw: str, hashed: str) -> bool:
    return bcrypt.checkpw(pw.encode('utf-8'), hashed.encode('utf-8'))

def register_patient(email, password, name, mobile):
    pid = "P" + (mobile[-6:] if mobile and len(mobile) >= 6 else f"{random.randint(100000,999999)}")
    c = get_patients_cursor()
    try:
        c.execute('INSERT INTO patients (email, password, name, mobile, patient_id) VALUES (?, ?, ?, ?, ?)',
                  (email, hash_password(password), name, mobile, pid))
        commit_patients()
        return True
    except sqlite3.IntegrityError:
        return False

def get_patient(email):
    c = get_patients_cursor()
    c.execute('SELECT * FROM patients WHERE email = ?', (email,))
    row = c.fetchone()
    if row:
        return {"email": row[0], "password": row[1], "name": row[2], "mobile": row[3], "patient_id": row[4], "role": "patient"}
    return None

def add_doctor(email, password, name, mobile, specialty, doc_id, qualification):
    c = get_doctors_cursor()
    try:
        c.execute('''
            INSERT INTO doctors (email, password, name, mobile, specialty, doc_id, qualification)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (email, hash_password(password), name, mobile, specialty, doc_id, qualification))
        commit_doctors()
        return True
    except sqlite3.IntegrityError:
        return False

def get_doctor(email):
    c = get_doctors_cursor()
    c.execute('SELECT * FROM doctors WHERE email = ?', (email,))
    row = c.fetchone()
    if row:
        return {
            "email": row[0], "password": row[1], "name": row[2],
            "mobile": row[3], "specialty": row[4], "doc_id": row[5],
            "qualification": row[6], "role": "doctor"
        }
    return None

def get_all_doctors():
    c = get_doctors_cursor()
    c.execute('SELECT email, name, mobile, specialty, doc_id, qualification FROM doctors')
    return [{"email":r[0],"name":r[1],"mobile":r[2],"specialty":r[3],"doc_id":r[4],"qualification":r[5],"role":"doctor"} for r in c.fetchall()]

def get_all_patients():
    """
    Retrieves all registered patients from the patients database.
    Returns a list of dictionaries with patient details.
    """
    c = get_patients_cursor()
    c.execute('SELECT email, name, mobile, patient_id FROM patients ORDER BY name')
    rows = c.fetchall()
    patients = []
    for row in rows:
        patients.append({
            "email": row[0],
            "name": row[1],
            "mobile": row[2],
            "patient_id": row[3]
        })
    return patients

def save_otp(email, otp):
    c = get_patients_cursor()
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    c.execute('INSERT OR REPLACE INTO otp_verifications (email, otp, created_at, attempts) VALUES (?, ?, ?, 0)', (email, otp, now))
    commit_patients()

def get_otp(email):
    c = get_patients_cursor()
    c.execute('SELECT otp, created_at, attempts FROM otp_verifications WHERE email = ?', (email,))
    row = c.fetchone()
    if row:
        otp, created_at, attempts = row
        if (time.time() - time.mktime(time.strptime(created_at, "%Y-%m-%d %H:%M:%S"))) > 600:
            delete_otp(email)
            return None
        return {"otp": otp, "attempts": attempts}
    return None

def increment_otp_attempts(email):
    c = get_patients_cursor()
    c.execute('UPDATE otp_verifications SET attempts = attempts + 1 WHERE email = ?', (email,))
    commit_patients()

def delete_otp(email):
    c = get_patients_cursor()
    c.execute('DELETE FROM otp_verifications WHERE email = ?', (email,))
    commit_patients()

def send_verification_email(email, otp):
    sender = os.getenv("EMAIL_USER")
    password = os.getenv("EMAIL_PASS")
    if not sender or not password:
        st.error("Email not configured. Add EMAIL_USER and EMAIL_PASS to .env")
        return False

    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = email
    msg["Subject"] = "E-Healthcare: Verify Your Account"

    body = f"""
    <h2>Welcome!</h2>
    <p>Your verification code:</p>
    <h1 style="letter-spacing:5px;color:#0066cc;">{otp}</h1>
    <p>Expires in 10 minutes.</p>
    """
    msg.attach(MIMEText(body, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender, password)
            server.sendmail(sender, email, msg.as_string())
        return True
    except Exception as e:
        st.error(f"Email failed: {e}")
        return False

def get_chat_requests():
    c = get_doctors_cursor()
    c.execute('SELECT * FROM chat_requests ORDER BY timestamp DESC')
    return [{k:v for k,v in zip([
        "request_id","patient_email","doctor_email","specialty","doctor_name","doctor_id",
        "qualification","query","status","patient_name","patient_id","flag","timestamp"
    ], r)} for r in c.fetchall()]

def add_chat_request(req):
    c = get_doctors_cursor()
    c.execute('INSERT INTO chat_requests VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)', (
        req['request_id'], req['patient_email'], req['doctor_email'], req['specialty'],
        req['doctor_name'], req['doctor_id'], req['qualification'], req['query'],
        req['status'], req['patient_name'], req['patient_id'], req['flag'], req['timestamp']
    ))
    commit_doctors()
    add_notification(req['doctor_email'], f"New request from {req['patient_name']} (ID: {req['request_id']})", req['request_id'])

def update_chat_request_status(rid, status):
    c = get_doctors_cursor()
    c.execute('SELECT patient_email, doctor_name FROM chat_requests WHERE request_id = ?', (rid,))
    res = c.fetchone()
    if res:
        p_email, d_name = res
        c.execute('UPDATE chat_requests SET status = ? WHERE request_id = ?', (status, rid))
        commit_doctors()
        if status == "Accepted":
            add_notification(p_email, f"Dr. {d_name} accepted (ID: {rid})", rid)
        elif status == "Closed":
            add_notification(p_email, f"Chat closed (ID: {rid})", rid)

def get_chat_messages(rid):
    c = get_doctors_cursor()
    c.execute('SELECT sender, role, text, timestamp FROM chat_messages WHERE request_id = ? ORDER BY id', (rid,))
    return [{"sender":r[0],"role":r[1],"text":r[2],"timestamp":r[3]} for r in c.fetchall()]

def add_chat_message(rid, sender, role, text):
    ts = time.strftime("%H:%M")
    c = get_doctors_cursor()
    c.execute('INSERT INTO chat_messages (request_id, sender, role, text, timestamp) VALUES (?,?,?,?,?)',
              (rid, sender, role, text, ts))
    commit_doctors()
    c.execute('SELECT patient_email, doctor_email FROM chat_requests WHERE request_id = ?', (rid,))
    p, d = c.fetchone()
    recipient = d if role == "patient" else p
    add_notification(recipient, f"New message from {sender}", rid)

# File attachment functions
def add_chat_attachment(request_id, filename, file_path, sender, role):
    ts = time.strftime("%H:%M")
    c = get_doctors_cursor()
    c.execute('''
        INSERT INTO chat_attachments 
        (request_id, filename, file_path, sender, role, timestamp) 
        VALUES (?,?,?,?,?,?)
    ''', (request_id, filename, file_path, sender, role, ts))
    commit_doctors()

    c.execute('SELECT patient_email, doctor_email FROM chat_requests WHERE request_id = ?', (request_id,))
    p, d = c.fetchone()
    recipient = d if role == "patient" else p
    add_notification(recipient, f"New file from {sender}: {filename}", request_id)

def get_chat_attachments(request_id):
    c = get_doctors_cursor()
    c.execute('''
        SELECT sender, role, filename, file_path, timestamp 
        FROM chat_attachments 
        WHERE request_id = ? 
        ORDER BY id
    ''', (request_id,))
    return [{"sender":r[0], "role":r[1], "filename":r[2], "file_path":r[3], "timestamp":r[4]} for r in c.fetchall()]

# Prescription functions
def add_prescription(request_id, patient_email, doctor_email, doctor_name, patient_name, medicines, advice=""):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    medicines_json = json.dumps(medicines)
    c = get_doctors_cursor()
    c.execute('''
        INSERT INTO prescriptions 
        (request_id, patient_email, doctor_email, doctor_name, patient_name, medicines, advice, timestamp)
        VALUES (?,?,?,?,?,?,?,?)
    ''', (request_id, patient_email, doctor_email, doctor_name, patient_name, medicines_json, advice, ts))
    commit_doctors()

    add_notification(patient_email, f"New prescription from Dr. {doctor_name} (Chat #{request_id})", request_id)

def get_prescriptions_for_patient(patient_email):
    c = get_doctors_cursor()
    c.execute('''
        SELECT id, request_id, doctor_name, medicines, advice, timestamp 
        FROM prescriptions 
        WHERE patient_email = ? 
        ORDER BY timestamp DESC
    ''', (patient_email,))
    rows = c.fetchall()
    prescriptions = []
    for row in rows:
        medicines = json.loads(row[3]) if row[3] else []
        prescriptions.append({
            "id": row[0],
            "request_id": row[1],
            "doctor_name": row[2],
            "medicines": medicines,
            "advice": row[4],
            "timestamp": row[5]
        })
    return prescriptions

def add_submission(sub):
    c = get_patients_cursor()
    c.execute('INSERT INTO submissions (date, symptoms, prediction, patient_email) VALUES (?,?,?,?)',
              (sub['date'], sub['symptoms'], sub['prediction'], sub['patient_email']))
    commit_patients()

def get_submissions(email=None):
    c = get_patients_cursor()
    if email:
        c.execute('SELECT id, date, symptoms, prediction FROM submissions WHERE patient_email = ?', (email,))
    else:
        c.execute('SELECT id, date, symptoms, prediction, patient_email FROM submissions')
    return [{"id":r[0],"date":r[1],"symptoms":r[2],"prediction":r[3],"patient_email":r[4] if len(r)>4 else None} for r in c.fetchall()]

def add_feedback(fb):
    c = get_patients_cursor()
    c.execute('INSERT INTO feedback (user_email, feedback, timestamp) VALUES (?,?,?)',
              (fb['user_email'], fb['feedback'], fb['timestamp']))
    commit_patients()

def get_feedback():
    c = get_patients_cursor()
    c.execute('SELECT user_email, feedback, timestamp FROM feedback')
    return [{"user_email":r[0],"feedback":r[1],"timestamp":r[2]} for r in c.fetchall()]

def add_notification(email, msg, rid=None):
    c = get_doctors_cursor()
    c.execute('INSERT INTO notifications (user_email, message, timestamp, request_id) VALUES (?,?,?,?)',
              (email, msg, time.strftime("%Y-%m-%d %H:%M:%S"), rid))
    commit_doctors()

def get_notifications(email):
    c = get_doctors_cursor()
    c.execute('SELECT id, message, status, timestamp, request_id FROM notifications WHERE user_email = ? ORDER BY timestamp DESC', (email,))
    return [{"id":r[0],"message":r[1],"status":r[2],"timestamp":r[3],"request_id":r[4]} for r in c.fetchall()]

def mark_notification_read(nid):
    c = get_doctors_cursor()
    c.execute('UPDATE notifications SET status = "read" WHERE id = ?', (nid,))
    commit_doctors()

def mark_notifications_read_by_request(rid, email):
    c = get_doctors_cursor()
    c.execute('UPDATE notifications SET status = "read" WHERE request_id = ? AND user_email = ?', (rid, email))
    commit_doctors()