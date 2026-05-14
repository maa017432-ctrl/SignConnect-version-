"""Temporal sequence buffer for motion-based gesture recognition."""

from __future__ import annotations

import logging
from collections import deque
from typing import Optional

import numpy as np


LOGGER = logging.getLogger(__name__)


class SequenceBuffer:
    """Accumulate landmark frames into fixed-length sequences for LSTM inference.

    The buffer collects ``seq_length`` consecutive landmark vectors. Once full,
    ``get_sequence`` returns the stacked array and the buffer slides forward,
    keeping ``seq_length - stride`` old frames.

    Args:
        seq_length: Number of frames per sequence window.
        feature_dim: Expected landmark vector size per frame (126 for two-hand).
        stride: How many frames to advance after each full sequence (default 1).
    """

    def __init__(
        self, seq_length: int = 15, feature_dim: int = 126, stride: int = 1,
    ) -> None:
        self._seq_length = seq_length
        self._feature_dim = feature_dim
        self._stride = max(1, stride)
        self._buffer: deque[np.ndarray] = deque(maxlen=seq_length)
        self._frames_since_output = 0

    @property
    def seq_length(self) -> int:
        return self._seq_length

    @property
    def is_ready(self) -> bool:
        """True when the buffer has accumulated enough frames."""
        return (
            len(self._buffer) >= self._seq_length
            and self._frames_since_output >= self._stride
        )

    def push(self, landmarks: Optional[np.ndarray]) -> None:
        """Add a frame's landmarks (or zeros for missing-hand frames)."""
        if landmarks is None or landmarks.size == 0:
            vec = np.zeros(self._feature_dim, dtype=np.float32)
        else:
            vec = landmarks.astype(np.float32).reshape(-1)
            if vec.size < self._feature_dim:
                vec = np.pad(vec, (0, self._feature_dim - vec.size), mode="constant")
            elif vec.size > self._feature_dim:
                vec = vec[: self._feature_dim]
        self._buffer.append(vec)
        self._frames_since_output += 1

    def get_sequence(self) -> Optional[np.ndarray]:
        """Return ``(1, seq_length, feature_dim)`` array or None if not ready."""
        if not self.is_ready:
            return None
        self._frames_since_output = 0
        seq = np.stack(list(self._buffer), axis=0).astype(np.float32)
        return seq.reshape(1, self._seq_length, self._feature_dim)

    def reset(self) -> None:
        """Clear all accumulated frames."""
        self._buffer.clear()
        self._frames_since_output = 0
