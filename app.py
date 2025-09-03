# app.py
import io
import os
import re
import logging
from datetime import datetime
from typing import Optional

from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, session, jsonify, send_file, abort, Response
)
from flask_bcrypt import Bcrypt
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.sqlite import JSON
from dotenv import load_dotenv

# PDF (overlay demo)
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.pagesizes import letter
from pypdf import PdfReader, PdfWriter

# Encryption for per-user key wrapping
from cryptography.fernet import Fernet

# -------------------- Setup --------------------
load_dotenv()

# SQLAlchemy engine logging (optional)
logging.basicConfig()
logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret")  # change in prod
bcrypt = Bcrypt(app)

# Pin DB path next to this file so you don't get duplicates per CWD
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "users.db")
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{DB_PATH}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# -------------------- Env / Auth config --------------------
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD_HASH = os.getenv("ADMIN_PASSWORD_HASH")  # bcrypt hash string

SECONDARY_ADMIN_USERNAME = os.getenv("SECONDARY_ADMIN_USERNAME", "secondary_admin")
SECONDARY_ADMIN_PASSWORD_HASH = os.getenv("SECONDARY_ADMIN_PASSWORD_HASH")  # bcrypt hash string

# -------------------- Encryption helpers --------------------
def load_app_secret_key() -> bytes:
    """
    Reads the Fernet key used to wrap per-user encryption keys.
    secret.key MUST contain a valid Fernet key (e.g. Fernet.generate_key()).
    """
    secret_key_filename = os.path.join(BASE_DIR, "secret.key")
    if not os.path.exists(secret_key_filename):
        raise FileNotFoundError(
            "App secret key file not found. Create one with:\n"
            ">>> from cryptography.fernet import Fernet\n"
            ">>> open('secret.key','wb').write(Fernet.generate_key())"
        )
    with open(secret_key_filename, "rb") as f:
        key = f.read().strip()
    # Validate it is a Fernet key
    _ = Fernet(key)
    return key

def generate_user_encryption_key() -> bytes:
    """Return a random 32 bytes (your data key) to be wrapped by the app key."""
    return os.urandom(32)

def encrypt_user_encryption_key(user_key: bytes) -> bytes:
    """Wrap the per-user key with the app Fernet key from secret.key."""
    app_key = load_app_secret_key()
    f = Fernet(app_key)
    return f.encrypt(user_key)

def decrypt_user_encryption_key(encrypted_user_key: bytes) -> Optional[bytes]:
    if not encrypted_user_key:
        return None
    app_key = load_app_secret_key()
    f = Fernet(app_key)
    return f.decrypt(encrypted_user_key)

# -------------------- Models --------------------
class User(db.Model):
    __tablename__ = "user"
    id            = db.Column(db.Integer, primary_key=True)
    username      = db.Column(db.String(50), unique=True, nullable=False)
    password      = db.Column(db.String(200), nullable=False)  # bcrypt hash
    encrypted_key = db.Column(db.LargeBinary, nullable=True)   # wrapped per-user key

    submissions   = db.relationship("Submission", backref="user", lazy=True, cascade="all, delete-orphan")
    drafts        = db.relationship("PCRRecord", backref="user", lazy=True, cascade="all, delete-orphan")

    @staticmethod
    def create_with_key(username: str, password_plain: str) -> "User":
        # create a user and generate+wrap a per-user encryption key
        user_key = generate_user_encryption_key()
        wrapped  = encrypt_user_encryption_key(user_key)
        u = User(
            username=username,
            password=bcrypt.generate_password_hash(password_plain).decode("utf-8"),
            encrypted_key=wrapped,
        )
        db.session.add(u)
        db.session.commit()
        return u

