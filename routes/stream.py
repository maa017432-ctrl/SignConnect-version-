"""Video stream and camera frame routes."""

from __future__ import annotations

import logging
import os
import threading
import time
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

        display_label = smoothed_label or raw_label
        if display_label and landmarks is not None:
            cv2.putText(
                annotated,
                f"{display_label} ({raw_confidence:.2f})",
                (10, 40),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.0,
                (40, 220, 40) if smoothed_label else (180, 180, 60),
                2,
            )

        if sentence_builder is not None and sentence_builder.current_label:
            progress = min(
                1.0, sentence_builder.current_run / sentence_builder.stable_frames
            )
            bar_w = int(annotated.shape[1] * progress)
            h = annotated.shape[0]
            cv2.rectangle(annotated, (0, h - 6), (bar_w, h), (40, 220, 40), -1)

        prediction_payload = {
            "label": raw_label,
            "confidence": float(raw_confidence),
            "smoothed_label": smoothed_label,
            "top_candidates": top_candidates,
            "sentence": sentence_builder.sentence if sentence_builder else "",
            "current_run": sentence_builder.current_run if sentence_builder else 0,
            "stable_frames": sentence_builder.stable_frames if sentence_builder else 15,
            "is_cooling_down": sentence_builder.is_cooling_down if sentence_builder else False,
            "model_type": getattr(classifier, "model_type", "unknown"),
            "inference_ms": float(inference_ms) if inference_ms is not None else None,
        }
        with _prediction_lock:
            app.extensions["latest_prediction"] = {
                "label": raw_label,
                "confidence": float(raw_confidence),
                "smoothed_label": smoothed_label,
                "top_candidates": list(top_candidates),
                "model_type": getattr(classifier, "model_type", "unknown"),
                "inference_ms": float(inference_ms) if inference_ms is not None else None,
            }

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
            time.sleep(1.0 / _TARGET_FPS)


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
