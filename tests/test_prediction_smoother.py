"""Tests for PredictionSmoother sliding-window logic."""

from __future__ import annotations

import pytest

from core.prediction_smoother import PredictionSmoother


class TestPredictionSmoother:
    def test_empty_window_returns_none(self) -> None:
        smoother = PredictionSmoother(window=5, min_fraction=0.6)
        label, frac = smoother.update(None, 0.0)
        assert label is None
        assert frac == 0.0

    def test_single_label_dominance(self) -> None:
        smoother = PredictionSmoother(window=5, min_fraction=0.6)
        for _ in range(5):
            label, _ = smoother.update("hello", 0.9)
        assert label == "hello"

    def test_label_below_threshold(self) -> None:
        smoother = PredictionSmoother(window=10, min_fraction=0.6)
        smoother.update("hello", 0.9)
        smoother.update("world", 0.9)
        smoother.update("hello", 0.9)
        label, _ = smoother.update("world", 0.9)
        assert label is None

    def test_window_decays_with_none(self) -> None:
        smoother = PredictionSmoother(window=5, min_fraction=0.6)
        for _ in range(5):
            smoother.update("hello", 0.9)
        label, _ = smoother.update("hello", 0.9)
        assert label == "hello"

        for _ in range(5):
            smoother.update(None, 0.0)
        label, _ = smoother.update(None, 0.0)
        assert label is None

    def test_reset_clears_window(self) -> None:
        smoother = PredictionSmoother(window=5, min_fraction=0.6)
        for _ in range(5):
            smoother.update("hello", 0.9)
        smoother.reset()
        smoother.update("hello", 0.9)
        smoother.update(None, 0.0)
        label, _ = smoother.update(None, 0.0)
        assert label is None

    def test_invalid_min_fraction_raises(self) -> None:
        with pytest.raises(ValueError):
            PredictionSmoother(window=5, min_fraction=0.0)
        with pytest.raises(ValueError):
            PredictionSmoother(window=5, min_fraction=1.5)

    def test_window_size_property(self) -> None:
        smoother = PredictionSmoother(window=8, min_fraction=0.5)
        assert smoother.window_size == 8

    def test_competing_labels_picks_most_common(self) -> None:
        smoother = PredictionSmoother(window=5, min_fraction=0.5)
        smoother.update("a", 0.9)
        smoother.update("a", 0.9)
        smoother.update("a", 0.9)
        smoother.update("b", 0.9)
        label, _ = smoother.update("b", 0.9)
        assert label == "a"
