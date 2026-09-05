"""Pin existing normalized paper references, not a merged scientific dataset.

No provider capture, researcher artifact, DB, replay or calculator is read/run.
Selection hashes one existing normalized replay index (bounded to 512 MiB),
retaining only <=2,500 row references and small stratum summaries. Exact source
versions remain separate. This local-only tool is not an ingestion command.
"""

from __future__ import annotations

import argparse
import hashlib
import heapq
import json
import os
import re
from collections import Counter
from pathlib import Path

from physics_atlas_api.certification.validation_artifacts import (
    MAX_VALIDATION_PAPERS,
    check_validation_size,
    require_validation_runtime,
)
from physics_atlas_api.storage.historical_read import AFFILIATION_ROLES, open_artifact

VERSION = "bounded-cross-track-validation-sample-v1"
MAX_SOURCE_BYTES = 512 * 1024**2
MAX_SOURCE_ROWS = 250_000
MAX_LINE_BYTES = 1024**2
MAX_MANIFEST_BYTES = 8 * 1024**2
PAIRED_ROLES = (
    "canonical-papers",
    "decisions",
    "affiliation-shares",
    "field-ledgers",
    "citation-observations",
)
SHA256 = re.compile(r"[0-9a-f]{64}")


class SampleError(ValueError):
    """Invalid source/identity/bounds; no sample is published."""


