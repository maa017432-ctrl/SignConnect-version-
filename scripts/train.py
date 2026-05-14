"""
Train the SignConnect gesture classifier from collected landmark data.

Run from the signconnect folder:
    .venv311\\Scripts\\python scripts\\train.py

Reads:  data/landmarks.csv           (produced by collect_data.py)
Writes: models/gesture_model.h5      (replaces placeholder / previous model)
        models/label_map.json         (updated with training labels)

The script prints a final accuracy report and saves the best weights found
during training (not just the last epoch).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from model_contract import HAND_DIM, MODEL_INPUT_DIM

# ── Dependency checks ──────────────────────────────────────────────────────
try:
    import numpy as np
except ImportError:
    sys.exit("ERROR: numpy not installed. Run: pip install numpy")

try:
    import pandas as pd
except ImportError:
    sys.exit("ERROR: pandas not installed. Run: pip install pandas")

try:
    import tensorflow as tf
    from tensorflow import keras
except ImportError:
    sys.exit("ERROR: tensorflow not installed. Run: pip install tensorflow==2.15.1")

# ── Paths ──────────────────────────────────────────────────────────────────
DATA_CSV     = PROJECT_ROOT / "data" / "landmarks.csv"
MODEL_OUT    = PROJECT_ROOT / "models" / "gesture_model.h5"
LABEL_MAP_OUT= PROJECT_ROOT / "models" / "label_map.json"

# ── Model architecture (must match ai_model.py expectations) ───────────────
INPUT_DIM = MODEL_INPUT_DIM  # 2 hands × 21 landmarks × 3 coords (x, y, z)
ALPHABET_LABELS = {chr(code) for code in range(ord("A"), ord("Z") + 1)} | {
    chr(code) for code in range(ord("a"), ord("z") + 1)
}


def build_model(num_classes: int, dropout_rate: float = 0.4) -> keras.Sequential:
    """Build the MLP classifier.

    Architecture:
        Input(126) → Dense(256, ReLU) → BN → Dropout(0.4)
                 → Dense(256, ReLU) → BN → Dropout(0.3)
                 → Dense(128, ReLU) → BN → Dropout(0.2)
                 → Dense(num_classes, Softmax)
    """
    reg = keras.regularizers.l2(1e-4)
    model = keras.Sequential(
        [
            keras.layers.Input(shape=(INPUT_DIM,), name="landmarks"),
            keras.layers.Dense(
                256, activation="relu", kernel_regularizer=reg, name="hidden_1",
            ),
            keras.layers.BatchNormalization(name="bn_1"),
            keras.layers.Dropout(dropout_rate, name="drop_1"),
            keras.layers.Dense(
                256, activation="relu", kernel_regularizer=reg, name="hidden_2",
            ),
            keras.layers.BatchNormalization(name="bn_2"),
            keras.layers.Dropout(max(0.1, dropout_rate - 0.1), name="drop_2"),
            keras.layers.Dense(
                128, activation="relu", kernel_regularizer=reg, name="hidden_3",
            ),
            keras.layers.BatchNormalization(name="bn_3"),
            keras.layers.Dropout(max(0.1, dropout_rate - 0.2), name="drop_3"),
            keras.layers.Dense(num_classes, activation="softmax", name="output"),
        ],
        name="signconnect_gesture_classifier",
    )
    return model


def build_lstm_model(
    num_classes: int, seq_length: int = 15, feature_dim: int = INPUT_DIM,
    dropout_rate: float = 0.3,
) -> keras.Model:
    """Build an LSTM-based temporal classifier for motion gestures.

    Architecture:
        Input(seq_length, feature_dim)
          -> LSTM(128, return_sequences=True) -> Dropout
          -> LSTM(64)                         -> Dropout
          -> Dense(64, ReLU) -> Dropout
          -> Dense(num_classes, Softmax)
    """
    reg = keras.regularizers.l2(1e-4)
    model = keras.Sequential(
        [
            keras.layers.Input(shape=(seq_length, feature_dim), name="landmark_seq"),
            keras.layers.LSTM(128, return_sequences=True, kernel_regularizer=reg, name="lstm_1"),
            keras.layers.Dropout(dropout_rate, name="drop_lstm_1"),
            keras.layers.LSTM(64, kernel_regularizer=reg, name="lstm_2"),
            keras.layers.Dropout(dropout_rate, name="drop_lstm_2"),
            keras.layers.Dense(64, activation="relu", kernel_regularizer=reg, name="hidden_1"),
            keras.layers.Dropout(dropout_rate / 2, name="drop_3"),
            keras.layers.Dense(num_classes, activation="softmax", name="output"),
        ],
        name="signconnect_temporal_classifier",
    )
    return model


def load_dataset(
    csv_path: Path,
    min_samples_per_class: int,
    max_classes: int,
    include_labels: set[str] | None,
) -> tuple[np.ndarray, np.ndarray, dict[int, str], dict[str, int]]:
    """Load CSV, encode labels, return (X, y, label_map).

    Returns:
        X         — float32 array of shape (N, 63)
        y         — int32 integer class indices of shape (N,)
        label_map — {int_index: label_string} mapping (for label_map.json)
        class_counts — {"label": count} for filtered dataset

    Raises:
        SystemExit: If the CSV is missing, empty, or malformed.
    """
    if not csv_path.exists():
        sys.exit(
            f"ERROR: {csv_path} not found.\n"
            "Run collect_data.py first to gather landmark samples."
        )

    df = pd.read_csv(csv_path)
    if df.empty:
        sys.exit(f"ERROR: {csv_path} is empty — collect some data first.")

    if "label" not in df.columns:
        sys.exit("ERROR: CSV is missing a 'label' column.")

    feature_cols = [c for c in df.columns if c != "label"]
    if len(feature_cols) not in (HAND_DIM, INPUT_DIM):
        sys.exit(
            f"ERROR: Expected {HAND_DIM} or {INPUT_DIM} feature columns, "
            f"found {len(feature_cols)}.\n"
            "Re-run collect_data.py to regenerate the CSV."
        )

    original_count = len(df)
    if include_labels:
        df = df[df["label"].isin(include_labels)]

    counts = df["label"].value_counts()
    if min_samples_per_class > 1:
        keep = counts[counts >= min_samples_per_class].index
        df = df[df["label"].isin(keep)]
        counts = df["label"].value_counts()

    if max_classes > 0:
        keep = counts.sort_values(ascending=False).head(max_classes).index
        df = df[df["label"].isin(keep)]
        counts = df["label"].value_counts()

    if df.empty:
        sys.exit(
            "ERROR: No rows left after filtering.\n"
            "Try lowering --min-samples-per-class and/or increasing --max-classes."
        )

    labels_sorted = sorted(df["label"].unique())
    label_to_idx  = {lbl: idx for idx, lbl in enumerate(labels_sorted)}
    label_map     = {idx: lbl for lbl, idx in label_to_idx.items()}

    X = df[feature_cols].values.astype(np.float32)
    if X.shape[1] == HAND_DIM:
        X = np.pad(X, ((0, 0), (0, HAND_DIM)), mode="constant")
    y = df["label"].map(label_to_idx).values.astype(np.int32)

    # Print dataset summary
    print(
        f"\n  Dataset: {len(X)} samples, {len(labels_sorted)} classes "
        f"(from {original_count} rows)"
    )
    for lbl in labels_sorted:
        count = (df["label"] == lbl).sum()
        bar   = "#" * (count // 10)
        print(f"    {lbl:>8}: {count:>4}  {bar}")

    return X, y, label_map, counts.to_dict()


def stratified_split(
    X: np.ndarray,
    y: np.ndarray,
    val_split: float,
    seed: int = 42,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Create a stratified train/val split without sklearn dependency."""
    rng = np.random.default_rng(seed)
    by_class: dict[int, list[int]] = defaultdict(list)
    for idx, cls in enumerate(y):
        by_class[int(cls)].append(idx)

    train_indices: list[int] = []
    val_indices: list[int] = []
    for cls, indices in by_class.items():
        cls_indices = np.array(indices, dtype=np.int32)
        rng.shuffle(cls_indices)
        n = len(cls_indices)
        n_val = int(round(n * val_split))
        if n >= 8:
            n_val = max(1, n_val)
        else:
            n_val = 0
        n_val = min(max(0, n_val), n - 1) if n > 1 else 0
        val_indices.extend(cls_indices[:n_val].tolist())
        train_indices.extend(cls_indices[n_val:].tolist())

    if not train_indices or not val_indices:
        sys.exit(
            "ERROR: Stratified split produced empty train/val set.\n"
            "Collect more samples or lower --val-split."
        )

    X_train = X[np.array(train_indices, dtype=np.int32)]
    y_train = y[np.array(train_indices, dtype=np.int32)]
    X_val = X[np.array(val_indices, dtype=np.int32)]
    y_val = y[np.array(val_indices, dtype=np.int32)]
    return X_train, X_val, y_train, y_val


