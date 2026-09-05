# Atlas Physicus — bounded validation-ledger scaling safety

2026-09-05; starting local/GitHub `main` verified at `21bfcdb`. Source/fixture
inspection only: no Railway, provider acquisition, real scientific replay,
other-class evidence processing, archive change or deletion. Historical
[batch evidence](certification-ledger-batch-2026-09-05.md) remains unchanged.

## Generation-path audit

Paths below are relative to `backend/`.

| Path / entry point | Classification and original boundary | Finding / action |
| --- | --- | --- |
| `src/physics_atlas_api/worker.py` → `updates/engine.py` → `metrics/recomputation.py` | Production ingestion; ORM source/canonical/lineage state, NoFormulaMetricRecalculator | No paired/recovery/comparison sink or call. Regression test checks transitive production imports/calls plus a real worker/engine cycle against mocked persistence/transport. |
| `src/physics_atlas_api/paired_trial_certification.py`: `certify_paired_trial`, `_derive_bundle`, `verify_paired_trial_certification_manifest` | Bounded validation only; fixed week, two scopes, ≤2,498 occurrences. Generates decisions and nine other certification artifacts; verifier recomputes without publishing copies. | Command installed in production package despite offline purpose. Added production refusal and decision row/byte caps before output publication. Existing scope/source checks preserved. |
| `src/physics_atlas_api/certification/staging.py`: `certify_replay_bundle`, `summarize_replay_bundle`, `write_replay_certification_bundle`; CLI `replay_certification.py` | Offline validation only; in-memory 100k-decision ceiling; summary defaults to no ledger | **Gap:** explicit retained stream previously had no corpus/output cap. Added bounded-paper preflight, actual row/byte limits and production refusal. Public alternate writer bounded too. |
| `tools/verify_payload_recovery.py`: `run_pilot` | Validation-only reference recovery/comparison, exact hashes and 635 occurrences / 474 papers | Already fixed-batch, but now refuses production before restored-source/output creation. Same shared certification path. |
| `tools/verify_staging_dual_read.py`: `run`, `scientific_result` | Validation-only inline/reference/rollback triple; exact batch, 449 catalog rows, owned local PostgreSQL socket | Added early production refusal to runner and directly callable scientific helper. Local socket, fixed-batch and optimized-Python safety checks preserved. No PostgreSQL run needed here. |
| `tools/compact_historical_artifact.py`, `resolve_historical_artifact.py`, `prove_historical_artifact_resolution.py` | Explicit one-artifact archive/restore/equivalence; existing 4 GiB / 3M-row ceilings, pinned identity/hash and isolated temporary restore | Recovery of retained authority, not new corpus certification. Not copied to production image; unchanged. Restoring the historical 3.44 GB artifact remains possible. No real restore performed. |
| `storage/compact.py`; `tools/benchmark_compact_storage.py` | Local lossless audit-storage prototype ≤10k decisions; benchmark additionally pins the 9,999-decision source hash | No production caller; not the authoritative certification store. Preserved, not broadly redesigned. |
| `tools/benchmark_payload_references.py` | Fixed 635-occurrence layout comparison with private PostgreSQL checks | No certification-ledger generation beyond fixed recovery dependencies; retained unchanged. |
| `historical_replay_materialization.py`, `historical_ror.py`, historical INSPIRE enrichers | Offline source/canonical replay artifacts and identity/attribution evidence; repeated runs can duplicate bundles across roots | Necessary scientific evidence is distinct from A/B proof copies. No automatic paired/recovery generation found; other evidence classes and replay code remain out of scope/unchanged. |
| `identity/validation.py`; `certification/*`; `metrics/*` | Manual-review sample defaults to 100 cases; pure certification/eligibility contracts, aggregate diagnostics and calculation proofs | Not full serialized A/B ledgers. Scientific review/decision state and required provenance remain intact. No identity data processed. |

