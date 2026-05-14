"""Audit local WLASL coverage before extraction/training.

Reports local video availability, split counts, and class tiers. This is a
metadata audit only; it does not run MediaPipe over every video.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WLASL_DIR = PROJECT_ROOT.parent / "WLASL"
VIDEO_EXTENSIONS = (".mp4", ".mov", ".avi", ".mkv", ".webm")


def _video_exists(videos_dir: Path, video_id: str) -> bool:
    return any((videos_dir / f"{video_id}{extension}").exists() for extension in VIDEO_EXTENSIONS)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wlasl-dir", type=Path, default=DEFAULT_WLASL_DIR)
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "data" / "wlasl_audit.csv")
    parser.add_argument("--top", type=int, default=50)
    args = parser.parse_args()

    wlasl_dir = args.wlasl_dir.resolve()
    info_path = wlasl_dir / "info.json"
    videos_dir = wlasl_dir / "videos"
    if not info_path.exists():
        sys.exit(f"ERROR: info.json not found: {info_path}")
    if not videos_dir.exists():
        sys.exit(f"ERROR: videos directory not found: {videos_dir}")

    with info_path.open("r", encoding="utf-8") as file_obj:
        payload = json.load(file_obj)

    rows: list[dict[str, object]] = []
    split_totals: Counter[str] = Counter()
    total_instances = 0
    local_instances = 0

    for entry in payload:
        label = str(entry.get("gloss", "")).strip()
        instances = entry.get("instances", [])
        total_instances += len(instances)
        local_split_counts: Counter[str] = Counter()
        all_split_counts: Counter[str] = Counter()
        local_count = 0

        for instance in instances:
            split = str(instance.get("split", "")).strip().lower() or "unknown"
            all_split_counts[split] += 1
            video_id = str(instance.get("video_id", "")).strip()
            if _video_exists(videos_dir, video_id):
                local_count += 1
                local_instances += 1
                local_split_counts[split] += 1
                split_totals[split] += 1

        rows.append(
            {
                "label": label,
                "metadata_instances": len(instances),
                "local_videos": local_count,
                "local_train": local_split_counts["train"],
                "local_val": local_split_counts["val"],
                "local_test": local_split_counts["test"],
                "metadata_train": all_split_counts["train"],
                "metadata_val": all_split_counts["val"],
                "metadata_test": all_split_counts["test"],
            }
        )

    rows.sort(key=lambda row: (-int(row["local_videos"]), str(row["label"])))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    eligible_10 = sum(1 for row in rows if int(row["local_videos"]) >= 10)
    eligible_20 = sum(1 for row in rows if int(row["local_videos"]) >= 20)
    eligible_30 = sum(1 for row in rows if int(row["local_videos"]) >= 30)

    print("\n" + "=" * 64)
    print("SignConnect - WLASL Audit")
    print("=" * 64)
    print(f"WLASL dir          : {wlasl_dir}")
    print(f"Metadata classes   : {len(rows)}")
    print(f"Metadata instances : {total_instances}")
    print(f"Local videos       : {local_instances}")
    print(f"Local split counts : {dict(split_totals)}")
    print(f"Classes >=10 videos: {eligible_10}")
    print(f"Classes >=20 videos: {eligible_20}")
    print(f"Classes >=30 videos: {eligible_30}")
    print(f"CSV report         : {args.output}")
    print("-" * 64)
    print(f"Top {args.top} local classes:")
    for row in rows[: args.top]:
        print(
            f"  {str(row['label']):>18}: "
            f"local={int(row['local_videos']):3d} "
            f"train={int(row['local_train']):3d} "
            f"val={int(row['local_val']):3d} "
            f"test={int(row['local_test']):3d}"
        )
    print("=" * 64 + "\n")


if __name__ == "__main__":
    main()