def encoded(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode()


def checksum(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def validate_sample(value):
    """Validate a pinned manifest's bounded contract, without reading evidence.

    This checks immutable metadata and identity, not scientific truth or source
    freshness. Source hashes/row bytes are separately verified during selection
    and by future consumers; matching a self-hash alone is not a valid sample.
    """

    def digest(item):
        return isinstance(item, str) and SHA256.fullmatch(item) is not None

    def integer(item, minimum=0, maximum=None):
        return (
            type(item) is int
            and item >= minimum
            and (maximum is None or item <= maximum)
        )

    def relative(item):
        return (
            isinstance(item, str)
            and bool(item)
            and "\0" not in item
            and not Path(item).is_absolute()
            and ".." not in Path(item).parts
            and Path(item).as_posix() == item
        )

    if not isinstance(value, dict) or value.get("version") != VERSION:
        raise SampleError("unsupported sample version")
    unsigned = {key: entry for key, entry in value.items() if key != "sample_id"}
    if not digest(value.get("sample_id")) or value["sample_id"] != checksum(unsigned):
        raise SampleError("sample identity mismatch")
    if (
        value.get("scientific_processing_performed") is not False
        or value.get("metric_activation_authorized") is not False
    ):
        raise SampleError("sample cannot authorize scientific processing or activation")
    target = value.get("paper_reference_count")
    paired_count = value.get("paired_count")
    replay_count = value.get("corrected_replay_count")
    if (
        not integer(target, 1000, MAX_VALIDATION_PAPERS)
        or not integer(paired_count, 1)
        or not integer(replay_count, 1)
        or paired_count + replay_count != target
    ):
        raise SampleError("sample count must be bounded and internally consistent")
    sources = value.get("sources")
    expected_roles = {
        "paired-v2": PAIRED_ROLES,
        "cond-mat-corrected-v2": ("paper-components",),
    }
    if not isinstance(sources, dict) or set(sources) != set(expected_roles):
        raise SampleError("sample must retain the two separate source identities")
    for source, roles in expected_roles.items():
        metadata = sources[source]
        if (
            not isinstance(metadata, dict)
            or not relative(metadata.get("manifest_path"))
            or not digest(metadata.get("manifest_sha256"))
            or not isinstance(metadata.get("version"), str)
            or not metadata["version"].strip()
            or not isinstance(metadata.get("artifacts"), dict)
            or set(metadata["artifacts"]) != set(roles)
        ):
            raise SampleError("invalid sample source metadata")
        for role in roles:
            artifact = metadata["artifacts"][role]
            if (
                not isinstance(artifact, dict)
                or artifact.get("role") != role
                or not relative(artifact.get("path"))
                or not digest(artifact.get("checksum"))
                or not integer(artifact.get("byte_count"), 1, MAX_SOURCE_BYTES)
                or not integer(artifact.get("row_count"), 1, MAX_SOURCE_ROWS)
            ):
                raise SampleError("invalid sample source artifact metadata")
    canonical = sources["paired-v2"]["artifacts"]["canonical-papers"]
    if canonical["row_count"] != paired_count:
        raise SampleError("sample must retain every bounded paired paper")
    decisions = sources["paired-v2"]["artifacts"]["decisions"]
    check_validation_size(
        paper_count=paired_count,
        decision_count=decisions["row_count"],
        decision_bytes=decisions["byte_count"],
    )
    members = value.get("members")
    if not isinstance(members, list) or len(members) != target:
        raise SampleError("sample member count mismatch")
    identities, locators, counts = set(), set(), Counter()
    for member in members:
        if not isinstance(member, dict):
            raise SampleError("sample member must be a reference object")
        source, role = member.get("source"), member.get("role")
        if not isinstance(source, str) or source not in sources:
            raise SampleError("unknown sample member source")
        expected_role = (
            "canonical-papers" if source == "paired-v2" else "paper-components"
        )
        if role != expected_role:
            raise SampleError("invalid sample member role")
        artifact = sources[source]["artifacts"][role]
        paper_id = member.get("paper_id")
        offset, length, row = (
            member.get("byte_offset"),
            member.get("byte_count"),
            member.get("row_number"),
        )
        if (
            not isinstance(paper_id, str)
            or not paper_id.strip()
            or not integer(row, 1, artifact["row_count"])
            or not integer(offset)
            or not integer(length, 1, MAX_LINE_BYTES)
            or offset + length > artifact["byte_count"]
            or not digest(member.get("row_sha256"))
        ):
            raise SampleError("invalid sample row identity or locator")
        identity, locator = (source, paper_id), (source, row)
        if identity in identities or locator in locators:
            raise SampleError("duplicate sample identity or row locator")
        identities.add(identity)
        locators.add(locator)
        counts[source] += 1
    if counts != {"paired-v2": paired_count, "cond-mat-corrected-v2": replay_count}:
        raise SampleError("sample source membership count mismatch")


def _path(root, reference):
    relative = Path(reference)
    if relative.is_absolute() or ".." in relative.parts:
        raise SampleError("source reference must be relative and contained")
    path = root / relative
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise SampleError("symlink source is forbidden")
    if not path.is_file() or not path.resolve().is_relative_to(root):
        raise SampleError("source is missing or outside evidence root")
    return path


def _read_manifest(root, reference, expected, kind):
    path = _path(root, reference)
    if path.stat().st_size > MAX_MANIFEST_BYTES:
        raise SampleError("manifest size limit exceeded")
    body = path.read_bytes()
    if hashlib.sha256(body).hexdigest() != expected:
        raise SampleError("manifest checksum mismatch")
    value = json.loads(body)
    key = "manifest_checksum" if kind == "paired" else "bundle_manifest_checksum"
    claimed = value.pop(key)
    if checksum(value) != claimed:
        raise SampleError("manifest self checksum mismatch")
    value[key] = claimed
    if kind == "paired":
        valid = (
            value.get("manifest_version")
            == "physics-paired-trial-certification-manifest-v2"
        )
    else:
        valid = value.get("acquisition_scope") == "cond-mat-validation-v1"
    if not valid or value.get("metric_observations_created") != 0:
        raise SampleError("unsupported source boundary")
    return value, path.parent.parent


def _rows(root, bundle, artifact):
    reference = (bundle / artifact["path"]).relative_to(root).as_posix()
    path = root / reference
    if artifact["role"] not in AFFILIATION_ROLES:
        path = _path(root, reference)
    expected_bytes, expected_rows = artifact["byte_count"], artifact["row_count"]
    if (
        type(expected_bytes) is not int
        or type(expected_rows) is not int
        or not 0 < expected_bytes <= MAX_SOURCE_BYTES
        or not 0 < expected_rows <= MAX_SOURCE_ROWS
    ):
        raise SampleError("bounded source dimensions mismatch")
    digest, offset, count = hashlib.sha256(), 0, 0
    with open_artifact(
        path,
        role=artifact["role"],
        checksum=artifact["checksum"],
        byte_count=expected_bytes,
        row_count=expected_rows,
        bundle_root=bundle,
    ) as stream:
        before = os.fstat(stream.fileno())
        if before.st_size != expected_bytes:
            raise SampleError("bounded source dimensions mismatch")
        while line := stream.readline(MAX_LINE_BYTES + 1):
            if len(line) > MAX_LINE_BYTES or offset + len(line) > expected_bytes:
                raise SampleError("source line/byte limit exceeded")
            count += 1
            if count > expected_rows:
                raise SampleError("source row count exceeded")
            digest.update(line)
            row = json.loads(line)
            if not isinstance(row, dict):
                raise SampleError("source row must be an object")
            locator = {
                "row_number": count,
                "byte_offset": offset,
                "byte_count": len(line),
                "row_sha256": hashlib.sha256(line).hexdigest(),
            }
            offset += len(line)
            yield row, locator
        # Check the actual opened representation's pathname too, preserving the
        # inline atomic-replacement guard without statting an archived original.
        after = Path(stream.name).stat()
        if (
            count != expected_rows
            or offset != expected_bytes
            or digest.hexdigest() != artifact["checksum"]
            or (before.st_ino, before.st_size, before.st_mtime_ns)
            != (after.st_ino, after.st_size, after.st_mtime_ns)
        ):
            raise SampleError("source integrity/identity changed")


def _artifact(manifest, role):
    entries = [entry for entry in manifest["artifacts"] if entry["role"] == role]
    if len(entries) != 1:
        raise SampleError("source must contain exactly one requested artifact role")
    return entries[0]


def _identifiers(row, kind):
    entries = (
        row["strong_identifiers"]
        if kind == "paired"
        else [
            item
            for occurrence in row["occurrences"]
            for item in occurrence["identifiers"]
        ]
    )
    # These are already normalized canonical IDs; no new fuzzy/entity resolution.
    return {
        (item["scheme"], item["value"])
        for item in entries
        if item["scheme"] in ("doi", "arxiv", "inspire")
    }


def build_sample(
    *, root, paired_manifest, paired_sha256, replay_manifest, replay_sha256, target=1000
):
    require_validation_runtime()
    if type(target) is not int or not 1000 <= target <= MAX_VALIDATION_PAPERS:
        raise SampleError("sample target must be 1000..2500 papers")
    root = Path(root).resolve(strict=True)
    paired, paired_root = _read_manifest(root, paired_manifest, paired_sha256, "paired")
    replay, replay_root = _read_manifest(root, replay_manifest, replay_sha256, "replay")
    paired_papers = _artifact(paired, "canonical-papers")
    if not 1 <= paired_papers["row_count"] < target:
        raise SampleError("paired source must fit within the bounded target")
    decisions = _artifact(paired, "decisions")
    check_validation_size(
        paper_count=paired_papers["row_count"],
        decision_count=decisions["row_count"],
        decision_bytes=decisions["byte_count"],
    )
    sources = {}
    for name, manifest, bundle, manifest_ref, manifest_hash, roles in (
        (
            "paired-v2",
            paired,
            paired_root,
            paired_manifest,
            paired_sha256,
            PAIRED_ROLES,
        ),
        (
            "cond-mat-corrected-v2",
            replay,
            replay_root,
            replay_manifest,
            replay_sha256,
            ("paper-components",),
        ),
    ):
        sources[name] = {
            "manifest_path": str(manifest_ref),
            "manifest_sha256": manifest_hash,
            "version": manifest.get(
                "projection_pipeline_version", manifest.get("replay_version")
            ),
            "artifacts": {
                role: {
                    **_artifact(manifest, role),
                    "path": (bundle / _artifact(manifest, role)["path"])
                    .relative_to(root)
                    .as_posix(),
                }
                for role in roles
            },
        }
    members, paired_ids, strong_ids = [], set(), set()
    scope_counts, eligibility = Counter(), Counter()
    for row, locator in _rows(root, paired_root, paired_papers):
        identity = row["canonical_paper_id"]
        if identity in paired_ids:
            raise SampleError("duplicate source-scoped paper identity")
        paired_ids.add(identity)
        strong_ids.update(_identifiers(row, "paired"))
        scope_counts.update(row["source_scopes"])
        eligibility[str(row["eligible_for_metrics"])] += 1
        members.append(
            {
                "source": "paired-v2",
                "paper_id": identity,
                "role": "canonical-papers",
                **locator,
            }
        )
    coverage = {
        "paired_source_scope_membership": dict(scope_counts),
        "paired_metric_eligibility": dict(eligibility),
    }
    for role in PAIRED_ROLES[1:]:
        counts = Counter()
        for row, _ in _rows(root, paired_root, _artifact(paired, role)):
            if role == "decisions":
                counts["state:" + row["state"]] += 1
            elif role == "affiliation-shares":
                counts["affiliation:" + row["paper_time_affiliation_state"]] += 1
                counts["institution:" + row["institution_state"]] += 1
            elif role == "field-ledgers":
                counts["assignments:" + str(len(row["assignments"]))] += 1
                counts[
                    "provider_disagreement:" + str(row["provider_disagreement"])
                ] += 1
            elif role == "citation-observations":
                value = row.get("non_self_citation_count")
                counts[
                    "non_self:"
                    + (
                        "missing"
                        if value is None
                        else "zero"
                        if value == 0
                        else "positive"
                    )
                ] += 1
        coverage[role] = dict(sorted(counts.items()))
    extra = target - len(members)
    best_by_stratum, heap, seen, excluded = {}, [], set(), 0
    replay_artifact = _artifact(replay, "paper-components")
    for row, locator in _rows(root, replay_root, replay_artifact):
        identity = row["candidate_id"]
        if identity in seen:
            raise SampleError("duplicate source-scoped paper identity")
        seen.add(identity)
        if strong_ids & _identifiers(row, "replay"):
            excluded += 1
            continue
        years = sorted({item["acquisition_year"] for item in row["source_lineage"]})
        providers = sorted({item["provider"] for item in row["source_lineage"]})
        stratum = json.dumps(
            [years, providers, row["status"], bool(row["conflict_schemes"])],
            separators=(",", ":"),
        )
        rank = int(hashlib.sha256((VERSION + ":" + identity).encode()).hexdigest(), 16)
        member = {
            "source": "cond-mat-corrected-v2",
            "paper_id": identity,
            "role": "paper-components",
            "stratum": stratum,
            **locator,
        }
        candidate = (rank, identity, member)
        if (
            stratum not in best_by_stratum
            or candidate[:2] < best_by_stratum[stratum][:2]
        ):
            best_by_stratum[stratum] = candidate
        if len(best_by_stratum) > extra:
            raise SampleError("strata exceed sample budget; review replacement policy")
        entry = (-rank, identity, member)
        if len(heap) < extra:
            heapq.heappush(heap, entry)
        elif entry[:2] > heap[0][:2]:
            heapq.heapreplace(heap, entry)
    chosen = {value[1]: value for value in best_by_stratum.values()}
    for negative, identity, member in sorted(
        heap, key=lambda entry: (-entry[0], entry[1])
    ):
        if len(chosen) >= extra:
            break
        chosen.setdefault(identity, (-negative, identity, member))
    if len(chosen) != extra:
        raise SampleError("insufficient disjoint paper references")
    selected = sorted(chosen.values(), key=lambda entry: entry[:2])
    members.extend(value[2] for value in selected)
    coverage["replay_selected_strata"] = dict(
        sorted(Counter(value[2]["stratum"] for value in selected).items())
    )
    value = {
        "version": VERSION,
        "selection_policy": (
            "all paired-v2; exclude exact cross-source strong-ID overlaps; "
            "smallest SHA256(version:source paper ID) per observed replay "
            "year/provider/status/conflict stratum, then smallest hashes to target"
        ),
        "paper_reference_count": target,
        "paired_count": len(paired_ids),
        "corrected_replay_count": extra,
        "excluded_cross_source_strong_id_overlap_count": excluded,
        "sources": sources,
        "members": members,
        "coverage": coverage,
        "scientific_processing_performed": False,
        "metric_activation_authorized": False,
        "limitations": [
            "Source-scoped components, not a new global canonical dataset "
            "or pooled denominator.",
            "Exact strong-ID overlap exclusion is not a new scientific "
            "merge/identity review.",
            "All original source artifacts/versions remain authoritative; "
            "this manifest stores row references only.",
            "PASS is represented by existing certified decisions; public "
            "eligibility remains withheld, not promoted.",
            "No new certification, replay, acquisition, citation cohort "
            "or metric observation is created.",
            "Not population-representative; engineering edge/variation sample "
            "only. Replacement requires documented evidence/domain expansion.",
        ],
    }
    value["sample_id"] = checksum(value)
    validate_sample(value)
    return value


def pin_sample(value, output):
    """Exact reuse only; never silently replace a previous sample/version."""
    require_validation_runtime()
    output = Path(output)
    if any(part.is_symlink() for part in (output, *output.parents)):
        raise SampleError("symlink output is forbidden")
    validate_sample(value)
    body = (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        + "\n"
    ).encode()
    if len(body) > MAX_MANIFEST_BYTES:
        raise SampleError("sample manifest size limit exceeded")
    if output.exists():
        if (
            not output.is_file()
            or output.stat().st_size != len(body)
            or output.read_bytes() != body
        ):
            raise SampleError(
                "existing pinned sample differs; replacement requires review"
            )
        return "verified-reuse"
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream:
        stream.write(body)
    return "created"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--paired-manifest", required=True)
    parser.add_argument("--paired-sha256", required=True)
    parser.add_argument("--replay-manifest", required=True)
    parser.add_argument("--replay-sha256", required=True)
    parser.add_argument("--target", type=int, default=1000)
    parser.add_argument("--output", type=Path, required=True)
    args = vars(parser.parse_args())
    output = args.pop("output")
    value = build_sample(**args)
    print(
        json.dumps(
            {
                "sample_id": value["sample_id"],
                "result": pin_sample(value, output),
                "papers": value["paper_reference_count"],
            }
        )
    )


if __name__ == "__main__":
    main()
