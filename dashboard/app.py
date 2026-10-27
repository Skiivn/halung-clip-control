"""HALUNG Dashboard — Main Flask application."""
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from functools import wraps
from datetime import datetime
import json

from dashboard.config import (
    FLASK_SECRET, FLASK_HOST, FLASK_PORT, ADMIN_USER, ADMIN_PASSWORD,
    APP_VERSION, APP_NAME, EDGE_API_TOKEN
)
from dashboard.database import init_db, get_db

app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = FLASK_SECRET


def login_required(f):
    """Require login session."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function


@app.route("/", methods=["GET", "POST"])
def login():
    """Login page."""
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if username == ADMIN_USER and password == ADMIN_PASSWORD:
            session["admin"] = True
            session["user"] = username
            return redirect(url_for("dashboard"))
        flash("Invalid credentials", "danger")
    return render_template("login.html")


@app.route("/logout")
def logout():
    """Logout."""
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    """Dashboard overview."""
    con = get_db()
    stations = con.execute("SELECT * FROM stations ORDER BY code").fetchall()
    cycles = con.execute(
        "SELECT COUNT(*) as total, "
        "SUM(CASE WHEN status='OK' THEN 1 ELSE 0 END) as ok "
        "FROM cycles WHERE date(cycle_time)=date('now')"
    ).fetchone()
    con.close()

    return render_template(
        "dashboard.html",
        stations=stations,
        total_cycles=cycles["total"] or 0,
        ok_cycles=cycles["ok"] or 0,
        version=APP_VERSION,
    )


@app.route("/api/health")
def api_health():
    """Health check endpoint (no auth required)."""
    try:
        con = get_db()
        con.execute("SELECT 1").fetchone()
        con.close()
        return jsonify({"ok": True, "service": APP_NAME, "version": APP_VERSION})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 503


if __name__ == "__main__":
    init_db()
    print(f"{APP_NAME} V{APP_VERSION}")
    print(f"Dashboard: http://127.0.0.1:{FLASK_PORT}")
    print(f"Login: {ADMIN_USER} / {ADMIN_PASSWORD}")
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=False, threaded=True)
