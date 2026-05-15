"""Flask + SocketIO entry point for the SignConnect application."""

from __future__ import annotations

import atexit
import logging
from collections import deque
from pathlib import Path
from threading import Lock

from dotenv import load_dotenv
from flasgger import Swagger
from flask import Flask, jsonify, request, session
from flask.wrappers import Response
from flask_cors import CORS
from flask_socketio import SocketIO

from config import Config
from core.ai_model import GestureClassifier
from core.camera import CameraManager
from core.csrf import generate_csrf_token
from core.gesture_detector import GestureDetector
from core.logging_config import configure_logging
from core.prediction_smoother import PredictionSmoother, SentenceBuilder
from core.translator import Translator
from core.tts_engine import TTSEngine
from database.db import init_db
from routes.api import api_bp
from routes.auth import auth_bp
from routes.main import main_bp
from routes.stream import camera_frame_response, stream_bp


LOGGER = logging.getLogger(__name__)

# Module-level SocketIO instance so routes/stream.py can import it directly.
socketio = SocketIO()


def _configure_api_docs(app: Flask) -> Swagger:
    """Attach branded Swagger UI for public API exploration."""
    swagger_template = {
        "swagger": "2.0",
        "info": {
            "title": "SignConnect API",
            "description": (
                "Interactive API documentation for SignConnect's real-time "
                "sign-language translation platform."
            ),
            "version": "1.0.0",
            "contact": {
                "name": "SignConnect",
                "url": "https://github.com/venom010101/SignConnect",
            },
        },
        "basePath": "/",
        "schemes": ["http", "https"],
        "consumes": ["application/json"],
        "produces": ["application/json"],
    }
    swagger_config = {
        "headers": [],
        "title": "SignConnect API Docs",
        "specs": [
            {
                "endpoint": "signconnect_openapi",
                "route": "/api/docs/openapi.json",
                "rule_filter": (
                    lambda rule: rule.rule.startswith("/api")
                    or rule.rule in ("/camera_frame", "/video_feed")
                ),
                "model_filter": lambda tag: True,
            }
        ],
        "specs_route": "/api/docs",
        "swagger_ui": True,
        "favicon": "/static/icons/icon-192.png",
        "top_text": """
        <div class="sc-docs-hero">
          <img src="/static/logo.svg" alt="SignConnect" class="sc-docs-logo">
          <div class="sc-docs-copy">
            <span class="sc-docs-kicker">Graduation Project • API Documentation</span>
            <h1>SignConnect API</h1>
            <p>Interactive docs for live translation, health monitoring, camera streaming, and speech synthesis.</p>
          </div>
        </div>
        """,
        "doc_expansion": "list",
        "uiversion": 3,
    }
    return Swagger(app, config=swagger_config, template=swagger_template)


