"""Extract MediaPipe hand landmarks from local WLASL videos.

This creates ``data/landmarks.csv`` in the same format consumed by
``scripts/train.py``:

    label,h0_x0,h0_y0,h0_z0,...,h1_x20,h1_y20,h1_z20

The extractor intentionally defaults to the most represented classes. WLASL is
very sparse across all 2,000 glosses, so a smaller balanced subset gives a more
useful first model than trying to learn every class from a few clips each.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    import cv2
except ImportError:
    sys.exit("ERROR: opencv-python not installed. Run: pip install opencv-python")

try:
    import mediapipe as mp
except ImportError as exc:
    sys.exit(f"ERROR: mediapipe unavailable: {exc}")


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WLASL_DIR = PROJECT_ROOT.parent / "WLASL"
DEFAULT_OUTPUT_CSV = PROJECT_ROOT / "data" / "landmarks.csv"
VIDEO_EXTENSIONS = (".mp4", ".mov", ".avi", ".mkv", ".webm")


@dataclass(frozen=True)
class VideoSample:
    """One local WLASL clip to sample."""

    label: str
    video_path: Path
    frame_start: int
    frame_end: int
    split: str


def _build_header() -> list[str]:
    columns = ["label"]
    for hand_index in range(2):
        prefix = f"h{hand_index}_"
        columns.extend(
            f"{prefix}{axis}{landmark_index}"
            for landmark_index in range(21)
            for axis in ("x", "y", "z")
        )
    return columns


def _video_path(videos_dir: Path, video_id: str) -> Path | None:
    for extension in VIDEO_EXTENSIONS:
        candidate = videos_dir / f"{video_id}{extension}"
        if candidate.exists():
            return candidate
    return None


def _load_samples(
    info_path: Path,
    videos_dir: Path,
    max_classes: int,
    min_videos_per_class: int,
    split: str,
) -> list[VideoSample]:
    with info_path.open("r", encoding="utf-8") as file_obj:
        payload = json.load(file_obj)

    by_label: dict[str, list[VideoSample]] = {}
    for entry in payload:
        label = str(entry.get("gloss", "")).strip()
        if not label:
            continue
        for instance in entry.get("instances", []):
            instance_split = str(instance.get("split", "")).strip().lower()
            if split != "all" and instance_split != split:
                continue
            video_id = str(instance.get("video_id", "")).strip()
            path = _video_path(videos_dir, video_id)
            if path is None:
                continue
            by_label.setdefault(label, []).append(
                VideoSample(
                    label=label,
                    video_path=path,
                    frame_start=int(instance.get("frame_start", 1) or 1),
                    frame_end=int(instance.get("frame_end", -1) or -1),
                    split=instance_split,
                )
            )

    eligible = [
        (label, samples)
        for label, samples in by_label.items()
        if len(samples) >= min_videos_per_class
    ]
    eligible.sort(key=lambda item: (-len(item[1]), item[0]))
    if max_classes > 0:
        eligible = eligible[:max_classes]

    selected: list[VideoSample] = []
    for _, samples in eligible:
        selected.extend(samples)
    return selected


def _sample_frame_indices(
    total_frames: int,
    frame_start: int,
    frame_end: int,
    frames_per_video: int,
) -> list[int]:
    if total_frames <= 0:
        return []
    start = max(0, frame_start - 1)
    end = total_frames - 1 if frame_end <= 0 else min(total_frames - 1, frame_end - 1)
    if end < start:
        start, end = 0, total_frames - 1
    if frames_per_video <= 1 or start == end:
        return [(start + end) // 2]

    step = (end - start) / float(frames_per_video + 1)
    return sorted({int(round(start + step * idx)) for idx in range(1, frames_per_video + 1)})


def _extract_landmarks(hands: object, frame_bgr: object) -> list[float] | None:
    image_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
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


def _extract_video_rows(
    hands: object,
    sample: VideoSample,
    frames_per_video: int,
) -> tuple[list[list[object]], int]:
    cap = cv2.VideoCapture(str(sample.video_path))
    if not cap.isOpened():
        return [], 0
    try:
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        indices = _sample_frame_indices(
            total_frames,
            sample.frame_start,
            sample.frame_end,
            frames_per_video,
        )
        rows: list[list[object]] = []
        attempted = 0
        for frame_index in indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            ok, frame = cap.read()
            attempted += 1
            if not ok or frame is None:
                continue
            landmarks = _extract_landmarks(hands, frame)
            if landmarks is not None:
                rows.append([sample.label] + landmarks)
        return rows, attempted
    finally:
        cap.release()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wlasl-dir", type=Path, default=DEFAULT_WLASL_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_CSV)
    parser.add_argument("--max-classes", type=int, default=40)
    parser.add_argument("--min-videos-per-class", type=int, default=18)
    parser.add_argument("--frames-per-video", type=int, default=8)
    parser.add_argument("--split", choices=("train", "val", "test", "all"), default="train")
    parser.add_argument("--append", action="store_true")
    parser.add_argument("--min-detection", type=float, default=0.5)
    args = parser.parse_args()

    wlasl_dir = args.wlasl_dir.resolve()
    info_path = wlasl_dir / "info.json"
    videos_dir = wlasl_dir / "videos"
    output_path = args.output.resolve()

    if not info_path.exists():
        sys.exit(f"ERROR: WLASL info.json not found: {info_path}")
    if not videos_dir.exists():
        sys.exit(f"ERROR: WLASL videos directory not found: {videos_dir}")

    samples = _load_samples(
        info_path=info_path,
        videos_dir=videos_dir,
        max_classes=args.max_classes,
        min_videos_per_class=args.min_videos_per_class,
        split=args.split,
    )
    if not samples:
        sys.exit("ERROR: No local WLASL videos matched the selected filters.")

    by_label: dict[str, int] = {}
    for sample in samples:
        by_label[sample.label] = by_label.get(sample.label, 0) + 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not args.append or not output_path.exists() or output_path.stat().st_size == 0
    mode = "a" if args.append else "w"

    print("\n" + "=" * 64)
    print("SignConnect - WLASL Landmark Extraction")
    print("=" * 64)
    print(f"WLASL dir        : {wlasl_dir}")
    print(f"Output CSV       : {output_path}")
    print(f"Split            : {args.split}")
    print(f"Classes          : {len(by_label)}")
    print(f"Videos           : {len(samples)}")
    print(f"Frames per video : {args.frames_per_video}")
    print("Selected labels  : " + ", ".join(sorted(by_label)))

    written = 0
    attempted = 0
    skipped_videos = 0
    per_label_rows: dict[str, int] = {label: 0 for label in by_label}

    with output_path.open(mode, newline="", encoding="utf-8") as file_obj:
        writer = csv.writer(file_obj)
        if write_header:
            writer.writerow(_build_header())

        with mp.solutions.hands.Hands(
            static_image_mode=True,
            max_num_hands=2,
            model_complexity=1,
            min_detection_confidence=float(args.min_detection),
        ) as hands:
            for index, sample in enumerate(samples, start=1):
                rows, frame_attempts = _extract_video_rows(
                    hands,
                    sample,
                    frames_per_video=args.frames_per_video,
                )
                attempted += frame_attempts
                if not rows:
                    skipped_videos += 1
                for row in rows:
                    writer.writerow(row)
                    written += 1
                    per_label_rows[sample.label] = per_label_rows.get(sample.label, 0) + 1
                if index % 25 == 0 or index == len(samples):
                    print(
                        f"  processed={index:4d}/{len(samples)} "
                        f"written={written:5d} skipped_videos={skipped_videos:4d}"
                    )

    print("-" * 64)
    print(f"Frames attempted : {attempted}")
    print(f"Rows written     : {written}")
    print(f"Videos no hands  : {skipped_videos}")
    print("Rows by label:")
    for label, count in sorted(per_label_rows.items(), key=lambda item: (-item[1], item[0])):
        print(f"  {label:>16}: {count:4d}")
    print("=" * 64 + "\n")


if __name__ == "__main__":
    main()
