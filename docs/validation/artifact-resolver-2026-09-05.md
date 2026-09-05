# Atlas Physica — bounded archive-backed artifact resolver

2026-09-05; current working tree based on `05783c1`, including the preceding
[NO-GO review](archive-promotion-review-2026-09-05.md) unchanged as historical evidence.

**ARCHIVE AUTHORITY CONTRACT = PASS.**
**CORRECTED LEDGER READY FOR ORIGINAL-RETIREMENT TASK = YES.**
YES means a later task may consider retirement after fresh dependency/integrity
checks. **Neither original ledger was deleted.** This is a local, opt-in resolver,
not production integration, universal legacy-reader replacement or scientific
activation. No Railway/provider access, replay, second-artifact compression,
historical-manifest rewrite, policy relaxation or release-tag change occurred.

## Minimum contract and compatibility

`backend/tools/resolve_historical_artifact.py` adds one versioned descriptor and
context-managed verified access, reusing the unchanged lossless restore helper.

- Logical identity is SHA-256 of canonical sorted JSON containing artifact
  `type`, `schema_version` and original-content `sha256`; it excludes location
  and representation. Exact bytes and row bounds are additionally required.
- Descriptor version: `historical-artifact-descriptor-v1`; supported artifact:
  `evidence-certification-decisions`, schema
  `historical-replay-evidence-certification-v1`.
- Each representation has ID, type, contained storage reference and restore
  method. Archive entries pin their archive manifest; original entries use
  `verified-copy-v1`. Exactly one explicitly selected authority is used.
- A pinned unchanged certification manifest must self-verify and bind the exact
  recorded role/path/hash/size/rows/version. Its path remains historical metadata;
  the archive path is selected from the descriptor, never guessed from a filename.
- The archive's original identity and historical manifest/dataset/source-bundle
  linkage must agree. Selected storage paths reject traversal and symlinks.
  Missing/corrupt authority fails closed; an intact alternative is **not** fallback.
- Only fully verified temporary bytes are yielded to existing evidence consumers.
  Resolver exit or failure removes only its owned temporary directory. No existing
  input path is rewritten or removed. Direct filesystem callers must explicitly
  adopt this adapter; the resolver does not intercept arbitrary file opens.

Logical ID for the corrected ledger:
`045b1244b310d7fd8d7a581eeb0b290b14401202e233c51f904a6e750d9ac4fc`.
Content SHA-256 remains
`459c1f4065130cef61c3c098f4775994982bd08f2ecb2e7f313d076a8d48aa7f`.
The separate historical ledger `8d9ba03a…` is not represented by this archive.

The local authority record and descriptor live under
`physics-atlas-evidence/artifact-resolver-2026-09-05/`, beside the repository.
`corrected-ledger-authority.json` selects `corrected-ledger-archive-v1`; the retained
original is an unselected representation. The current selected archive remains
at its existing `local-retention-review-2026-09-05/pilot/history-jsonl-v1/` path.
`authority-record.json` links the descriptor, immutable historical manifest,
proof and source hashes. It grants no automatic deletion permission.

Example adapter use from the repository with `backend/tools` on the Python path:

```python
from pathlib import Path
from resolve_historical_artifact import resolve_historical_artifact

root = Path("../physics-atlas-evidence").resolve()
with resolve_historical_artifact(
    root / "artifact-resolver-2026-09-05/corrected-ledger-authority.json",
    expected_descriptor_sha256="dde467d68a4fe0adf7ef4a9426bfb3f68128549544d15a733b939d9726580d09",
    storage_root=root,
    certification_manifest=root / "cond-mat-validation-v1-2020-2025-v2-certification-corrected-final/certification/manifests/9c79eced71031e79f17827ba00825a9541d63f527aa7d4131940799b1711b0d3.json",
    expected_certification_manifest_sha256="dae7133e9caa4246d072cebac09ed2bb53063e3eb3f44e51e9d2cd44a1366995",
) as artifact:
    # Consume artifact.path inside this block, never after its automatic cleanup.
    print(artifact.logical_artifact_id, artifact.scientific_summary)
```

