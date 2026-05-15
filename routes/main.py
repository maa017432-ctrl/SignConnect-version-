"""Primary view routes for page rendering."""

from __future__ import annotations

from datetime import date, timedelta
import re

from flask import (
    Blueprint,
    current_app,
    redirect,
    render_template,
    send_from_directory,
    session,
    url_for,
)
from flask.wrappers import Response

from database.admin_queries import build_dashboard_payload
from database.db import get_connection


main_bp = Blueprint("main", __name__)
_LABEL_SOURCE_MAP = "label_map"
_LABEL_SOURCE_CONFIG = "config"
_FALLBACK_LABEL_PREFIX = "Class"


def _slugify_label(label: str) -> str:
    """Return a filesystem-friendly landmark preview key for a label."""
    return re.sub(r"[^a-z0-9]+", "_", label.strip().lower()).strip("_")


def _user_ctx() -> dict:
    """Return common user context for templates."""
    return {
        "current_user": {
            "id": session.get("user_id"),
            "email": session.get("user_email", ""),
            "name": session.get("user_name", ""),
            "is_authenticated": bool(session.get("user_id")),
        }
    }


def _supported_dictionary_labels() -> tuple[list[str], str]:
    """Return supported labels and the source used to build the list."""
    translator_ext = current_app.extensions.get("translator")
    labels = translator_ext.get_all_labels() if translator_ext else []
    if labels:
        return labels, _LABEL_SOURCE_MAP

    classifier = current_app.extensions.get("classifier")
    labels_count = int(
        getattr(classifier, "labels_count", 0) or current_app.config.get("LABELS_COUNT", 0)
    )
    fallback = [f"{_FALLBACK_LABEL_PREFIX} {idx}" for idx in range(1, labels_count + 1)]
    return fallback, _LABEL_SOURCE_CONFIG


def _translations_over_time(connection, days: int = 7) -> tuple[list[str], list[int]]:
    start_date = date.today() - timedelta(days=days - 1)
    rows = connection.execute(
        """
        SELECT DATE(created_at) AS day, COUNT(*) AS total
        FROM translations
        WHERE DATE(created_at) >= ?
        GROUP BY DATE(created_at)
        ORDER BY DATE(created_at)
        """,
        (start_date.isoformat(),),
    ).fetchall()
    totals_by_day = {row["day"]: int(row["total"]) for row in rows}

    labels: list[str] = []
    values: list[int] = []
    for offset in range(days):
        day = start_date + timedelta(days=offset)
        key = day.isoformat()
        labels.append(day.strftime("%b %d"))
        values.append(totals_by_day.get(key, 0))
    return labels, values


@main_bp.get("/")
def index() -> str:
    """Render project landing page."""
    return render_template("index.html", **_user_ctx())


@main_bp.get("/translator")
def translator() -> str:
    """Render live translation interface."""
    classifier = current_app.extensions.get("classifier")
    demo_mode = classifier.is_demo_mode if classifier else True
    return render_template("translator.html", demo_mode=demo_mode, **_user_ctx())


@main_bp.get("/sw.js")
def service_worker() -> Response:
    """Serve the PWA service worker from root scope with correct headers."""
    response = send_from_directory(
        current_app.static_folder,  # type: ignore[arg-type]
        "sw.js",
        mimetype="application/javascript",
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Service-Worker-Allowed"] = "/"
    return response


@main_bp.get("/history")
def history() -> str:
    """Render latest translation history from SQLite."""
    user_id = session.get("user_id")
    with get_connection(current_app.config["DATABASE_PATH"]) as connection:
        if user_id is None:
            rows = connection.execute(
                """
                SELECT gesture_label, confidence, audio_file, created_at
                FROM translations
                WHERE user_id IS NULL
                ORDER BY id DESC
                LIMIT 50
                """
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT gesture_label, confidence, audio_file, created_at
                FROM translations
                WHERE user_id = ?
                ORDER BY id DESC
                LIMIT 50
                """,
                (user_id,),
            ).fetchall()
    return render_template("history.html", rows=rows, **_user_ctx())


@main_bp.get("/dictionary")
def dictionary() -> str:
    """Render the gesture dictionary page."""
    labels, labels_source = _supported_dictionary_labels()
    dictionary_items = [
        {"label": label, "landmark_key": _slugify_label(label)}
        for label in labels
    ]
    return render_template(
        "dictionary.html",
        labels=labels,
        dictionary_items=dictionary_items,
        labels_source=labels_source,
        labels_from_config=(labels_source == _LABEL_SOURCE_CONFIG),
        **_user_ctx(),
    )


@main_bp.get("/alphabet")
def alphabet() -> str:
    """Render alphabet/finger-spelling translator page."""
    # Load alphabet letters for template
    alphabet_path = current_app.config.get("ALPHABET_LABEL_MAP_PATH", "models/alphabet_label_map.json")
    try:
        import json
        with open(alphabet_path, "r", encoding="utf-8") as f:
            alphabet_map = json.load(f)
        alphabet_letters = [alphabet_map[str(i)] for i in range(26)]
    except Exception:
        alphabet_letters = [chr(65 + i) for i in range(26)]  # A-Z fallback
    
    return render_template("alphabet.html", alphabet_letters=alphabet_letters, **_user_ctx())


@main_bp.get("/settings")
def settings() -> str:
    """Render the settings page."""
    classifier = current_app.extensions.get("classifier")
    return render_template(
        "settings.html",
        confidence_threshold=classifier.confidence_threshold if classifier else 0.7,
        **_user_ctx(),
    )


@main_bp.get("/admin")
def admin() -> str | Response:
    """Render the analytics dashboard for signed-in users."""
    if not session.get("user_id"):
        return redirect(url_for("auth.signin_get"))

    dashboard_payload = build_dashboard_payload(
        current_app.config["DATABASE_PATH"],
        current_app.extensions.get("runtime_metrics") or {},
    )
    return render_template(
        "admin.html",
        dashboard_payload=dashboard_payload,
        **_user_ctx(),
    )
