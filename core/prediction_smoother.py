"""Temporal prediction smoothing and sentence accumulation for SignConnect."""

from __future__ import annotations

import logging
from collections import Counter, deque
from typing import Optional


LOGGER = logging.getLogger(__name__)


class PredictionSmoother:
    """Reduce flickering by requiring a label to dominate a sliding window.

    Raw per-frame classifier output is noisy — hands move between gestures,
    lighting changes, and brief occlusions all cause single-frame mislabels.
    This class maintains a fixed-length sliding window of recent labels and
    only emits a label once it constitutes at least ``min_fraction`` of the
    window, suppressing transient noise.

    Args:
        window: Number of recent frames to keep in the window.
        min_fraction: Fraction of window slots the winning label must occupy
            before it is considered stable (0 < min_fraction ≤ 1).
    """

    def __init__(self, window: int = 10, min_fraction: float = 0.6) -> None:
        if not (0 < min_fraction <= 1):
            raise ValueError("min_fraction must be in (0, 1]")
        self._window: deque[str] = deque(maxlen=window)
        self._min_fraction = min_fraction

    # ── Public interface ───────────────────────────────────────────────────

    def update(
        self, label: Optional[str], confidence: float
    ) -> tuple[Optional[str], float]:
        """Feed a raw frame prediction and return the smoothed result.

        Args:
            label: Raw predicted label string, or ``None`` when the classifier
                returns below-threshold confidence (label_index < 0).
            confidence: Raw confidence score [0, 1] from the classifier.

        Returns:
            ``(smoothed_label, dominant_fraction)`` where ``smoothed_label``
            is ``None`` when no label clears the minimum fraction threshold.
        """
        # Inject empty string as "no gesture" vote so the window decays when
        # the hand disappears rather than getting stuck on the last label.
        slot = label if label is not None else ""
        self._window.append(slot)

        counts = Counter(lbl for lbl in self._window if lbl)
        if not counts:
            return None, 0.0

        most_common, count = counts.most_common(1)[0]
        fraction = count / len(self._window)

        if fraction >= self._min_fraction:
            return most_common, fraction
        return None, 0.0

    def reset(self) -> None:
        """Clear the sliding window entirely."""
        self._window.clear()

    @property
    def window_size(self) -> int:
        """Maximum number of frames in the sliding window."""
        return self._window.maxlen  # type: ignore[return-value]


class SentenceBuilder:
    """Accumulate stable smoothed predictions into a growing sentence.

    A label is "committed" (appended to the sentence) only after it appears
    as the dominant smoothed output for ``stable_frames`` consecutive frames.
    A per-word cooldown prevents the same gesture from being repeated
    immediately — the user must briefly lower their hand before the next word.

    Args:
        stable_frames: Consecutive frames a smoothed label must persist before
            the word is committed to the sentence.
        cooldown_frames: Frames to ignore new commits after a word is appended
            (prevents a held gesture from spamming the same word).
        max_words: Hard cap on sentence length to avoid unbounded growth.
    """

    def __init__(
        self,
        stable_frames: int = 15,
        cooldown_frames: int = 20,
        max_words: int = 30,
    ) -> None:
        self._stable_frames = stable_frames
        self._cooldown_frames = cooldown_frames
        self._max_words = max_words

        self._words: list[str] = []
        self._current_label: Optional[str] = None
        self._current_run: int = 0
        self._cooldown: int = 0
        self._last_committed: Optional[str] = None

    # ── Public interface ───────────────────────────────────────────────────

    def update(self, smoothed_label: Optional[str]) -> bool:
        """Feed the current smoothed label; return True when a word is added.

        Args:
            smoothed_label: Output from :meth:`PredictionSmoother.update`.

        Returns:
            True on the frame that a new word is appended to the sentence.
        """
        if self._cooldown > 0:
            self._cooldown -= 1
            return False

        if not smoothed_label:
            self._current_label = None
            self._current_run = 0
            return False

        if smoothed_label == self._current_label:
            self._current_run += 1
        else:
            self._current_label = smoothed_label
            self._current_run = 1

        if (
            self._current_run >= self._stable_frames
            and smoothed_label != self._last_committed
            and len(self._words) < self._max_words
        ):
            self._words.append(smoothed_label)
            self._last_committed = smoothed_label
            self._cooldown = self._cooldown_frames
            self._current_run = 0
            LOGGER.info("Word committed: %r → sentence: %r", smoothed_label, self.sentence)
            return True

        return False

    @property
    def sentence(self) -> str:
        """Current sentence as a space-separated string."""
        return " ".join(self._words)

    @property
    def words(self) -> list[str]:
        """Current word list (shallow copy)."""
        return list(self._words)

    @property
    def current_label(self) -> Optional[str]:
        """Label currently being tracked (not yet committed)."""
        return self._current_label

    @property
    def current_run(self) -> int:
        """Consecutive frames the current label has been the dominant output."""
        return self._current_run

    @property
    def stable_frames(self) -> int:
        """Frames required before a word is committed."""
        return self._stable_frames

    @property
    def is_cooling_down(self) -> bool:
        """True while the post-commit cooldown is active."""
        return self._cooldown > 0

    def delete_last_word(self) -> Optional[str]:
        """Remove and return the last committed word, or None if empty."""
        if not self._words:
            return None
        word = self._words.pop()
        self._last_committed = self._words[-1] if self._words else None
        return word

    def clear(self) -> None:
        """Reset the entire sentence and all internal tracking state."""
        self._words.clear()
        self._current_label = None
        self._current_run = 0
        self._cooldown = 0
        self._last_committed = None
