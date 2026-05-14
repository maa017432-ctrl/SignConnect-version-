"""SignConnect — cross-platform production launcher.

Uses Waitress (pure-Python, Windows-compatible) as the WSGI server.
Flask-SocketIO is initialised in ``threading`` async_mode so that the ML
inference thread never blocks the WSGI worker pool.

Usage (from the project root):
    python run_production.py

Environment variables (can be set in .env or the shell):
    HOST          - bind address        (default: 0.0.0.0)
    PORT          - TCP port            (default: 5000)
    THREADS       - Waitress threads    (default: 8)
    LOG_LEVEL     - Python log level    (default: INFO)
    MJPEG_JPEG_QUALITY - MJPEG quality  (default: 75, range 0-100)

Note on WebSockets
------------------
Waitress is a pure HTTP/1.1 server and does NOT handle the WebSocket
upgrade handshake.  Flask-SocketIO automatically falls back to HTTP
long-polling when a WebSocket upgrade cannot be completed, so all
real-time prediction push notifications continue to work correctly.

For full WebSocket support in production, place a reverse proxy
(e.g. nginx or Caddy) in front of Waitress that handles the WS upgrade
and forwards plain HTTP/1.1 to Waitress on localhost.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# ── Load .env before anything else so Config() sees the right values ──
load_dotenv(Path(__file__).resolve().parent / ".env")

try:
    from waitress import serve
except ImportError:
    sys.exit(
        "ERROR: waitress is not installed.  "
        "Run: pip install waitress>=3.0.0"
    )

from app import create_app  # noqa: E402 — must come after load_dotenv

HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "5000"))
THREADS = int(os.environ.get("THREADS", "8"))
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    stream=sys.stdout,
)
LOGGER = logging.getLogger(__name__)


def main() -> None:
    flask_app = create_app()

    LOGGER.info(
        "SignConnect production server starting — http://%s:%s  threads=%d",
        HOST, PORT, THREADS,
    )
    LOGGER.info(
        "SocketIO async_mode=threading  "
        "(WebSocket upgrade requires a reverse proxy; long-polling is the fallback)"
    )

    serve(
        flask_app,
        host=HOST,
        port=PORT,
        threads=THREADS,
        connection_limit=500,
        channel_timeout=120,
        # Disable Waitress's internal response buffering so MJPEG chunks
        # stream immediately to the browser without being coalesced.
        asyncore_use_poll=True,
    )


if __name__ == "__main__":
    main()
