"""
Convert labeled image folders into SignConnect landmark CSV training data.

Expected input layout:
    frames/
      A/
        img1.jpg
        img2.png
      B/
        sample1.jpg
      Hello/
        hello_01.jpeg

Output format (compatible with scripts/train.py):
    label,x0,y0,z0,...,x20,y20,z20

Usage examples:
    .venv311\\Scripts\\python scripts\\images_to_landmarks.py
    .venv311\\Scripts\\python scripts\\images_to_landmarks.py --input-dir "C:\\data\\frames"
    .venv311\\Scripts\\python scripts\\images_to_landmarks.py --append
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

try:
    import cv2
except ImportError:
    sys.exit("ERROR: opencv-python not installed. Run: pip install opencv-python")

try:
    import mediapipe as mp
    if not hasattr(mp, "solutions"):
        raise ImportError("MediaPipe solutions not available")
except ImportError as exc:
    sys.exit(f"ERROR: mediapipe unavailable — {exc}")


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_DIR = PROJECT_ROOT / "frames"
DEFAULT_OUTPUT_CSV = PROJECT_ROOT / "data" / "landmarks.csv"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def _build_header() -> list[str]:
    """Build CSV header columns for label + 126 landmark values (two hands)."""
    cols = ["label"]
    for hand_idx in range(2):
        prefix = f"h{hand_idx}_"
        cols += [f"{prefix}{axis}{index}" for index in range(21) for axis in ("x", "y", "z")]
    return cols


def _iter_images(label_dir: Path) -> list[Path]:
    """Return sorted image paths in one label directory."""
    return sorted(
        path
        for path in label_dir.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )


def _extract_landmarks(hands: object, image_path: Path) -> list[float] | None:
    """Extract flattened 126-value landmark vector (two hands) from an image.

    Second hand is zero-padded when only one hand is detected.
    """
    image_bgr = cv2.imread(str(image_path))
    if image_bgr is None:
        return None
    image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    result = hands.process(image_rgb)
    if not result.multi_hand_landmarks:
        return None

    hands_data: list[list[float]] = []
    for hand_landmarks in result.multi_hand_landmarks[:2]:
        hands_data.append(
            [coord for lm in hand_landmarks.landmark for coord in (lm.x, lm.y, lm.z)]
        )
    if len(hands_data) == 1:
        hands_data.append([0.0] * 63)
    return hands_data[0] + hands_data[1]


def main() -> None:
    """Parse arguments, convert images to landmarks, and write CSV output."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=DEFAULT_INPUT_DIR,
        help=f"Root directory containing class subfolders (default: {DEFAULT_INPUT_DIR})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_CSV,
        help=f"Output CSV path (default: {DEFAULT_OUTPUT_CSV})",
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Append to existing CSV instead of overwriting it.",
    )
    parser.add_argument(
        "--max-per-label",
        type=int,
        default=0,
        help="Optional cap per label (0 = no limit).",
    )
    parser.add_argument(
        "--min-detection",
        type=float,
        default=0.5,
        help="MediaPipe min_detection_confidence (default: 0.5).",
    )
    parser.add_argument(
        "--min-tracking",
        type=float,
        default=0.5,
        help="MediaPipe min_tracking_confidence (default: 0.5).",
    )
    args = parser.parse_args()

    input_dir = args.input_dir.resolve()
    output_csv = args.output.resolve()

    if not input_dir.exists():
        sys.exit(f"ERROR: Input directory does not exist: {input_dir}")

    label_dirs = sorted(path for path in input_dir.iterdir() if path.is_dir())
    if not label_dirs:
        sys.exit(
            "ERROR: No label subfolders found.\n"
            "Expected layout: <input-dir>/<label-name>/*.jpg"
        )

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    write_header = not args.append or not output_csv.exists() or output_csv.stat().st_size == 0
    mode = "a" if args.append else "w"

    print("\n" + "=" * 64)
    print("SignConnect — Image to Landmark Converter")
    print("=" * 64)
    print(f"Input dir : {input_dir}")
    print(f"Output CSV: {output_csv}")
    print(f"Mode      : {'append' if args.append else 'overwrite'}")
    print(f"Labels    : {', '.join(path.name for path in label_dirs)}")

    totals: dict[str, dict[str, int]] = {}
    total_written = 0
    total_skipped = 0

    with output_csv.open(mode, newline="", encoding="utf-8") as file_obj:
        writer = csv.writer(file_obj)
        if write_header:
            writer.writerow(_build_header())

        with mp.solutions.hands.Hands(
            static_image_mode=True,
            max_num_hands=2,
            model_complexity=1,
            min_detection_confidence=float(args.min_detection),
            min_tracking_confidence=float(args.min_tracking),
        ) as hands:
            for label_dir in label_dirs:
                label = label_dir.name
                image_paths = _iter_images(label_dir)
                if args.max_per_label > 0:
                    image_paths = image_paths[: args.max_per_label]

                written = 0
                skipped = 0
                for image_path in image_paths:
                    landmarks = _extract_landmarks(hands, image_path)
                    if landmarks is None:
                        skipped += 1
                        continue
                    writer.writerow([label] + landmarks)
                    written += 1

                totals[label] = {"written": written, "skipped": skipped}
                total_written += written
                total_skipped += skipped
                print(f"  {label:>12}: written={written:4d}  skipped={skipped:4d}")

    print("-" * 64)
    print(f"TOTAL written: {total_written}")
    print(f"TOTAL skipped: {total_skipped} (no hand detected / unreadable image)")
    print(f"Saved CSV    : {output_csv}")
    print("\nNext step:")
    print("  .venv311\\Scripts\\python scripts\\train.py")
    print("=" * 64 + "\n")


if __name__ == "__main__":
    main()