The production package re-exports staging functions from `certification/__init__`.
Therefore module presence alone is not a production call. Tests allow the export
shim and pure scientific contracts, but reject new production call/import edges
to offline generators (including ordinary aliases). Installed CLI reachability
was a real accidental-use risk, not evidence that operated ingestion emitted
these files. No existing Full Physics importer was run or newly implemented.

## Enforced contract and equivalence

PA-051 and [storage architecture](../storage-architecture.md#validation-artifact-scaling-contract)
define the durable rule and future per-version sample policy. Existing runtime
settings, including `.env`, must identify development/test. Invalid settings and
production fail closed before scientific input reads or filesystem output.

Retained replay needs an explicit paper limit ≤2,500. Each verbose trace is capped
at 100,000 decisions and 128 MiB; in-memory replay/writer and paired output are
also protected. Paper/estimated-decision preflight precedes input artifact reads;
the unchanged checksum/row verification still follows. Streaming output checks
actual size before each write and removes its unpublished temporary file on
failure. Paired trace validation precedes all artifact publication. No clipping,
sampling-by-omission, modified states/reasons or changed scientific versions.

Fixture comparison preserves every certification artifact/manifest byte between
in-memory and bounded-retained replay; summary-only produces the same decision
hash, state and reason counts without retaining the ledger. Existing inline/
reference/rollback and archive fixtures validate provenance, missing/null/zero,
conservation information and certified-only calculator admission. No assertion
here claims new scientific evidence, recertification or independent-host recovery.

## Pathological storage scenario (warning only)

The retained 474-paper trial ledgers span 10,829,837–12,233,044 bytes per copy.
Naive linear scenario: `measured ledger bytes × target papers / 474`.
Decimal MB/GB; excludes all scientific state, source evidence, indexes, archives,
backup history and processing peaks. Three copies illustrate inline/reference/
rollback alone; additional recovery/restore copies would add again.

| Papers | One full decision trace | Three duplicated traces |
| ---: | ---: | ---: |
| 10,000 | 228.478–258.081 MB | 0.685–0.774 GB |
| 100,000 | 2.285–2.581 GB | 6.854–7.742 GB |
| 1,000,000 | 22.848–25.808 GB | 68.543–77.424 GB |

Expected contract: zero such traces from production ingestion; bounded proof
storage per reviewed pipeline version/sample, not proportional to corpus size.
Necessary compact authoritative certification still scales with scientific state.
This is not an exact Full Physics footprint or a storage-capacity PASS.

## Validation and remaining boundaries

- 188 focused fixture tests pass (4.24s), including 29 new limit/production-boundary
  cases, existing paired/replay/recovery/rollback, compact storage, certification,
  Metric System v1, historical archive/resolver and worker tests.
- Strict backend mypy passes all 81 source files; Ruff lint/format passes all 132
  source/test/tool files; whitespace and 70 local documentation targets pass.
  Baseline `21bfcdb` passed [CI 33947697399](https://github.com/Tech-Echo-Collective/atlas-physicus/actions/runs/33947697399).
  Independent review passes, including an additional prohibition on production
  reuse of the compact-audit prototype. Commit/CI status is reported at handoff.
- The mocked production worker uses an empty source batch and real engine/scheduler
  against mocks; it is not a live integration or production health probe. GitHub
  CI supplies the existing deterministic PostgreSQL/API/container checks.
- Per-run limits do not enforce cumulative operator quotas or stop privileged
  code/configuration overrides. Never shard the corpus into proof jobs. Future
  scheduling needs explicit per-version retention and representative sample review.
- Output limits do not bound every parser allocation or total source/artifact
  memory. This task closes verbose-output amplification, not broad import sizing.
- The production compact certification schema remains undeployed; raw/provider
  storage amplification and both activation/capacity gates remain unresolved.
  Eight older paired ledger paths, both historical archives and all proofs stay.

Smallest next action: review/pin a representative version-level sample and proof
retention budget before any separately authorized larger processing design. No
new artifact-class cleanup, Full Physics load or v3.1 is authorized.
