"""Route tests for expected status codes."""

from __future__ import annotations

import pytest

pytest.importorskip("flask")


@pytest.fixture()
def client():
    """Create Flask test client."""
    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as test_client:
        yield test_client


@pytest.fixture()
def client_no_testing():
    """Flask test client with TESTING=False so CSRF validation is active."""
    from app import create_app

    app = create_app()
    app.config["TESTING"] = False
    with app.test_client() as test_client:
        yield test_client


@pytest.fixture()
def client_no_testing_secure():
    """Flask test client with TESTING/DEBUG disabled and API key configured."""
    from app import create_app

    app = create_app()
    app.config["TESTING"] = False
    app.config["DEBUG"] = False
    app.config["API_KEY"] = "unit-test-api-key"
    with app.test_client() as test_client:
        yield test_client


def test_main_routes(client) -> None:
    """Ensure page routes render correctly."""
    assert client.get("/").status_code == 200
    assert client.get("/translator").status_code == 200
    assert client.get("/history").status_code == 200
    assert client.get("/dictionary").status_code == 200


def test_translator_page_renders_svg_action_and_stat_icons(client) -> None:
    """Translator page should render structured SVG icon buttons/cards for the light-mode UI."""
    response = client.get("/translator")
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'id="auto-speak-btn"' in body
    assert 'class="sc-btn__icon-wrap"' in body
    assert 'class="sc-stat-mini-icon"' in body
    assert "🔊" not in body
    assert "📋" not in body


def test_dictionary_page_renders_searchable_supported_signs(client) -> None:
    """Dictionary page should show educational searchable glossary UI."""
    response = client.get("/dictionary")
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Supported Signs Dictionary" in body
    assert 'id="dict-search"' in body
    assert "Showing " in body
    assert 'static/js/dictionary.js' in body
    assert "Landmark preview not available yet" in body


def test_dictionary_uses_config_fallback_when_label_map_is_empty(client) -> None:
    """When no labels exist in the map, dictionary should fall back to configured classes."""
    translator = client.application.extensions["translator"]
    classifier = client.application.extensions["classifier"]
    original_label_map = dict(translator.label_map)
    original_labels_count = classifier.labels_count
    try:
        translator.label_map = {}
        classifier.labels_count = 3
        response = client.get("/dictionary")
        body = response.get_data(as_text=True)
        assert response.status_code == 200
        assert "Class 1" in body
        assert "Class 3" in body
        assert "config fallback" in body
    finally:
        translator.label_map = original_label_map
        classifier.labels_count = original_labels_count


