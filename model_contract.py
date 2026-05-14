"""Shared model/data contract constants for SignConnect."""

from __future__ import annotations

from typing import Any

HAND_DIM = 63
FRAME_FEATURE_DIM = 126
MODEL_INPUT_DIM = FRAME_FEATURE_DIM
SEQUENCE_LENGTH = 30
DEFAULT_MODEL_TYPE = "mlp"
TEMPORAL_MODEL_TYPE = "temporal_landmark"
SUPPORTED_MODEL_TYPES = (DEFAULT_MODEL_TYPE, TEMPORAL_MODEL_TYPE)


def _last_dim(shape: Any) -> int | None:
    """Return the final concrete dimension from a Keras-like shape object."""
    if shape is None:
        return None
    if isinstance(shape, list):
        shape = shape[0] if shape else None
    if shape is None:
        return None
    try:
        value = shape[-1]
    except (TypeError, IndexError):
        return None
    return int(value) if value is not None else None


def model_input_dim(input_shape: Any) -> int | None:
    """Return the feature dimension expected by a loaded model."""
    return _last_dim(input_shape)


def model_output_count(output_shape: Any) -> int | None:
    """Return the number of output classes from a loaded model."""
    return _last_dim(output_shape)


def model_sequence_length(input_shape: Any) -> int | None:
    """Return the concrete temporal sequence length from a Keras-like shape."""
    if shape := input_shape:
        if isinstance(shape, list):
            shape = shape[0] if shape else None
        try:
            value = shape[1]
        except (TypeError, IndexError):
            return None
        return int(value) if value is not None else None
    return None
