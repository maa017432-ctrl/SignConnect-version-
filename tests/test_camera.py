"""Tests for camera manager behavior."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("numpy")

from core.camera import CameraManager, CameraUnavailableError, cv2


class _FakeCaptureClosed:
    """Fake camera that cannot be opened."""

    def isOpened(self) -> bool:
        return False

    def release(self) -> None:
        return None


class _FakeCaptureOpen:
    """Fake camera that opens and returns a valid frame."""

    def __init__(self) -> None:
        import numpy as _np

        self._frame = _np.zeros((2, 2, 3), dtype=_np.uint8)

    def isOpened(self) -> bool:
        return True

    def set(self, *_args, **_kwargs) -> bool:
        return True

    def read(self):
        return True, self._frame

    def release(self) -> None:
        return None


@pytest.mark.skipif(cv2 is None, reason="OpenCV not installed")
@patch("core.camera.cv2.VideoCapture", return_value=_FakeCaptureClosed())
def test_unavailable_camera_raises_error(_: object) -> None:
    """Raise camera unavailable error when capture cannot open."""
    manager = CameraManager()
    with pytest.raises(CameraUnavailableError):
        manager.start()


@pytest.mark.skipif(cv2 is None, reason="OpenCV not installed")
def test_is_available_without_probe_does_not_open_camera() -> None:
    """Passive availability checks should never trigger a hardware open."""
    manager = CameraManager()
    with patch("core.camera.cv2.VideoCapture", return_value=_FakeCaptureOpen()) as mocked:
        assert manager.is_available(probe_hardware=False) is False
    mocked.assert_not_called()


@pytest.mark.skipif(cv2 is None, reason="OpenCV not installed")
@patch("core.camera.cv2.VideoCapture", return_value=_FakeCaptureOpen())
def test_start_sets_cached_availability(_: object) -> None:
    """A successful start should mark camera availability in cache."""
    manager = CameraManager()
    manager.start()
    try:
        assert manager.is_available(probe_hardware=False) is True
    finally:
        manager.stop()


class TestGestureDetectorClose:
    """GestureDetector.close() must release MediaPipe native resources."""

    def test_close_calls_hands_close(self) -> None:
        """close() should call hands.close() and set hands to None."""
        from core.gesture_detector import GestureDetector

        detector = GestureDetector()
        fake_hands = MagicMock()
        detector.hands = fake_hands
        detector._available = True

        detector.close()

        fake_hands.close.assert_called_once()
        assert detector.hands is None
        assert detector._available is False

    def test_close_is_idempotent(self) -> None:
        """Calling close() twice must not raise."""
        from core.gesture_detector import GestureDetector

        detector = GestureDetector()
        detector.hands = MagicMock()
        detector.close()
        detector.close()  # second call — no exception

    def test_reinit_closes_previous_hands(self) -> None:
        """_try_init() must close the old Hands object before creating a new one."""
        from core.gesture_detector import GestureDetector

        detector = GestureDetector()
        old_hands = MagicMock()
        detector.hands = old_hands

        # _try_init with mp/cv2 unavailable will fail gracefully, but the old
        # hands object must still be closed beforehand.
        with patch("core.gesture_detector.mp", None):
            detector._try_init()

        old_hands.close.assert_called_once()
        assert detector.hands is None
