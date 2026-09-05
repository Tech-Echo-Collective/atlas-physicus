# Atlas Physicus — bounded sample, retention and affiliation audit

2026-09-05; baseline `main` = `338891fd5186192f3598042f1ad53d550f6d385a`,
verified against GitHub. No Railway access, acquisition, scientific replay,
provider-capture/researcher processing, metric change, activation, migration or
original-evidence deletion. PA-052 extends the operational PA-051 boundary.
Decimal MB/GB unless explicitly MiB/GiB.

## Reusable sample

`bounded-cross-track-validation-sample-v1` pins **1,000 source-scoped references**:
all 474 official paired-v2 components plus 526 corrected Condensed Matter replay
components. It excludes 380 exact strong-ID overlaps with the paired source;
it does not merge source versions or create a pooled scientific denominator.
The paired source has 108 hep-th and 380 Condensed Matter memberships, including
14 shared components. Selection retains each observed year/provider/identity
stratum, then fills by stable SHA-256 order. Acquisition-year membership is not
canonical year certification.

- Sample ID: `5f520b2aa269c21ace9f637157684c6968f9461d7dc49f77187b0ae877ae0185`.
- Manifest SHA-256: `2ac319694fab48bf42f79098809f1fca90e39613a318eae809d72fd0062befca`;
  360,547 bytes. Exact repeated selection/reuse and independent offset/length/
  row-hash recovery pass for **1,000/1,000** references.
- Existing paired decisions: 2,305 certified, 1,686 needs_review, 6,007
  insufficient_evidence, one conflicted. There are no formal `withheld` decision
  rows here: WITHHELD behavior means all 474 public eligibility flags remain
  false. The added replay sample includes 37 identity-conflict components.
- Affiliation/institution, field and citation variation remain source-bound.
  No new certification, coverage or calculator readiness is claimed.

Local evidence root is the sibling `physics-atlas-evidence/`; all new metadata
is under `affiliation-retention-2026-09-05/`. Sample and independent proof are
`sample/validation-sample-v1.json` and `sample/reuse-proof.json`. The committed
`backend/tools/pin_validation_sample.py` verifies schema, immutable sample ID,
counts, source roles/versions, locators and exact reuse. Retained scientific
inputs remain necessary; Git alone does not contain the acquired evidence.

## Cumulative proof budget

The v1 operational ceiling is **1 GiB (1,073,741,824 bytes)**, within—not added
to—PA-048's combined 5 GB budget. Existing per-trace ceilings remain 2,500 papers,
100,000 decisions and 128 MiB. All physical copies, archived traces, old versions,
REVIEW files and metadata count; classification never deducts potential savings.

The reviewed proof scope includes every retained result/proof tree, both large
historical decision archives, paired/recovery/rollback source copies, new sample/
pilot metadata, the known archive-only workspace and two earlier small proof kits.
Base acquired and canonical
replay input bundles are outside this **proof-output sub-budget**, but still count
in full under PA-048. No evidence is relabeled ephemeral to achieve a PASS.

Final proof inventory plus accounting receipts: **848,393,201 bytes**
(~79.01% of 1 GiB): KEEP 619,641,841; COMPRESS/ARCHIVE 35,131,578;
REVIEW 193,619,782; REGENERABLE and RETIRE_CANDIDATE zero. No deletion is implied.
`retention-final-inventory.json` SHA-256:
`becb852392bfcd73541a2d94ac179a5e78a3d58acc6926db546a1ec64f640112`.
`accounting-supplement.json` corrects the initial census omission of two earlier
proof-metadata kits (23,831 bytes / 12 files), retaining the original receipt
unchanged. Corrected accounting, including those bytes at every admission, still
fits all 48 MiB reservations. No capacity was obtained by removing old evidence.

Each new pilot was admitted with a fresh inventory and 48 MiB reservation,
binding sample, pipeline version, proof plan and create-exclusive output path.
The writer checks its complete byte allowance before publishing. Actual retained
pilot trees are 3.67–3.93 MB each, including expanded small sample copies and full
accounting receipts. No repeated-job sharding of the corpus is permitted.

