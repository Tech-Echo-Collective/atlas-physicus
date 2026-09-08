"""Evaluate the exact owner-created launch checkpoints, without provider access.

Only trusted files produced by launch_build inside the same private ephemeral
directory are accepted. This command neither publishes nor activates metrics.
"""

from __future__ import annotations

import argparse
import gzip
import json
import pickle
from collections import Counter
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from .certification.build_cache import bounded_build_verification_cache
from .certification.launch_inputs import canonicalize_launch_inputs
from .certification.launch_metric_coverage import certify_launch_source_coverage
from .certification.launch_years import build_launch_source_year
from .certification.years import ENUMERATED_LAUNCH_SOURCE_YEAR_RULE_VERSION
from .launch_build import _write_checkpoint


def evaluate(root: Path, years: tuple[int, ...]) -> None:
    root = root.resolve(strict=True)
    if root.parent != Path("/private/tmp") or not root.name.startswith(
        "atlas-live-launch."
    ):
        raise ValueError("only the explicit private ephemeral launch root is accepted")
    cutoff = datetime.now(UTC)
    for year in years:
        source = root / f"source-{year}.pickle.gz"
        if source.is_symlink() or not source.is_file():
            raise ValueError("the original trusted acquired checkpoint is required")
        with gzip.open(source, "rb") as stream:
            captured, attributions = pickle.load(stream)  # noqa: S301 -- own private build state only
        canonical = canonicalize_launch_inputs(captured.occurrences)
        print(
            json.dumps(
                {
                    "stage": "canonical",
                    "year": year,
                    "paperStates": dict(
                        Counter(p.component.status for p in canonical.papers)
                    ),
                }
            ),
            flush=True,
        )
        with bounded_build_verification_cache(
            maximum_entries=20_000, maximum_key_nodes=1_000_000, stream_large_keys=True
        ) as cache:
            for entity_type in ("institution", "country"):
                build = build_launch_source_year(
                    captured,
                    canonical,
                    attributions,
                    entity_type=entity_type,
                    evidence_cutoff=cutoff,
                    identity_completeness_policy=ENUMERATED_LAUNCH_SOURCE_YEAR_RULE_VERSION,
                )
                report: dict[str, object] = {
                    "year": year,
                    "entityType": entity_type,
                    "counts": build.measured_counts,
                    "blockers": build.blockers,
                }
                if build.source_year is None:
                    print(
                        json.dumps({"stage": "source-unavailable", **report}),
                        flush=True,
                    )
                    continue
                coverage = certify_launch_source_coverage(build)
                report.update(
                    {
                        "membershipState": build.source_year.state,
                        "sourceQualityState": coverage.source_year.state,
                        "sourceQualityReasons": (
                            coverage.source_year.certification.reasons
                        ),
                        "coverage": coverage.measured_coverage,
                        "cache": asdict(cache.stats),
                    }
                )
                _write_checkpoint(
                    root,
                    root / f"evaluated-{year}-{entity_type}.pickle.gz",
                    (build, coverage),
                )
                (root / f"evaluated-{year}-{entity_type}.json").write_text(
                    json.dumps(report, sort_keys=True, separators=(",", ":")),
                    encoding="utf-8",
                )
                print(json.dumps({"stage": "source-evaluated", **report}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ephemeral-root", type=Path, required=True)
    parser.add_argument(
        "--years", type=int, nargs="+", choices=range(2018, 2024), required=True
    )
    args = parser.parse_args()
    evaluate(args.ephemeral_root, tuple(args.years))
