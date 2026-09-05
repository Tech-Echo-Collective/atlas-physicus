# Atlas Physica — bounded staging dual-read and rollback proof

Date: 2026-09-05. Source baseline: `8915ec7` on `main`.
Result: **PASS for this isolated rehearsal only**. No production migration,
acquisition, broad replay, scientific-policy change, metric activation, service
rename, URL/domain change, or release-tag change was performed.

## Fixed batch and isolation

Reused the same retained 2020-01-13–19 paired batch as the
[payload-reference pilot](payload-reference-recovery-2026-09-05.md):

- 170 INSPIRE + 465 arXiv occurrences = **635 occurrences / 474 papers**;
- **449 original-byte files**: eight provider pages, 439 already-retained
  authority responses, and two acquisition/enrichment manifests;
- source manifest `b715c6f2d81013c4ea1bea632edbfb75ab25fa8d3874df2d4326cc2b532e3322`;
- enrichment manifest `8880eaf2afd3c6c32fc46f923d56bb6b6626318af8415653d5756d9c15ee539d`;
- original certification manifest ID
  `e7b99d22e632a30e5b949f4a0165873ecd665b06411984ba3d8a478875bb2729`.

The additive catalog ran in fresh schema `dual_read_cf808958bec7` on private
local PostgreSQL 17.11, database `physics_atlas_storage_benchmark`, Unix socket
only. The runner rejects network PostgreSQL, other database/socket targets,
overlapping source/output directories, and optimized Python execution (which
would disable its proof assertions). The server was stopped after verification.
Raw sources and original manifests remain unchanged outside Git.

This is **not** a production `RawEntityRecord`/`SourceSnapshot` export or ORM
migration: the staged inline representation is retained original source bytes,
not reconstructed JSONB wire formatting. Both inline and reference forms remain
present throughout. No new storage saving or Full Physics capacity is claimed.

## One shared scientific path

`storage/dual_read.py` chooses an explicit inline or reference mode. Metadata
binds provider/record, acquisition/snapshot, dataset/scope, capture time/status,
payload size and original SHA-256. Cold references retain the existing separate
compressed-artifact hash. Full write and verified read-back precede promotion.

`tools/verify_staging_dual_read.py` recovers and verifies every catalog entry
before creating input files, then invokes the **same existing** source parsers,
normalization, `_canonicalize`, and `certify_paired_trial`. No alternative
scientific parser, certification rule or calculator is added.

| Proof | Inline | Reference | Explicit rollback |
| --- | --- | --- | --- |
| Recovered source files | 449 exact | 449 exact | 449 exact |
| Scientific artifacts | 10 exact | 10 exact | 10 exact |
| Certification decisions | 9,999 | 9,999 | 9,999 |
| Unique provenance references recovered | 1,033 / 1,033 | 1,033 / 1,033 | 1,033 / 1,033 |
| New observations / certified years / windows | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| Transactional checkpoint | inline, generation 0 | reference, generation 1 | inline, generation 2 |

All ten output artifacts and the full certification manifest are byte-identical
across the three modes and the preserved baseline. Decision states remain
2,305 `certified`, 1,686 `needs_review`, 6,007 `insufficient_evidence`, one
`conflicted`, and zero `withheld` in this batch; existing compact-certification
fixtures additionally cover explicit `withheld`. Reasons, versions, affiliations,
institution decisions, paper identity, attribution/field ledgers and missing-vs-zero
semantics are unchanged. The same certified-only projection boundary remains
mandatory; a raw payload, dictionary or storage selection cannot enter a calculator.
Provenance has 11,742 references, 1,033 unique (635 paper + 398 authority), zero lost.

Normalization digest:
`39f8f773ae0c05547559712b84b4793dbb5e9828c9add2061d6d3d41772b4e4e`.
Full certification manifest file SHA-256 (including its serialized checksum
field/newline, distinct from its manifest ID):
`7b4c1839346b32c06a59db6ffe3f2facbcde5cbcc739f2d48865a67e96ccdf73`.

## Fail-closed and rollback results

Seven native-SQL fault rehearsals passed: missing artifact, invalid reference,
checksum mismatch, truncated artifact, unavailable archive, interrupted/partial
archive write, and interrupted SQL transaction. Each returns an explicit
operational **blocked** result before parser/certification output, with the
catalog and checkpoint fingerprint unchanged. Unit tests also exercise corrupt
gzip, absent archive configuration, changed acquisition metadata and failed
read-after-write verification. Unrelated runtime bugs are not accepted as
successful fault injections.

Reference mode never silently uses retained inline bytes. Archive candidates
verify before one compare-and-swap SQL transaction changes row selections and
the checkpoint. The injected pre-commit interruption rolls back both rows and
checkpoint; an uncertain commit/network-loss outcome was not rehearsed. A
partial/orphan cold write cannot become a selected payload or valid scientific
evidence.