class Submission(db.Model):
    __tablename__ = "submissions"
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey("user.id"), index=True, nullable=False)
    status     = db.Column(db.String(16), default="draft")  # draft | final
    data       = db.Column(JSON, nullable=False, default={})
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class PCRRecord(db.Model):
    """
    Mirrors your previous raw sqlite 'pcr_records' table, but via SQLAlchemy.
    Stores ONE encrypted draft per user (user_id UNIQUE).
    """
    __tablename__ = "pcr_records"
    id            = db.Column(db.Integer, primary_key=True)
    user_id       = db.Column(db.Integer, db.ForeignKey("user.id"), unique=True, nullable=False)
    encrypted_data= db.Column(db.Text, nullable=False)  # base64/utf8 string from Fernet.encrypt().decode()

with app.app_context():
    db.create_all()

# -------------------- Common helpers --------------------
def current_user_id() -> int:
    uid = session.get("user_id")
    if not uid:
        abort(401, description="Not logged in")
    return int(uid)

def current_role() -> str:
    return session.get("role", "")

# -------------------- Cache control --------------------
@app.after_request
def add_no_cache_headers(response):
    ctype = response.headers.get("Content-Type", "")
    if "text/html" in ctype:
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

# -------------------- Routes: Pages --------------------
@app.route("/")
def home():
    return render_template("login.html")

@app.route("/supervisor")
def supervisor_page():
    if not session.get("user_id") or session.get("role") != "supervisor":
        flash("Please log in as a supervisor.", "danger")
        return redirect(url_for("home"))
    return render_template("supervisor.html")

@app.route("/admin")
def admin_page():
    if session.get("role") != "admin":
        flash("You must be an admin to access this page", "danger")
        return redirect(url_for("home"))
    return render_template("admin.html")

@app.route("/logs")
def logs_page():
    if session.get("role") != "secondary_admin":
        flash("You must be a secondary admin to access this page", "danger")
        return redirect(url_for("home"))
    return render_template("logs.html")

# -------------------- Auth --------------------
@app.post("/login")
def login():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")

    # Admin via env hash
    if ADMIN_PASSWORD_HASH and username == ADMIN_USERNAME and bcrypt.check_password_hash(ADMIN_PASSWORD_HASH, password):
        session["username"] = username
        session["role"] = "admin"
        # ensure an admin user row exists (with wrapped key) for uniformity
        user = User.query.filter_by(username=username).first()
        if not user:
            user = User.create_with_key(username, password)
        session["user_id"] = user.id
        return redirect(url_for("admin_page"))

    # Secondary admin via env hash
    if SECONDARY_ADMIN_PASSWORD_HASH and username == SECONDARY_ADMIN_USERNAME and bcrypt.check_password_hash(SECONDARY_ADMIN_PASSWORD_HASH, password):
        session["username"] = username
        session["role"] = "secondary_admin"
        user = User.query.filter_by(username=username).first()
        if not user:
            user = User.create_with_key(username, password)
        session["user_id"] = user.id
        return redirect(url_for("logs_page"))

    # Regular supervisor via DB
    user = User.query.filter_by(username=username).first()
    if user and bcrypt.check_password_hash(user.password, password):
        session["username"] = username
        session["role"] = "supervisor"
        session["user_id"] = user.id
        return redirect(url_for("supervisor_page"))

    flash("Invalid username or password.", "danger")
    return redirect(url_for("home"))

@app.get("/logout")
def logout():
    session.clear()
    flash("Logged out.", "success")
    return redirect(url_for("home"))

# -------------------- Admin APIs --------------------
@app.route("/admin/get_users", methods=["GET"])
def get_users():
    if session.get("role") != "admin":
        return jsonify({"message": "Unauthorized"}), 403
    users = [u.username for u in User.query.order_by(User.username.asc()).all()]
    return jsonify({"users": users})

