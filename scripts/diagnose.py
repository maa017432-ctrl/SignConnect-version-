"""One-shot diagnostics for environment, camera, MediaPipe, TensorFlow, and model file."""

from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from model_contract import (
    MODEL_INPUT_DIM,
    SEQUENCE_LENGTH,
    TEMPORAL_MODEL_TYPE,
    model_input_dim,
    model_output_count,
    model_sequence_length,
)


def _import_module(name: str):
    """Import a runtime dependency and report a readable error on failure."""
    try:
        return importlib.import_module(name)
    except Exception as error:
        print(f"{name} import FAILED: {error}")
        return None


print(f"Python: {sys.version}")
print(f"Executable: {sys.executable}")
print(f"Expected model input dim: {MODEL_INPUT_DIM}")
print(f"Expected temporal sequence length: {SEQUENCE_LENGTH}")
print(f"MODEL_TYPE env: {os.getenv('MODEL_TYPE', 'mlp')}")
print(f"SEQUENCE_LENGTH env: {os.getenv('SEQUENCE_LENGTH', str(SEQUENCE_LENGTH))}")

cv2 = _import_module("cv2")
if cv2 is not None:
    cap = cv2.VideoCapture(0)
    print(f"Camera opened: {cap.isOpened()}")
    if cap.isOpened():
        ret, frame = cap.read()
        print(f"Frame read: {ret}, shape: {frame.shape if ret else 'N/A'}")
    cap.release()

mp = _import_module("mediapipe")
if mp is not None:
    print(f"MediaPipe version: {getattr(mp, '__version__', 'unknown')}")
    try:
        hands = mp.solutions.hands.Hands()
        print("MediaPipe Hands: OK")
        hands.close()
    except Exception as error:
        print(f"MediaPipe Hands FAILED: {error}")

protobuf = _import_module("google.protobuf")
if protobuf is not None:
    print(f"protobuf version: {getattr(protobuf, '__version__', 'unknown')}")

tf = _import_module("tensorflow")
if tf is not None:
    print(f"TensorFlow version: {tf.__version__}")
    model_path = PROJECT_ROOT / "models" / "gesture_model.h5"
    label_map_path = PROJECT_ROOT / "models" / "label_map.json"
    norm_stats_path = PROJECT_ROOT / "models" / "norm_stats.npz"
    demo_marker_path = PROJECT_ROOT / "models" / "gesture_model.demo"
    print(f"Model file exists: {model_path.exists()}")
    print(f"Model file size: {model_path.stat().st_size if model_path.exists() else 'N/A'} bytes")
    print(f"Norm stats exists: {norm_stats_path.exists()}")
    print(f"Demo marker exists: {demo_marker_path.exists()}")
    try:
        with label_map_path.open(encoding="utf-8") as file_obj:
            label_count = len(json.load(file_obj))
    except Exception:
        label_count = None
    try:
        model = tf.keras.models.load_model(str(model_path))
        input_dim = model_input_dim(model.input_shape)
        output_count = model_output_count(model.output_shape)
        sequence_length = model_sequence_length(model.input_shape)
        print(f"Model loaded: OK - input shape: {model.input_shape}")
        print(f"Model output shape: {model.output_shape}")
        print(f"Input contract OK: {input_dim == MODEL_INPUT_DIM}")
        print(
            "Temporal contract OK: "
            f"{sequence_length == SEQUENCE_LENGTH if sequence_length is not None else 'N/A'}"
        )
        print(f"Output-label contract OK: {output_count == label_count}")
        metrics_path = PROJECT_ROOT / "models" / "temporal_metrics.json"
        if metrics_path.exists():
            with metrics_path.open(encoding="utf-8") as file_obj:
                metrics = json.load(file_obj)
            print(f"Metrics model type: {metrics.get('model_type', TEMPORAL_MODEL_TYPE)}")
            print(f"Metrics classes: {metrics.get('classes', 'N/A')}")
            print(f"Metrics samples: {metrics.get('samples', 'N/A')}")
            print(f"Metrics sequence_length: {metrics.get('sequence_length', 'N/A')}")
            print(f"Eval top-1 accuracy: {metrics.get('eval_top1_accuracy', 'N/A')}")
            print(f"Eval top-5 accuracy: {metrics.get('eval_top5_accuracy', 'N/A')}")
            print(f"Metrics-label contract OK: {metrics.get('classes') == label_count}")
    except Exception as error:
        print(f"Model load FAILED: {error}")
