"""Tests for model prediction thresholds."""

from __future__ import annotations

from unittest.mock import patch

import pytest

np = pytest.importorskip("numpy")
from core.ai_model import GestureClassifier


@pytest.fixture(autouse=True)
def reset_gesture_classifier_singleton() -> None:
    """Each test gets a fresh ``GestureClassifier`` (no singleton to reset)."""
    yield


class _FakeModel:
    def __init__(self, input_shape=(None, 126), output_shape=(None, 31)) -> None:
        self.input_shape = input_shape
        self.output_shape = output_shape


def test_predict_with_dummy_input() -> None:
    """Prediction should return tuple with label index and confidence."""
    classifier = GestureClassifier(
        model_path="missing-model.h5",
        confidence_threshold=0.75,
        labels_count=31,
    )
    label, confidence = classifier.predict(np.random.rand(63).astype(np.float32))
    assert isinstance(label, int)
    assert isinstance(confidence, float)


def test_confidence_threshold_rejection() -> None:
    """Demo mode returns synthetic scores in [0.76, 0.95] (threshold not applied)."""
    classifier = GestureClassifier(
        model_path="missing-model.h5",
        confidence_threshold=0.95,
        labels_count=31,
    )
    label, confidence = classifier.predict(np.random.rand(63).astype(np.float32))
    assert classifier.is_demo_mode
    assert 0.76 <= confidence <= 0.95
    assert label >= 0


def test_classifier_instances_are_independent_with_different_configs(caplog) -> None:
    first = GestureClassifier(
        model_path="missing-model.h5",
        confidence_threshold=0.75,
        labels_count=31,
    )
    second = GestureClassifier(
        model_path="other-model.h5",
        confidence_threshold=0.5,
        labels_count=12,
    )

    assert first is not second
    assert first.model_path.name == "missing-model.h5"
    assert second.model_path.name == "other-model.h5"
    assert first.confidence_threshold == 0.75
    assert second.confidence_threshold == 0.5
    assert not first.is_available
    assert first.is_demo_mode
    assert not second.is_available
    assert second.is_demo_mode
    assert "singleton already initialized" not in caplog.text


def test_loaded_model_contract_match_is_available(tmp_path) -> None:
    model_path = tmp_path / "model.h5"
    model_path.write_text("placeholder", encoding="utf-8")

    with patch("core.ai_model.load_model", return_value=_FakeModel()):
        classifier = GestureClassifier(
            model_path=str(model_path),
            confidence_threshold=0.75,
            labels_count=31,
        )

    assert classifier.is_available
    assert not classifier.is_demo_mode


def test_loaded_model_output_mismatch_falls_back_to_demo(tmp_path) -> None:
    model_path = tmp_path / "model.h5"
    model_path.write_text("placeholder", encoding="utf-8")

    with patch("core.ai_model.load_model", return_value=_FakeModel(output_shape=(None, 30))):
        classifier = GestureClassifier(
            model_path=str(model_path),
            confidence_threshold=0.75,
            labels_count=31,
        )

    assert not classifier.is_available
    assert classifier.is_demo_mode


def test_loaded_model_input_mismatch_falls_back_to_demo(tmp_path) -> None:
    model_path = tmp_path / "model.h5"
    model_path.write_text("placeholder", encoding="utf-8")

    with patch("core.ai_model.load_model", return_value=_FakeModel(input_shape=(None, 64))):
        classifier = GestureClassifier(
            model_path=str(model_path),
            confidence_threshold=0.75,
            labels_count=31,
        )

    assert not classifier.is_available
    assert classifier.is_demo_mode
