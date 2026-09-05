# Production PostgreSQL storage sizing — 2026-09-04

Status: **current production healthy; Full Physics Storage Budget Gate
WITHHELD**

Audit cutoff: `2026-09-04T14:52:44.590740Z`
Method: read-only PostgreSQL and filesystem statistics from the authenticated
Railway PostgreSQL service console. No variables were revealed and no database,
service, or filesystem state was changed.

## Capacity and current use

| Measure | Bytes | Display value |
| --- | ---: | ---: |
| Mounted PostgreSQL volume capacity | 4,685,873,152 | 4.364 GiB |
| Volume used (`df`) | 499,077,120 | 10.65% |
| PostgreSQL database | 306,534,079 | 292.3 MiB |
| Public relations, including TOAST and indexes | 296,837,120 | 283.1 MiB |
| Public table storage, including TOAST | 241,106,944 | 229.9 MiB |
| Public indexes | 55,730,176 | 53.1 MiB |
| `pg_wal` | 167,809,024 | 160.0 MiB |

Database operation was healthy at the audit point: three of 500 connections,
one active and two idle, 99.18% cache hit rate, 579 dead rows, and no obvious
dead-row pressure in the available statistics. Twenty indexes totaling about
23.9 MB had no recorded use,
but the statistics horizon and lazy endpoint workload are not sufficient
evidence to remove them.

## Scientific state counts

| State | Rows |
| --- | ---: |
| Papers | 823 |
| Researchers | 8,485 |
| Authorships | 9,013 |
| Paper-time affiliation shares | 15,838 |
| Profile `Affiliation` rows | 0 |
| Canonical institutions | 0 |
| Paper-field mappings | 1,627 |
| Citation edges/observations | 0 |
| Evidence certification records | 0 (schema not deployed) |
| Metric observations | 0 |
| Raw entity records | 15,708 |
| Source snapshots | 27 |
| Identity resolutions / reviews | 15,708 / 440 |
| Authority identifiers | 22,598 |
| Search terms | 87,078 |
| External resources / checks | 5,577 / 5,238 |
| Dataset updates / update runs | 27 / 27 |

## Largest relations

Sizes include each relation's TOAST data; `total` also includes indexes.

| Relation | Table bytes | Index bytes | Total bytes |
| --- | ---: | ---: | ---: |
| `raw_entity_records` | 91,275,264 | 3,661,824 | 94,937,088 |
| `source_snapshots` | 60,407,808 | 49,152 | 60,456,960 |
| `entity_search_terms` | 17,612,800 | 27,164,672 | 44,777,472 |
| `paper_affiliations` | 29,663,232 | 5,103,616 | 34,766,848 |
| `authority_identifiers` | 10,305,536 | 6,676,480 | 16,982,016 |
| `identity_resolutions` | 9,986,048 | 4,423,680 | 14,409,728 |
| `authorships` | 4,415,488 | 3,129,344 | 7,544,832 |
| `researchers` | 4,964,352 | 1,073,152 | 6,037,504 |
| `paper_fields` | 3,637,248 | 286,720 | 3,923,968 |
| `papers` | 2,793,472 | 229,376 | 3,022,848 |

The 27 snapshot payloads contain 58,122,374 logical bytes. Raw-record payloads
contain 69,097,623 bytes, with a further 7,686,552 bytes of normalized
attributes. The two raw relations occupy 155,394,048 bytes, or 52.35% of all
public-relation storage, and duplicate provider evidence at batch and row
levels. They are therefore the first cold-storage candidates. This finding
does not authorize deleting or rewriting current production history.

## Empirical multipliers

These ratios describe the current bounded `hep-th-v1` production shape; they
are not scientific corpus estimates.

| Per canonical paper | Rows |
| --- | ---: |
| Researchers | 10.310 |
| Authorships | 10.951 |
| Paper-time affiliation shares | 19.244 |
| Field rows | 1.977 |
| Raw records / identity resolutions | 19.086 each |
| Authority identifiers | 27.458 |
| Search terms | 105.806 |
| Direct paper relationships total | 32.173 |
| Broader evidence/identity/resource auxiliary rows | 185.112 |
| Combined measured relationship/evidence multiplier | 217.284 |

Dividing the complete current database size by 823 yields an observed ratio of
372,459 bytes per canonical paper, or 3.725 decimal GB per 10,000 papers. This
ratio includes fixed catalog/database effects and is not a clean marginal
per-paper cost. A lower-bound hot-only proxy that excludes both raw relations
is 171,863 bytes per paper, or 1.719 decimal GB per 10,000 under the same
division. It is deliberately called a lower bound: certification, compact
citation history, and metric rows do not yet exist.

## Scenario projections

These are linear capacity scenarios, not claims about the number of Physics
papers. They include current fixed database/WAL overhead but not the 25%
Storage Budget Gate contingency. The no-raw proxy scales public-relation bytes
after removing the two raw relations and retains the full 202,240,000 bytes of
measured volume use outside public relations as fixed overhead; it does not
silently discard PostgreSQL catalog or filesystem overhead.

| Canonical papers | Current layout | No-raw lower bound |
| ---: | ---: | ---: |
| 10,000 (minimum future representative sample) | 3.917 GB | 1.921 GB |
| 47,726 (existing hep-th staging scale) | 17.968 GB | 8.405 GB |
| 129,464 (existing Condensed Matter staging scale) | 48.412 GB | 22.452 GB |
| 250,000 | 93.307 GB | 43.168 GB |
| 500,000 | 186.422 GB | 86.134 GB |
| 1,000,000 | 372.652 GB | 172.065 GB |

Applying the gate's required 25% estimation contingency gives the following
capacity-test values. These remain illustrative scenarios, not a reviewed Full
Physics target-population estimate.

| Canonical papers | Current layout + 25% | No-raw lower bound + 25% |
| ---: | ---: | ---: |
| 10,000 | 4.896 GB | 2.401 GB |
| 47,726 | 22.460 GB | 10.506 GB |
| 129,464 | 60.515 GB | 28.065 GB |
| 250,000 | 116.634 GB | 53.960 GB |
| 500,000 | 233.028 GB | 107.668 GB |
| 1,000,000 | 465.815 GB | 215.081 GB |

Raw-payload externalization is necessary but not sufficient. Search/authority
fan-out, JSON-heavy relationship state, index shape, and canonical evidence
representation need representative-load profiling and bounded optimization
before a field-scale or Full Physics load.

## Storage Budget Gate result

For the actual 4,685,873,152-byte volume, the v1 ceilings are:

- steady-state upper bound (60%): 2,811,523,891 bytes;
- peak upper bound (80%): 3,748,698,521 bytes.

Result: **WITHHELD**. Current use is healthy, but the live 823-paper sample is
below the required 10,000-paper representative measurement, the final
certification/citation schema has not been load-tested, backup/restore evidence
is incomplete, and every evaluated field-scale projection exceeds the safe budget.
No broader load is authorized.

This read-only audit is a sizing observation, not a passing gate artifact. A
future assessment must additionally bind measured sample/fixed bytes and its
environment/timestamp, the exact reviewed target-population manifest, the v1
deterministic projection inputs, and a typed reviewed backup-to-isolated-restore
attestation. Content checksums protect those reviewed records from mutation;
they do not independently demonstrate that the physical measurement or restore
occurred.