## Original-absent proof

An isolated kit was placed at `/private/tmp/atlas-physica-resolver.u3QEsB` with
only copied archive, pinned descriptor, archive/certification manifests and prior
proof metadata. The OS denied all reads/writes to the real evidence tree and
private DB workspaces, all network operations, and repository writes. Explicit
open-only controls returned PermissionError for the original ledger, original
archive and DB; the loopback connection control was also OS-denied. No original
ledger bytes were read, even by the controls.

At `04:13:19Z`, the new proof runner completed descriptor → historical binding →
archive → checksum-verified restore → verified evidence access. A second digest
of the restored file independently matched the pinned expected content checksum.
The entire restored scientific summary matched both original and restored
summaries in the pinned prior proof:

| Preserved evidence | Result |
| --- | ---: |
| Exact decoded bytes | 3,437,302,947 |
| Decisions | 2,766,760 |
| certified / needs_review | 388,038 / 1,287,642 |
| insufficient_evidence / withheld / conflicted | 1,026,684 / 64,396 / 0 |
| Reason entries | 2,378,722 |
| Evidence-reference occurrences | 5,365,415 |
| Ordered identity, status/reason/version, provenance digests | All equal |

Exact full-byte equality against the recorded SHA-256 preserves all stored
conservation-related evidence, missing/null/zero distinctions, provenance and
decision semantics, including fields outside the summary. No source conservation
was recalculated and no provider-link availability was newly certified. The audit
ledger is **not** a `CertifiedMetricPartition`; recovered audit JSON still fails
the unchanged certified-only calculator boundary, just like original audit JSON.

## Temporary storage and limitations

The resolver removed its 3,437,302,947-byte expanded copy on context exit. The
new 282,831,800-byte isolated archive duplicate was then freshly hash-compared to
the retained archive and removed; no pre-existing evidence was removed. Only small
kit/receipt metadata remain: 6,359 bytes in the evidence authority directory and
11,963 bytes in the isolated kit, excluding repository code/docs/test caches.
Peak additional data was 3,720,134,747 bytes plus metadata; persistent savings
are **zero** while both originals remain.

Future streaming could reduce peak expanded storage, but exposing unverified
partial rows would be unsafe. No streaming redesign was implemented. This proof
is same-host recovery, not independent-host backup durability; malicious
same-account concurrent writers and arbitrary legacy direct-path callers are
outside this local resolver contract. Original retirement still requires a
separate fresh review using the registered adapter and preserved metadata.

## Validation and pins

65 focused tests pass: 33 resolver cases, 12 existing lossless-archive fixtures,
and 20 existing certification tests. They cover identity/location independence,
inline/archive equality, original read/stat denial, all five decision states,
missing/null/zero, certified-only admission, invalid authority/metadata, historical
bindings, missing/corrupt/truncated data, symlinks/traversal, interrupted restore,
caller failure and owned-temp cleanup. Changed-file Ruff format/lint pass.
Independent read-only review found no material defect. Existing CI runs against
the publication commit; no broad scientific reprocessing is requested locally.

| Retained pin | SHA-256 |
| --- | --- |
| `corrected-ledger-authority.json` | `dde467d68a4fe0adf7ef4a9426bfb3f68128549544d15a733b939d9726580d09` |
| `resolver-proof.json` | `2e874aedbacd17999f4f9f1aee0e2a1a3995b3096ef96eda0bcee20a61ed6ca1` |
| Resolver source | `554d16c78cadba00799acbfeda82ad18a0f9d08e72de29ac34b0f48e010b4f24` |
| Proof runner | `78bb27e9ebfb679b9cb3c3978bee5fb2a320f463eaa556f46f9e238c67bb48fc` |
| Unchanged restore helper | `654d90ed2033f72a8f1a10e6f5dc8946e51a1a7301ff4bfc4ba485ffe467fa3d` |

The original archive and historical manifest pins remain those recorded in the
[NO-GO review](archive-promotion-review-2026-09-05.md). That report is preserved;
this later resolver proof resolves its specific authority-contract blocker, not
the project's independent scientific, durability or combined-storage gates.
