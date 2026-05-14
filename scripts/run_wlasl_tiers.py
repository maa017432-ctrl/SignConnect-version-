"""Run staged WLASL temporal extraction and training tiers."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _run(command: list[str]) -> None:
    print("\n$ " + " ".join(command))
    subprocess.run(command, cwd=PROJECT_ROOT, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tiers", type=int, nargs="+", default=[50, 100, 300])
    parser.add_argument("--wlasl-dir", type=Path, default=PROJECT_ROOT.parent / "WLASL")
    parser.add_argument("--sequence-length", type=int, default=30)
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--force-extract", action="store_true")
    args = parser.parse_args()

    python = sys.executable
    _run([python, "scripts/audit_wlasl.py", "--wlasl-dir", str(args.wlasl_dir)])

    for tier in args.tiers:
        min_videos = 20 if tier <= 50 else 10
        dataset = PROJECT_ROOT / "data" / "wlasl_sequences" / f"tier{tier}_sequences.npz"
        extract_command = [
            python,
            "scripts/wlasl_to_sequences.py",
            "--wlasl-dir",
            str(args.wlasl_dir),
            "--max-classes",
            str(tier),
            "--min-videos-per-class",
            str(min_videos),
            "--sequence-length",
            str(args.sequence_length),
            "--output",
            str(dataset),
        ]
        if args.force_extract:
            extract_command.append("--force")
        _run(extract_command)

        _run(
            [
                python,
                "scripts/train_temporal.py",
                "--data",
                str(dataset),
                "--max-classes",
                str(tier),
                "--min-samples-per-class",
                "6",
                "--epochs",
                str(args.epochs),
                "--batch-size",
                str(args.batch_size),
            ]
        )


if __name__ == "__main__":
    main()
