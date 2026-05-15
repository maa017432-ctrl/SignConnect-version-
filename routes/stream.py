"""Video stream and camera frame routes."""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import deque
from datetime import datetime, timezone
from io import BytesIO
from typing import Any, Iterator

import numpy as np
from flask import Blueprint, Response, current_app
from PIL import Image, ImageDraw

from core.camera import CameraUnavailableError

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None


LOGGER = logging.getLogger(__name__)
stream_bp = Blueprint("stream", __name__)

_CAMERA_RETRY_INTERVAL_S = 5.0
_JPEG_QUALITY = max(0, min(100, int(os.environ.get("MJPEG_JPEG_QUALITY", "75"))))  # clamped 0-100
_TARGET_FPS = 30
_prediction_lock = threading.Lock()
_coaching_lock = threading.Lock()
_coaching_centroids: deque[tuple[float, float]] = deque(maxlen=8)
_COACHING_EDGE_MARGIN = 0.03
_COACHING_TOO_FAR_AREA = 0.025
_COACHING_TOO_CLOSE_AREA = 0.45
_COACHING_SHAKE_DELTA = 0.035


def _placeholder_frame(text: str = "") -> bytes:
    """Generate a fallback 1x1 JPEG frame.
    
    This keeps the MJPEG stream alive without triggering the frontend
    to hide the 'Connecting to camera' overlay (since naturalWidth <= 1).
    """
    image = Image.new("RGB", (1, 1), color=(0, 0, 0))
    buffer = BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


def _mjpeg_chunk(jpeg_bytes: bytes) -> bytes:
    """Format one multipart part for MJPEG."""
    return (
        b"--frame\r\n"
        b"Content-Type: image/jpeg\r\n\r\n"
        + jpeg_bytes
        + b"\r\n"
    )


def _emit_prediction(app: Any, payload: dict[str, object]) -> None:
    """Push prediction data via SocketIO stored in app.extensions."""
    sio = app.extensions.get("socketio")
    if sio is None:
        return
    try:
        sio.emit("prediction", payload)
    except Exception:
        LOGGER.debug("SocketIO emit failed", exc_info=True)


def _infer_coaching(landmarks: np.ndarray | None) -> dict[str, object]:
    """Infer live coaching feedback from normalized landmark coverage and motion."""
    if landmarks is None:
        with _coaching_lock:
            _coaching_centroids.clear()
        return {
            "state": "error",
            "issue": "missing",
            "message": "Hand not detected",
        }

    points = np.asarray(landmarks, dtype=np.float32).reshape(-1, 3)
    valid = points[np.any(np.abs(points) > 1e-6, axis=1)]
    if valid.shape[0] < 6:
        with _coaching_lock:
            _coaching_centroids.clear()
        return {
            "state": "error",
            "issue": "missing",
            "message": "Hand not detected",
        }

    xy = valid[:, :2]
    min_x, min_y = float(np.min(xy[:, 0])), float(np.min(xy[:, 1]))
    max_x, max_y = float(np.max(xy[:, 0])), float(np.max(xy[:, 1]))
    width = max(0.0, max_x - min_x)
    height = max(0.0, max_y - min_y)
    area = width * height
    center_x = (min_x + max_x) * 0.5
    center_y = (min_y + max_y) * 0.5

    with _coaching_lock:
        _coaching_centroids.append((center_x, center_y))
        shaky = False
        if len(_coaching_centroids) >= 4:
            deltas = []
            for idx in range(1, len(_coaching_centroids)):
                prev = _coaching_centroids[idx - 1]
                curr = _coaching_centroids[idx]
                deltas.append(((curr[0] - prev[0]) ** 2 + (curr[1] - prev[1]) ** 2) ** 0.5)
            shaky = (sum(deltas) / len(deltas)) > _COACHING_SHAKE_DELTA

    if (
        min_x <= _COACHING_EDGE_MARGIN
        or min_y <= _COACHING_EDGE_MARGIN
        or max_x >= (1.0 - _COACHING_EDGE_MARGIN)
        or max_y >= (1.0 - _COACHING_EDGE_MARGIN)
    ):
        return {
            "state": "warning",
            "issue": "outside_frame",
            "message": "Center your hand",
        }
    if area <= _COACHING_TOO_FAR_AREA:
        return {
            "state": "warning",
            "issue": "too_far",
            "message": "Move hand closer",
        }
    if area >= _COACHING_TOO_CLOSE_AREA:
        return {
            "state": "warning",
            "issue": "too_close",
            "message": "Move hand farther",
        }
    if shaky:
        return {
            "state": "warning",
            "issue": "unstable",
            "message": "Hold steady",
        }
    return {
        "state": "success",
        "issue": "good",
        "message": "Good position",
    }