Limits: this is serialized operational admission, **not an OS quota or universal
retrofit of every old standalone CLI**. Existing bounded paired/replay commands
still require an operator's fresh version-level admission before use. Managed
pilot output is enforced; historical scattered-scope completeness is reviewed.
The census checks current paths/sizes and reuses 3,734 previously recorded hashes;
it does not reopen provider/researcher payloads or claim fresh integrity for them.
Pilot affiliation/archive hashes are independently verified separately.

## Entire affiliation class and decision matrix

Fresh SHA-256, complete row count, stable-file checks and ten manifest bindings
pass for all nine original paths. Evidence-root affiliation bytes remain
**2,267,637,717 / eight files**. The known archive-only workspace adds
**1,795,148 / one file**: all scoped originals **2,269,432,865 bytes**.
Exact paths, roles, hashes and dependencies: `inventory/inventory.json`,
`inventory/classification.json`, `inventory/FINDINGS.md`.

| Artifact/group | Bytes / files | Role | Compactable / regenerable | Exact duplicate | Active dependency | Action |
| --- | ---: | --- | --- | --- | --- | --- |
| Corrected replay `36b3550d…` | 1,128,564,601 / 1 | Current staging affiliation projection | Sample proven / not independently regenerated | Retained representative | Replay/ROR/certification readers | ARCHIVE_CANDIDATE; keep |
| Historical replay, same hash | 1,128,564,601 / 1 | Required historical bundle | Same format / not regenerated | Corrected twin | Separate historical manifest path | REVIEW; keep |
| Paired v1 `e3e8dd40…` | 1,532,775 / 1 | Unique historical certification shares | Entire-file pilot proven / no scientific regeneration | No | Two v1 manifests | ARCHIVE_CANDIDATE; keep |
| Official paired v2 `4c18c1a6…` | 1,795,148 / 1 | Current bounded certification shares | Entire-file pilot proven / no scientific regeneration | Retained representative | Official comparison source | ARCHIVE_CANDIDATE; keep |
| Recovery + inline/reference/rollback, same v2 hash | 7,180,592 / 4 | Required path-bound proof copies | Same exact bytes | Yes | Each retained bundle manifest | REVIEW; keep |
| Archive-only workspace, same v2 hash | 1,795,148 / 1 | Independent recovery proof copy | Same exact bytes | Yes | Historical proof path | REVIEW; keep |

Disjoint evidence-root A–E totals: **A 0; B 1,131,892,524; C 0;
D 1,135,745,193; E 0 bytes**. Workspace adds D 1,795,148. A=0 means these
are offline artifacts, not measured production rows; production-critical database
affiliation bytes are **not measured**, not zero. All B/D content remains required
until path-compatible authority is separately established. Reclaimable now: **0**.
Do not add duplicate savings to compression savings over the same bytes.
Adjacent attribution ledgers (250,341,360 bytes) are separately metadata-listed
and excluded; embedded provider/researcher fragments and SQL/index sizes were
not inspected or claimed as part of this file-class census.

## Amplification and measured pilots

The replay twins account for **99.54%** of affiliation bytes: 700,661 share rows
per copy, 5.412 rows per paper and 1,610.714 bytes per row. Identical projections
persist under two distinct historical bundle paths. A bounded 1,024-row profile
finds repeated JSON keys, provenance/path/checksum/version fields and exact weight
structures dominate. Root key tokens occupy 35.45%; provenance/version key-values
40.33%; three weight structures 12.08% (overlapping measures, not additive).
Raw affiliation fragments are only 2.33% in that prefix. JSON is already minified;
no SQL/index amplification exists in this class. Missing/unresolved shares and
their lineage are scientifically necessary, not removable padding.

Three gzip-level-6, deterministic, read-only pilots use the existing
`ArtifactRef` / `FilesystemArtifactStore`. This is **not a new authority resolver**.

| Pilot | Complete paper groups / rows | Exact original bytes | Archive bytes | Reduction | Manifest bytes |
| --- | ---: | ---: | ---: | ---: | ---: |
| Paired v1, entire file | 474 / 2,290 | 1,532,775 | 153,596 | 89.98% | 270,716 |
| Paired v2, entire file | 474 / 2,290 | 1,795,148 | 145,867 | 91.87% | 271,707 |
| Historical, first 200 replay members in pinned order | 200 / 1,053 | 1,664,623 | 154,569 | 90.71% | 131,932 |

