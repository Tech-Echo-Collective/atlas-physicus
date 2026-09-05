# Atlas Physicus — affiliation archive reader and retirement batch

2026-09-05; verified baseline `main` = `f32e261cf822b05b03fd603d7963efc50e1bf397`
([green CI](https://github.com/Tech-Echo-Collective/atlas-physicus/actions/runs/33952033813)).
Local affiliation representation work only. No Railway access, provider-capture
or researcher processing, acquisition, broad replay, policy/metric change,
activation, production migration, release-tag movement or Full Physics load.
Decimal MB/GB below. This supersedes the prior affiliation audit's **current**
path-dependency blocker, not its historical measurements or manifests.

## Result and scope

**AFFILIATION ARCHIVE READER = PASS. Replay-twin compatibility = PASS.**
Nine original paths, representing three exact contents, passed all six gates
and were retired. Three small prior pilot inputs (4,992,546 bytes) remain; their
old pilot-path contract was not promoted. No unique scientific bytes were lost.

| Artifact/group | Original bytes / paths | Archive bytes | Restore | Authority | Dependencies | Scientific equivalence | Retirement | Net reclaimed before shared metadata | Blocker |
| --- | ---: | ---: | --- | --- | --- | --- | --- | ---: | --- |
| Corrected + historical replay twins `36b3550d…` | 2,257,129,202 / 2 | 110,694,392 | PASS | PASS | PASS | PASS | GO; retired | 2,146,371,597 | None |
| Paired v1 `e3e8dd40…`, two manifests | 1,532,775 / 1 | 153,596 | PASS | PASS | PASS | PASS | GO; retired | 1,316,891 | None |
| Paired v2 `4c18c1a6…`, official/recovery/inline/reference/rollback/workspace | 10,770,888 / 6 | 145,867 | PASS | PASS | PASS | PASS | GO; retired | 10,453,817 | None |

Archive integrity is PASS for every row. Net group numbers include their own
metadata, proofs and new authority indices; subtract **1,861,047 bytes** of shared
batch accounting/tooling/review metadata for the total net result below.
The prior three pilot inputs/archives and sample/audit receipts remain unchanged;
do not treat the 200-paper historical slice as a full-source authority.

## Authority and current callers

PA-053 extends the **same** logical artifact resolver. Its implementation moved
from a standalone tool to `storage.historical_authority`; the old module name
still aliases it. The decision codec likewise moved with unchanged behavior.
An affiliation codec supplies exact gzip recovery, not new scientific logic.

Descriptors explicitly select an archive. Logical IDs hash type/schema/content:

| Content | Logical artifact ID | Compressed SHA-256 |
| --- | --- | --- |
| Replay twins | `5ca59a3fbbe4ff2eccdd3c3e0c530dd1def1fd0098ec0d6abef0d02d3773a443` | `10dabcb9509f2baf9d3afb014e707fc42089123298b9ede59669a6152b6b4800` |
| Paired v1 | `493ab6ff4e7c06e6e945b1db73fc86b58afca5ea569c7efa2d8b6c3f596dc54f` | `f84a4d03dbe0e7ce52374f6672175f82c71c962fb41d4b7e80d762a87e46625e` |
| Paired v2 | `762cfe49e45189b249ca6fc45234d06fd386f7e60c20e7de0a640cd80db686ad` | `4c5e1a35d09c303082f971576b570d6c8462c4996397475f40a464ddb5e7f8c1` |

Each of ten original manifest/path relationships is pinned independently,
including both distinct replay manifests and two v1 manifests for one file.
Nine additive `artifact-authority.json` indices connect current readers to these
authorities. Historical manifests and recorded provenance paths are unchanged.
No filename guessing, approximate matching or fallback from broken authority.

Current staging verification/JSONL readers, ROR/institution/enrichment shared
reader, paired verification, sample pinning, bounded pilot selection, recovery
and dual-read comparisons use the same bridge. Historical completed scripts
remain as-of records: `assess_paired_joint_gate.py` accepts an isolated restored
`--certification-root`; the old accounting script can use its unchanged relative
layout in a restored mirror. Neither must open the retired originals in place.
Historical source-code pins are not rewritten. An additive current compatibility
check verifies both earlier **decision** archive authorities and fresh compressed
hashes, without another large decision-ledger restore.

## Recovery and scientific checks

The already-proven small paired-v2 gzip was adopted without recompression first.
All six historical paths recovered exactly under OS read denial of originals,
the retained archive/evidence tree and old workspace, plus network denial.
Only after that PASS was the whole original-path batch inventoried. Fresh stable
hashes, sizes and row counts passed for nine originals before deletion.

Paired v1 uses its existing complete gzip; both manifests passed. A single new
full replay archive was then made and independently restored **once per historical
binding**, sequentially, with both originals unavailable. All ten bindings
preserve exact byte SHA-256, ordered semantic/state/reason/version fingerprints,
institution/provenance links, absent/null/zero distinctions and stored eligibility.

- Each paired content: 2,290 rows, 474 source-bound components, exact mass 474;
  all metric eligibility flags remain false. Distinct v1/v2 institution decisions
  are preserved, not merged.
- Replay: 700,661 rows; 129,416 distinct **affiliation-stream** locators, including
  306 null-canonical components using their existing candidate locator. This is
  not a new count/certification of all papers in the wider replay bundle.
  Exact mass 129,416; zero non-unit totals and zero mismatched author × affiliation
  products across all 700,661 rows.
- Replay states remain 510,576 no-affiliation, 189,863 unresolved and 222
  ambiguous shares; all 700,661 public eligibility flags remain false.

No corpus decisions or metrics were regenerated. Exact existing scientific
inputs are restored; a tiny fixture additionally traverses the existing parser
and affiliation certifier and verifies identical decisions/reasons/versions/
provenance and certified-only calculator rejection. No other evidence class was
read to infer new scientific eligibility.

After retirement, seven small paths passed actual archive-backed reads. Both
large references passed current index/descriptor/historical binding and fresh
archive integrity checks; their independent original-absent full restores remain
the recovery proof. No redundant post-delete 1.13 GB restore was run.

## Storage and safeguards

Snapshot **2026-09-05 10:59:08Z**, including its final accounting receipt:

| Measure | Bytes |
| --- | ---: |
| Gross original bytes retired | 2,269,432,865 |
| Three new authoritative archive copies | 110,993,855 |
| Entire new batch: archives + metadata/tooling/proofs | 113,142,020 |
| Nine new authority indices | 9,587 |
| **Net logical bytes reclaimed** | **2,156,281,258** |
| Affiliation class before, including prior audit/pilots/sample | 2,282,922,617 |
| Same class after, including new authority/proofs | 126,641,359 |
| All retained evidence | 7,799,190,261 |
| Eight scoped Atlas workspace roots | 1,879,165,793 |
| **Combined scoped local footprint** | **9,678,356,054** |
| Cumulative proof retention, within 1 GiB | 949,239,041 |

No duplicate savings are added again to compression savings. Existing small pilot
archives/copies are still charged. Git/test/documentation metadata may drift after
the snapshot. No physical/APFS space reclamation is claimed.

PA-052's fresh source/sample/code-pinned admission reserved 208 MiB, including a
192 MiB hard archive cap and 16 MiB metadata allowance; projection 1,066,960,027
bytes fit the 1 GiB ceiling. A previous task's **+153-byte tooling-script**
inventory discrepancy was fresh-hashed and classified REVIEW with both old/new
pins. Its earlier 07:14:17Z modification and subsequent accounting supplement
predate this task. No historical file was changed to satisfy admission, and this
exception does not admit changed scientific payloads.

Largest temporary expanded file: 1,128,564,601 bytes; restoration is sequential.
The archive + metadata transport kits (111,104,069 bytes) were removed only after
exact retained-copy comparison, and all resolver-expanded files were removed.
Those temporary removals are **not** counted as original evidence savings.
Retained kit metadata, plans, checksums and receipts allow later rehydration.
Visible-handle checks found none before retirement; process visibility is not
universal and local hashes do not prove independent-host backup durability.

Production worker processing still writes authoritative `PaperAffiliation` state,
not duplicate full-corpus JSONL/recovery twins. New creation/adoption functions
refuse production; call-boundary tests cover their packaged names. Snapshot/JSON
history can still grow; this is not a Full Physics capacity measurement. The
combined 5 GB budget remains **FAIL**, migration remains **NO-GO**, and public
metric activation remains withheld.

## Evidence, validation and next action

Local receipts are under sibling
`physics-atlas-evidence/affiliation-archive-batch-2026-09-05/`:
`candidate-inventory.json`, `dependency-review.json`, `budget-replay-twins/`,
`current-authority-compatibility.json`, each group's descriptor/archive/manifests/
reader proof/retirement result/kit metadata, `post-retirement-health.json` and
`final-accounting.json`. Exact deleted paths and recovery descriptors are in each
`retirement-result.json`; artifacts are local evidence, not stored in Git.

Restore instructions: reconstruct a group's isolated kit from `kit-metadata/`,
copy its retained gzip into the matching `archive/` path, then use the retained
plan with `backend/tools/prove_affiliation_archive.py --plan ...
--plan-sha256 ... --kit ... --output <new receipt>`, under the retained OS-denial
profile. A normal consumer uses the current sidecar and context-managed resolver;
it need not recreate the proof runner. Never edit an old manifest to name gzip.

**432 focused tests pass**; Ruff lint/format (142 files), strict mypy (86 source
files) and whitespace checks pass. Tests cover byte integrity, failure closure,
original-absent/twin recovery, current callers, attribution/institution/provenance
equivalence, scientific eligibility and production boundaries. Final commit and
CI status are recorded at handoff; existing release tags remain unchanged.

Smallest next action: separately scope a **read-only provider-capture dependency
and payload-reference compatibility review**. That class measures 2,811,032,515
evidence bytes / 1,472 files, or 2,819,208,251 bytes including eight retained
workspace pages. Counts use existing inventory/stat metadata only. Do not begin
provider/researcher processing, another cleanup or Full Physics from this result.