def _annotate_and_encode_jpeg(app: Any, frame: np.ndarray) -> bytes | None:
    """Run detection overlay, update ``latest_prediction``, return JPEG bytes."""
    if cv2 is None:
        return None
    gesture_detector = app.extensions["gesture_detector"]
    classifier = app.extensions["classifier"]
    translator = app.extensions["translator"]
    smoother = app.extensions.get("prediction_smoother")
    sentence_builder = app.extensions.get("sentence_builder")
    try:
        annotated, landmarks = gesture_detector.detect(frame)

        raw_label: str | None = None
        raw_confidence: float = 0.0
        smoothed_label: str | None = None
        top_candidates: list[dict[str, object]] = []

        if landmarks is not None:
            inference_start = time.perf_counter()
            details = classifier.predict_with_details(landmarks)
            inference_ms = (time.perf_counter() - inference_start) * 1000.0
            label_index = int(details.get("label_index", -1))
            raw_confidence = float(details.get("confidence", 0.0))
            raw_label = translator.get_label(label_index) if label_index >= 0 else None
            top_candidates = [
                {
                    "index": int(candidate.get("index", -1)),
                    "confidence": float(candidate.get("confidence", 0.0)),
                    "label": translator.get_label(int(candidate.get("index", -1))),
                }
                for candidate in details.get("top_candidates", [])
            ]
        elif hasattr(classifier, "reset_sequence"):
            classifier.reset_sequence()
            inference_ms = None
        else:
            inference_ms = None

        if smoother is not None:
            smoothed_label, _ = smoother.update(raw_label, raw_confidence)
        else:
            smoothed_label = raw_label

        if sentence_builder is not None:
            sentence_builder.update(smoothed_label)

        coaching = _infer_coaching(landmarks)

        prediction_payload = {
            "label": raw_label,
            "confidence": float(raw_confidence),
            "smoothed_label": smoothed_label,
            "top_candidates": top_candidates,
            "coaching": coaching,
            "sentence": sentence_builder.sentence if sentence_builder else "",
            "current_run": sentence_builder.current_run if sentence_builder else 0,
            "stable_frames": sentence_builder.stable_frames if sentence_builder else 15,
            "is_cooling_down": sentence_builder.is_cooling_down if sentence_builder else False,
            "model_type": getattr(classifier, "model_type", "unknown"),
            "inference_ms": float(inference_ms) if inference_ms is not None else None,
        }
        with _prediction_lock:
            existing_payload = dict(app.extensions.get("latest_prediction") or {})
            last_valid_confidence = float(existing_payload.get("last_valid_confidence") or 0.0)
            if raw_label and raw_confidence > 0.0:
                last_valid_confidence = float(raw_confidence)
            app.extensions["latest_prediction"] = {
                "label": raw_label,
                "confidence": float(raw_confidence),
                "last_valid_confidence": last_valid_confidence,
                "smoothed_label": smoothed_label,
                "top_candidates": list(top_candidates),
                "coaching": coaching,
                "model_type": getattr(classifier, "model_type", "unknown"),
                "inference_ms": float(inference_ms) if inference_ms is not None else None,
            }

        runtime_metrics = app.extensions.get("runtime_metrics")
        runtime_metrics_lock = app.extensions.get("runtime_metrics_lock")
        if runtime_metrics is not None:
            if runtime_metrics_lock is None:
                runtime_metrics_lock = threading.Lock()
                app.extensions["runtime_metrics_lock"] = runtime_metrics_lock
            with runtime_metrics_lock:
                runtime_metrics["prediction_events"] = int(runtime_metrics.get("prediction_events") or 0) + 1
                runtime_metrics["last_prediction_at"] = datetime.now(timezone.utc).isoformat()
                runtime_metrics["last_prediction_label"] = smoothed_label or raw_label
                runtime_metrics["last_prediction_confidence"] = float(raw_confidence)
                runtime_metrics["model_status"] = getattr(classifier, "model_type", "unknown")
                runtime_metrics["demo_mode"] = bool(classifier.is_demo_mode)
                runtime_metrics["camera_index"] = int(getattr(app.extensions.get("camera_manager"), "camera_index", 0) or 0)
                runtime_metrics["confidence_threshold"] = float(getattr(classifier, "confidence_threshold", 0.75) or 0.75)
                if inference_ms is not None:
                    samples = runtime_metrics.setdefault("inference_samples", deque(maxlen=120))
                    samples.append(float(inference_ms))

        _emit_prediction(app, prediction_payload)

        if inference_ms is not None:
            LOGGER.debug(
                "inference_ms=%.1f label=%s confidence=%.3f",
                inference_ms, raw_label, raw_confidence,
            )

        ok, encoded = cv2.imencode(
            ".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, _JPEG_QUALITY]
        )
        if not ok:
            return None
        return encoded.tobytes()
    except Exception:
        LOGGER.exception("Frame annotation/encode failed")
        return None


