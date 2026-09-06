# Minimum launch integration — 2026-09-06

Status: bounded implementation/diagnostic evidence, **not a production activation
or complete-year certification**. Final validation, commit and deployment status
belong in `PROJECT_STATE.md` and `WORKLOG.md`; none is inferred from this report.
No Railway mutation, bulk scientific replay or Full Physics load is represented.

## Scope and implementation

PA-056 permits a first certified ontology-branch slice with all five Metric System
v1 dimensions together, not partial metric activation or a broad-Physics claim.
The fixed trial recipe is nuclear Physics, exact INSPIRE `preprint_date` years
2018–2023, with the existing `nucl-th`/`nucl-ex` leaf catalog. Six-year acquisition
has not been established by the single-page observations below.

The integration adds source-bound date/researcher admission, conserved branch
Diversity projection, scoped release/export boundaries and strict PA-057 ROR
affiliation matching. Partial-field structural conservation and known-field
admission are separated from field coverage. These are existing-method
completion paths, not new formulas or lower scientific thresholds. Source/test
changes passed the focused validation recorded in the recent worklog. Tests are
not real data certification, and local success is not a CI/deployment assertion.

## Exact 2018 page diagnostic

The successful read was 2026-09-06 **02:23:48.120576–02:23:52.961847 UTC**:

```text
document_type:article and (subject:Theory-Nucl or subject:Experiment-Nucl)
and preprint_date:2018-01-01->2018-12-31
size=250, page=1, sort=mostrecent
```

Requested metadata: `control_number,titles,preprint_date,authors,arxiv_eprints,
inspire_categories,document_type,dois,publication_info`. The provider reported
2,306 hits; this read contains only 250 records (IDs 1711749 through 1704480),
5,407,843 response bytes. SHA-256:
`5a840d3f77e2a9f8c6a084ff1a2d4375ef510761d4fe10c39390221472fb94dc`.

| Measured sample property | Result |
| --- | --- |
| Existing whole-ledger automatic field state | 206 certified; 44 insufficient |
| Rejected records with positive known mapped leaves | 44; wholly unmapped: 0 |
| Known mapped paper-equivalent mass | 229.4 / 250 = 91.76% |
| Explicit unmapped mass | 20.6 / 250 = 8.24% |
| Additional known mass lost by whole-record rejection | 23.4 |
| Maximum field-conservation error | 0 |
| Paper-native affiliation presence, author-fraction weighted | 240.896505620816 / 250 = 96.35860225% |
| Structured affiliation presence, author-fraction weighted | 193.529749289715 / 250 = 77.41189972% |
| Author appearances | 8,313 total; 7,930 structured; 8,259 structured or raw |
| Complete paper-level researcher identity state | 243 certified; 7 conflicted |

Affiliation figures measure source presence, **not canonical institution coverage**.
Each paper contributes the fraction of its author appearances having that evidence;
an author-count percentage would overweight large collaborations. All seven
identity-conflicted papers repeat native IDs across positions; two also contain
conflicting identifiers within appearances. No ORCID was observed co-asserted for
multiple native identities in those failed papers. People were not inferred or merged.

Unmapped label occurrences within the 44 rejected records overlap:

| Label | Occurrences |
| --- | ---: |
| General Physics | 21 |
| Instrumentation | 17 |
| Condensed Matter | 14 |
| Quantum Physics | 6 |
| Data Analysis and Statistics | 5 |
| Computing | 3 |
| Other | 2 |
| Accelerators | 1 |

Every rejected record also contains supported mapped evidence. The intended fix
preserves those known weights and the explicit unknown remainder; it does not map
these labels by guesswork. Existing metric-population code already distinguishes
known contribution from possible contribution including unresolved mass. Merely
marking whole partial papers certified would overstate coverage and is not the fix.
INSPIRE-embedded arXiv labels were present, but were not relabeled as independently
acquired arXiv evidence.

This page cannot establish whole-year coverage, canonical identity-merge success,
citation comparability, normalization peer counts or five-metric readiness. The
payload had been discarded before a later canonical-merge diagnostic was requested;
no such result is claimed here. A preliminary attempt stopped after fetching due
to a diagnostic connector-constructor error; the corrected bounded repeat above
completed. Neither attempt wrote a payload file.

