"""Integration tests for the full prediction pipeline."""

from __future__ import annotations

import pytest

np = pytest.importorskip("numpy")

from core.ai_model import GestureClassifier
from core.prediction_smoother import PredictionSmoother, SentenceBuilder
from core.translator import Translator


@pytest.fixture(autouse=True)
def reset_classifier_singleton():
    """Each test gets a fresh ``GestureClassifier`` (no singleton to reset)."""
    yield


class TestFullPipeline:
    """End-to-end flow: landmarks -> classifier -> translator -> smoother -> sentence."""

    def test_demo_mode_pipeline(self) -> None:
        classifier = GestureClassifier(
            model_path="nonexistent.h5",
            confidence_threshold=0.7,
            labels_count=38,
        )
        translator = Translator(label_map_path="models/label_map.json")
        smoother = PredictionSmoother(window=5, min_fraction=0.5)
        builder = SentenceBuilder(stable_frames=3, cooldown_frames=0, max_words=10)

        assert classifier.is_demo_mode

        landmarks = np.random.rand(126).astype(np.float32)
        details = classifier.predict_with_details(landmarks)

        assert "label_index" in details
        assert "confidence" in details
        assert "top_candidates" in details

        label_index = int(details["label_index"])
        confidence = float(details["confidence"])

        if label_index >= 0:
            label_text = translator.get_label(label_index)
            assert isinstance(label_text, str)
        else:
            label_text = None

        smoothed, _ = smoother.update(label_text, confidence)

    def test_classifier_handles_empty_landmarks(self) -> None:
        classifier = GestureClassifier(
            model_path="nonexistent.h5",
            confidence_threshold=0.7,
            labels_count=10,
        )
        details = classifier.predict_with_details(np.array([]))
        assert details["label_index"] == -1
        assert details["confidence"] == 0.0

    def test_classifier_handles_none_landmarks(self) -> None:
        classifier = GestureClassifier(
            model_path="nonexistent.h5",
            confidence_threshold=0.7,
            labels_count=10,
        )
        details = classifier.predict_with_details(None)
        assert details["label_index"] == -1

    def test_translator_unknown_index(self) -> None:
        translator = Translator(label_map_path="models/label_map.json")
        assert translator.get_label(99999) == "Unknown"

    def test_prepare_features_63_dim(self) -> None:
        classifier = GestureClassifier(
            model_path="nonexistent.h5",
            confidence_threshold=0.7,
            labels_count=10,
        )
        landmarks = np.random.rand(63).astype(np.float32)
        features = classifier._prepare_features(landmarks)
        assert features.shape == (1, 126)

    def test_prepare_features_126_dim(self) -> None:
        classifier = GestureClassifier(
            model_path="nonexistent.h5",
            confidence_threshold=0.7,
            labels_count=10,
        )
        landmarks = np.random.rand(126).astype(np.float32)
        features = classifier._prepare_features(landmarks)
        assert features.shape == (1, 126)

    def test_smoother_to_sentence_flow(self) -> None:
        smoother = PredictionSmoother(window=3, min_fraction=0.6)
        builder = SentenceBuilder(stable_frames=2, cooldown_frames=0, max_words=5)

        for _ in range(3):
            smoothed, _ = smoother.update("hello", 0.9)

        assert smoothed == "hello"

        builder.update(smoothed)
        committed = builder.update(smoothed)
        assert committed is True
        assert builder.sentence == "hello"