def _canonicalize_hand(hand: np.ndarray) -> np.ndarray:
    """Canonicalize a single 21-landmark hand (63 values)."""
    points = hand.reshape(21, 3).astype(np.float32)
    points = points - points[0]
    scale = float(np.linalg.norm(points[9]))
    if scale < 1e-6:
        scale = float(np.linalg.norm(points[5] - points[17]))
    if scale < 1e-6:
        scale = 1.0
    return (points / scale).reshape(-1)


def canonicalize_sample(flat: np.ndarray) -> np.ndarray:
    """Canonicalize one landmark vector (supports 63 or 126 dim).

    Each hand is independently wrist-centered and scale-normalized.
    63-dim inputs are zero-padded to 126-dim.
    """
    flat = flat.astype(np.float32)
    if flat.size == HAND_DIM:
        flat = np.pad(flat, (0, HAND_DIM), mode="constant")
    hand1 = _canonicalize_hand(flat[:HAND_DIM])
    hand2_raw = flat[HAND_DIM:INPUT_DIM]
    has_second = float(np.abs(hand2_raw).sum()) > 1e-6
    hand2 = _canonicalize_hand(hand2_raw) if has_second else hand2_raw
    return np.concatenate([hand1, hand2])


def canonicalize_batch(X: np.ndarray) -> np.ndarray:
    """Apply landmark canonicalization across a batch."""
    return np.stack([canonicalize_sample(sample) for sample in X], axis=0).astype(
        np.float32
    )