## Bounded ROR cross-check

An initial held-out diagnostic at **01:47:41–01:47:48 UTC** selected five distinct
institution targets from a 25-record page, each author appearance having one raw
and one structured affiliation. Independent comparison targets were explicit
INSPIRE institution→ROR identifiers. Eleven requests returned 210,376 bytes
(largest response 116,590 bytes):

- Two matches accepted and agreed with the explicit target.
- Three withheld: one lacked a unique ROR choice; two ROR `chosen` suggestions
  disagreed with the explicit target and were correctly withheld.
- Zero accepted-ID mismatches. Five cases do not establish global precision or
  activation-eligible canonical coverage.

Review then tightened geographic corroboration to mandatory country evidence and
replaced open subunit prefixes with a conservative whole-clause grammar. The final
strict method was rechecked at **01:54:56.789537–01:54:59.897420 UTC** using only
paper 2698774, two explicit institution records and two ROR queries (five requests,
49,547 bytes total, maximum response 18,788 bytes):

| Paper author index (zero-based) | Explicit INSPIRE institution | Explicit ROR / accepted ROR | Final result |
| --- | --- | --- | --- |
| 8 | 904826 | 03cve4549 — Tsinghua University | Certified; exact Department of Physics clause, Beijing, China |
| 9 | 903920 | 00v5gqm66 — China Institute of Atomic Energy | Certified; exact institutional clause, Beijing, China |

Both actual source strings contain matching country/city evidence. Final receipt
digests, respectively:

- `46cc49df1f909594d41798e072884c2409e8482e00e000455dc7d8710e8842b3`
- `b197e83433d79507e337a69e4b7fe7f42535afdaf667e11d35fb158e2965be6b`

The paper metadata checksum was
`f862e3d9815d7184f4bb50fe053fd77d2be76985e4171b4fee7679fe475c9c07`.
ROR response SHA-256 values, respectively:

- `da1b99c9f62e4c588fc5c8250019b244af6dbea532bc32b63d89d3ac99de849c`
- `6ae9bf7a7210e264671bb42ec2d0c4823b3392389d9f9d29b96237203e773d36`