Archive → independent isolated restore passes exact bytes/SHA-256, ordered full
semantic digest, institution/provenance linkage, original status/eligibility and
whole-paper mass for all three. Mass totals are exactly 474, 474 and 200, with
zero non-unit papers. The historical slice preserves 832 no-affiliation and 221
unresolved shares, all ineligible; it does not claim the entire population's
ambiguous cases were selected. Fixture tests cover ambiguous/conflicted edges.
Null/missing/zero, reasons, policy versions and raw fields survive unchanged.
The OS denied original evidence, previous workspace and network access during
each successful restore. Temporary expanded/transport copies were removed;
all originals and small retained pilot inputs remain.

Initial nested sandbox startup was blocked by the host permission boundary, then
rerun with approved OS isolation. Its three temporary transport copies were
removed only after exact retained-kit comparison; receipt retained. Historical
selection initially stopped on null canonical IDs: the corrected storage locator
uses an existing historical candidate ID without resolving or changing that null.

Full archive/manifest/proof pins and restore paths are in `final-accounting.json`.
For any pilot, use `backend/tools/pilot_affiliation_compaction.py --manifest ...
--manifest-sha256 ... --store ... --output <fresh-temporary-file>` in development/
test runtime. It never reads the historical original during restore. Local
read-only permissions do not establish independent backup durability.

## Estimates and current storage

After the final scope-correction census, evidence including its receipt is
**9,953,677,547 bytes**; Atlas-only workspace **1,880,296,954 bytes**, combined
**11,833,974,501**. This task adds **13,489,752 persistent evidence bytes** including sample, archives,
expanded small pilot copies, inventories and proofs. No pre-existing evidence
bytes were reclaimed. Later Git/test metadata may change workspace slightly.

Strictly proven-safe retirement saving remains **zero**: the existing decision
resolver does not support affiliation schemas or their direct-path callers.
Thus the presently justified retained footprint is still **9.954 GB evidence**.

Conditional same-format planning scenario, **not approved savings**: retain both
replay representations; apply the historical pilot's archive **plus per-row
manifest** ratio to those files, the separately measured complete-file v1/v2
ratios to their own copies, and add 25% contingency. Estimated affiliation class
is **~488.738 MB**, yielding **~8.175 GB evidence** (~10.055 GB with workspace),
before any newly required migration/backup costs. No deduplication credit is
taken. The 200-paper selection is not a statistical guarantee or full-file
recovery proof; broader content distributions, authority adapters and durable
backups remain unvalidated. Neither this estimate nor the sub-budget admission
passes PA-048's global 5 GB budget or authorizes Full Physics.

## Guardrails, validation and next action

Production worker → authoritative attribution ORM state remains unchanged.
Offline historical replay/public builder and expanded writers now refuse
production before input/output; development default planning writes no artifacts.
The production import-closure test forbids accidental reuse. No new Full Import
implementation, affiliation schema or scientific policy was introduced.

Small fixes: reject self-hashed malformed sample manifests; preserve historical
null-canonical candidate locators without merging them; stop growing affiliation
streams at pinned row/byte limits; verify pilot identity, corrupt gzip handling
and reservation paper bounds. All are operational/representation checks.

**277 focused fixture tests pass** (256 + 21, 2.66s combined). Ruff lint/format
passes 138 files; strict mypy passes 82 source files; whitespace and 71 local
documentation targets pass. Tests cover sample identity/reuse, cumulative budgets, archive
integrity, original-absent recovery, exact states/provenance/institution linkage,
conservation, missing semantics and production refusal. No scientific recertification
or live probe occurred. Baseline [CI 33949872535](https://github.com/Tech-Echo-Collective/atlas-physicus/actions/runs/33949872535)
passed; final commit/CI outcome is recorded at handoff. Release tags unchanged.

Smallest next action: review one affiliation-schema/path-compatibility adapter
using an already proven small paired archive, **without retiring evidence yet**.
Reuse the pinned sample and fresh cumulative admission. Do not proceed to provider
captures, researcher evidence, Full Physics or v3.1 without a separate task.
