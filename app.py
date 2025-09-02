import os
import re
import logging
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_bcrypt import Bcrypt
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
from datetime import datetime, timedelta
from cryptography.fernet import Fernet
import sqlite3  # Ensure this is present


# Set up logging for SQLAlchemy engine output
logging.basicConfig()
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)

# Load environment variables from .env file
load_dotenv()

# Initialize the Flask app
app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'default_secret')  # Session key
bcrypt = Bcrypt(app)


# Function to load the app secret key from the plaintext file 'secret.key'
def load_app_secret_key():
    secret_key_filename = "secret.key"
    if not os.path.exists(secret_key_filename):
        raise FileNotFoundError("App secret key file not found.")
    with open(secret_key_filename, 'rb') as file:
        return file.read()

# Function to generate and save a user encryption key
def generate_user_encryption_key():
    return os.urandom(32)  # Generate a random 32-byte encryption key for the user

# Function to encrypt the user encryption key using the app's secret key
def encrypt_user_encryption_key(user_encryption_key):
    app_secret_key = load_app_secret_key()  # Load the app's secret key from the file
    fernet = Fernet(app_secret_key)  # Use the app's secret key to encrypt
    encrypted_user_key = fernet.encrypt(user_encryption_key)
    return encrypted_user_key

# Function to create a user and store the encrypted user encryption key
def create_user_and_key(username, password):
    # Generate a user encryption key
    encryption_key = generate_user_encryption_key()

    # Encrypt the encryption key with the app's secret key
    encrypted_key = encrypt_user_encryption_key(encryption_key)

    # Add the user to the database
    new_user = User(username=username, password=password, encrypted_key=encrypted_key)
    db.session.add(new_user)
    db.session.commit()

# Function to retrieve and decrypt a user's encryption key
def get_decrypted_encryption_key(user_id):
    # Retrieve the encrypted encryption key from the database
    user = User.query.get(user_id)

    if user and user.encrypted_key:
        # Load the app's secret key from the file
        app_secret_key = load_app_secret_key()  # Load the app's secret key
        fernet = Fernet(app_secret_key)  # Use the app secret key
        decrypted_key = fernet.decrypt(user.encrypted_key)  # Decrypt the user's key
        return decrypted_key
    return None  # Or raise an exception if the key is not found














# Configure the main user database (Use SQLite for simplicity here)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize the db instance
db = SQLAlchemy(app)

# User model (Now storing both user credentials and encrypted keys in one table)
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)  # Hashed password
    encrypted_key = db.Column(db.LargeBinary, nullable=True)  # Store the encrypted encryption key

    def __init__(self, username, password, encrypted_key=None):
        self.username = username
        self.password = bcrypt.generate_password_hash(password).decode('utf-8')
        self.encrypted_key = encrypted_key  # Optional: May be None if not set initially

    def set_encrypted_key(self, encrypted_key):
        self.encrypted_key = encrypted_key  # Set the encrypted key when available

# Create database tables for the 'user' model (users.db)
with app.app_context():
    db.create_all()  # Create the 'user' table in 'users.db'







 


# Default admin credentials (stored securely in .env)
ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD_HASH')  # Should be a hashed password
SECONDARY_ADMIN_USERNAME = os.getenv('SECONDARY_ADMIN_USERNAME', 'secondary_admin')
SECONDARY_ADMIN_PASSWORD = os.getenv('SECONDARY_ADMIN_PASSWORD_HASH')  # Hashed

@app.route('/')
def home():
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    username = request.form['username']
    password = request.form['password']

    # Admin authentication
    if username == ADMIN_USERNAME and bcrypt.check_password_hash(ADMIN_PASSWORD, password):
        session['username'] = username
        session['role'] = 'admin'
        return redirect(url_for('admin'))

    elif username == SECONDARY_ADMIN_USERNAME and bcrypt.check_password_hash(SECONDARY_ADMIN_PASSWORD, password):
        session['username'] = username
        session['role'] = 'secondary_admin'
        return redirect(url_for('logs'))

    # Check in database for supervisors
    user = User.query.filter_by(username=username).first()
    if user and bcrypt.check_password_hash(user.password, password):
        session['username'] = username
        session['role'] = 'supervisor'
        return redirect(url_for('supervisor'))

    flash('Invalid Username or Password', 'danger')
    return redirect(url_for('home'))

@app.route('/admin')
def admin():
    if 'role' not in session or session['role'] != 'admin':
        flash('You must be an admin to access this page', 'danger')
        return redirect(url_for('home'))

    return render_template('admin.html')

# 📌 API: Fetch all users
@app.route('/admin/get_users', methods=['GET'])
def get_users():
    if 'role' not in session or session['role'] != 'admin':
        return jsonify({"message": "Unauthorized"}), 403

    users = [user.username for user in User.query.all()]
    return jsonify({"users": users})