Official ROR guidance recommends `chosen` for automatic matching but acknowledges
incorrect matches. The bounded observations demonstrate why exact corroboration
and unresolved outcomes remain necessary. [Affiliation API](https://ror.readme.io/docs/api-affiliation),
[matching guidance](https://ror.readme.io/docs/matching).

## Same-sample known-identifier authority follow-through

Root's bounded follow-through at **02:25:25–02:27:07 UTC** used the same 250-paper
sample, resolving its observed institution references only: 746 INSPIRE institution
records and 546 ROR records, within 1,293 total requests and 7,480,032 response bytes.
No HTTP errors or source files were reported. These are targeted authority reads,
not new paper-population acquisition or a complete-year proof.

Before the PA-058 granularity correction, certified canonical institution mass was
**122.847469436810 / 250 = 49.13898777%**, with 58 fully allocated papers. Reported
withheld assertion categories were:

| Reason | Assertions |
| --- | ---: |
| ROR parent absent from the supplied authority registry | 3,187 |
| No ROR link | 658 |
| Raw affiliation unresolved | 409 |
| Conflicting ROR evidence | 65 |
| Multiple ROR identifiers | 15 |
| Inactive identity | 12 |

Assertion counts are not paper-fraction percentages and must not be added to the
certified numerator. The largest failure category exposed a granularity issue:
requiring parent-rollup authority even when retaining the directly identified
ROR organization was the intended operation. ROR scope guidance distinguishes
independent organizations with their own records from ordinary internal departments.

PA-058 introduces an explicit exact-identity option, retaining parent links without
automatically rolling up or duplicating attribution. Legacy rollup remains intact;
missing, conflicting, multiple and inactive identity evidence is not excused. The
new path required focused validation and the fresh measurement below; the pre-fix
numbers were not relabeled as improved coverage.

### Post-fix measurement of the same sample

The subsequent exact-ID diagnostic ran **02:42:09.185042–02:43:50.366027 UTC**,
again reading the same 250-record query and its 746 INSPIRE/546 ROR targets. All
1,293 requests returned HTTP 200 with no redirects/errors; total response bytes
were 7,480,032 and the largest authority response was 36,603 bytes. The source page
remained 5,407,843 bytes, now with checksum
`8fd09960630792fc14cd9676726ff7ddcd3e55bc8d30b0ebdbb53d779dcd92e2`;
the timestamped request-receipt digest was
`a20aabeb153bf5403da61aba874cf54d9074bb6d502a88d0805d0d0379b44e93`.

Exact-identity retention raised allocated canonical institution mass to
**168.385899364154 / 250 = 67.35435975%**, an increase of 18.21537 percentage
points. There were 112 fully allocated, 75 partially allocated and 63 zero-allocated
papers. Native affiliation presence remained 96.35860225%; attribution conservation
error was exactly zero. **The 95% canonical coverage gate still does not pass on
this sample.** Raw matching was not acquired or applied in this diagnostic.

Remaining withheld mass is partitioned by exact reason set below; these rows are
disjoint, unlike counts of individual assertions:

| Reason | Paper-equivalent mass | Percentage of 250 |
| --- | ---: | ---: |
| Raw affiliation lacks resolved authority | 49.39616810 | 19.75846724% |
| Structured INSPIRE institution lacks ROR authority | 19.40692188 | 7.76276875% |
| Missing paper-time affiliation | 9.10349438 | 3.64139775% |
| Historical lifecycle requires dated resolution | 1.97519841 | 0.79007937% |
| Provider/paper ROR assertions conflict | 1.04329748 | 0.41731899% |
| ROR establishment is after the paper | 0.52740898 | 0.21096359% |
| Country missing/ambiguous | 0.08333333 | 0.03333333% |
| Multiple author-level ROR targets for one row | 0.07827807 | 0.03131123% |

The exact withheld total was 81.614100635846. Hypothetically resolving both raw
and missing-ROR classes alone would reach only 94.87559574% on this page, not a
gate PASS. This is a sample bound, not a whole-year claim or a reason to guess
unresolved lifecycle/conflicting evidence.

Alternate identifiers among the affected INSPIRE records were SPIRES (91), HAL
(8) and GRID (5), with no ISNI/Wikidata observed. Two high-value exact crosswalk
candidates are INSPIRE 903099 → `grid.473340.7` and 902703 → `grid.463917.e`.
Their historical organization/lifecycle facts still require verification. A name,
hierarchy or unverified lookup table is not authority evidence; this diagnostic
did not acquire a ROR crosswalk or infer parent identity.

## Whole-2018 membership and identifier-role diagnostic

Root's bounded 2018 collection ran **02:34:18–02:43:59 UTC**: 2,306 records over
231 bounded pages, 78,269,258 response bytes, maximum page 6,052,980 bytes. All
2,306 source dates were exact. Known field mass was
**2,153.9 / 2,306 = 93.40416305%**, with the remaining field mass explicit. The
canonicalizer retained all 2,306 components: 2,269 matched and 37 `needs_review`.
The typed source-year proof remained withheld on those structural identity
decisions; acquisition completion and passing field coverage were not a year PASS.

A preceding attempt with 100 records per page stopped when a subsequent response
exceeded the existing 8 MiB page bound. It was discarded, not skipped over or
combined with differently sized pages; the successful whole-query restart used
10 records per page. The byte figure above describes that successful traversal,
not total network traffic across all diagnostics. Neither attempt wrote payloads.

The pre-role-fix proof identifiers were:

- source-year: `source-year-49ebaae7457ea18290d60a492542674125099f8d1a0b4993d5003ae79f11b116`
- capture: `b4db58775be18e8c874704d97c9de3cbbde7ce2bc9ce09a7cbc2086bf26f70cd`

Both had `insufficient_evidence` status, not positive certification. There were
zero exact-date blockers and 128 unresolved paper-equivalent researcher units,
including the 37 identity-unresolved papers. Institution/country units were
deliberately unresolved for all 2,306 papers because this whole-year collection
did not acquire institution authority; those values are not a measured canonical
institution coverage result.

A lower-payload identity-only recheck at **02:54:38.120463–02:54:49.655339 UTC**
read ten pages of the same query (`size=250`, no authors), verified 2,306 unique
records against the reported total, and reproduced those component states. It
transferred 2,570,119 bytes, largest page 281,805 bytes; receipt digest:
`1be1295f24cdfd96eb84204881b97864fe27df0e5b1b3a524c663f8630af4b1e`.

The 37 pre-role-fix conflicts consisted of:

- 29 with one non-erratum DOI plus explicitly labeled erratum DOI(s);
- six other multiple-DOI cases without a single non-erratum target;
- two arXiv-identifier conflicts.

All components retained one exact source date. The existing normalizer already
collapsed 1,413 duplicate/case-normalized DOI occurrences; those are not new
conflicts. INSPIRE 1705646 illustrates the role issue: publication DOI
`10.1103/PhysRevLett.122.122001` and an explicitly labeled erratum DOI
`10.1103/PhysRevLett.124.199901` were incorrectly treated as interchangeable paper
identifiers. Conversely, 1710487 supplies two distinct `material: publication`
DOIs; that is not resolved merely by recognizing errata.

### Verified source-role correction

After source-role-preserving extraction, a final observable recheck ran
**03:04:01.192657–03:04:13.537628 UTC**, again using ten metadata-only pages of
the same query. It transferred 2,570,119 bytes, maximum page 281,805 bytes; receipt
digest: `3a687938b079362e316a95f4005911f0906be13fa6c18239721c344820c189de`.
The diagnostic was bounded to 3 MiB and wrote no payload files. This recovery read
followed a dispatched recheck whose tool result was lost during context compaction;
no unobserved result is used as evidence.

All 2,306 source IDs were retained, with zero construction failures or dropped
projections. All components retained one exact date. **2,299 components matched;
seven remained `needs_review`**, resolving 30 of the former 37 conflicts without
treating explicit erratum/addendum identifiers as the original paper's identity.
Related-document assertions remain provenance-linked compact facts. The remaining
cases are explicit, unresolved source assertions:

| INSPIRE ID | Remaining assertion conflict | Targeted authority finding; no resolution applied |
| --- | --- | --- |
| 1677161 | arXiv `1803.05701` / `1806.03050`; DOI `10.1103/physrevlett.121.042701` | [arXiv administrators explicitly identify the first as a withdrawn duplicate of the second](https://arxiv.org/abs/1803.05701). A narrow exact duplicate/replacement adapter could consume this evidence; none is implemented. |
| 1615387 | arXiv `1803.01322` / `1809.03846`; DOI `10.5506/aphyspolb.48.1279` | [The reply](https://arxiv.org/abs/1803.01322) explicitly discusses [the original publication](https://arxiv.org/abs/1809.03846). These are different document roles, not aliases; shared related DOI cannot justify merging them. |
| 1710487 | Publication DOIs `10.1088/0022-3727/42/2/025102` / `10.1088/1361-6471/aaf5dc` | [The first DOI registers a 2008 liquid-crystal-device article](https://api.crossref.org/works/10.1088%2F0022-3727%2F42%2F2%2F025102); [the paper's arXiv metadata](https://arxiv.org/abs/1812.08513) links the second, a hadron-physics publication. This is unrelated-work contamination, not an alias. |
| 1662925 | Publication DOIs `10.1134/s0044451018110056` / `10.1134/s1063776118110067` | [arXiv explicitly describes Russian/English translation publications](https://arxiv.org/abs/1803.06254), but no exact Crossref DOI-pair relation was found, and [the publisher says the article is published in the original](https://link.springer.com/article/10.1134/S1063776118110067). Do not promote translation context to verified DOI equivalence. |
| 1683814 | Publication DOIs `10.1103/physrevc.99.014321` / `10.1103/prc.99.014321` | [arXiv](https://arxiv.org/abs/1807.09294) and Crossref identify the first. The second returned 404 from Crossref and DOI.org without redirect: probable malformed assertion, not an authoritative alias proof. |
| 1693607 | Publication DOIs `10.1140/epja/i2018-12606-3` / `10.3847/1538-4365/aada4a` | [arXiv links the nuclear freeze-out article](https://arxiv.org/abs/1809.03881); [the second DOI registers an astronomy catalog](https://api.crossref.org/works/10.3847%2F1538-4365%2Faada4a). Distinct publications, not equivalent identifiers. |
| 1646733 | Unspecified-material DOIs `10.15407/ujpe62.10.0835` / `10.15407/ujpe62.10.835` | [arXiv](https://arxiv.org/abs/1801.02488) and Crossref identify the zero-padded DOI. The other returned 404 from both authorities without redirect; do not infer equivalence by inserting a zero. |

Similar-looking identifiers do not establish equivalence; no target was chosen
by spelling, publication preference or guesswork. This identifier-only recheck
does not repeat researcher/affiliation certification or generate a complete-year
certificate. The earlier withheld source-year hash remains a historical failed
proof, not a certificate updated by these new counts.

The targeted authority check used **25 logical reads**: 16 directly measured
Crossref/arXiv-API/DOI-header requests and nine official metadata/abstract pages
through web retrieval. The direct requests transferred **121,142 bytes**, maximum
27,236 bytes; web-page transfer bytes were not measured and are not included in
that total. Direct outcomes were ten HTTP 200, four 404 and two 429 responses.
The 429 responses represent unavailable service evidence, never missing scientific
evidence or a certification decision. One bounded Crossref retry succeeded;
the arXiv API batch remained unavailable, while official abstract metadata was
read separately. No full text, payload file, code change or scientific resolution
was produced. All seven records remain unresolved under the current rules.

## Safety and remaining work

### Existing coverage-bound policy is not an arithmetic bug

The current entity-specific possible denominator can assign all globally
unresolved mass `U` to each candidate entity for its conservative coverage bound.
With known entity mass `K`, the 95% bound requires `K/(K+U) >= .95`, or `K >= 19U`.
In a simple common-field cohort of 30 disjoint entities this implies
`U / total <= 1/(30*19+1)`, approximately **0.17513%**. This conditional scenario
is not the whole-year coverage measurement above. It shows why the current
worst-case rule is stricter than the nominal source-global 95% rule.

Existing tests and method intentionally encode that possible-mass bound.
Separating source-global coverage, observed entity evidence and retained
uncertainty bounds therefore needs an explicit versioned policy decision. The
question is pending; no unknown mass has been removed or reallocated, no entity
threshold lowered and no new coverage-policy version enabled in this change.

All diagnostic payloads were processed in memory and discarded; these probes wrote
no scientific files, caches or payload archives. The report retains compact facts
and hashes, not a replay bundle. A later mutable provider response is not guaranteed
byte-identical; hashes are observation bindings, not recovery of discarded bytes.
Temporary validation/build work was confined to
`/private/tmp/atlas-minimum-launch.eAjJt3`. Final cleanup removed this exact
directory, 1,475 regular files totaling **129,412,818 logical bytes**, plus 81
temporary symlinks. The maximum observed filesystem allocation was **114,958,336
bytes**; logical and allocated sizes differ. This was below 2 GB; it is not a
claim about total RAM or provider-transfer bytes. The directory is absent; no
unapproved scientific/build leftovers remain. Legacy evidence was not touched.

Final local validation: **420 focused backend tests**, **139 frontend tests**,
**seven pipeline tests**, full Ruff lint/format, strict mypy over 102 source files,
TypeScript, ESLint and production build all pass. Factory optimization retains
identical certification objects/hashes and independent tamper rejection. The
loader rejects globally positive but non-co-located five-metric groups. Existing
Starlette deprecation and optional pilot chunk warnings are unchanged. CI status
is recorded in the worklog after the validated source is pushed.

At **03:10:33 UTC**, read-only health and observation requests returned HTTP 200,
healthy API/database, expected `https://atlas.techecho.org` CORS and **zero public
metric observations**. Web commit/pin/configuration were not changed. No live
dataset was generated, no layers activated and no deployment success is claimed.
The retained-scientific-evidence export field is a descriptor, not verification
that a future published artifact can actually be recovered; the publisher must
perform that check before any eventual activation.

Real complete canonical years, authority-resolved institution denominators, mature
common-session citation cohorts, eligible normalization peers and exact-five
branch/entity/period observations remain to be demonstrated. The 91.76% mapped
mass and two accepted institution matches are sample diagnostics, not permission
to activate any public layer or claim a successful launch.