def augment_mirror(X: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Double the dataset with mirrored-x landmarks (supports 126-dim)."""
    mirrored = X.reshape(-1, 42, 3).copy()
    mirrored[:, :, 0] *= -1.0
    X_aug = np.concatenate([X, mirrored.reshape(-1, INPUT_DIM)], axis=0)
    y_aug = np.concatenate([y, y], axis=0)
    return X_aug.astype(np.float32), y_aug.astype(np.int32)


def augment_noise(
    X: np.ndarray, y: np.ndarray, noise_std: float = 0.01, rng: np.random.Generator | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Add Gaussian noise to landmark coordinates."""
    rng = rng or np.random.default_rng(42)
    noisy = X + rng.normal(0.0, noise_std, size=X.shape).astype(np.float32)
    X_aug = np.concatenate([X, noisy], axis=0)
    y_aug = np.concatenate([y, y], axis=0)
    return X_aug.astype(np.float32), y_aug.astype(np.int32)


def augment_scale_jitter(
    X: np.ndarray, y: np.ndarray, lo: float = 0.9, hi: float = 1.1,
    rng: np.random.Generator | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Randomly scale each sample's landmarks."""
    rng = rng or np.random.default_rng(42)
    scales = rng.uniform(lo, hi, size=(len(X), 1)).astype(np.float32)
    scaled = X * scales
    X_aug = np.concatenate([X, scaled], axis=0)
    y_aug = np.concatenate([y, y], axis=0)
    return X_aug.astype(np.float32), y_aug.astype(np.int32)


def augment_rotation(
    X: np.ndarray, y: np.ndarray, max_degrees: float = 15.0,
    rng: np.random.Generator | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Apply small 2D rotations (x, y only) to each sample."""
    rng = rng or np.random.default_rng(42)
    angles = rng.uniform(-max_degrees, max_degrees, size=len(X))
    rotated = X.reshape(-1, 42, 3).copy()
    for i, angle in enumerate(angles):
        rad = np.radians(angle)
        cos_a, sin_a = np.cos(rad), np.sin(rad)
        x_vals = rotated[i, :, 0].copy()
        y_vals = rotated[i, :, 1].copy()
        rotated[i, :, 0] = cos_a * x_vals - sin_a * y_vals
        rotated[i, :, 1] = sin_a * x_vals + cos_a * y_vals
    X_aug = np.concatenate([X, rotated.reshape(-1, INPUT_DIM)], axis=0)
    y_aug = np.concatenate([y, y], axis=0)
    return X_aug.astype(np.float32), y_aug.astype(np.int32)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--epochs", type=int, default=80,
        help="Training epochs (default: 80)",
    )
    parser.add_argument(
        "--batch-size", type=int, default=32,
        help="Mini-batch size (default: 32)",
    )
    parser.add_argument(
        "--val-split", type=float, default=0.15,
        help="Fraction of data held out for validation (default: 0.15)",
    )
    parser.add_argument(
        "--data", type=Path, default=DATA_CSV,
        help=f"Path to landmarks CSV (default: {DATA_CSV})",
    )
    parser.add_argument(
        "--lr", type=float, default=1e-3,
        help="Initial learning rate (default: 0.001)",
    )
    parser.add_argument(
        "--min-samples-per-class",
        type=int,
        default=15,
        help="Drop labels with fewer samples than this threshold (default: 15).",
    )
    parser.add_argument(
        "--max-classes",
        type=int,
        default=250,
        help="Keep top-N labels by sample count; 0 disables cap (default: 250).",
    )
    parser.add_argument(
        "--include-labels",
        nargs="*",
        default=None,
        help="Optional explicit label whitelist (space-separated).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducible splitting (default: 42).",
    )
    parser.add_argument(
        "--augment-mirror",
        action="store_true",
        help="Augment with left-right mirrored landmarks.",
    )
    parser.add_argument(
        "--augment-noise",
        action="store_true",
        help="Augment with Gaussian noise on landmark coords.",
    )
    parser.add_argument(
        "--augment-scale",
        action="store_true",
        help="Augment with random scale jitter (0.9-1.1x).",
    )
    parser.add_argument(
        "--augment-rotate",
        action="store_true",
        help="Augment with small 2D rotations (+-15 degrees).",
    )
    parser.add_argument(
        "--augment-all",
        action="store_true",
        help="Enable all augmentation strategies.",
    )
    parser.add_argument(
        "--preset",
        choices=("none", "alphabet"),
        default="none",
        help="Optional label preset filter (default: none).",
    )
    parser.add_argument(
        "--model-type",
        choices=("mlp", "lstm"),
        default="mlp",
        help="Model architecture: mlp (single-frame) or lstm (temporal sequence).",
    )
    parser.add_argument(
        "--seq-length",
        type=int,
        default=15,
        help="Sequence length for LSTM model (default: 15 frames).",
    )
    args = parser.parse_args()

    print(f"\n{'='*54}")
    print("  SignConnect - Gesture Classifier Training")
    print(f"{'='*54}")
    print(f"  TensorFlow : {tf.__version__}")
    print(f"  CSV        : {args.data}")
    print(f"  Epochs     : {args.epochs}  |  Batch: {args.batch_size}")
    print(
        f"  Filters    : min_samples={args.min_samples_per_class}, "
        f"max_classes={args.max_classes}"
    )

    # ── Load data ──────────────────────────────────────────────────────────
    include_labels = set(args.include_labels) if args.include_labels else None
    if args.preset == "alphabet":
        include_labels = ALPHABET_LABELS if include_labels is None else include_labels & ALPHABET_LABELS

    X, y, label_map, class_counts = load_dataset(
        args.data,
        min_samples_per_class=args.min_samples_per_class,
        max_classes=args.max_classes,
        include_labels=include_labels,
    )
    num_classes = len(label_map)

    # ── Canonicalize landmarks (translation + scale invariance) ───────────
    X = canonicalize_batch(X)
    print("  Canonical   : wrist-centered, scale-normalized")

    aug_rng = np.random.default_rng(args.seed)
    do_mirror = args.augment_mirror or args.augment_all
    do_noise = args.augment_noise or args.augment_all
    do_scale = args.augment_scale or args.augment_all
    do_rotate = args.augment_rotate or args.augment_all

    if do_mirror:
        X, y = augment_mirror(X, y)
        print(f"  Augment     : mirror-x -> {len(X)} samples")
    if do_noise:
        X, y = augment_noise(X, y, noise_std=0.01, rng=aug_rng)
        print(f"  Augment     : gaussian noise -> {len(X)} samples")
    if do_scale:
        X, y = augment_scale_jitter(X, y, rng=aug_rng)
        print(f"  Augment     : scale jitter -> {len(X)} samples")
    if do_rotate:
        X, y = augment_rotation(X, y, max_degrees=15.0, rng=aug_rng)
        print(f"  Augment     : rotation -> {len(X)} samples")

    # ── Build stratified split ─────────────────────────────────────────────
    X_train, X_val, y_train, y_val = stratified_split(
        X, y, val_split=args.val_split, seed=args.seed
    )
    print(
        f"  Split      : train={len(X_train)} samples, "
        f"val={len(X_val)} samples"
    )

    # ── Build class weights for imbalance ─────────────────────────────────
    train_class_counts = np.bincount(y_train, minlength=num_classes).astype(np.float32)
    max_count = float(train_class_counts.max())
    class_weight = {
        cls_idx: float(np.sqrt(max_count / max(count, 1.0)))
        for cls_idx, count in enumerate(train_class_counts)
    }

    # ── Normalize from TRAIN split only (avoid leakage) ───────────────────
    mean = X_train.mean(axis=0)
    std = X_train.std(axis=0) + 1e-8
    X_train = (X_train - mean) / std
    X_val = (X_val - mean) / std

    norm_path = MODEL_OUT.parent / "norm_stats.npz"
    np.savez(norm_path, mean=mean, std=std)
    print(f"  Norm stats  : saved to {norm_path}")

    # ── Build model ────────────────────────────────────────────────────────
    if args.model_type == "lstm":
        seq_len = args.seq_length
        print(f"  LSTM mode   : seq_length={seq_len}")
        X_train = X_train.reshape(-1, 1, INPUT_DIM)
        X_train = np.repeat(X_train, seq_len, axis=1)
        X_val = X_val.reshape(-1, 1, INPUT_DIM)
        X_val = np.repeat(X_val, seq_len, axis=1)
        model = build_lstm_model(num_classes, seq_length=seq_len)
    else:
        model = build_model(num_classes)
    model.compile(
        optimizer=keras.optimizers.Adam(learning_rate=args.lr),
        loss="sparse_categorical_crossentropy",
        metrics=["accuracy"],
    )
    model.summary()

    # ── Callbacks ──────────────────────────────────────────────────────────
    MODEL_OUT.parent.mkdir(parents=True, exist_ok=True)

    callbacks = [
        keras.callbacks.ModelCheckpoint(
            str(MODEL_OUT),
            monitor="val_accuracy",
            save_best_only=True,
            verbose=1,
        ),
        keras.callbacks.EarlyStopping(
            monitor="val_accuracy",
            patience=15,
            restore_best_weights=True,
            verbose=1,
        ),
        keras.callbacks.ReduceLROnPlateau(
            monitor="val_loss",
            factor=0.5,
            patience=7,
            min_lr=1e-6,
            verbose=1,
        ),
    ]

    # ── Train ──────────────────────────────────────────────────────────────
    print(f"\n{'-'*54}")
    print("  Training...")
    print(f"{'-'*54}")
    history = model.fit(
        X_train,
        y_train,
        epochs=args.epochs,
        batch_size=args.batch_size,
        validation_data=(X_val, y_val),
        class_weight=class_weight,
        callbacks=callbacks,
        verbose=1,
    )

    # ── Results ────────────────────────────────────────────────────────────
    best_val_acc = max(history.history.get("val_accuracy", [0]))
    demo_marker_path = MODEL_OUT.with_suffix(".demo")
    if demo_marker_path.exists():
        demo_marker_path.unlink()
    print(f"\n{'='*54}")
    print(f"  Best validation accuracy : {best_val_acc:.4f} ({best_val_acc*100:.1f}%)")
    print(f"  Model saved to           : {MODEL_OUT}")
    print(f"  Labels used              : {len(class_counts)}")

    # ── Per-class metrics ──────────────────────────────────────────────────
    y_pred_probs = model.predict(X_val, verbose=0)
    y_pred = np.argmax(y_pred_probs, axis=1)

    print(f"\n{'-'*54}")
    print("  Per-class metrics (validation set)")
    print(f"{'-'*54}")
    print(f"  {'Label':>20}  {'Prec':>6}  {'Recall':>6}  {'F1':>6}  {'Count':>5}")

    per_class_data: list[dict[str, object]] = []
    for cls_idx in range(num_classes):
        cls_label = label_map.get(cls_idx, f"class_{cls_idx}")
        true_pos = int(((y_pred == cls_idx) & (y_val == cls_idx)).sum())
        pred_pos = int((y_pred == cls_idx).sum())
        actual_pos = int((y_val == cls_idx).sum())
        precision = true_pos / max(1, pred_pos)
        recall = true_pos / max(1, actual_pos)
        f1 = (
            2 * precision * recall / max(1e-9, precision + recall)
            if (precision + recall) > 0
            else 0.0
        )
        per_class_data.append({
            "label": cls_label, "precision": precision,
            "recall": recall, "f1": f1, "count": actual_pos,
        })
        print(f"  {cls_label:>20}  {precision:6.3f}  {recall:6.3f}  {f1:6.3f}  {actual_pos:5d}")

    worst = sorted(per_class_data, key=lambda d: float(d["f1"]))[:10]
    if worst:
        print(f"\n  Worst-performing classes (bottom 10 by F1):")
        for entry in worst:
            print(f"    {entry['label']:>20}: F1={float(entry['f1']):.3f}")

    # ── Confusion matrix (saved to file) ───────────────────────────────────
    confusion = np.zeros((num_classes, num_classes), dtype=np.int32)
    for true_cls, pred_cls in zip(y_val, y_pred):
        confusion[true_cls][pred_cls] += 1
    cm_path = MODEL_OUT.parent / "confusion_matrix.csv"
    header_labels = [label_map.get(i, str(i)) for i in range(num_classes)]
    with cm_path.open("w", encoding="utf-8") as fh:
        fh.write("true\\pred," + ",".join(header_labels) + "\n")
        for i, row in enumerate(confusion):
            fh.write(header_labels[i] + "," + ",".join(str(v) for v in row) + "\n")
    print(f"\n  Confusion matrix saved to: {cm_path}")

    # ── Save label map ─────────────────────────────────────────────────────
    with LABEL_MAP_OUT.open("w", encoding="utf-8") as fh:
        json.dump({str(k): v for k, v in label_map.items()}, fh, indent=2)
    print(f"  Label map saved to       : {LABEL_MAP_OUT}")
    print(f"  Classes                  : {list(label_map.values())}")
    print(f"{'='*54}\n")
    print("  Next step: restart the Flask app - it will load the new model.")
    print("    .\\run.ps1   (or run.bat)\n")


if __name__ == "__main__":
    main()
