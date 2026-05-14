"""Lightweight CSRF protection using the double-submit session-token pattern.

A random token is stored in the server-side session on first request.  Every
state-changing form POST must include that same token in a hidden field named
``csrf_token``.  Validation uses :func:`hmac.compare_digest` to prevent
timing-based oracle attacks.

TESTING mode bypass
-------------------
When ``app.config["TESTING"]`` is ``True`` the validation step is skipped
entirely so that test clients do not need to submit tokens.
"""

from __future__ import annotations

import hmac
import logging
import os

from flask import abort, current_app, request, session

LOGGER = logging.getLogger(__name__)

_TOKEN_KEY = "csrf_token"


def generate_csrf_token() -> str:
    """Return the CSRF token for the current session, creating it if absent."""
    if _TOKEN_KEY not in session:
        session[_TOKEN_KEY] = os.urandom(32).hex()
    return session[_TOKEN_KEY]  # type: ignore[return-value]


def validate_csrf_token() -> None:
    """Verify the submitted CSRF token against the session token.

    Aborts with HTTP 400 if the token is missing or doesn't match.
    Skipped entirely when ``app.config["TESTING"]`` is truthy.
    """
    if current_app.config.get("TESTING"):
        return

    expected: str = session.get(_TOKEN_KEY, "")
    submitted: str = request.form.get(_TOKEN_KEY, "")

    if not expected or not hmac.compare_digest(expected, submitted):
        LOGGER.warning(
            "CSRF validation failed for %s %s (token present: submitted=%s session=%s)",
            request.method,
            request.path,
            bool(submitted),
            bool(expected),
        )
        abort(400, description="CSRF token missing or invalid.")