def create_app() -> Flask:
    """Create and configure the Flask + SocketIO application instance."""
    env_path = Path(__file__).resolve().parent / ".env"
    load_dotenv(env_path)

    app = Flask(__name__)
    app.config.from_object(Config())

    configure_logging(app.config["LOG_LEVEL"])

    # ── CORS: restrict to configured origins only (no wildcard) ──
    CORS(app, origins=app.config["ALLOWED_ORIGINS"], supports_credentials=True)

    # Threading async_mode + simple-websocket: real WebSockets without eventlet/gevent
    socketio.init_app(
        app,
        cors_allowed_origins=app.config["ALLOWED_ORIGINS"],
        async_mode="threading",
        logger=False,
        engineio_logger=False,
    )

    @app.after_request
    def _no_cache_for_api_and_frames(response: Response) -> Response:
        """Prevent browsers from caching /api/* and frame endpoints."""
        path = request.path
        if path.startswith("/api") or path in ("/camera_frame",):
            response.headers["Cache-Control"] = (
                "no-store, no-cache, must-revalidate, max-age=0"
            )
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

    init_db(app.config["DATABASE_PATH"], app.config["SCHEMA_PATH"])

    camera_manager = CameraManager(camera_index=app.config["CAMERA_INDEX"])
    gesture_detector = GestureDetector(
        min_detection_confidence=app.config["MP_MIN_DETECTION_CONFIDENCE"],
        min_tracking_confidence=app.config["MP_MIN_TRACKING_CONFIDENCE"],
    )
    translator = Translator(label_map_path=app.config["LABEL_MAP_PATH"])
    labels_count = len(translator.get_all_labels()) or app.config["LABELS_COUNT"]
    classifier = GestureClassifier(
        model_path=app.config["MODEL_PATH"],
        confidence_threshold=app.config["PREDICTION_CONFIDENCE_THRESHOLD"],
        labels_count=labels_count,
        model_input_dim=app.config["MODEL_INPUT_DIM"],
        model_type=app.config["MODEL_TYPE"],
        sequence_length=app.config["SEQUENCE_LENGTH"],
    )
    tts_engine = TTSEngine(
        audio_dir=app.config["AUDIO_CACHE_DIR"],
        cache_ttl_seconds=app.config["AUDIO_CACHE_TTL_SECONDS"],
    )
    smoother = PredictionSmoother(
        window=app.config.get("SMOOTHER_WINDOW", 10),
        min_fraction=app.config.get("SMOOTHER_MIN_FRACTION", 0.6),
    )
    sentence_builder = SentenceBuilder(
        stable_frames=app.config.get("SENTENCE_STABLE_FRAMES", 15),
        cooldown_frames=app.config.get("SENTENCE_COOLDOWN_FRAMES", 20),
    )

    app.extensions["camera_manager"]      = camera_manager
    app.extensions["gesture_detector"]    = gesture_detector
    app.extensions["classifier"]          = classifier
    app.extensions["translator"]          = translator
    app.extensions["tts_engine"]          = tts_engine
    app.extensions["prediction_smoother"] = smoother
    app.extensions["sentence_builder"]    = sentence_builder
    app.extensions["socketio"]            = socketio
    runtime_metrics_lock = Lock()
    app.extensions["runtime_metrics_lock"] = runtime_metrics_lock
    app.extensions["runtime_metrics"] = {
        "connected_clients": 0,
        "connected_users": 0,
        "connections": {},
        "prediction_events": 0,
        "last_prediction_at": None,
        "last_prediction_label": None,
        "last_prediction_confidence": 0.0,
        "model_status": getattr(classifier, "model_type", "unknown"),
        "demo_mode": bool(classifier.is_demo_mode),
        "camera_index": camera_manager.camera_index,
        "confidence_threshold": classifier.confidence_threshold,
        "inference_samples": deque(maxlen=120),
    }
    app.extensions["latest_prediction"]   = {
        "label": None,
        "confidence": 0.0,
        "last_valid_confidence": 0.0,
        "smoothed_label": None,
        "top_candidates": [],
        "coaching": {"state": "error", "issue": "missing", "message": "Hand not detected"},
    }

    @socketio.on("connect")
    def _track_socket_connect() -> None:
        runtime_metrics = app.extensions.get("runtime_metrics")
        if runtime_metrics is None:
            return
        sid = request.sid
        user_key = session.get("user_id") or f"guest:{sid}"
        with runtime_metrics_lock:
            connections = runtime_metrics.setdefault("connections", {})
            connections[sid] = user_key
            runtime_metrics["connected_clients"] = len(connections)
            runtime_metrics["connected_users"] = len(
                {value for value in connections.values() if not str(value).startswith("guest:")}
            )

    @socketio.on("disconnect")
    def _track_socket_disconnect() -> None:
        runtime_metrics = app.extensions.get("runtime_metrics")
        if runtime_metrics is None:
            return
        sid = request.sid
        with runtime_metrics_lock:
            connections = runtime_metrics.setdefault("connections", {})
            connections.pop(sid, None)
            runtime_metrics["connected_clients"] = len(connections)
            runtime_metrics["connected_users"] = len(
                {value for value in connections.values() if not str(value).startswith("guest:")}
            )

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(stream_bp)
    app.register_blueprint(api_bp)

    @app.context_processor
    def _inject_csrf() -> dict[str, object]:
        """Make ``csrf_token()`` callable in every Jinja2 template."""
        return {"csrf_token": generate_csrf_token}

    app.add_url_rule(
        "/camera_frame",
        "camera_frame",
        camera_frame_response,
        methods=["GET"],
    )
    _configure_api_docs(app)

    LOGGER.info("SignConnect started — JPEG preview: /camera_frame, /api/camera_frame")

    @app.errorhandler(404)
    def not_found(_: Exception) -> tuple[Response, int]:
        return jsonify({"error": "Resource not found", "code": 404}), 404

    @app.errorhandler(500)
    def server_error(_: Exception) -> tuple[Response, int]:
        return jsonify({"error": "Internal server error", "code": 500}), 500

    def _stop_camera_on_exit() -> None:
        try:
            camera_manager.stop()
        except Exception:
            LOGGER.exception("Failed to stop camera manager on exit")

    atexit.register(_stop_camera_on_exit)

    # atexit only fires on a clean Python exit; a raw SIGTERM (e.g. systemd
    # `stop`, `kill <pid>`, or container orchestrator shutdown) bypasses it.
    # Install an explicit handler so the camera FD is always released.
    import signal as _signal

    _original_sigterm = _signal.getsignal(_signal.SIGTERM)

    def _sigterm_handler(sig: int, frame: object) -> None:
        LOGGER.info("SIGTERM received — releasing camera hardware lock before exit")
        _stop_camera_on_exit()
        # Restore and re-raise so the WSGI server (Waitress) can complete its
        # own orderly shutdown (drain in-flight requests, close sockets, etc.).
        _signal.signal(_signal.SIGTERM, _original_sigterm or _signal.SIG_DFL)
        _signal.raise_signal(_signal.SIGTERM)

    _signal.signal(_signal.SIGTERM, _sigterm_handler)

    return app


if __name__ == "__main__":
    flask_app = create_app()
    # Development only — use run_production.ps1 / waitress for production.
    if flask_app.config["DEBUG"]:
        socketio.run(
            flask_app,
            host=flask_app.config["HOST"],
            port=flask_app.config["PORT"],
            debug=True,
            allow_unsafe_werkzeug=True,
            use_reloader=False,
        )
    else:
        # Production: use waitress (already in requirements.txt)
        from waitress import serve
        LOGGER.info(
            "Starting production server on %s:%s",
            flask_app.config["HOST"],
            flask_app.config["PORT"],
        )
        serve(
            flask_app,
            host=flask_app.config["HOST"],
            port=flask_app.config["PORT"],
            threads=4,
        )