def _jpeg_response(data: bytes) -> Response:
    return Response(
        data,
        mimetype="image/jpeg",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
        },
    )


def _try_start_camera(camera_manager: Any) -> bool:
    """Attempt camera start, returning True on success."""
    try:
        camera_manager.start()
        return True
    except CameraUnavailableError:
        return False


def _generate_frames(app: Any) -> Iterator[bytes]:
    """Yield MJPEG byte chunks with periodic camera retry on failure."""
    with app.app_context():
        try:
            camera_manager = app.extensions["camera_manager"]
        except Exception as error:
            LOGGER.exception("video_feed: failed to read extensions: %s", error)
            for _ in range(50):
                yield _mjpeg_chunk(_placeholder_frame("Server error"))
                time.sleep(0.5)
            return

        while not _try_start_camera(camera_manager):
            LOGGER.warning("Camera unavailable for stream; retrying in %.0fs", _CAMERA_RETRY_INTERVAL_S)
            deadline = time.monotonic() + _CAMERA_RETRY_INTERVAL_S
            while time.monotonic() < deadline:
                yield _mjpeg_chunk(_placeholder_frame("Camera unavailable — retrying"))
                time.sleep(0.2)

        while True:
            loop_started = time.perf_counter()
            frame = camera_manager.get_frame()
            if frame is None or cv2 is None:
                yield _mjpeg_chunk(_placeholder_frame("Waiting for Camera"))
                time.sleep(0.05)
                continue

            jpeg = _annotate_and_encode_jpeg(app, frame)
            if jpeg is None:
                yield _mjpeg_chunk(_placeholder_frame("Processing error"))
                time.sleep(0.05)
                continue
            yield _mjpeg_chunk(jpeg)
            elapsed = time.perf_counter() - loop_started
            remaining = max(0.0, (1.0 / _TARGET_FPS) - elapsed)
            if remaining > 0.0:
                time.sleep(remaining)


def camera_frame_response() -> Response:
    """Return one JPEG frame (polling).

    Exposed as ``GET /camera_frame`` (``app.add_url_rule``) and
    ``GET /api/camera_frame``.
    ---
    tags:
      - Streaming
    summary: Poll a single annotated frame
    produces:
      - image/jpeg
    responses:
      200:
        description: JPEG snapshot for lightweight preview polling.
        schema:
          type: string
          format: binary
    """
    app = current_app._get_current_object()
    try:
        camera_manager = app.extensions["camera_manager"]
    except Exception as error:
        LOGGER.exception("camera_frame: extensions: %s", error)
        return _jpeg_response(_placeholder_frame("Server error"))

    if not camera_manager.is_streaming:
        if not _try_start_camera(camera_manager):
            return _jpeg_response(_placeholder_frame())

    frame = camera_manager.get_frame()
    if frame is None or cv2 is None:
        return _jpeg_response(_placeholder_frame("Waiting for Camera"))

    jpeg = _annotate_and_encode_jpeg(app, frame)
    if jpeg is None:
        return _jpeg_response(_placeholder_frame("Processing error"))
    return _jpeg_response(jpeg)


@stream_bp.get("/video_feed")
def video_feed() -> Response:
    """Serve live camera feed as MJPEG stream (legacy / direct clients).
    ---
    tags:
      - Streaming
    summary: Stream the live annotated camera feed
    produces:
      - multipart/x-mixed-replace; boundary=frame
    responses:
      200:
        description: Continuous MJPEG stream for browser or kiosk clients.
        schema:
          type: string
          format: binary
    """
    app = current_app._get_current_object()
    return Response(
        _generate_frames(app),
        mimetype="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
