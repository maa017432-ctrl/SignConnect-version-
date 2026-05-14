"""Extract temporal MediaPipe landmark sequences from local WLASL videos."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
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

try:
    import numpy as np
except ImportError:
    sys.exit("ERROR: numpy not installed. Run: pip install numpy")


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WLASL_DIR = PROJECT_ROOT.parent / "WLASL"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "wlasl_sequences" / "wlasl_sequences.npz"
VIDEO_EXTENSIONS = (".mp4", ".mov", ".avi", ".mkv", ".webm")
FEATURE_DIM = 126


@dataclass(frozen=True)
class Clip:
    label: str
    video_id: str
    video_path: Path
    frame_start: int
    frame_end: int
    split: str
    signer_id: int

    @property
    def clip_key(self) -> str:
        """Stable key identifying one label+clip slice."""
        return (
            f"{self.label}|{self.video_id}|{self.frame_start}|"
            f"{self.frame_end}|{self.split}"
        )


def _video_path(videos_dir: Path, video_id: str) -> Path | None:
    for extension in VIDEO_EXTENSIONS:
        candidate = videos_dir / f"{video_id}{extension}"
        if candidate.exists():
            return candidate
    return None


def _load_clips(
    info_path: Path,
    videos_dir: Path,
    max_classes: int,
    min_videos_per_class: int,
) -> list[Clip]:
    with info_path.open("r", encoding="utf-8") as file_obj:
        payload = json.load(file_obj)

    by_label: dict[str, list[Clip]] = {}
    for entry in payload:
        label = str(entry.get("gloss", "")).strip()
        if not label:
            continue
        for instance in entry.get("instances", []):
            video_id = str(instance.get("video_id", "")).strip()
            path = _video_path(videos_dir, video_id)
            if path is None:
                continue
            by_label.setdefault(label, []).append(
                Clip(
                    label=label,
                    video_id=video_id,
                    video_path=path,
                    frame_start=int(instance.get("frame_start", 1) or 1),
                    frame_end=int(instance.get("frame_end", -1) or -1),
                    split=str(instance.get("split", "")).strip().lower() or "unknown",
                    signer_id=int(instance.get("signer_id", -1) or -1),
                )
            )

    eligible = [
        (label, clips)
        for label, clips in by_label.items()
        if len(clips) >= min_videos_per_class
    ]
    eligible.sort(key=lambda item: (-len(item[1]), item[0]))
    if max_classes > 0:
        eligible = eligible[:max_classes]

    selected: list[Clip] = []
    for _, clips in eligible:
        selected.extend(clips)
    return selected


def _frame_indices(total_frames: int, start_frame: int, end_frame: int, sequence_length: int) -> list[int]:
    if total_frames <= 0:
        return []
    start = max(0, start_frame - 1)
    end = total_frames - 1 if end_frame <= 0 else min(total_frames - 1, end_frame - 1)
    if end < start:
        start, end = 0, total_frames - 1
    if sequence_length <= 1:
        return [(start + end) // 2]
    return [
        int(round(start + (end - start) * (idx / max(1, sequence_length - 1))))
        for idx in range(sequence_length)
    ]


def _extract_frame(hands: object, frame_bgr: object) -> np.ndarray | None:
    result = hands.process(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB))
    if not result.multi_hand_landmarks:
        return None

    hands_data: list[tuple[float, list[float]]] = []
    for hand_landmarks in result.multi_hand_landmarks[:2]:
        flat = [coord for lm in hand_landmarks.landmark for coord in (lm.x, lm.y, lm.z)]
        mean_x = float(sum(lm.x for lm in hand_landmarks.landmark) / 21.0)
        hands_data.append((mean_x, flat))
    hands_data.sort(key=lambda item: item[0])
    if len(hands_data) == 1:
        hands_data.append((2.0, [0.0] * 63))
    return np.asarray(hands_data[0][1] + hands_data[1][1], dtype=np.float32)


def _extract_clip(hands: object, clip: Clip, sequence_length: int, min_detected_frames: int) -> np.ndarray | None:
    cap = cv2.VideoCapture(str(clip.video_path))
    if not cap.isOpened():
        return None
    try:
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        sequence = np.zeros((sequence_length, FEATURE_DIM), dtype=np.float32)
        detected = 0
        last_landmarks: np.ndarray | None = None
        for out_idx, frame_idx in enumerate(
            _frame_indices(total_frames, clip.frame_start, clip.frame_end, sequence_length)
        ):
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ok, frame = cap.read()
            if not ok or frame is None:
                if last_landmarks is not None:
                    sequence[out_idx] = last_landmarks
                continue
            landmarks = _extract_frame(hands, frame)
            if landmarks is None:
                if last_landmarks is not None:
                    sequence[out_idx] = last_landmarks
                continue
            sequence[out_idx] = landmarks
            last_landmarks = landmarks
            detected += 1
        if detected < min_detected_frames:
            return None
        return sequence
    finally:
        cap.release()


def _write_dataset(
    output_path: Path,
    sequences: list[np.ndarray],
    labels: list[str],
    splits: list[str],
    video_ids: list[str],
    clip_keys: list[str],
    signer_ids: list[int],
    sequence_length: int,
) -> None:
    """Write the currently usable sequence dataset to disk."""
    temp_path = output_path.with_suffix(".tmp.npz")
    np.savez_compressed(
        temp_path,
        X=np.asarray(sequences, dtype=np.float32),
        labels=np.asarray(labels),
        splits=np.asarray(splits),
        video_ids=np.asarray(video_ids),
        clip_keys=np.asarray(clip_keys),
        signer_ids=np.asarray(signer_ids, dtype=np.int32),
        sequence_length=np.asarray([sequence_length], dtype=np.int32),
    )
    os.replace(temp_path, output_path)


def _load_checkpoint(
    output_path: Path,
) -> tuple[list[np.ndarray], list[str], list[str], list[str], list[str], list[int]]:
    """Load a partial extraction checkpoint if it exists."""
    if not output_path.exists():
        return [], [], [], [], [], []
    try:
        payload = np.load(output_path, allow_pickle=True)
    except (EOFError, OSError, ValueError):
        return [], [], [], [], [], []
    if "clip_keys" in payload:
        clip_keys = [str(value) for value in payload["clip_keys"]]
    else:
        # Backward compatibility with older checkpoints
        clip_keys = [str(value) for value in payload["video_ids"]]
    return (
        [sample.astype(np.float32) for sample in payload["X"]],
        [str(value) for value in payload["labels"]],
        [str(value) for value in payload["splits"]],
        [str(value) for value in payload["video_ids"]],
        clip_keys,
        [int(value) for value in payload["signer_ids"]],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wlasl-dir", type=Path, default=DEFAULT_WLASL_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--max-classes", type=int, default=50)
    parser.add_argument("--min-videos-per-class", type=int, default=10)
    parser.add_argument("--sequence-length", type=int, default=30)
    parser.add_argument("--min-detected-frames", type=int, default=6)
    parser.add_argument("--min-detection", type=float, default=0.5)
    parser.add_argument("--checkpoint-every", type=int, default=50)
    parser.add_argument("--progress-every", type=int, default=10)
    parser.add_argument("--max-clips-this-run", type=int, default=0)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    output_path = args.output.resolve()
    manifest_path = output_path.with_suffix(".json")

    wlasl_dir = args.wlasl_dir.resolve()
    info_path = wlasl_dir / "info.json"
    videos_dir = wlasl_dir / "videos"
    if not info_path.exists():
        sys.exit(f"ERROR: info.json not found: {info_path}")
    if not videos_dir.exists():
        sys.exit(f"ERROR: videos directory not found: {videos_dir}")

    clips = _load_clips(
        info_path=info_path,
        videos_dir=videos_dir,
        max_classes=args.max_classes,
        min_videos_per_class=args.min_videos_per_class,
    )
    if not clips:
        sys.exit("ERROR: No clips matched the selected filters.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    shard_dir = output_path.with_suffix("")
    if args.force and output_path.exists():
        output_path.unlink()
    if args.force and manifest_path.exists():
        manifest_path.unlink()
    if args.force and shard_dir.exists():
        shutil.rmtree(shard_dir)
    shard_dir.mkdir(parents=True, exist_ok=True)
    sequences, labels, splits, video_ids, clip_keys, signer_ids = _load_checkpoint(output_path)
    processed_clip_keys = set(clip_keys)
    if manifest_path.exists() and len(processed_clip_keys) < len(clips):
        manifest_path.unlink()
    skipped = 0
    skipped_reasons: dict[str, int] = {
        "missing_landmarks_or_low_detection": 0,
        "already_processed": 0,
    }
    split_counts_selected: dict[str, int] = {}
    signer_counts_selected: dict[int, int] = {}
    for clip in clips:
        split_counts_selected[clip.split] = split_counts_selected.get(clip.split, 0) + 1
        signer_counts_selected[clip.signer_id] = signer_counts_selected.get(clip.signer_id, 0) + 1

    duplicate_video_ids: dict[str, int] = {}
    video_seen: dict[str, int] = {}
    for clip in clips:
        video_seen[clip.video_id] = video_seen.get(clip.video_id, 0) + 1
    for video_id, count in video_seen.items():
        if count > 1:
            duplicate_video_ids[video_id] = count

    print("\n" + "=" * 64, flush=True)
    print("SignConnect - WLASL Temporal Sequence Extraction", flush=True)
    print("=" * 64, flush=True)
    print(f"WLASL dir         : {wlasl_dir}", flush=True)
    print(f"Output            : {output_path}", flush=True)
    print(f"Candidate clips   : {len(clips)}", flush=True)
    print(f"Sequence length   : {args.sequence_length}", flush=True)
    print(f"Checkpoint samples: {len(sequences)}", flush=True)
    print(f"Checkpoint clips  : {len(processed_clip_keys)}", flush=True)
    print(f"Duplicate video_ids in selected set: {len(duplicate_video_ids)}", flush=True)

    with mp.solutions.hands.Hands(
        static_image_mode=False,
        max_num_hands=2,
        model_complexity=1,
        min_detection_confidence=float(args.min_detection),
    ) as hands:
        processed_this_run = 0
        for index, clip in enumerate(clips, start=1):
            if clip.clip_key in processed_clip_keys:
                skipped_reasons["already_processed"] = skipped_reasons.get("already_processed", 0) + 1
                continue
            if args.max_clips_this_run > 0 and processed_this_run >= args.max_clips_this_run:
                break
            shard_hash = hashlib.sha1(clip.clip_key.encode("utf-8")).hexdigest()[:16]
            shard_path = shard_dir / f"{shard_hash}.npy"
            if shard_path.exists():
                sequence = np.load(shard_path).astype(np.float32)
            else:
                sequence = _extract_clip(
                    hands=hands,
                    clip=clip,
                    sequence_length=args.sequence_length,
                    min_detected_frames=args.min_detected_frames,
                )
                if sequence is not None:
                    np.save(shard_path, sequence)
            if sequence is None:
                skipped += 1
                skipped_reasons["missing_landmarks_or_low_detection"] = (
                    skipped_reasons.get("missing_landmarks_or_low_detection", 0) + 1
                )
            else:
                sequences.append(sequence)
                labels.append(clip.label)
                splits.append(clip.split)
                video_ids.append(clip.video_id)
                clip_keys.append(clip.clip_key)
                signer_ids.append(clip.signer_id)
                processed_clip_keys.add(clip.clip_key)
            processed_this_run += 1

            if args.progress_every > 0 and (index % args.progress_every == 0 or index == len(clips)):
                print(
                    f"  processed={index:5d}/{len(clips)} "
                    f"kept={len(sequences):5d} skipped={skipped:5d}",
                    flush=True,
                )
            if sequences and args.checkpoint_every > 0 and index % args.checkpoint_every == 0:
                _write_dataset(
                    output_path=output_path,
                    sequences=sequences,
                    labels=labels,
                    splits=splits,
                    video_ids=video_ids,
                    clip_keys=clip_keys,
                    signer_ids=signer_ids,
                    sequence_length=args.sequence_length,
                )

    if not sequences:
        sys.exit("ERROR: No usable landmark sequences were extracted.")

    label_counts: dict[str, int] = {}
    for label in labels:
        label_counts[label] = label_counts.get(label, 0) + 1

    _write_dataset(
        output_path=output_path,
        sequences=sequences,
        labels=labels,
        splits=splits,
        video_ids=video_ids,
        clip_keys=clip_keys,
        signer_ids=signer_ids,
        sequence_length=args.sequence_length,
    )

    manifest_path.write_text(
        json.dumps(
            {
                "dataset": str(output_path),
                "sequence_length": args.sequence_length,
                "feature_dim": FEATURE_DIM,
                "selected_clips_total": len(clips),
                "processed_clip_keys_total": len(processed_clip_keys),
                "kept_samples_total": len(sequences),
                "remaining_clip_keys": max(0, len(clips) - len(processed_clip_keys)),
                "is_complete": len(processed_clip_keys) >= len(clips),
                "samples": len(sequences),
                "classes": len(label_counts),
                "split_counts_selected": split_counts_selected,
                "split_counts_kept": {
                    split: int(sum(1 for value in splits if value == split))
                    for split in sorted(set(split_counts_selected))
                },
                "distinct_signers_selected": len(signer_counts_selected),
                "distinct_signers_kept": len(set(int(value) for value in signer_ids)),
                "skipped_reasons": skipped_reasons,
                "duplicate_video_ids_selected": {
                    "count": len(duplicate_video_ids),
                    "examples": dict(list(sorted(duplicate_video_ids.items()))[:25]),
                },
                "label_counts": dict(sorted(label_counts.items())),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print("-" * 64, flush=True)
    print(f"Samples kept      : {len(sequences)}", flush=True)
    print(f"Clips skipped     : {skipped}", flush=True)
    print(f"Classes           : {len(label_counts)}", flush=True)
    print(f"Manifest          : {manifest_path}", flush=True)
    print("=" * 64 + "\n", flush=True)


if __name__ == "__main__":
    main()
