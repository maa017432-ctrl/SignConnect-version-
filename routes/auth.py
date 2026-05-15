"""Authentication routes: sign-in, sign-up, sign-out."""

from __future__ import annotations

import logging
import re
import sqlite3

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from core.csrf import validate_csrf_token
from database.db import get_connection
from flask import current_app

LOGGER = logging.getLogger(__name__)
auth_bp = Blueprint("auth", __name__)

_EMAIL_RE = re.compile(r"^(?!.*\.\.)[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,63}$")
_PASSWORD_MIN_LENGTH = 8
_PASSWORD_MAX_LENGTH = 128
_NAME_MAX_LENGTH = 80
_EMAIL_MAX_LENGTH = 254


def _is_valid_email(email: str) -> bool:
    if not _EMAIL_RE.match(email):
        return False
    if "@" not in email:
        return False
    local_part, domain_part = email.rsplit("@", 1)
    if (
        not local_part
        or not domain_part
        or local_part.startswith(".")
        or local_part.endswith(".")
        or domain_part.startswith(".")
        or domain_part.endswith(".")
        or ".." in local_part
        or ".." in domain_part
    ):
        return False
    return True


def _sanitize_text(value: str, *, max_length: int) -> str:
    """Trim and remove control chars from a user-provided value."""
    if not isinstance(value, str):
        value = ""
    clean = re.sub(r"[\x00-\x1f\x7f]+", "", value).strip()
    return clean[:max_length]


def _password_strength_error(password: str) -> str | None:
    """Return an error message when password does not meet policy."""
    if len(password) < _PASSWORD_MIN_LENGTH:
        return f"Password must be at least {_PASSWORD_MIN_LENGTH} characters."
    if len(password) > _PASSWORD_MAX_LENGTH:
        return f"Password must be at most {_PASSWORD_MAX_LENGTH} characters."
    if not re.search(r"[A-Z]", password):
        return "Password must include at least one uppercase letter."
    if not re.search(r"[a-z]", password):
        return "Password must include at least one lowercase letter."
    if not re.search(r"\d", password):
        return "Password must include at least one number."
    return None


# ── helpers ──────────────────────────────────────────────────────────────────

def _get_user_by_email(db_path: str, email: str) -> dict | None:
    """Return a user row dict or None."""
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT id, email, password_hash, full_name, is_suspended FROM users WHERE email = ?",
            (email.lower().strip(),),
        ).fetchone()
    return dict(row) if row else None


def _create_user(db_path: str, email: str, password: str, full_name: str) -> int:
    """Insert a new user and return their id."""
    pw_hash = generate_password_hash(password)
    with get_connection(db_path) as conn:
        cursor = conn.execute(
            "INSERT INTO users (email, password_hash, full_name) VALUES (?, ?, ?)",
            (email.lower().strip(), pw_hash, full_name.strip()),
        )
    return cursor.lastrowid


# ── routes ────────────────────────────────────────────────────────────────────

@auth_bp.get("/signin")
def signin_get() -> str:
    """Render sign-in page. Redirect to home if already logged in."""
    if session.get("user_id"):
        return redirect(url_for("main.index"))
    return render_template("signin.html", error=None)


@auth_bp.post("/signin")
def signin_post():
    """Handle sign-in form submission."""
    validate_csrf_token()
    email = _sanitize_text(request.form.get("email", ""), max_length=_EMAIL_MAX_LENGTH).lower()
    password = str(request.form.get("password", ""))

    if not email or not password:
        return render_template("signin.html", error="Email and password are required.")
    if not _is_valid_email(email):
        return render_template("signin.html", error="Please enter a valid email address.")

    db_path = current_app.config["DATABASE_PATH"]
    user = _get_user_by_email(db_path, email)

    if not user or not check_password_hash(user["password_hash"], password):
        return render_template("signin.html", error="Invalid email or password.")
    if bool(user.get("is_suspended")):
        return render_template("signin.html", error="This account is suspended. Please contact the administrator.")

    session.clear()
    session["user_id"] = user["id"]
    session["user_email"] = user["email"]
    session["user_name"] = user["full_name"] or user["email"].split("@")[0]
    session.permanent = True

    LOGGER.info("User %s signed in", user["email"])
    return redirect(url_for("main.index"))


@auth_bp.get("/signup")
def signup_get() -> str:
    """Render sign-up page. Redirect to home if already logged in."""
    if session.get("user_id"):
        return redirect(url_for("main.index"))
    return render_template("signup.html", error=None)


@auth_bp.post("/signup")
def signup_post():
    """Handle sign-up form submission."""
    validate_csrf_token()
    first = _sanitize_text(request.form.get("first_name", ""), max_length=_NAME_MAX_LENGTH)
    last = _sanitize_text(request.form.get("last_name", ""), max_length=_NAME_MAX_LENGTH)
    email = _sanitize_text(request.form.get("email", ""), max_length=_EMAIL_MAX_LENGTH).lower()
    password = str(request.form.get("password", ""))

    # Validation
    if not email or not password or not first:
        return render_template("signup.html", error="All fields are required.")
    if not _is_valid_email(email):
        return render_template("signup.html", error="Please enter a valid email address.")
    password_error = _password_strength_error(password)
    if password_error:
        return render_template("signup.html", error=password_error)

    db_path = current_app.config["DATABASE_PATH"]

    if _get_user_by_email(db_path, email):
        return render_template("signup.html", error="An account with that email already exists.")

    try:
        full_name = f"{first} {last}".strip()
        user_id = _create_user(db_path, email, password, full_name)
    except sqlite3.IntegrityError:
        return render_template("signup.html", error="An account with that email already exists.")
    except Exception:
        LOGGER.exception("Failed to create user account")
        return render_template("signup.html", error="Account creation failed. Please try again.")

    session.clear()
    session["user_id"] = user_id
    session["user_email"] = email.lower()
    session["user_name"] = full_name or email.split("@")[0]
    session.permanent = True

    LOGGER.info("New user registered: %s", email)
    return redirect(url_for("main.index"))


@auth_bp.get("/signout")
@auth_bp.post("/signout")
def signout():
    """Clear session and redirect to home."""
    session.clear()
    return redirect(url_for("main.index"))
