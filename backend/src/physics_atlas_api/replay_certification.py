"""Offline CLI for evidence certification of a historical replay bundle."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from .certification import (
    summarize_replay_bundle,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Verify and summarize an immutable historical replay bundle without "
            "network, database, or metric writes."
        )
    )
    parser.add_argument("--bundle-root", type=Path, required=True)
    parser.add_argument("--bundle-manifest", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        help="optional root for content-addressed certification artifacts",
    )
    parser.add_argument(
        "--retain-decisions",
        action="store_true",
        help="stream and retain the complete decision artifact (requires --output)",
    )
    return parser


def run(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.retain_decisions and args.output is None:
        _parser().error("--retain-decisions requires --output")
    result = summarize_replay_bundle(
        bundle_root=args.bundle_root,
        bundle_manifest=args.bundle_manifest,
        output_root=args.output,
        retain_decisions=args.retain_decisions,
    )
    summary = {
        **result.report,
        "certification_manifest_checksum": result.certification_manifest[
            "certification_manifest_checksum"
        ],
        "output_manifest_path": (
            str(result.output_manifest_path)
            if result.output_manifest_path is not None
            else None
        ),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through run()
    raise SystemExit(run())