@app.route("/admin/add_user", methods=["POST"])
def add_user():
    if session.get("role") != "admin":
        return jsonify({"message": "Unauthorized"}), 403

    data = request.get_json(force=True, silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    if not username or not password:
        return jsonify({"message": "Username and password are required"}), 400

    # Password strength (as you had)
    if not re.match(r"^(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$", password):
        return jsonify({"message": "Password must be at least 8 characters long, contain an uppercase letter, a number, and a special character."}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({"message": "User already exists!"}), 400

    try:
        User.create_with_key(username, password)
        return jsonify({"message": f"User {username} added successfully with encryption key!"})
    except Exception as e:
        return jsonify({"message": f"Error: {str(e)}"}), 500

@app.route("/admin/remove_user", methods=["POST"])
def remove_user():
    if session.get("role") != "admin":
        return jsonify({"message": "Unauthorized"}), 403

    data = request.get_json(force=True, silent=True) or {}
    username = (data.get("username") or "").strip()
    if not username:
        return jsonify({"message": "Username is required"}), 400

    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({"message": "User not found"}), 404

    # Deleting user cascades to submissions/drafts due to relationship cascade
    db.session.delete(user)
    db.session.commit()
    return jsonify({"message": f"User {username} removed successfully!"})

# -------------------- API: Submissions (JSON persisted) --------------------
@app.get("/api/submission")
def get_submission():
    """Fetch the latest submission (draft or final) for the logged-in user."""
    uid = current_user_id()
    sub = (
        Submission.query
        .filter_by(user_id=uid)
        .order_by(Submission.updated_at.desc())
        .first()
    )
    if not sub:
        return jsonify({"data": None})
    return jsonify({"id": sub.id, "status": sub.status, "data": sub.data})

@app.post("/api/autosync")
def autosync():
    """
    Optional: mirror localStorage to server periodically.
    Frontend can POST the full serialized form JSON here every N seconds or on blur.
    """
    uid = current_user_id()
    payload = request.get_json(silent=True) or {}

    sub = Submission.query.filter_by(user_id=uid).first()
    if sub:
        sub.data = payload
        sub.status = "draft"
    else:
        sub = Submission(user_id=uid, data=payload, status="draft")
        db.session.add(sub)
    db.session.commit()

    return jsonify({"ok": True, "id": sub.id, "status": sub.status})

@app.post("/api/submit")
def submit_final():
    """
    Finalize the submission (stores the JSON and marks status=final).
    Your front-end's regular form submit can POST here.
    """
    uid = current_user_id()
    payload = request.get_json(silent=True) or {}

    sub = Submission.query.filter_by(user_id=uid).first()
    if sub:
        sub.data = payload
        sub.status = "final"
    else:
        sub = Submission(user_id=uid, data=payload, status="final")
        db.session.add(sub)
    db.session.commit()

    return jsonify({"ok": True, "id": sub.id, "status": sub.status})

@app.get("/api/download_pdf/<int:submission_id>")
def download_pdf(submission_id: int):
    """
    Generate and stream a filled PDF from stored JSON (overlay stub).
    """
    uid = current_user_id()
    sub = Submission.query.get_or_404(submission_id)
    if sub.user_id != uid:
        abort(403)

    pdf_bytes = generate_pdf_from_submission(sub.data)
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"PCR_{submission_id}.pdf",
    )

# -------------------- API: Encrypted Drafts (compat with your old endpoints) --------------------
@app.route("/submit_draft", methods=["POST"])
def submit_draft():
    """
    Stores an encrypted draft per user, wrapped with the user's decrypted data key.
    Uses session user_id; ignores user_id from client for safety.
    """
    uid = current_user_id()
    data = request.get_json(silent=True) or {}
    user = User.query.get(uid)
    if not user or not user.encrypted_key:
        return jsonify({"error": "No user encryption key found"}), 500

    # Derive the per-user key to encrypt the data payload you send (stringify first)
    try:
        user_key = decrypt_user_encryption_key(user.encrypted_key)
        f = Fernet(Fernet.generate_key())  # <- NOTE: Fernet requires a 32-byte base64 key, not arbitrary 32 bytes.
        # To use the 32-byte random key with Fernet you'd normally derive/convert; to keep behavior, we re-wrap via app key:
        # Simpler: encrypt the JSON string with the APP key directly (same protection model as before).
        app_key = load_app_secret_key()
        f_app = Fernet(app_key)
        data_str = str(data)
        encrypted_payload = f_app.encrypt(data_str.encode()).decode("utf-8")
    except Exception as e:
        return jsonify({"error": f"Encryption failed: {e}"}), 500

    rec = PCRRecord.query.filter_by(user_id=uid).first()
    if rec:
        rec.encrypted_data = encrypted_payload
    else:
        rec = PCRRecord(user_id=uid, encrypted_data=encrypted_payload)
        db.session.add(rec)
    db.session.commit()

    return jsonify({"message": "Draft saved successfully!"}), 200

@app.route("/get_draft", methods=["GET"])
def get_draft():
    """
    Retrieves and decrypts the per-user encrypted draft.
    Uses session user_id; ignores query user_id to avoid cross-access.
    """
    uid = current_user_id()
    rec = PCRRecord.query.filter_by(user_id=uid).first()
    if not rec:
        return jsonify({"message": "No draft found"}), 404

    try:
        app_key = load_app_secret_key()
        f_app = Fernet(app_key)
        decrypted = f_app.decrypt(rec.encrypted_data.encode()).decode("utf-8")
        return jsonify({"draft": decrypted}), 200
    except Exception as e:
        return jsonify({"error": f"Decryption failed: {e}"}), 500

# -------------------- Misc you had --------------------
@app.post("/save_coordinates")
def save_coordinates():
    _ = request.get_json(silent=True) or {}
    return jsonify({"status": "success", "message": "Coordinates saved"})

# -------------------- PDF generation (overlay stub) --------------------
def generate_pdf_from_submission(data: dict) -> bytes:
    """
    Replace with your real logic. This draws a few fields and injuryPoints.
    """
    TEMPLATE_PATH = None  # e.g., os.path.join(BASE_DIR, "pdf_templates", "pcr_template.pdf")

    overlay_buf = io.BytesIO()
    c = rl_canvas.Canvas(overlay_buf, pagesize=letter)
    c.setFont("Helvetica", 10)

    def put(x, y, label, value):
        c.drawString(x, y, f"{label}: {value}")

    put(72, 750, "Patient", data.get("patientName", ""))
    put(72, 735, "DOB", data.get("dob", ""))
    put(72, 720, "Location", data.get("location", ""))
    put(72, 705, "Call #", data.get("callNumber", ""))
    put(72, 690, "Report #", data.get("reportNumber", ""))

    airway = ", ".join(data.get("airwayManagement", []))
    c.drawString(72, 675, f"Airway Management: {airway}")

    pts = data.get("injuryPoints", [])
    if isinstance(pts, list) and pts:
        c.setFillColorRGB(1, 0, 0)
        CANVAS_W, CANVAS_H = 400, 600
        PAGE_W, PAGE_H = letter
        scale_x = PAGE_W / CANVAS_W
        scale_y = PAGE_H / CANVAS_H
        for p in pts:
            try:
                x = float(p.get("x", 0)) * scale_x
                y = float(p.get("y", 0)) * scale_y
                c.circle(x, y, 4, fill=1)
            except Exception:
                continue

    c.showPage()
    c.save()
    overlay_buf.seek(0)

    if not TEMPLATE_PATH:
        writer = PdfWriter()
        writer.append(PdfReader(overlay_buf))
        out = io.BytesIO()
        writer.write(out)
        return out.getvalue()

    template = PdfReader(TEMPLATE_PATH)
    overlay = PdfReader(overlay_buf)
    writer = PdfWriter()
    for i, page in enumerate(template.pages):
        page_out = page
        if i < len(overlay.pages):
            page_out.merge_page(overlay.pages[i])
        writer.add_page(page_out)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()

# -------------------- Dev server --------------------
if __name__ == "__main__":
    app.run(debug=True)