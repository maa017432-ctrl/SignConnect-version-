"""Primary view routes for page rendering."""

from __future__ import annotations

from datetime import date, timedelta

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

from database.db import get_connection


main_bp = Blueprint("main", __name__)
_LABEL_SOURCE_MAP = "label_map"
_LABEL_SOURCE_CONFIG = "config"
_FALLBACK_LABEL_PREFIX = "Class"


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
    return render_template(
        "dictionary.html",
        labels=labels,
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

    with get_connection(current_app.config["DATABASE_PATH"]) as connection:
        summary = connection.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM translations) AS total_translations,
                (SELECT COUNT(*) FROM users) AS total_users,
                (SELECT COUNT(DISTINCT user_id) FROM translations WHERE user_id IS NOT NULL) AS active_users,
                (SELECT COUNT(*) FROM translations WHERE DATE(created_at) = DATE('now')) AS translations_today,
                (SELECT AVG(confidence) FROM translations WHERE confidence IS NOT NULL) AS average_confidence
            """
        ).fetchone()

        top_gestures = connection.execute(
            """
            SELECT gesture_label, COUNT(*) AS total
            FROM translations
            GROUP BY gesture_label
            ORDER BY total DESC, gesture_label ASC
            LIMIT 6
            """
        ).fetchall()

        confidence_by_gesture = connection.execute(
            """
            SELECT gesture_label, AVG(confidence) AS avg_confidence
            FROM translations
            WHERE confidence IS NOT NULL
            GROUP BY gesture_label
            HAVING COUNT(*) >= 1
            ORDER BY avg_confidence DESC, gesture_label ASC
            LIMIT 6
            """
        ).fetchall()

        labels, totals = _translations_over_time(connection)

    stats = {
        "total_translations": int(summary["total_translations"] or 0),
        "total_users": int(summary["total_users"] or 0),
        "active_users": int(summary["active_users"] or 0),
        "translations_today": int(summary["translations_today"] or 0),
        "average_confidence": round(float(summary["average_confidence"] or 0.0) * 100, 1),
    }
    chart_data = {
        "translations_over_time": {
            "labels": labels,
            "values": totals,
        },
        "top_gestures": {
            "labels": [row["gesture_label"] for row in top_gestures] or ["No data yet"],
            "values": [int(row["total"]) for row in top_gestures] or [1],
        },
        "confidence_by_gesture": {
            "labels": [row["gesture_label"] for row in confidence_by_gesture] or ["No data yet"],
            "values": [
                round(float(row["avg_confidence"] or 0.0) * 100, 1)
                for row in confidence_by_gesture
            ] or [0],
        },
    }
    return render_template(
        "admin.html",
        stats=stats,
        chart_data=chart_data,
        **_user_ctx(),
    )
