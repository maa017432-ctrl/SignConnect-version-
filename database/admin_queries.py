"""Admin dashboard query helpers for SignConnect."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from database.db import get_connection


_ACTIVE_WINDOW = timedelta(minutes=15)
_RECENT_WINDOW = timedelta(hours=24)


def _parse_timestamp(raw: object) -> datetime | None:
    if not raw:
        return None
    try:
        value = str(raw).strip().replace(" ", "T")
        if value.endswith("Z"):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def activity_status(raw_timestamp: object, *, suspended: bool = False) -> str:
    """Map a timestamp into a user-facing activity status label."""
    if suspended:
        return "Suspended"
    dt = _parse_timestamp(raw_timestamp)
    if dt is None:
        return "Inactive"
    age = datetime.now(timezone.utc) - dt.astimezone(timezone.utc)
    if age <= _ACTIVE_WINDOW:
        return "Active now"
    if age <= _RECENT_WINDOW:
        return "Recent"
    return "Inactive"


def _translations_over_time(connection, *, days: int = 7) -> tuple[list[str], list[int]]:
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
    totals_by_day = {row["day"]: int(row["total"] or 0) for row in rows}

    labels: list[str] = []
    values: list[int] = []
    for offset in range(days):
        day = start_date + timedelta(days=offset)
        key = day.isoformat()
        labels.append(day.strftime("%b %d"))
        values.append(totals_by_day.get(key, 0))
    return labels, values


def _serialize_user_row(row) -> dict[str, Any]:
    suspended = bool(row["is_suspended"])
    last_active = row["last_active"]
    return {
        "id": int(row["id"]),
        "full_name": row["full_name"] or "Unnamed user",
        "email": row["email"],
        "created_at": row["created_at"],
        "last_active": last_active,
        "translations": int(row["translation_count"] or 0),
        "avg_confidence": round(float(row["avg_confidence"] or 0.0) * 100, 1),
        "is_suspended": suspended,
        "activity_status": activity_status(last_active, suspended=suspended),
    }


def fetch_users(database_path: str, *, query: str = "", limit: int = 50) -> list[dict[str, Any]]:
    """Return user management rows with activity metadata."""
    normalized_query = f"%{query.strip().lower()}%"
    safe_limit = max(1, min(int(limit), 100))
    with get_connection(database_path) as connection:
        rows = connection.execute(
            """
            SELECT
                users.id,
                users.full_name,
                users.email,
                users.created_at,
                users.is_suspended,
                COUNT(translations.id) AS translation_count,
                AVG(translations.confidence) AS avg_confidence,
                MAX(translations.created_at) AS last_active
            FROM users
            LEFT JOIN translations ON translations.user_id = users.id
            WHERE (? = '%%' OR LOWER(users.full_name) LIKE ? OR LOWER(users.email) LIKE ?)
            GROUP BY users.id, users.full_name, users.email, users.created_at, users.is_suspended
            ORDER BY users.is_suspended ASC,
                     COALESCE(MAX(translations.created_at), users.created_at) DESC,
                     users.email ASC
            LIMIT ?
            """,
            (normalized_query, normalized_query, normalized_query, safe_limit),
        ).fetchall()
    return [_serialize_user_row(row) for row in rows]


def fetch_translations(
    database_path: str,
    *,
    query: str = "",
    gesture: str = "",
    user_id: int | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Return translation history rows with user metadata."""
    normalized_query = f"%{query.strip().lower()}%"
    normalized_gesture = gesture.strip().lower()
    safe_limit = max(1, min(int(limit), 200))
    with get_connection(database_path) as connection:
        rows = connection.execute(
            """
            SELECT
                translations.id,
                translations.gesture_label,
                translations.confidence,
                translations.audio_file,
                translations.created_at,
                users.id AS user_id,
                users.full_name,
                users.email
            FROM translations
            LEFT JOIN users ON users.id = translations.user_id
            WHERE (? = '%%' OR LOWER(translations.gesture_label) LIKE ? OR LOWER(COALESCE(users.full_name, '')) LIKE ? OR LOWER(COALESCE(users.email, '')) LIKE ?)
              AND (? = '' OR LOWER(translations.gesture_label) = ?)
              AND (? IS NULL OR translations.user_id = ?)
            ORDER BY translations.id DESC
            LIMIT ?
            """,
            (
                normalized_query,
                normalized_query,
                normalized_query,
                normalized_query,
                normalized_gesture,
                normalized_gesture,
                user_id,
                user_id,
                safe_limit,
            ),
        ).fetchall()
    payload: list[dict[str, Any]] = []
    for row in rows:
        payload.append(
            {
                "id": int(row["id"]),
                "gesture_label": row["gesture_label"],
                "confidence": row["confidence"],
                "confidence_pct": round(float(row["confidence"] or 0.0) * 100, 2),
                "audio_file": row["audio_file"],
                "audio_path": f"/static/audio/{row['audio_file']}" if row["audio_file"] else None,
                "created_at": row["created_at"],
                "user_id": row["user_id"],
                "user_name": row["full_name"] or "Guest",
                "user_email": row["email"] or "guest@local",
            }
        )
    return payload


