"""Shared authentication helpers for dashboard routes."""
import hmac
from functools import wraps

from flask import jsonify, redirect, request, session, url_for

from dashboard.config import EDGE_API_TOKEN


def login_required(f):
    """Browser pages redirect to login; /api/ calls get a JSON 401."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("admin"):
            if request.path.startswith("/api/"):
                return jsonify(ok=False, error="login required"), 401
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


def edge_token_required(f):
    """Raspberry calls authenticate with 'Authorization: Bearer <token>'."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        sent = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        if not sent or not hmac.compare_digest(sent, EDGE_API_TOKEN):
            return jsonify(ok=False, error="invalid token"), 401
        return f(*args, **kwargs)
    return wrapper
