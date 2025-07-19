import os
from dotenv import load_dotenv
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path=dotenv_path)
import requests
from flask import Flask, session, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user, LoginManager, UserMixin
from models import User
from forms import LoginForm, RegisterForm
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import mysql.connector
from bs4 import BeautifulSoup

# Flask app and LoginManager initialization
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dev_secret')
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Hugging Face config
HUGGINGFACE_API_KEY = os.getenv("HUGGINGFACE_API_KEY")
print("🔑 Loaded Key:", HUGGINGFACE_API_KEY)
# Hugging Face Summarizer Function
def get_summary_from_huggingface(text):
    try:
        if len(text.split()) < 10:
            return "Content too short to summarize effectively."

        API_URL = "https://api-inference.huggingface.co/models/sshleifer/distilbart-cnn-12-6"
        headers = {
            "Authorization": f"Bearer {HUGGINGFACE_API_KEY}"
        }
        payload = {
            "inputs": f"Summarize this clearly: {text}",
            "parameters": {"max_length": 100, "min_length": 30, "do_sample": False}
        }
        response = requests.post(API_URL, headers=headers, json=payload)
        response.raise_for_status()
        result = response.json()
        return result[0]['summary_text']
    except Exception as e:
        print("🔥 Hugging Face error:", e)
        return "Summary failed due to error."

# DB Connection Helper
def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="admin",  # Replace with your MySQL password
        database="ainote"
    )

# Flask-Login user loader
def get_user_by_id(user_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    user_row = cursor.fetchone()
    cursor.close()
    conn.close()
    if user_row:
        return User(user_row['id'], user_row['username'], user_row['password'])
    return None

@login_manager.user_loader
def load_user(user_id):
    return get_user_by_id(user_id)

@app.route('/')
def home():
    return render_template('base.html', show_hero=True)

@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        username = form.username.data
        password = form.password.data
        hashed_password = generate_password_hash(password)
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO users (username, password) VALUES (%s, %s)", (username, hashed_password))
            conn.commit()
            return redirect(url_for('login'))
        except mysql.connector.errors.IntegrityError:
            flash("User already exists", "danger")
        finally:
            conn.close()
    return render_template('register.html', form=form, show_hero=False)

@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        username = form.username.data
        password = form.password.data
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        user_row = cursor.fetchone()
        conn.close()
        if user_row and check_password_hash(user_row['password'], password):
            user = User(user_row['id'], user_row['username'], user_row['password'])
            login_user(user)
            session['username'] = username
            return redirect(url_for('dashboard'))
        else:
            flash("Invalid credentials", "danger")
    return render_template('login.html', form=form, show_hero=False)

@app.route('/dashboard', methods=['GET', 'POST'])
@login_required
def dashboard():
    search_query = request.args.get('q', '').strip()
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    if search_query:
        # Use COLLATE utf8mb4_general_ci for case-insensitive search
        cursor.execute("SELECT * FROM notes WHERE user_id = %s AND (title LIKE %s COLLATE utf8mb4_general_ci OR content LIKE %s COLLATE utf8mb4_general_ci OR summary LIKE %s COLLATE utf8mb4_general_ci) ORDER BY created_at DESC", (current_user.id, f"%{search_query}%", f"%{search_query}%", f"%{search_query}%"))
    else:
        cursor.execute("SELECT * FROM notes WHERE user_id = %s ORDER BY created_at DESC", (current_user.id,))
    notes = cursor.fetchall()
    conn.close()
    return render_template("dashboard.html", notes=notes, name=current_user.username, search_query=search_query)

@app.route('/add_note', methods=['GET', 'POST'])
@login_required
def add_note():
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        # Extract plain text for summarization
        soup = BeautifulSoup(content, "html.parser")
        content_text = soup.get_text(separator=' ', strip=True)
        summary = get_summary_from_huggingface(content_text)
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO notes (user_id, title, content, summary) VALUES (%s, %s, %s, %s)",
            (current_user.id, title, content, summary)
        )
        conn.commit()
        cursor.close()
        conn.close()
        flash('Note added and summarized by AI!', 'success')
        return redirect(url_for('dashboard'))
    return render_template('add_note.html')

@app.route('/edit_note/<int:note_id>', methods=['GET', 'POST'])
@login_required
def edit_note(note_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM notes WHERE id = %s AND user_id = %s", (note_id, current_user.id))
    note = cursor.fetchone()
    if not note:
        conn.close()
        flash('Note not found or you do not have permission to edit it.', 'danger')
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        # Extract plain text for summarization (fix for HTML input)
        soup = BeautifulSoup(content, "html.parser")
        content_text = soup.get_text(separator=' ', strip=True)
        summary = get_summary_from_huggingface(content_text)
        cursor.execute("UPDATE notes SET title = %s, content = %s, summary = %s WHERE id = %s AND user_id = %s",
                       (title, content, summary, note_id, current_user.id))
        conn.commit()
        conn.close()
        flash('Note updated and summarized by AI!', 'success')
        return redirect(url_for('dashboard'))
    conn.close()
    return render_template('edit_note.html', note=note)

@app.route('/delete_note/<int:note_id>')
@login_required
def delete_note(note_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM notes WHERE id = %s AND user_id = %s", (note_id, current_user.id))
    conn.commit()
    conn.close()
    flash('Note deleted.', 'success')
    return redirect(url_for('dashboard'))

@app.route('/logout')
def logout():
    session.pop('username', None)
    logout_user()
    return redirect(url_for('login'))

@app.context_processor
def inject_user():
    return dict(current_user=current_user)

if __name__ == '__main__':
    app.run(debug=False,use_reloader=True)  # Use reloader for development convenience
