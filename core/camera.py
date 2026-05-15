"""Camera lifecycle management for SignConnect."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Optional

import numpy as np

try:
    import cv2
except ImportError:  # pragma: no cover - depends on runtime environment
    cv2 = None


LOGGER = logging.getLogger(__name__)


class CameraUnavailableError(RuntimeError):
    """Raised when the camera device cannot be initialized."""


class CameraManager:
    """Thread-safe camera manager with non-blocking frame capture loop."""

    _INDICES = (0, 1, 2)
    _WARMUP_READS = 3

    def __init__(self, camera_index: int = 0) -> None:
        self.camera_index = camera_index
        self._capture: Optional[Any] = None
        self._active_camera_index: Optional[int] = None
        self._lock = threading.Lock()
        self._running = False
        self._initializing = False
        self._thread: Optional[threading.Thread] = None
        self._latest_frame: Optional[np.ndarray] = None
        self._hw_probe_time: float = 0.0
        self._hw_probe_cache: Optional[bool] = None
        self._hw_probe_ttl_seconds: float = 30.0
        self._read_failures: int = 0
        self._last_read_warning_at: float = 0.0

    @property
    def _camera_index(self) -> Optional[int]:
        """Camera device index that succeeded during open (task-named property)."""
        return self._active_camera_index

    @property
    def active_camera_index(self) -> Optional[int]:
        """Camera index currently active for capture."""
        return self._active_camera_index

    def _probe_order(self, preferred_index: Optional[int]) -> list[int]:
        indices = list(self._INDICES)
        if preferred_index is None or preferred_index < 0:
            return indices
        if preferred_index in indices:
            return [preferred_index] + [idx for idx in indices if idx != preferred_index]
        return [preferred_index] + indices

    def _try_open_camera(
        self, preferred_index: Optional[int] = None
    ) -> tuple[Optional[Any], Optional[int]]:
        """Try preferred index first, then known fallback indices.

        The capture object is configured for 640x480 @ 30 FPS and warmed up
        with several discarded reads.  Returns ``(None, None)`` if no camera
        index produces a valid frame.
        """
        if cv2 is None:
            return None, None
        for index in self._probe_order(preferred_index):
            cap = cv2.VideoCapture(index)
            if not cap.isOpened():
                cap.release()
                continue
            try:
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                cap.set(cv2.CAP_PROP_FPS, 30)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                for _ in range(self._WARMUP_READS):
                    cap.read()
                ok, frame = cap.read()
                if ok and frame is not None and frame.size > 0:
                    LOGGER.info("Camera opened on index %s", index)
                    return cap, index
            except Exception as error:
                LOGGER.warning("Camera probe failed on index %s: %s", index, error)
            cap.release()
        return None, None

    def _try_init(self) -> bool:
        """Open the first usable camera and store it on the instance.

        Returns:
            True if a capture is stored on ``self._capture`` and index set.
        """
        cap, index = self._try_open_camera(self.camera_index)
        if cap is not None:
            self._capture = cap
            self._active_camera_index = index
            return True
        self._capture = None
        self._active_camera_index = None
        return False

    def start(self) -> None:
        """Start camera capture in a daemon thread."""
        if cv2 is None:
            raise CameraUnavailableError("OpenCV is not installed")
        with self._lock:
            if self._running or self._initializing:
                return
            self._initializing = True
        try:
            if not self._try_init():
                raise CameraUnavailableError("Camera not found or busy")
            with self._lock:
                if self._running:
                    return
                self._running = True
                self._read_failures = 0
                self._last_read_warning_at = 0.0
                self._thread = threading.Thread(target=self._capture_loop, daemon=True)
                self._thread.start()
                LOGGER.info("Camera capture started")
        finally:
            with self._lock:
                self._initializing = False

    def _capture_loop(self) -> None:
        """Continuously read frames to keep latest frame available."""
        while self._running:
            if self._capture is None:
                break
            ok, frame = self._capture.read()
            if ok and frame is not None:
                with self._lock:
                    self._latest_frame = frame.copy()
                    self._read_failures = 0
            else:
                now = time.monotonic()
                with self._lock:
                    self._read_failures += 1
                    failures = self._read_failures
                    should_log = (now - self._last_read_warning_at) >= 5.0
                    if should_log:
                        self._last_read_warning_at = now
                if should_log:
                    LOGGER.warning("Frame read failed; retrying")
                if failures >= 20 and self._running:
                    LOGGER.warning("Camera read failed repeatedly; attempting recovery")
                    if self._capture is not None:
                        try:
                            self._capture.release()
                        except Exception:
                            LOGGER.debug("Camera release during recovery failed", exc_info=True)
                        self._capture = None
                    if not self._try_init():
                        time.sleep(0.2)
                        continue
                    with self._lock:
                        self._read_failures = 0
                time.sleep(0.05)
            time.sleep(0.01)  # ~100fps cap, reduces CPU usage

    def stop(self) -> None:
        """Stop capture thread and release camera resource safely."""
        with self._lock:
            self._running = False
            if self._capture is not None:
                self._capture.release()
                self._capture = None
            self._latest_frame = None
            self._active_camera_index = None
            self._read_failures = 0
            self._last_read_warning_at = 0.0
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.5)

    def set_camera_index(self, camera_index: int) -> None:
        """Apply a new preferred camera index and restart capture if needed."""
        try:
            normalized_index = int(camera_index)
        except (TypeError, ValueError) as error:
            raise CameraUnavailableError("Invalid camera index") from error

        was_streaming = self.is_streaming
        previous_index = self.camera_index
        self.camera_index = normalized_index
        self._hw_probe_cache = None
        self._hw_probe_time = 0.0

        if not was_streaming:
            return

        self.stop()
        try:
            self.start()
        except CameraUnavailableError:
            self.camera_index = previous_index
            self._hw_probe_cache = None
            self._hw_probe_time = 0.0
            self.start()
            raise

    def get_frame(self) -> Optional[np.ndarray]:
        """Return a copy of the latest frame if available."""
        with self._lock:
            if self._latest_frame is None:
                return None
            return self._latest_frame.copy()

    def _probe_hardware_available(self) -> bool:
        """Return True if some camera index can produce a frame."""
        cap, _ = self._try_open_camera()
        if cap is not None:
            cap.release()
            return True
        return False

    @property
    def is_streaming(self) -> bool:
        """True when capture thread is active and a device is open."""
        with self._lock:
            return self._running and self._capture is not None

    def is_available(self, probe_hardware: bool = False) -> bool:
        """True if capture is running, or (optionally) hardware probe succeeds."""
        with self._lock:
            if self._running and self._capture is not None:
                return True
        if not probe_hardware:
            return False
        now = time.time()
        if (
            self._hw_probe_cache is not None
            and (now - self._hw_probe_time) < self._hw_probe_ttl_seconds
        ):
            return self._hw_probe_cache
        self._hw_probe_cache = self._probe_hardware_available()
        self._hw_probe_time = now
        return self._hw_probe_cache
