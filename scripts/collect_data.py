"""
Interactive landmark data-collection tool for SignConnect gesture training.

Run from the signconnect folder:
    .venv311\\Scripts\\python scripts\\collect_data.py

Controls (OpenCV window):
    SPACE  — start capturing samples for the current label
    S      — skip the current label
    Q/ESC  — quit and save whatever was collected

Output:
    data/landmarks.csv   (appended — safe to run multiple sessions)

CSV columns:
    label, x0, y0, z0, x1, y1, z1, ... x20, y20, z20   (63 landmark cols)
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from pathlib import Path

# ── Dependency checks ──────────────────────────────────────────────────────
try:
    import cv2
except ImportError:
    sys.exit("ERROR: opencv-python not installed. Run: pip install opencv-python")

try:
    import mediapipe as mp
    if not hasattr(mp, "solutions"):
        raise ImportError("MediaPipe solutions not available")
    _hands_module = mp.solutions.hands
    _drawing_utils = mp.solutions.drawing_utils
except ImportError as exc:
    sys.exit(f"ERROR: MediaPipe unavailable — {exc}")

# ── Constants ──────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_CSV   = PROJECT_ROOT / "data" / "landmarks.csv"

# Default gesture vocabulary (matches generate_demo_model.py label_map.json)
DEFAULT_LABELS = (
    list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    + ["Hello", "Yes", "No", "Help", "Thanks"]
)

COUNTDOWN_SEC  = 3     # seconds shown before capture starts
CAPTURE_DELAY  = 0.05  # seconds between captured samples (~20 fps capture)
WINDOW_NAME    = "SignConnect — Data Collection"

# ── Helpers ────────────────────────────────────────────────────────────────

def _overlay_text(
    frame: cv2.typing.MatLike,  # type: ignore[name-defined]
    lines: list[str],
    start_y: int = 40,
    color: tuple[int, int, int] = (255, 255, 255),
) -> None:
    """Draw multiple lines of text onto a frame in-place."""
    for i, line in enumerate(lines):
        cv2.putText(
            frame,
            line,
            (12, start_y + i * 36),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            color,
            2,
            cv2.LINE_AA,
        )


def _extract_landmarks(results: object) -> list[float] | None:
    """Return flat 126-value vector (two hands, zero-padded) or None."""
    if not results.multi_hand_landmarks:  # type: ignore[union-attr]
        return None
    hands_data: list[list[float]] = []
    for hand in results.multi_hand_landmarks[:2]:  # type: ignore[union-attr]
        hands_data.append(
            [coord for lm in hand.landmark for coord in (lm.x, lm.y, lm.z)]
        )
    if len(hands_data) == 1:
        hands_data.append([0.0] * 63)
    return hands_data[0] + hands_data[1]


def _open_camera() -> cv2.VideoCapture:
    """Try camera indices 0-2 and return the first that works."""
    for idx in range(3):
        cap = cv2.VideoCapture(idx)
        if cap.isOpened():
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            cap.set(cv2.CAP_PROP_FPS, 30)
            # Warm-up reads
            for _ in range(5):
                cap.read()
            ok, frame = cap.read()
            if ok and frame is not None:
                print(f"  Camera opened on index {idx}")
                return cap
        cap.release()
    sys.exit("ERROR: No camera found on indices 0-2.")


def _ensure_csv_header(path: Path) -> None:
    """Write CSV header if the file is new/empty."""
    if path.exists() and path.stat().st_size > 0:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    header = ["label"]
    for hand_idx in range(2):
        prefix = f"h{hand_idx}_"
        header += [f"{prefix}{c}{i}" for i in range(21) for c in ("x", "y", "z")]
    with path.open("w", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerow(header)


def _count_existing(path: Path, label: str) -> int:
    """Count rows already collected for a given label."""
    if not path.exists():
        return 0
    count = 0
    with path.open("r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            if row.get("label") == label:
                count += 1
    return count

# ── Main ───────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--samples", type=int, default=200,
        help="Number of landmark samples to capture per label (default: 200)",
    )
    parser.add_argument(
        "--labels", nargs="+", default=None,
        help="Labels to collect (default: A-Z + Hello/Yes/No/Help/Thanks)",
    )
    args = parser.parse_args()

    labels: list[str] = args.labels or DEFAULT_LABELS
    samples_per_label: int = args.samples

    _ensure_csv_header(OUTPUT_CSV)

    cap = _open_camera()

    print(f"\n{'─'*54}")
    print(f"  Output  : {OUTPUT_CSV}")
    print(f"  Labels  : {', '.join(labels)}")
    print(f"  Samples : {samples_per_label} per label")
    print(f"  Controls: SPACE=capture  S=skip  Q/ESC=quit")
    print(f"{'─'*54}\n")

    with _hands_module.Hands(
        static_image_mode=False,
        max_num_hands=2,
        model_complexity=1,
        min_detection_confidence=0.6,
        min_tracking_confidence=0.5,
    ) as hands:
        label_idx = 0
        total_collected = 0

        while label_idx < len(labels):
            label = labels[label_idx]
            existing = _count_existing(OUTPUT_CSV, label)
            needed   = max(0, samples_per_label - existing)

            if needed == 0:
                print(f"  [{label}] already has {existing} samples — skipping")
                label_idx += 1
                continue

            print(f"  [{label}] needs {needed} more samples  ({existing} existing)")

            # ── WAITING phase ─────────────────────────────────────────────
            state   = "waiting"  # waiting | countdown | capturing | done
            cd_end  = 0.0
            captured_this = 0

            while True:
                ok, frame = cap.read()
                if not ok:
                    continue

                frame  = cv2.flip(frame, 1)
                rgb    = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                result = hands.process(rgb)

                # Draw landmarks
                if result.multi_hand_landmarks:
                    _drawing_utils.draw_landmarks(
                        frame,
                        result.multi_hand_landmarks[0],
                        _hands_module.HAND_CONNECTIONS,
                    )

                # Progress bar
                if needed > 0:
                    frac = captured_this / needed
                    bar_w = int(frame.shape[1] * frac)
                    cv2.rectangle(frame, (0, frame.shape[0] - 8),
                                  (bar_w, frame.shape[0]), (0, 200, 80), -1)

                if state == "waiting":
                    _overlay_text(frame, [
                        f"Label: {label}",
                        f"Need {needed} samples",
                        "SPACE=start  S=skip  Q=quit",
                    ])

                elif state == "countdown":
                    remaining = max(0, cd_end - time.time())
                    _overlay_text(
                        frame,
                        [f"Label: {label}", f"Starting in {remaining:.1f}s…"],
                        color=(80, 200, 255),
                    )
                    if remaining <= 0:
                        state = "capturing"

                elif state == "capturing":
                    _overlay_text(
                        frame,
                        [
                            f"Label: {label}",
                            f"Captured: {captured_this}/{needed}",
                        ],
                        color=(40, 220, 40),
                    )
                    landmarks = _extract_landmarks(result)
                    if landmarks is not None:
                        with OUTPUT_CSV.open("a", newline="", encoding="utf-8") as fh:
                            csv.writer(fh).writerow([label] + landmarks)
                        captured_this += 1
                        total_collected += 1
                        if captured_this >= needed:
                            state = "done"
                    time.sleep(CAPTURE_DELAY)

                elif state == "done":
                    _overlay_text(
                        frame,
                        [f"[{label}] done! {captured_this} samples captured."],
                        color=(80, 80, 255),
                    )
                    cv2.imshow(WINDOW_NAME, frame)
                    cv2.waitKey(1200)
                    break

                cv2.imshow(WINDOW_NAME, frame)
                key = cv2.waitKey(1) & 0xFF

                if key in (ord("q"), 27):  # Q or ESC
                    print(f"\n  Quit — collected {total_collected} samples total.")
                    cap.release()
                    cv2.destroyAllWindows()
                    return

                if key == ord("s") and state == "waiting":
                    print(f"  [{label}] skipped")
                    break

                if key == ord(" ") and state == "waiting":
                    cd_end = time.time() + COUNTDOWN_SEC
                    state  = "countdown"

            label_idx += 1

    cap.release()
    cv2.destroyAllWindows()
    print(f"\n  All labels processed. Total new samples: {total_collected}")
    print(f"  Saved to: {OUTPUT_CSV}")
    print(f"\n  Next step: .venv311\\Scripts\\python scripts\\train.py")


if __name__ == "__main__":
    main()
