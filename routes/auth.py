"""Authentication routes: sign-in, sign-up, sign-out."""

from __future__ import annotations

import logging
import secrets
import re
import sqlite3
from hmac import compare_digest
from urllib.parse import urlencode

import requests
from flask import (
    Blueprint,
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
_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"


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


def _google_client_config() -> tuple[str, str]:
    client_id = str(current_app.config.get("GOOGLE_CLIENT_ID", "")).strip()
    client_secret = str(current_app.config.get("GOOGLE_CLIENT_SECRET", "")).strip()
    return client_id, client_secret


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


@auth_bp.get("/signin/google")
def signin_google():
    """Start Google OAuth sign-in flow."""
    if session.get("user_id"):
        return redirect(url_for("main.index"))

    client_id, _ = _google_client_config()
    if not client_id:
        return render_template("signin.html", error="Google sign-in is not configured yet.")

    state = secrets.token_urlsafe(32)
    session["google_oauth_state"] = state
    redirect_uri = url_for("auth.google_callback", _external=True)
    auth_query = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "prompt": "select_account",
        }
    )
    return redirect(f"{_GOOGLE_AUTH_URL}?{auth_query}")


@auth_bp.get("/auth/google/callback")
def google_callback():
    """Handle Google OAuth callback and sign the user in."""
    if session.get("user_id"):
        return redirect(url_for("main.index"))

    oauth_error = _sanitize_text(request.args.get("error", ""), max_length=80)
    if oauth_error:
        return render_template("signin.html", error="Google sign-in was cancelled or failed.")

    received_state = _sanitize_text(request.args.get("state", ""), max_length=256)
    expected_state = str(session.pop("google_oauth_state", ""))
    if not expected_state or not received_state or not compare_digest(expected_state, received_state):
        return render_template("signin.html", error="Invalid Google sign-in state. Please try again.")

    code = _sanitize_text(request.args.get("code", ""), max_length=2048)
    if not code:
        return render_template("signin.html", error="Google sign-in did not return an authorization code.")

    client_id, client_secret = _google_client_config()
    if not client_id or not client_secret:
        return render_template("signin.html", error="Google sign-in is not configured yet.")

    redirect_uri = url_for("auth.google_callback", _external=True)
    try:
        token_response = requests.post(
            _GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
            timeout=10,
        )
        if token_response.status_code != 200:
            LOGGER.warning("Google OAuth token exchange failed with status %s", token_response.status_code)
            return render_template("signin.html", error="Unable to complete Google sign-in. Please try again.")
        token_payload = token_response.json()
        access_token = str(token_payload.get("access_token", "")).strip()
        if not access_token:
            return render_template("signin.html", error="Unable to complete Google sign-in. Please try again.")

        userinfo_response = requests.get(
            _GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        if userinfo_response.status_code != 200:
            LOGGER.warning("Google OAuth userinfo failed with status %s", userinfo_response.status_code)
            return render_template("signin.html", error="Unable to fetch your Google account details.")
        userinfo = userinfo_response.json()
    except requests.RequestException:
        LOGGER.exception("Google OAuth network error")
        return render_template("signin.html", error="Google sign-in failed due to a network error.")
    except ValueError:
        LOGGER.exception("Google OAuth response parsing error")
        return render_template("signin.html", error="Google sign-in returned an unexpected response.")

    email = _sanitize_text(str(userinfo.get("email", "")), max_length=_EMAIL_MAX_LENGTH).lower()
    if not email or not _is_valid_email(email):
        return render_template("signin.html", error="Google account email is missing or invalid.")
    if userinfo.get("email_verified") is False:
        return render_template("signin.html", error="Your Google email must be verified to sign in.")

    full_name = _sanitize_text(str(userinfo.get("name", "")), max_length=_NAME_MAX_LENGTH)
    if not full_name:
        given_name = _sanitize_text(str(userinfo.get("given_name", "")), max_length=_NAME_MAX_LENGTH)
        full_name = given_name or email.split("@")[0]

    db_path = current_app.config["DATABASE_PATH"]
    user = _get_user_by_email(db_path, email)
    if user and bool(user.get("is_suspended")):
        return render_template("signin.html", error="This account is suspended. Please contact the administrator.")
    if not user:
        try:
            generated_password = secrets.token_urlsafe(32)
            user_id = _create_user(db_path, email, generated_password, full_name)
            user = {
                "id": user_id,
                "email": email,
                "full_name": full_name,
                "is_suspended": 0,
            }
        except sqlite3.IntegrityError:
            user = _get_user_by_email(db_path, email)
            if not user:
                return render_template("signin.html", error="Unable to create your account. Please try again.")
        except Exception:
            LOGGER.exception("Failed to create Google OAuth user")
            return render_template("signin.html", error="Unable to create your account. Please try again.")

    session.clear()
    session["user_id"] = user["id"]
    session["user_email"] = user["email"]
    session["user_name"] = user.get("full_name") or user["email"].split("@")[0]
    session.permanent = True

    LOGGER.info("User %s signed in with Google OAuth", user["email"])
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