def build_dashboard_payload(database_path: str, runtime_metrics: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build the admin dashboard payload for SSR and API responses."""
    runtime_metrics = runtime_metrics or {}
    with get_connection(database_path) as connection:
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
        recent_users_rows = connection.execute(
            """
            SELECT
                users.id,
                users.full_name,
                users.email,
                users.created_at,
                users.is_suspended,
                COUNT(translations.id) AS translation_count,
                AVG(translations.confidence) AS avg_confidence,
                MAX(translations.created_at) AS last_active
            FROM users
            LEFT JOIN translations ON translations.user_id = users.id
            GROUP BY users.id, users.full_name, users.email, users.created_at, users.is_suspended
            ORDER BY COALESCE(MAX(translations.created_at), users.created_at) DESC, users.email ASC
            LIMIT 8
            """
        ).fetchall()
        recent_translations_rows = connection.execute(
            """
            SELECT
                translations.id,
                translations.gesture_label,
                translations.confidence,
                translations.audio_file,
                translations.created_at,
                users.id AS user_id,
                users.full_name,
                users.email
            FROM translations
            LEFT JOIN users ON users.id = translations.user_id
            ORDER BY translations.id DESC
            LIMIT 12
            """
        ).fetchall()
        labels, totals = _translations_over_time(connection)

    recent_translations = [
        {
            "id": int(row["id"]),
            "gesture_label": row["gesture_label"],
            "confidence": row["confidence"],
            "confidence_pct": round(float(row["confidence"] or 0.0) * 100, 2),
            "audio_file": row["audio_file"],
            "audio_path": f"/static/audio/{row['audio_file']}" if row["audio_file"] else None,
            "created_at": row["created_at"],
            "user_id": row["user_id"],
            "user_name": row["full_name"] or "Guest",
            "user_email": row["email"] or "guest@local",
        }
        for row in recent_translations_rows
    ]

    inference_samples = list(runtime_metrics.get("inference_samples") or [])
    avg_inference_ms = round(sum(inference_samples) / len(inference_samples), 1) if inference_samples else 0.0
    stats = {
        "total_translations": int(summary["total_translations"] or 0),
        "total_users": int(summary["total_users"] or 0),
        "active_users": int(summary["active_users"] or 0),
        "translations_today": int(summary["translations_today"] or 0),
        "average_confidence": round(float(summary["average_confidence"] or 0.0) * 100, 1),
        "active_sessions": int(runtime_metrics.get("connected_clients") or 0),
        "connected_users": int(runtime_metrics.get("connected_users") or 0),
        "predictions_served": int(runtime_metrics.get("prediction_events") or 0),
        "avg_inference_ms": avg_inference_ms,
    }
    charts = {
        "translations_over_time": {"labels": labels, "values": totals},
        "top_gestures": {
            "labels": [row["gesture_label"] for row in top_gestures] or ["No data yet"],
            "values": [int(row["total"] or 0) for row in top_gestures] or [1],
        },
        "confidence_by_gesture": {
            "labels": [row["gesture_label"] for row in confidence_by_gesture] or ["No data yet"],
            "values": [round(float(row["avg_confidence"] or 0.0) * 100, 1) for row in confidence_by_gesture] or [0],
        },
    }
    monitoring = {
        "connected_users": int(runtime_metrics.get("connected_users") or 0),
        "active_sessions": int(runtime_metrics.get("connected_clients") or 0),
        "predictions_served": int(runtime_metrics.get("prediction_events") or 0),
        "last_prediction_at": runtime_metrics.get("last_prediction_at"),
        "last_prediction_label": runtime_metrics.get("last_prediction_label") or "—",
        "last_prediction_confidence": round(float(runtime_metrics.get("last_prediction_confidence") or 0.0) * 100, 1),
        "avg_inference_ms": avg_inference_ms,
        "model_status": runtime_metrics.get("model_status") or "loading",
        "demo_mode": bool(runtime_metrics.get("demo_mode")),
    }
    return {
        "stats": stats,
        "charts": charts,
        "monitoring": monitoring,
        "users": [_serialize_user_row(row) for row in recent_users_rows],
        "translations": recent_translations,
        "settings": {
            "confidence_threshold": round(float(runtime_metrics.get("confidence_threshold") or 0.75) * 100, 0),
            "camera_index": int(runtime_metrics.get("camera_index") or 0),
        },
    }
