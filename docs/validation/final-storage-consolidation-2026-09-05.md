# Atlas Physicus — final bounded storage consolidation

2026-09-05; baseline `main` = `3b30124716e3b4ffdf6faf31c9ddcfa88638a394`,
[green CI](https://github.com/Tech-Echo-Collective/atlas-physicus/actions/runs/33962228728).
Local storage investigation only: no Railway access, acquisition, broad replay,
production migration, policy/metric change, activation or tag movement.
All sizes are decimal bytes/MB/GB unless explicitly labelled MiB/GiB.

## Inventory before mutation

The read-only classification completed at **11:22:22Z**, before creating the
new audit/pilot directory. Evidence: **7,799,190,261 bytes / 5,505 files**.
The same eight explicitly scoped workspace roots occupy **1,879,370,818 bytes**;
combined **9,678,561,079 bytes**. Workspace drift since the prior snapshot is
205,025 bytes. Unrelated projects/user files and symlink targets are excluded.

| Evidence class | Files | Bytes | Role / dependency / treatment |
| --- | ---: | ---: | --- |
| Provider captures | 1,472 | 2,811,032,515 | Original JSON/XML page evidence, acquisition manifests and record locators; direct-path readers. Archive candidates and path-bound copies. |
| Researcher evidence | 9 | 1,467,739,702 | JSONL appearance/identity evidence, source links and unresolved states; historical/paired readers still require original paths. |
| Canonical paper outputs | 8 | 863,394,600 | Versioned replay/paired JSONL, not the production database; historical artifact bindings remain required. |
| Source occurrences | 8 | 833,496,688 | Ordered provider occurrence/provenance JSONL; historical replay inputs/locators. |
| Five authoritative archives | 5 | 676,543,045 | Both distinct certification histories and three affiliation contents; **KEEP** existing descriptors/indices/restore proofs. |
| Field evidence | 8 | 669,195,022 | Preserved classification, weights and explicit unmapped mass; historical JSONL readers. |
| Attribution ledgers | 2 | 250,341,360 | Exact stored attribution/conservation evidence; path-bound replay twins. |
| Expanded paired decisions | 7 | 84,063,754 | Historical v1/v2 decisions and comparison copies; unsupported paired authority contract. |
| Citation evidence | 16 | 82,263,710 | Observations/cutoffs and source links; historical/paired readers. |
| Other metadata, cold objects and small evidence | 3,970 | 61,119,865 | Detailed disjoint categories in the census; retain authority responses, manifests, proof inventories, scripts and uncertain inputs. |
| **Total** | **5,505** | **7,799,190,261** | No prospective savings deducted. |

The workspace also retains eight provider pages (8,175,736 bytes), one researcher
file (1,154,251), and one paired ledger (12,233,044). They are counted there,
not silently added to the evidence table. Scientific JSONL is not classified as
production hot state merely because it contains canonical IDs.

| Disjoint evidence retention | Files | Bytes |
| --- | ---: | ---: |
| ARCHIVE_CANDIDATE | 2,256 | 4,896,598,646 |
| REGENERABLE by named exact-copy representative | 2,088 | 2,188,020,759 |
| KEEP | 1,157 | 709,577,854 |
| REVIEW | 3 | 4,992,546 |
| RETIRE_CANDIDATE, not cleared | 1 | 456 |

REGENERABLE here means recoverable by copying a named retained identical file,
**not permission to break an active or historical path**. The three REVIEW
inputs are prior small affiliation pilots. The 456-byte unpublished partial
artifact is deliberately retained; this batch performs no miscellaneous cleanup.
Historical hashes plus fresh path/size checks classify the whole inventory;
fresh checksums additionally cover the entire retained proof scope, all ten
researcher files including workspace, and 58 bounded provider bodies. No claim
is made that every multi-gigabyte scientific class was freshly parsed or replayed.

## Amplification and remaining contracts

- Provider captures are dominated by Condensed Matter: **1,424 pages /
  2,761,978,099 bytes**, comprising 133 INSPIRE JSON pages (2,464,019,505 bytes)
  and 1,291 arXiv XML pages (297,958,594). Whole original responses retain
  embedded references and figure metadata as well as authors/affiliations and
  provenance. In one bounded INSPIRE example, serialized reference metadata is
  12,511,194 bytes and figure metadata 1,715,928, versus authors 603,528;
  these are sample-specific component measurements, not corpus-wide savings.
  Forty exact redundant official-page occurrences add **40,878,680 bytes**
  including workspace, or 32,702,944 within evidence. Different v1 capture
  hashes remain separate evidence despite coincidentally equal byte totals.
- **102 INSPIRE pages / 2,101,164,886 bytes exceed the existing 16 MiB payload
  limit**; the largest is 23,453,291 bytes. Condensed Matter's old page manifest
  also lacks the per-page acquisition timestamp/HTTP lineage required by the
  current payload envelope. Do not fabricate it from partition completion time.
- Researcher evidence has four distinct contents across ten paths including
  workspace. Fresh hashes verify **735,577,938 duplicate bytes**, including
  one **729,806,683-byte** historical/corrected twin. This is repeated per-paper
  appearance/authority/provenance JSON, not that many unique researchers.
- Paper, occurrence, field, attribution and citation replay twins repeat
  expanded data and provenance. Their manifest identities and historical
  scientific outcomes remain distinct; compression or content equality does
  not supersede these contracts.
- The authority resolver currently admits historical decisions and affiliation
  roles only. Researcher, provider, paper, occurrence, field and citation readers
  do not acquire archive authority from a generic `ArtifactRef`. Paired decision
  ledgers retain the previously documented unsupported role/path/schema boundary.
  Extending all these contracts is separate compatibility work, not an implicit
  permission to discard files in this batch.

Thus all remaining expanded scientific groups are **retirement NO-GO** under
the unchanged authority contract. Small metadata is KEEP; compressing it offers
little benefit while increasing recovery dependencies. Existing archives remain
KEEP. No shared resolver/integrity defect has been demonstrated.

## Bounded probes and retirement matrix

Two existing payload envelopes were reused without recompression. Four complete
small files from official paired-v2 manifest `e7b99d22…` were compressed with
deterministic gzip and stored using the existing `ArtifactRef` / filesystem
store. Their full manifest file SHA remains
`7b4c1839346b32c06a59db6ffe3f2facbcde5cbcc739f2d48865a67e96ccdf73`.
No new resolver or scientific path was introduced.

| Representative | Original bytes | Archive bytes | Archive | Restore | Stored scientific/provenance equivalence | Authority | Dependencies | Retirement |
| --- | ---: | ---: | --- | --- | --- | --- | --- | --- |
| INSPIRE page, 88 records | 3,986,634 | 955,327, existing | PASS | PASS | PASS | FAIL* | FAIL* | NO-GO |
| arXiv page, 100 records | 199,018 | 48,875, existing | PASS | PASS | PASS | FAIL* | FAIL* | NO-GO |
| Researcher appearances, 2,101 rows | 1,154,251 | 134,088 | PASS | PASS | PASS | FAIL* | FAIL* | NO-GO |
| Canonical papers, 474 rows | 283,071 | 23,567 | PASS | PASS | PASS | FAIL* | FAIL* | NO-GO |
| Field ledgers, 474 rows | 1,021,298 | 29,500 | PASS | PASS | PASS | FAIL* | FAIL* | NO-GO |
| Citation observations, 170 rows | 136,937 | 8,675 | PASS | PASS | PASS | FAIL* | FAIL* | NO-GO |

**FAIL\*** means unsupported historical authority/direct-path dependency, not
corrupt bytes. The four candidate descriptors deliberately fail the existing
type/schema whitelist; they are labelled probes, never installed as authority.
Logical IDs use the existing type + schema version + original SHA contract.
The retained plans bind every exact source path/hash/size/row count and compressed
reference. None of the large researcher/replay twins or oversized provider pages
was recompressed. Their NO-GO is not disguised as a measured compression result.

Independent subprocesses consumed copied archive/metadata kits while the OS
denied original evidence and network access. The provider proof additionally
denied the previous restore workspace and local DB files. All six original
SHA-256/byte lengths match. Existing INSPIRE/arXiv parsing and normalization
produce identical ordered records, IDs and provenance. The four JSONL files
preserve complete ordered semantic, identity, state, version and provenance
fingerprints, including missing/null/zero distinctions and stored field weights.
This preserves scientific **inputs**, not new certification or coverage results;
no corpus canonicalization, certification or calculator execution was performed.

The researcher sample retains 70 ORCID identifier occurrences, 1,585 insufficient
and 516 needs-review appearances, with zero canonical researchers. Dated ORCID
employment/current-homepage assertions are absent in this file and stay absent;
paper/source links to separate historical affiliation evidence remain intact.
The distinct large historical conflict states are not replaced by this small
sample. Existing certified-only admission remains mandatory and unchanged.

Six tiny fault cases fail closed: missing archive, invalid reference, compressed
checksum mismatch, decoded checksum mismatch, truncated gzip and decoded-size
mismatch. The first nested-sandbox launches were blocked operationally; they did
not indicate archive corruption. Recovery retried with the OS denial controls
intact, rather than weakening isolation or altering frozen archive code.

The four new archives total **195,830 bytes** versus 2,595,557 original bytes.
That is a bounded representation measurement, **not reclaimed storage**: originals
stay. Ratios are not applied to the 729.807 MB researcher twins or to unrelated
schemas. Successful transport kits are disposable only after exact retained-copy
checks; no expanded scientific file is written during these in-memory restores.

## Scaling boundary

The current worker/engine writes source/canonical/lineage ORM state; it does not
emit provider A/B captures, researcher JSONL replay comparisons, paired ledgers
or recovery/rollback twins. Development/test guards and production import/call
boundary tests remain in force. Fixed-source historical archive restoration is
different from generating a new full-corpus trace.

PA-051/052 still require one reviewed sample/version proof, never sharding the
corpus into many proof jobs. The pinned 1,000-reference sample is unchanged.
Whole-file storage probes retain their own manifest scope; the sample ID is
proof context, not a claim that every page equals that sample. The unchanged
**1 GiB cumulative proof budget** counts archives, old versions, copies and
REVIEW files. A shared **16 MiB** allowance covers this entire new audit/pilot
directory, including inventories and scripts. There is no per-corpus proof term
in the future model.

This is not a complete compact production schema. Existing raw snapshots,
researcher occurrences, normalized attributes, provenance and update history
still scale; necessary citation history, final certification persistence and
backup/restore costs remain unmeasured. Production migration remains NO-GO.

## Budget interpretation

Final census: **11:48:50Z**, including its own receipt and all retained new
outputs. Every baseline evidence path/size remains present; all nine prior
affiliation retirements and authority-index pins remain unchanged. All three
new transport-kit paths are absent after verified cleanup. No pre-existing
artifact was removed.

| Final measured boundary | Bytes |
| --- | ---: |
| Evidence, 5,537 files | 7,804,064,942 |
| Eight scoped workspace roots | 1,879,388,032 |
| **Combined local footprint** | **9,683,452,974** |
| Gross original bytes removed | **0** |
| New retained audit/probe bytes, including 195,830 archive bytes | 4,874,681 |
| **Net persistent bytes reclaimed** | **−4,874,681** |
| Cumulative proof retention, cross-cutting rather than additive | 954,113,722 |
| Remaining proof-budget headroom | 119,628,102 |

The footprint **increased by 4.875 MB** because proof/inventory metadata and
small archives were retained while originals stayed. Temporary-kit removal is
not counted as reclamation of old evidence. No physical/APFS saving is claimed.
Documentation, Git and test-cache bytes may drift after this timestamp.

| Disjoint final storage category | Bytes |
| --- | ---: |
| Live canonical/hot scientific state | **Not measured**; none included in this local tally |
| Cold scientific archives/objects, including retained copies and unpromoted probes | 689,656,892 |
| Required expanded scientific history and offline canonical/replay state | 7,011,320,584 |
| Remaining validation traces, samples, support and tooling | 127,633,600 |
| Provenance/authority/restore metadata | 12,953,766 |
| Development workspace, dependencies, Git and stopped private test DB | 1,772,483,781 |
| Retained caches/generated development outputs | 69,404,351 |
| **Local tally** | **9,683,452,974** |

The private DB is development state, not the operated Railway database.
Cache/regenerable labels confer no deletion permission. Counting evidence plus
the three retained historical proof workspaces, but excluding ordinary development
state, gives **7,841,564,842 bytes** of required local history/proof persistence.
This is already a lower boundary for total production-relevant retained data;
the live DB, durable backups and unmeasured operational costs are additional,
not zero. The 954.114 MB proof-budget tally overlaps several rows and is not
added again.

A reporting-only correction assigned 18 legacy `cold-store/cold` objects
(4,945,397 bytes) to cold archives instead of proof support. The first receipt
remains intact; `final-accounting-v2.json` records the correction and both
receipts' storage. No scientific data, codec, classification threshold or
production code was changed.

**STORAGE BUDGET GATE = FAIL for the currently required retained representation.**
Evidence alone exceeds nominal 5,000,000,000 bytes, before production, backups,
workspace or headroom. Even conditional removal of all 2.188 GB of named
duplicate copies would leave approximately **5.611 GB** of baseline evidence;
those removals are not authorized or credited.

Future final-layout readiness remains **WITHHELD**, not PASS. Preserve the
25% contingency, 3.0 GB steady ceiling and 4.0 GB peak ceiling, plus actual
per-volume limits. Unknown costs cannot be replaced by zero or hidden inside
contingency. Local recovery does not establish independent-host durability.

### Conservative capacity scenarios, not deployment approval

The known compact **component** estimate per 10k hypothetical papers is
**2,008.406 MB**: hot scientific/index state 1,920.784 MB, cold inputs/audit
75.172 MB, and restore/catalog metadata 12.451 MB. It combines previously
measured PostgreSQL prototypes and a different earlier production mix:

```text
hot(N)      = N × (141680640 / 823 + 6373376 / 474 + 3072000 / 474)
cold(N)     = N × (2506196 / 474 + 1056945 / 474)
metadata(N) = N × 590165 / 474
H           = 7,841,564,842 retained local history/proof bytes
subtotal    = H + 185,466,880 fixed non-public DB bytes
                + hot(N) + cold(N) + metadata(N)
planning    = 1.25 × subtotal
```

The 474-paper compact certification archive preserves its SQL/scientific
semantics but does **not** replace an original historical JSONL hash. Its use
here is a candidate new production-layout component, not retirement credit for
any old ledger. The new four-file pilot ratios are not extrapolated to large
historical files. Inputs/method limitations are in the earlier
[native storage](storage-amplification-2026-09-05.md),
[payload](payload-reference-recovery-2026-09-05.md) and
[total-storage](production-storage-design-review-2026-09-05.md) reports.

N below means **hypothetical additional paper populations alongside retained
history**, not the current corpus size or an inferred Full Physics population.
The conservative no-sharing assumption may overcount future reusable bytes;
unproved deduplication or historical retirement receives no credit. The fixed
history term includes bounded proofs once, never a per-paper A/B trace.

| Additional papers, scenario only | Hot GB | Cold GB | Metadata GB | Total with fixed history/DB GB | With 25% contingency GB |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 10,000 | 1.921 | 0.075 | 0.012 | 10.035 | 12.544 |
| 50,000 | 9.604 | 0.376 | 0.062 | 18.069 | 22.586 |
| 100,000 | 19.208 | 0.752 | 0.125 | 28.111 | 35.139 |
| 250,000 | 48.020 | 1.879 | 0.311 | 58.237 | 72.796 |

These are bounded extrapolations, **not measured final-schema capacity**.
Future comparable citation/history generations, eligible review/metric state,
independent backups/replication, final descriptor/schema costs, cloud allocation
and WAL/rewrite/restore peaks remain unresolved. The 474/823-paper ratios are
below the existing representative 10k-final-schema requirement. No safe larger
paper capacity is certified; a 500k scenario adds no defensible evidence.

No Full Physics load, scientific coverage work, metric activation or v3.1 follows
from this report. The smallest separate next action is a **narrow provider-page
authority/binding design review** covering oversized legacy pages and genuinely
missing acquisition metadata, with no migration, acquisition or deletion.

## Evidence and validation boundary

Complete local audit/probe material is retained under sibling
`physics-atlas-evidence/final-storage-consolidation-2026-09-05/`, not in Git.
Historical manifests and earlier reports are unchanged. Repository changes are
documentation only; no application, storage resolver, codec or scientific code
is altered. **387 focused fixture tests pass** (373 storage/recovery/guardrail
tests plus 14 budget tests) for artifact stores, payloads,
dual-read/recovery, compact state, decision/affiliation archives and resolvers,
current historical readers, sample/admission and production scaling guardrails.
Focused storage Ruff checks pass. Local probes are additional evidence, not CI
scientific reprocessing. New-commit CI is reported at handoff.

| Local evidence file, under the new batch directory | SHA-256 |
| --- | --- |
| `baseline-census.json` | `92a439c8a4275c5369a80d34cc2f6c56abe828d837588c59fa3133ffd4bc87a5` |
| `retention-inventory.json` | `f62ee7039366c0e13b9627faf90c425d5979bc19bfb13e889df1e914d38f5dda` |
| `retention-admission.json` | `c3b056c75b73f706b04004dad16a433e2295ab2647adbc3a86d2ceb72d4632d8` |
| `provider/provider-recovery-report.json` | `7f766d6fedb8ab024f40d727eeb6f458d3806d71ec97724a2408de822a403396` |
| `researcher-history/reader-proof.json` | `2ad6c6d695672de56af628b412eb8f022dc8743e953477b660ea132818107e99` |
| `researcher-history/receipt.json` | `3dbbfd5d72b70b355409da75776da075da4e509ed991dabc570beab8d237a77f` |
| `final-accounting-v2.json` | `4302db6f0fb303dba31b3ded9480d61889e6b26bc5c50f5cac7988beeb656edf` |

The frozen probe plans/scripts and retained kit metadata describe exact original
hashes, artifact references, versions and restore commands. Reconstruct a fresh
isolated kit from them and invoke the pinned recovery-only verifier with OS
original-read/network denial. No original path may be replaced by the rejected
candidate descriptors. This remains a local same-host proof, not an independent
backup or production deployment. The full inputs and archives are deliberately
not committed to Git.

Railway was not contacted. Its last documented read-only health is the earlier
02:26:03Z observation, not a fresh production-health claim. No public observations
were generated by this work; existing scientific activation stays withheld.