Explicit rollback reselects verified original inline bytes while preserving
reference and acquisition metadata. The whole scientific proof still passes
with the archive deliberately unavailable. No provider reacquisition or source
history rewrite is needed. This proves a private batch rollback, not production
worker crash/restart or independent-site disaster recovery.

Machine report (external, not committed):
`physics-atlas-evidence/staging-dual-read-2026-09-05/postgres-v1/staging-report.json`.
Measured `2026-09-05T01:56:21.158071Z`, SHA-256:
`726ea20a2ba497265b12b8bcd1f9214aa04a81be2b4f15a2dca4c8fc440b9939`.
The neighboring cold artifacts and all three restored output trees are retained.
Git contains tooling/tests and this compact report, not raw scientific payloads.

## Existing resource-check failure

A bounded production **read-only** query found exactly one failed resource:

- ID `resource-doi-5df06459d8ed2af678f1`;
- URL <https://doi.org/10.1119/5.0353857>, resource type: paper;
- check `2026-09-03T02:54:07.956371Z`: `broken`, HTTP **404**, one attempt,
  no transport exception; one recorded check for that resource;
- independent header-only request at `2026-09-05T01:58:17Z`: HTTP **404** again.

The exact observed cause is the DOI resolver returning not found. This does not
prove why the provider supplied that DOI or whether it may resolve later.
The monitor correctly records 404/410 as broken; the failure predates the
September 5 payload-reference work and uses no archive/storage reader. No code
fix, invented DOI correction, deletion, health reset, production recheck job, or
scientific-data edit is justified. Reconsider only with supported provider
evidence or a later normal successful resource check.

## Rename and compatibility

PA-047 establishes **Atlas Physica**, developed and maintained by Tech Echo
Collective, as the canonical public/product name. Current app heading, page and
social metadata, API display title/description, README, citation title, NOTICE,
current project/methodology docs, and separate public deployment wrapper use it.
Historical names/records and original copyright remain. The old social image
is retained but no longer advertised by metadata, avoiding a mismatched title;
social previews are text-only pending a separately reviewed asset refresh.

GitHub repository names, package/import/CLI IDs, database/schema names, Railway
services, environment variables, deployment URLs/domains, release tags and
serialized scientific provenance remain unchanged. The public wrapper must pin
the validated source commit so its visible app and secondary navigation agree.
No new map behavior, scientific layer or metric observation is enabled.

## Validation and limits

- **130 focused backend tests pass** (3.35s): dual-read, integrity/recovery,
  rollback/orchestration, compact and full certification, resource/update and
  API branding paths. Strict mypy passes 80 source files; focused Ruff
  lint/format passes six changed Python files.
- Frontend typecheck/lint, **132 Vitest + seven pipeline tests**, and production
  build pass. The existing large pilot chunk warning is unchanged.
- Private native PostgreSQL rehearsal passes. CI PostgreSQL migration/worker,
  API and container checks are separate fixture-only validation, not live replay.
- Production at `02:00:44Z`: API/database healthy, both providers healthy with
  zero failure streaks, recalculation idle, 440 unresolved entities and the
  diagnosed one resource failure. Public `/api/metric-observations` returns
  `total: 0`. No production payload was migrated or deleted.
- Source commit `1601b7e` passed
  [CI 33937979974](https://github.com/Tech-Echo-Collective/atlas-physicus/actions/runs/33937979974),
  including all 452 backend fixture tests, PostgreSQL/API/worker and containers.
  Web commit `14ff4df` pins that source and passed
  [Pages build/deploy 33938111627](https://github.com/Tech-Echo-Collective/Physics-Atlas-Web/actions/runs/33938111627):
  typecheck/lint, 12 routing/branding tests and production build. Its pre-existing
  `atlas.techecho.org` domain/routing commits were preserved. The live root and
  direct Atlas reload show Atlas Physica, matching project information and Live
  API mode with no scores. Post-publication production check at `02:07:55Z`
  remains healthy with unchanged cursors, one diagnosed DOI failure and zero
  observations; expected public-origin CORS is present. No tag was moved.

## Smallest next action

Review a **one-batch production-compatible schema/reader plan**, including a
durable archive retention/backup contract and independent restore test. Keep
inline rollback bytes until archive write/read-back, atomic worker/checkpoint
behavior, independent provenance recovery and deliberate rollback are verified
in that environment. Retire no production payload in this task. A representative
final-schema capacity measurement remains later work; both scientific and
Storage Budget gates stay withheld, with Full Physics loading and v3.1 unauthorized.
