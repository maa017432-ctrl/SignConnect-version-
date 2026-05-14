"""
Generates a real (untrained) model with the correct input/output shape.
Input: (126,) — 2 hands × 21 MediaPipe landmarks × 3 coords (x/y/z)
Output: number of classes from label_map.json
Saves to: models/gesture_model.h5
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tensorflow import keras

from model_contract import MODEL_INPUT_DIM

label_path = ROOT / "models" / "label_map.json"
out_path = ROOT / "models" / "gesture_model.h5"
marker_path = ROOT / "models" / "gesture_model.demo"

INPUT_DIM = MODEL_INPUT_DIM

with label_path.open(encoding="utf-8") as f:
    label_map = json.load(f)
num_classes = len(label_map)

reg = keras.regularizers.l2(1e-4)
model = keras.Sequential(
    [
        keras.layers.Input(shape=(INPUT_DIM,)),
        keras.layers.Dense(256, activation="relu", kernel_regularizer=reg),
        keras.layers.BatchNormalization(),
        keras.layers.Dropout(0.4),
        keras.layers.Dense(256, activation="relu", kernel_regularizer=reg),
        keras.layers.BatchNormalization(),
        keras.layers.Dropout(0.3),
        keras.layers.Dense(128, activation="relu", kernel_regularizer=reg),
        keras.layers.BatchNormalization(),
        keras.layers.Dropout(0.2),
        keras.layers.Dense(num_classes, activation="softmax"),
    ],
    name="signconnect_gesture_classifier",
)

model.compile(
    optimizer="adam",
    loss="sparse_categorical_crossentropy",
    metrics=["accuracy"],
)

model.summary()
model.save(str(out_path))
marker_path.write_text(
    "Generated placeholder model. Replace with a trained model and remove this marker.\n",
    encoding="utf-8",
)
print(f"\nOK: Model saved to {out_path}")
print(f"   Demo marker: {marker_path}")
print(f"   Input shape: ({INPUT_DIM},) — 2 hands × 21 landmarks × 3 coords")
print(f"   Output classes: {num_classes}")
