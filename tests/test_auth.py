"""Authentication tests: signup, login, and credential validation."""

from __future__ import annotations

import pytest
from authlib.integrations.base_client.errors import OAuthError

pytest.importorskip("flask")


@pytest.fixture()
def client():
    """Create Flask test client with TESTING=True (CSRF bypass)."""
    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as test_client:
        yield test_client


# ── helper ───────────────────────────────────────────────────────────────────

def _register_user(client, email: str, password: str = "ValidPass1") -> None:
    """Register a user directly via the database to avoid circular dependencies."""
    from database.db import get_connection
    from werkzeug.security import generate_password_hash

    db_path = client.application.config["DATABASE_PATH"]
    with get_connection(db_path) as conn:
        conn.execute("DELETE FROM users WHERE email = ?", (email,))
        conn.execute(
            "INSERT INTO users (email, password_hash, full_name) VALUES (?, ?, ?)",
            (email, generate_password_hash(password), "Test User"),
        )


# ── signup tests ─────────────────────────────────────────────────────────────

def test_signup_successful(client) -> None:
    """A valid new account should be created and the user redirected home."""
    from database.db import get_connection

    email = "new-signup-success@example.com"
    db_path = client.application.config["DATABASE_PATH"]
    with get_connection(db_path) as conn:
        conn.execute("DELETE FROM users WHERE email = ?", (email,))

    response = client.post(
        "/signup",
        data={
            "first_name": "New",
            "last_name": "User",
            "email": email,
            "password": "ValidPass1",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302, "Successful signup should redirect"
    assert response.headers["Location"].endswith("/")

    with get_connection(db_path) as conn:
        row = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    assert row is not None, "User should exist in the database after signup"


def test_signup_rejects_missing_first_name(client) -> None:
    """Signup without a first name should return an error."""
    response = client.post(
        "/signup",
        data={"first_name": "", "last_name": "User", "email": "nofirst@example.com", "password": "ValidPass1"},
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert b"required" in response.data


def test_signup_rejects_short_password(client) -> None:
    """Signup with a password shorter than 8 characters should be rejected."""
    response = client.post(
        "/signup",
        data={
            "first_name": "Short",
            "last_name": "Pw",
            "email": "short-pw@example.com",
            "password": "Ab1",
        },
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert b"8 characters" in response.data


def test_signup_rejects_password_without_uppercase(client) -> None:
    """Signup with a password missing an uppercase letter should be rejected."""
    response = client.post(
        "/signup",
        data={
            "first_name": "No",
            "last_name": "Upper",
            "email": "no-upper@example.com",
            "password": "nouppercase1",
        },
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert b"uppercase letter" in response.data


def test_signup_rejects_password_without_lowercase(client) -> None:
    """Signup with a password missing a lowercase letter should be rejected."""
    response = client.post(
        "/signup",
        data={
            "first_name": "No",
            "last_name": "Lower",
            "email": "no-lower@example.com",
            "password": "NOLOWERCASE1",
        },
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert b"lowercase letter" in response.data


def test_signup_rejects_password_without_number(client) -> None:
    """Signup with a password missing a number should be rejected."""
    response = client.post(
        "/signup",
        data={
            "first_name": "No",
            "last_name": "Number",
            "email": "no-number@example.com",
            "password": "NoNumberHere",
        },
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert b"number" in response.data


# ── login tests ──────────────────────────────────────────────────────────────

def test_signin_successful(client) -> None:
    """Signing in with correct credentials should redirect to home."""
    email = "signin-success@example.com"
    password = "ValidPass1"
    _register_user(client, email, password)

    response = client.post(
        "/signin",
        data={"email": email, "password": password},
        follow_redirects=False,
    )
    assert response.status_code == 302, "Successful sign-in should redirect"
    assert response.headers["Location"].endswith("/")


def test_signin_wrong_password(client) -> None:
    """Signing in with the correct email but wrong password should be rejected."""
    email = "wrong-pw@example.com"
    _register_user(client, email, "CorrectPass1")

    response = client.post(
        "/signin",
        data={"email": email, "password": "WrongPass1"},
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert b"Invalid email or password" in response.data


def test_signin_nonexistent_email(client) -> None:
    """Signing in with an email that is not registered should be rejected."""
    response = client.post(
        "/signin",
        data={"email": "ghost@example.com", "password": "AnyPass1"},
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert b"Invalid email or password" in response.data


def test_signin_rejects_empty_email(client) -> None:
    """Signing in without providing an email should return an error."""
    response = client.post(
        "/signin",
        data={"email": "", "password": "AnyPass1"},
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert b"required" in response.data


def test_signin_rejects_empty_password(client) -> None:
    """Signing in without providing a password should return an error."""
    response = client.post(
        "/signin",
        data={"email": "user@example.com", "password": ""},
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert b"required" in response.data


def test_signin_sets_session_on_success(client) -> None:
    """A successful sign-in should store user info in the session."""
    email = "session-check@example.com"
    password = "ValidPass1"
    _register_user(client, email, password)

    client.post(
        "/signin",
        data={"email": email, "password": password},
        follow_redirects=False,
    )
    with client.session_transaction() as sess:
        assert sess.get("user_id") is not None
        assert sess.get("user_email") == email


def test_signin_page_renders_google_button(client) -> None:
    """Sign-in page should expose a Google sign-in action."""
    response = client.get("/signin")
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Continue with Google" in body
    assert '/auth/google' in body


def test_signin_google_requires_configuration(client) -> None:
    """Google sign-in route should return a friendly error when not configured."""
    response = client.get("/auth/google", follow_redirects=False)
    assert response.status_code == 200
    assert b"Google sign-in is not configured yet" in response.data


def test_signin_google_redirects_to_google_when_configured(client, monkeypatch) -> None:
    """Configured Google sign-in should redirect to Google's OAuth endpoint."""
    import routes.auth as auth_routes

    captured = {}

    class _FakeGoogleClient:
        def authorize_redirect(self, **kwargs):
            captured.update(kwargs)
            from flask import redirect
            return redirect("https://accounts.google.com/mock-auth")

    monkeypatch.setattr(auth_routes, "_google_oauth_client", lambda: _FakeGoogleClient())

    response = client.get("/auth/google", follow_redirects=False)
    assert response.status_code == 302
    location = response.headers["Location"]
    assert location == "https://accounts.google.com/mock-auth"
    assert captured["redirect_uri"].endswith("/auth/google/callback")
    assert captured["prompt"] == "select_account"

    with client.session_transaction() as sess:
        assert sess.get("google_oauth_nonce") == captured["nonce"]


def test_google_callback_handles_provider_error(client) -> None:
    """Google callback should surface provider-side errors safely."""
    response = client.get("/auth/google/callback?error=access_denied", follow_redirects=False)
    assert response.status_code == 200
    assert b"Google sign-in was cancelled or failed" in response.data


def test_google_callback_requires_active_oauth_session(client, monkeypatch) -> None:
    """Google callback should reject callbacks without the stored nonce."""
    import routes.auth as auth_routes

    class _FakeGoogleClient:
        def authorize_access_token(self):
            return {"access_token": "access-token"}

    monkeypatch.setattr(auth_routes, "_google_oauth_client", lambda: _FakeGoogleClient())

    response = client.get("/auth/google/callback?code=auth-code&state=state-123", follow_redirects=False)
    assert response.status_code == 200
    assert b"Google sign-in session expired" in response.data


def test_google_callback_signs_in_existing_user(client, monkeypatch) -> None:
    """Google callback should sign in an existing matching user account."""
    email = "google-existing@example.com"
    _register_user(client, email, "StrongPass1")
    with client.session_transaction() as sess:
        sess["google_oauth_nonce"] = "nonce-123"

    import routes.auth as auth_routes

    class _FakeGoogleClient:
        def authorize_access_token(self):
            return {"access_token": "access-token", "id_token": "id-token"}

        def parse_id_token(self, token, nonce):
            if token["id_token"] != "id-token":
                raise AssertionError("expected ID token to be forwarded to parse_id_token")
            if nonce != "nonce-123":
                raise AssertionError("expected stored nonce to be forwarded to parse_id_token")
            return {
                "email": email,
                "email_verified": True,
                "name": "Google Existing",
            }

    monkeypatch.setattr(auth_routes, "_google_oauth_client", lambda: _FakeGoogleClient())

    response = client.get(
        "/auth/google/callback?state=state-123&code=auth-code",
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")
    with client.session_transaction() as sess:
        assert sess.get("user_email") == email
        assert sess.get("user_id") is not None


def test_google_callback_creates_new_user_when_missing(client, monkeypatch) -> None:
    """Google callback should auto-create a matching account when needed."""
    from database.db import get_connection

    email = "google-new-user@example.com"
    db_path = client.application.config["DATABASE_PATH"]
    with get_connection(db_path) as conn:
        conn.execute("DELETE FROM users WHERE email = ?", (email,))

    with client.session_transaction() as sess:
        sess["google_oauth_nonce"] = "nonce-456"

    import routes.auth as auth_routes

    class _FakeGoogleClient:
        def authorize_access_token(self):
            return {"access_token": "access-token", "id_token": "id-token"}

        def parse_id_token(self, token, nonce):
            if nonce != "nonce-456":
                raise AssertionError("expected stored nonce to be forwarded to parse_id_token")
            return {
                "email": email,
                "email_verified": True,
                "name": "Google New User",
            }

    monkeypatch.setattr(auth_routes, "_google_oauth_client", lambda: _FakeGoogleClient())

    response = client.get("/auth/google/callback?state=state-456&code=auth-code", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")

    with get_connection(db_path) as conn:
        row = conn.execute("SELECT email, full_name FROM users WHERE email = ?", (email,)).fetchone()
    assert row is not None
    assert row["full_name"] == "Google New User"


def test_google_callback_handles_oauth_failures(client, monkeypatch) -> None:
    """Google callback should handle Authlib OAuth failures gracefully."""
    import routes.auth as auth_routes

    with client.session_transaction() as sess:
        sess["google_oauth_nonce"] = "nonce-789"

    class _FakeGoogleClient:
        def authorize_access_token(self):
            raise OAuthError(error="access_denied")

    monkeypatch.setattr(auth_routes, "_google_oauth_client", lambda: _FakeGoogleClient())

    response = client.get("/auth/google/callback?state=state-789&code=auth-code", follow_redirects=False)
    assert response.status_code == 200
    assert b"Unable to complete Google sign-in" in response.data




def test_signin_rejects_suspended_account(client) -> None:
    """Suspended accounts should not be able to sign in."""
    from database.db import get_connection
    from werkzeug.security import generate_password_hash

    email = "suspended-user@example.com"
    password = "ValidPass1"
    db_path = client.application.config["DATABASE_PATH"]
    with get_connection(db_path) as conn:
        conn.execute("DELETE FROM users WHERE email = ?", (email,))
        conn.execute(
            "INSERT INTO users (email, password_hash, full_name, is_suspended) VALUES (?, ?, ?, 1)",
            (email, generate_password_hash(password), "Suspended User"),
        )

    response = client.post(
        "/signin",
        data={"email": email, "password": password},
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert b"account is suspended" in response.data

def test_signout_clears_session(client) -> None:
    """Signing out should clear the session."""
    email = "signout-test@example.com"
    password = "ValidPass1"
    _register_user(client, email, password)

    client.post(
        "/signin",
        data={"email": email, "password": password},
        follow_redirects=False,
    )
    client.get("/signout")
    with client.session_transaction() as sess:
        assert sess.get("user_id") is None