def test_admin_route_requires_authentication(client) -> None:
    """Admin dashboard should redirect guests to sign-in."""
    response = client.get("/admin", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/signin")


def test_admin_dashboard_renders_for_signed_in_user(client) -> None:
    """Signed-in users should see dashboard metrics and charts."""
    from database.db import get_connection

    db_path = client.application.config["DATABASE_PATH"]
    email = "admin-dashboard@example.com"
    with get_connection(db_path) as connection:
        connection.execute("DELETE FROM translations WHERE user_id IN (SELECT id FROM users WHERE email = ?)", (email,))
        connection.execute("DELETE FROM users WHERE email = ?", (email,))
        cursor = connection.execute(
            "INSERT INTO users (email, password_hash, full_name) VALUES (?, ?, ?)",
            (email, "hash", "Admin User"),
        )
        user_id = cursor.lastrowid
        session_id = connection.execute(
            "INSERT INTO sessions (ended_at) VALUES (NULL)"
        ).lastrowid
        connection.executemany(
            """
            INSERT INTO translations (session_id, user_id, gesture_label, confidence, audio_file)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (session_id, user_id, "Hello", 0.92, "hello.mp3"),
                (session_id, user_id, "Thank You", 0.88, "thanks.mp3"),
                (session_id, user_id, "Hello", 0.95, "hello2.mp3"),
            ],
        )

    with client.session_transaction() as flask_session:
        flask_session["user_id"] = user_id
        flask_session["user_name"] = "Admin User"
        flask_session["user_email"] = email

    response = client.get("/admin")
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Admin Dashboard" in body
    assert "Total Translations" in body
    assert "Most Common Gestures" in body
    assert "Hello" in body


def test_api_routes(client) -> None:
    """Ensure API routes return expected statuses."""
    status_response = client.get("/api/status")
    assert status_response.status_code == 200
    payload = status_response.get_json()
    assert payload is not None
    assert payload.get("camera_frame_route") is True
    assert client.get("/api/history").status_code == 200
    assert client.get("/api/export_history").status_code == 200
    assert client.delete("/api/history").status_code == 200
    assert client.get("/api/camera").status_code == 200


def test_export_history_csv_scopes_rows_to_signed_in_user(client) -> None:
    """CSV export should include only current user's translation history."""
    from database.db import get_connection

    db_path = client.application.config["DATABASE_PATH"]
    email = "csv-export@example.com"
    other_email = "csv-export-other@example.com"
    with get_connection(db_path) as connection:
        connection.execute(
            "DELETE FROM translations WHERE user_id IN (SELECT id FROM users WHERE email IN (?, ?))",
            (email, other_email),
        )
        connection.execute("DELETE FROM users WHERE email IN (?, ?)", (email, other_email))
        user_id = connection.execute(
            "INSERT INTO users (email, password_hash, full_name) VALUES (?, ?, ?)",
            (email, "hash", "Csv User"),
        ).lastrowid
        other_user_id = connection.execute(
            "INSERT INTO users (email, password_hash, full_name) VALUES (?, ?, ?)",
            (other_email, "hash", "Other User"),
        ).lastrowid
        session_id = connection.execute(
            "INSERT INTO sessions (ended_at) VALUES (NULL)"
        ).lastrowid
        connection.executemany(
            """
            INSERT INTO translations (session_id, user_id, gesture_label, confidence, audio_file)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (session_id, user_id, "Hello", 0.91, "hello.mp3"),
                (session_id, user_id, "Thanks", 0.83, "thanks.mp3"),
                (session_id, other_user_id, "Private", 0.77, "private.mp3"),
            ],
        )

    with client.session_transaction() as flask_session:
        flask_session["user_id"] = user_id
        flask_session["user_name"] = "Csv User"
        flask_session["user_email"] = email

    response = client.get("/api/export_history")
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    content_disposition = response.headers.get("Content-Disposition", "")
    assert content_disposition.startswith("attachment; filename=signconnect_history_")
    assert content_disposition.endswith(".csv")
    assert body.startswith("label,confidence,timestamp,audio_path")
    assert "Hello,91.00%," in body
    assert "Thanks,83.00%," in body
    assert "Private,77.00%," not in body


def test_history_page_includes_download_history_csv_button(client) -> None:
    """History page should expose a CSV download action in the UI."""
    response = client.get("/history")
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'id="download-history-btn"' in body
    assert "Download History CSV" in body


def test_history_endpoints_support_anonymous_null_user_rows(client) -> None:
    """Anonymous users should be able to export and clear NULL-scoped history rows."""
    from database.db import get_connection

    db_path = client.application.config["DATABASE_PATH"]
    with get_connection(db_path) as connection:
        session_id = connection.execute(
            "INSERT INTO sessions (ended_at) VALUES (NULL)"
        ).lastrowid
        connection.execute(
            """
            INSERT INTO translations (session_id, user_id, gesture_label, confidence, audio_file)
            VALUES (?, NULL, ?, ?, ?)
            """,
            (session_id, "Guest Hello", 0.73, "guest-hello.mp3"),
        )

    export_response = client.get("/api/export_history")
    csv_body = export_response.get_data(as_text=True)
    assert export_response.status_code == 200
    assert "Guest Hello,73.00%," in csv_body

    clear_response = client.delete("/api/history")
    assert clear_response.status_code == 200

    with get_connection(db_path) as connection:
        remaining = connection.execute(
            "SELECT COUNT(*) AS total FROM translations WHERE user_id IS NULL"
        ).fetchone()["total"]
    assert remaining == 0


def test_set_camera_endpoint_switches_index(client) -> None:
    camera_manager = client.application.extensions["camera_manager"]
    original_index = camera_manager.camera_index
    try:
        response = client.post("/api/camera", json={"camera_index": 1})
        assert response.status_code in (200, 503)
        # Configured preference is updated even if hardware is unavailable in CI.
        assert camera_manager.camera_index == 1
    finally:
        camera_manager.camera_index = original_index


def test_api_docs_routes(client) -> None:
    """Swagger UI and OpenAPI spec should be exposed for presentation/demo use."""
    docs_response = client.get("/api/docs")
    assert docs_response.status_code == 200
    assert "SignConnect API Docs" in docs_response.get_data(as_text=True)

    spec_response = client.get("/api/docs/openapi.json")
    assert spec_response.status_code == 200
    spec = spec_response.get_json()
    assert spec is not None
    assert spec["info"]["title"] == "SignConnect API"
    assert "/api/status" in spec["paths"]
    assert "/api/camera_frame" in spec["paths"]
    assert "/video_feed" in spec["paths"]


def test_health_endpoint(client) -> None:
    """Health endpoint should return JSON with required fields."""
    response = client.get("/api/health")
    # Status is either 200 (model loaded) or 503 (demo/no model) — both valid
    assert response.status_code in (200, 503)
    payload = response.get_json()
    assert payload is not None
    assert "status" in payload
    assert payload["status"] in ("ok", "degraded")
    assert "uptime_seconds" in payload
    assert isinstance(payload["uptime_seconds"], (int, float))
    assert payload["uptime_seconds"] >= 0
    assert "model_loaded" in payload
    assert isinstance(payload["model_loaded"], bool)
    # threads and memory are included when psutil is available (best-effort check)
    if "threads" in payload:
        assert isinstance(payload["threads"], int)
        assert payload["threads"] >= 1
    if "memory" in payload:
        assert isinstance(payload["memory"], dict)
        assert "rss_mb" in payload["memory"]
        assert "vms_mb" in payload["memory"]


def test_camera_frame_jpeg(client) -> None:
    """Translator preview polls these URLs; must be JPEG, not JSON 404."""
    for path in ("/camera_frame", "/api/camera_frame"):
        response = client.get(path)
        assert response.status_code == 200, path
        assert response.content_type.startswith("image/jpeg"), path


# ── CSRF protection tests ─────────────────────────────────────────────────────

def test_csrf_token_injected_in_signin_template(client) -> None:
    """The sign-in form must render a hidden CSRF token field."""
    response = client.get("/signin")
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'name="csrf_token"' in body


def test_csrf_token_injected_in_signup_template(client) -> None:
    """The sign-up form must render a hidden CSRF token field."""
    response = client.get("/signup")
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'name="csrf_token"' in body


def test_csrf_testing_mode_bypass_allows_signin(client) -> None:
    """In TESTING mode, signin POST succeeds without a CSRF token."""
    # The client fixture sets TESTING=True, so CSRF validation is skipped.
    response = client.post(
        "/signin",
        data={"email": "nobody@example.com", "password": "wrongpassword"},
        follow_redirects=False,
    )
    # Response is a rendered page with an error (bad credentials), not a 400.
    assert response.status_code == 200
    assert b"Invalid email or password" in response.data


def test_signup_rejects_invalid_email_format(client) -> None:
    response = client.post(
        "/signup",
        data={
            "first_name": "Invalid",
            "last_name": "Email",
            "email": "invalid-email",
            "password": "StrongPass1!",
        },
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert b"valid email address" in response.data


def test_signup_rejects_weak_password_policy(client) -> None:
    response = client.post(
        "/signup",
        data={
            "first_name": "Weak",
            "last_name": "Password",
            "email": "weak-pass@example.com",
            "password": "weakpassword1!",
        },
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert b"uppercase letter" in response.data


def test_signup_rejects_duplicate_account(client) -> None:
    from database.db import get_connection
    from werkzeug.security import generate_password_hash

    db_path = client.application.config["DATABASE_PATH"]
    email = "duplicate-account@example.com"
    with get_connection(db_path) as connection:
        connection.execute("DELETE FROM users WHERE email = ?", (email,))
        connection.execute(
            "INSERT INTO users (email, password_hash, full_name) VALUES (?, ?, ?)",
            (email, generate_password_hash("StrongPass1!"), "Duplicate User"),
        )

    response = client.post(
        "/signup",
        data={
            "first_name": "Duplicate",
            "last_name": "User",
            "email": email,
            "password": "StrongPass1!",
        },
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert b"already exists" in response.data


def test_signin_rejects_invalid_email_format(client) -> None:
    response = client.post(
        "/signin",
        data={"email": "bad-email", "password": "StrongPass1!"},
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert b"valid email address" in response.data


def test_csrf_missing_token_rejected_outside_testing(client_no_testing) -> None:
    """Outside TESTING mode, a POST without a CSRF token returns 400."""
    response = client_no_testing.post(
        "/signin",
        data={"email": "test@example.com", "password": "somepassword"},
        follow_redirects=False,
    )
    assert response.status_code == 400


def test_csrf_valid_token_accepted_outside_testing(client_no_testing) -> None:
    """Outside TESTING mode, a POST with the correct CSRF token is accepted."""
    # First GET to establish a session token.
    get_response = client_no_testing.get("/signin")
    assert get_response.status_code == 200
    body = get_response.get_data(as_text=True)

    # Extract the token value from the rendered form.
    import re
    match = re.search(r'name="csrf_token"\s+value="([^"]+)"', body)
    assert match, "CSRF token not found in signin form"
    token = match.group(1)

    # POST with the correct token — should reach the auth logic (not 400).
    response = client_no_testing.post(
        "/signin",
        data={"email": "test@example.com", "password": "somepassword", "csrf_token": token},
        follow_redirects=False,
    )
    # 400 would mean CSRF rejection; any other status means the form was processed.
    assert response.status_code != 400


def test_clear_history_delete_requires_csrf_without_api_key(client_no_testing_secure) -> None:
    """DELETE /api/history should fail without CSRF token when API key is absent."""
    response = client_no_testing_secure.delete("/api/history")
    assert response.status_code == 400


def test_clear_history_delete_accepts_csrf_without_api_key(client_no_testing_secure) -> None:
    """DELETE /api/history should pass with valid CSRF token when API key is absent."""
    get_response = client_no_testing_secure.get("/history")
    assert get_response.status_code == 200
    body = get_response.get_data(as_text=True)

    import re
    match = re.search(r'name="csrf-token"\s+content="([^"]+)"', body)
    assert match, "CSRF token meta tag not found in history page"
    token = match.group(1)

    response = client_no_testing_secure.delete(
        "/api/history",
        data={"csrf_token": token},
    )
    assert response.status_code == 200


def test_admin_dashboard_exposes_seed_data_and_management_sections(client) -> None:
    """The rebuilt admin dashboard should render management areas and seeded data."""
    from database.db import get_connection

    db_path = client.application.config["DATABASE_PATH"]
    email = "admin-seed@example.com"
    with get_connection(db_path) as connection:
        connection.execute("DELETE FROM translations WHERE user_id IN (SELECT id FROM users WHERE email = ?)", (email,))
        connection.execute("DELETE FROM users WHERE email = ?", (email,))
        user_id = connection.execute(
            "INSERT INTO users (email, password_hash, full_name) VALUES (?, ?, ?)",
            (email, "hash", "Seed Admin"),
        ).lastrowid
        session_id = connection.execute("INSERT INTO sessions (ended_at) VALUES (NULL)").lastrowid
        connection.execute(
            "INSERT INTO translations (session_id, user_id, gesture_label, confidence, audio_file) VALUES (?, ?, ?, ?, ?)",
            (session_id, user_id, "Hello", 0.93, "hello.mp3"),
        )

    with client.session_transaction() as flask_session:
        flask_session["user_id"] = user_id
        flask_session["user_name"] = "Seed Admin"
        flask_session["user_email"] = email

    response = client.get("/admin")
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "User Management" in body
    assert "Database Management" in body
    assert 'id="admin-dashboard-data"' in body
    assert "Hello" in body


def test_admin_api_endpoints_support_dashboard_user_and_export_flows(client) -> None:
    """Admin APIs should expose dashboard JSON, user management, and CSV export."""
    from database.db import get_connection

    db_path = client.application.config["DATABASE_PATH"]
    admin_email = "admin-api@example.com"
    target_email = "target-user@example.com"
    with get_connection(db_path) as connection:
        connection.execute("DELETE FROM translations WHERE user_id IN (SELECT id FROM users WHERE email IN (?, ?))", (admin_email, target_email))
        connection.execute("DELETE FROM users WHERE email IN (?, ?)", (admin_email, target_email))
        admin_id = connection.execute(
            "INSERT INTO users (email, password_hash, full_name) VALUES (?, ?, ?)",
            (admin_email, "hash", "Admin Api"),
        ).lastrowid
        target_id = connection.execute(
            "INSERT INTO users (email, password_hash, full_name) VALUES (?, ?, ?)",
            (target_email, "hash", "Target User"),
        ).lastrowid
        session_id = connection.execute("INSERT INTO sessions (ended_at) VALUES (NULL)").lastrowid
        connection.execute(
            "INSERT INTO translations (session_id, user_id, gesture_label, confidence, audio_file) VALUES (?, ?, ?, ?, ?)",
            (session_id, target_id, "Thanks", 0.84, "thanks.mp3"),
        )

    with client.session_transaction() as flask_session:
        flask_session["user_id"] = admin_id
        flask_session["user_name"] = "Admin Api"
        flask_session["user_email"] = admin_email

    dashboard = client.get("/api/admin/dashboard")
    assert dashboard.status_code == 200
    dashboard_payload = dashboard.get_json()
    assert dashboard_payload is not None
    assert "stats" in dashboard_payload
    assert "charts" in dashboard_payload

    users = client.get("/api/admin/users?query=target")
    assert users.status_code == 200
    users_payload = users.get_json()
    assert users_payload is not None
    assert users_payload["count"] >= 1

    suspend = client.post(f"/api/admin/users/{target_id}/suspend", data={"suspended": "true"})
    assert suspend.status_code == 200
    assert suspend.get_json()["is_suspended"] is True

    export_response = client.get("/api/admin/translations/export?query=Thanks")
    export_body = export_response.get_data(as_text=True)
    assert export_response.status_code == 200
    assert export_response.headers["Content-Disposition"] == "attachment; filename=signconnect_admin_translations.csv"
    assert "Thanks" in export_body