# 📌 API: Add new user
@app.route('/admin/add_user', methods=['POST'])
def add_user():
    if 'role' not in session or session['role'] != 'admin':
        return jsonify({"message": "Unauthorized"}), 403

    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({"message": "Username and password are required"}), 400

    # Validate password strength
    if not re.match(r'^(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$', password):
        return jsonify({"message": "Password must be at least 8 characters long, contain an uppercase letter, a number, and a special character."}), 400

    # Check if user exists
    existing_user = User.query.filter_by(username=username).first()
    if existing_user:
        return jsonify({"message": "User already exists!"}), 400

    # Call the function to create the user and encryption key
    try:
        create_user_and_key(username, password)
        return jsonify({"message": f"User {username} added successfully with encryption key!"})
    except Exception as e:
        return jsonify({"message": f"Error: {str(e)}"}), 500


# 📌 API: Remove user
@app.route('/admin/remove_user', methods=['POST'])
def remove_user():
    if 'role' not in session or session['role'] != 'admin':
        return jsonify({"message": "Unauthorized"}), 403

    data = request.get_json()
    username = data.get('username')

    if not username:
        return jsonify({"message": "Username is required"}), 400

    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({"message": "User not found"}), 404

    db.session.delete(user)
    db.session.commit()

    return jsonify({"message": f"User {username} removed successfully!"})



@app.route('/logs')
def logs():
    if 'role' not in session or session['role'] != 'secondary_admin':
        flash('You must be a secondary admin to access this page', 'danger')
        return redirect(url_for('home'))
    return render_template('logs.html')

@app.route('/supervisor')
def supervisor():
    if 'role' not in session or session['role'] != 'supervisor':
        flash('You must be a supervisor to access this page', 'danger')
        return redirect(url_for('home'))
    return render_template('supervisor.html')








# Function to initialize database
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pcr_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE NOT NULL,
            encrypted_data TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

init_db()

# Function to encrypt data
def encrypt_data(user_id, data):
    encryption_key = get_decrypted_encryption_key(user_id)
    if not encryption_key:
        return None

    fernet = Fernet(encryption_key)
    encrypted_data = fernet.encrypt(data.encode()).decode()
    return encrypted_data

# Function to decrypt data
def decrypt_data(user_id, encrypted_data):
    encryption_key = get_decrypted_encryption_key(user_id)
    if not encryption_key:
        return None

    fernet = Fernet(encryption_key)
    decrypted_data = fernet.decrypt(encrypted_data.encode()).decode()
    return decrypted_data

@app.route("/submit_draft", methods=["POST"])
def submit_draft():
    try:
        data = request.get_json()
        user_id = data.get("user_id")  # Ensure user_id is included in the request
        if not user_id:
            return jsonify({"error": "User ID is required"}), 400

        # Convert the form data to JSON string
        data_str = str(data)
        encrypted_data = encrypt_data(user_id, data_str)
        if not encrypted_data:
            return jsonify({"error": "Encryption failed"}), 500

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        # Check if user already has a draft
        cursor.execute("SELECT id FROM pcr_records WHERE user_id = ?", (user_id,))
        existing_draft = cursor.fetchone()

        if existing_draft:
            # Overwrite the existing draft
            cursor.execute("UPDATE pcr_records SET encrypted_data = ? WHERE user_id = ?", 
                           (encrypted_data, user_id))
        else:
            # Insert new draft
            cursor.execute("INSERT INTO pcr_records (user_id, encrypted_data) VALUES (?, ?)", 
                           (user_id, encrypted_data))

        conn.commit()
        conn.close()

        return jsonify({"message": "Draft saved successfully!"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/get_draft", methods=["GET"])
def get_draft():
    try:
        user_id = request.args.get("user_id")
        if not user_id:
            return jsonify({"error": "User ID is required"}), 400

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT encrypted_data FROM pcr_records WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        conn.close()

        if not result:
            return jsonify({"message": "No draft found"}), 404

        decrypted_data = decrypt_data(user_id, result[0])
        if not decrypted_data:
            return jsonify({"error": "Decryption failed"}), 500

        return jsonify({"draft": decrypted_data}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
























@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out', 'success')
    return redirect(url_for('home'))

@app.route('/')
def injury_report():
    return render_template('supervisor.html')

@app.route('/save_coordinates', methods=['POST'])
def save_coordinates():
    data = request.get_json()
    x = data.get('x')
    y = data.get('y')
    print(f"Coordinates: ({x}, {y})")  # You can save this data to a file or database
    return jsonify({"status": "success", "message": "Coordinates saved"})



if __name__ == '__main__':
    app.run(debug=True)
