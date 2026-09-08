# Atlas Physicus

Atlas Physicus is open scientific infrastructure for exploring the geographic,
temporal, and institutional structure of physics research ecosystems through a
map-first interface.

Part of Tech Echo Physica, a Tech Echo Collective project family for exploring physics through research mapping, knowledge structures, and interactive physical systems.

Atlas Physicus focuses on research mapping, alongside Illuminatio Physica for
knowledge structures and Theatrum Physicum for interactive physical systems.
The source repository is `atlas-physicus`. Historical names and release records
remain intact; deployed compatibility identifiers are documented in the
[deployment guide](docs/production-deployment.md#naming-and-deployment-compatibility).

It is not a ranking, recommendation, or prediction system, and it is not a
replacement for scholarly databases such as arXiv or INSPIRE.

[Open the public Atlas](https://atlas.techecho.org/)
· [View the source repository](https://github.com/Tech-Echo-Collective/atlas-physicus)

## What it does

Atlas Physicus supports a continuous exploration path:

```text
Physics → research field → time → world → country → institution
→ research group → researcher / papers
```

The system connects geographic views to canonical research entities,
paper-time affiliations, source evidence, and versioned scientific methods.

## Current live status

The public deployment uses the released `v3.0.5-alpha` architecture and a
bounded `hep-th-v1` provider scope through the production FastAPI/PostgreSQL
service. INSPIRE and arXiv supply literature evidence; ROR, ORCID, and Crossref
are used only through constrained identifier-led workflows.

The repository contains the deterministic Metric System v1 framework, explicit
evidence certification and a separate 0–100 Atlas Scale. Scientific validation
and the compact five-metric dataset launch remain incomplete. The
five live metric layers remain jointly withheld, so the
public map does not substitute zero or synthetic values for missing live
observations. Full Physics expansion and v3.1 have not started.

### Minimum remaining launch work

On September 8, 2026, the owner authorized separate validation of **observed
evidence coverage** and **unresolved attribution uncertainty** (PA-059).
The opt-in `observed-attribution-coverage-v1` adapter now measures completeness
conditional on actual conserved entity×field mass. Unknown attribution remains
in the complete source projections and exported possible-contribution bounds;
it is neither reassigned nor silently zeroed. These bounds are not statistical
confidence intervals or metric-score intervals and cannot be summed across
entities. Source-wide coverage still uses the full paper mass and the unchanged
90%/95% evidence gates. Old proof versions remain unchanged; normalization and
cross-field aggregation reject mixed coverage policies. This is an
admission-contract change, not a metric formula change or evidence that the
five-layer launch has passed.

PA-060 separately versions **complete source enumeration**, not identity approval.
The opt-in `enumerated-source-year-with-unresolved-identity-v1` retains every
captured paper, including identity conflicts with their original `needs_review`
decisions and full unknown attribution mass. Such conflicts cannot become
calculator inputs or measured citation identities. Exact dates, provenance,
conservation and source-wide 90%/95% gates still apply; mixed source-year policy
versions are rejected. This prevents one retained identity conflict from falsely
implying that an otherwise fully enumerated provider year was not read completely.

PA-062 implements the owner's subsequent explicit approval of **limited observed
release**. The new opt-in `conditional-observed-source-year-v1` admits completely
enumerated years without claiming that the whole source passes its quality gate.
Original source coverage, insufficient states and unknown mass remain unchanged
and publicly disclosed with annual cutoffs. The release authority binds actual
published observations and normalization peers: each observed entity×field×period
must pass the same 95% canonical-institution / 90% evidence thresholds and all
other v1 scientific rules. All five compatible metrics must still be released
together. Neither missing source evidence nor a favorable sample can substitute
for these exact proofs. The ordinary legacy full-source gate remains unchanged.

These values describe the recorded ecosystem, not complete-ecosystem estimates.
Momentum retains its backward-looking formula, but annual coverage changes may
affect apparent change. The map keeps a concise conditional-scope notice, while
Data provenance shows original annual coverage/mass, states and measurement
cutoffs, recorded citation-reference populations, and eligible/ineligible
normalization-peer counts once per cohort. The Physics overview initially shows
the explicitly labeled recorded Nuclear Physics subset; original observation
field identities are never copied or relabeled as full-Physics values. Selecting
an unsupported field still stays neutral, and the immutable timeline uses the
years actually available in the dataset. Missing fields, entities and years
remain neutral. A completed policy
adapter is not itself a successful scientific release or deployment.

The bounded launch runner now checkpoints only completed compact pages in its
single private temporary directory. A retry verifies the exact query, inventory,
versions and checksums; it never treats a conflicting source record as a missing
record. Contradictory primary/related DOI roles retain the entire linked identity
component as unresolved. Final export reconstructs the actual raw/normalized
proofs and retains compact historical facts, not recursive decision traces. It
also checks that the global map has a usable five-layer/composite country and
more than one supported historical period before writing release assets.

Previous PA-059 validation: 130 backend tests, 33 frontend compatibility tests, lint,
type checking and the production build pass. No new scientific data was acquired
or activated; all 36,456,719 bytes of isolated local test/build material were removed.

The six bounded traversals are complete: 2018–2023 contain
2,306 / 2,412 / 2,787 / 2,580 / 2,545 / 2,728 records respectively (15,358 total).
Enumeration is not certification or public activation. Preparation, common-window
citation measurement, exact-five calculation and final dataset validation must
finish before the public source is switched. Repeated pure coverage/structural
checks now reuse exact immutable inputs within the existing bounded build cache;
canonical JSON token emission is faster without changing scientific SHA-256,
thresholds, formulas or missing-data semantics. No additional persistent provider
store is introduced.

The latest bounded evidence still leaves these completion requirements:

- Resolve or explicitly withhold the seven identity-conflicted components among
  2,306 inspected 2018 nuclear-physics records without dropping their evidence.
- Finish source-quality certification and disclose its result. The complete
  current 2018 traversal contains **2,306** records, with **95.906%** paper-time
  affiliation presence and **68.614%** resolved institution mass before canonical
  conflict exclusion. These are acquisition measurements, not certification
  coverage or a metric release. PA-062 permits only genuinely eligible observed
  partitions to proceed, retaining the insufficient source verdict separately.
- Establish six certified historical years for the candidate 2018–2023 window,
  mature comparable citation cohorts, and the required eligible normalization
  peers. Impact retains its 24-month maturity, 50-paper reference-cohort minimum
  and 90% citation coverage; Activity, Impact and Momentum retain their respective
  30-peer requirements.
- Generate real, co-located observations for all five dimensions, verify the
  preserved raw metrics and versioned 0–100 values, then publish the compact
  dataset and regression-test the timeline, composite and existing Atlas UX.

Use existing certification, calculators and frontend interfaces, with only
targeted evidence acquisition and necessary adapter fixes. Mandatory human review,
Full Physics completeness and legacy evidence-storage cleanup are **not** launch
prerequisites. Unsupported fields, entities and periods remain missing; no partial
metric activation is allowed. Current measurements and exact limitations are in
the [minimum launch integration report](docs/validation/minimum-launch-integration-2026-09-06.md);
implementation and deployment status belong in [project state](docs/PROJECT_STATE.md).

## Core principles

- Describe research ecosystems without ranking their scientific worth.
- Keep missing, unresolved, immature, and measured-zero evidence distinct.
- Preserve source, identity, mapping, method, and dataset provenance.
- Keep synthetic, pilot, fixture-live, and provider-backed live data isolated.
- Use the map as an exploration interface, not a prestige dashboard.
- Publish no metric layer before its scientific and production gates pass.

## Scientific attribution

Scientific attribution follows six durable rules:

1. Paper-time affiliations are the primary attribution evidence.
2. Current profiles never retroactively overwrite historical affiliations.
3. Persistent researcher identifiers support identity resolution and
   cross-checking; they do not determine contribution weight.
4. Institution names resolve to canonical entities while useful subunit labels
   are retained.
5. Ambiguous or unresolved affiliations remain unresolved rather than guessed.
6. Missing evidence never silently becomes zero.

Fractional Attribution v1 gives each paper a total mass of one, divides it
equally among authors, then equally among each author's valid paper-time
affiliations when no reviewed numeric contribution rule exists. Unresolved mass
is withheld rather than reassigned. Author order and corresponding-author
status do not change the weight. See the
[Scientific Attribution Policy](docs/scientific-attribution.md).

## Metric philosophy

Metric System v1 contains exactly five descriptive dimensions:

- Research Activity;
- Research Impact;
- Collaboration / Connectivity;
- Research Diversity;
- Research Momentum / Sustainability.

Calculations are field-specific before any coverage-aware Physics-wide
aggregation, and each dimension uses an appropriate documented normalization.
The five dimensions activate only as one coherent system. They do not measure
scientific value, quality, prestige, or future potential.

Users may define an explicitly confirmed five-weight exploratory composite whose
weights total 100%. It is not an official default or an “overall scientific
score.” Detailed formulas and limits belong in the
[Metric System v1 specification](docs/metrics-spec-v1.md) and
[validation protocol](docs/metric-validation.md).

## Architecture

The currently operated API-backed path is:

```text
INSPIRE / arXiv / reviewed identifier lookups
  → immutable source evidence and update lineage
  → normalization and conservative entity resolution
  → paper-time attribution and canonical field mapping
  → PostgreSQL canonical graph and compact provenance
  → explicit scientific evidence certification
  → exact eligible populations → certified raw metrics
  → metric-specific normalization → Atlas Scale
  → evidence-certified Joint Activation Gate
  → FastAPI → APIRepository → map-first React application
```

The frontend uses React, TypeScript, Vite, MapLibre GL JS, and Zod. The backend
uses Python, FastAPI, SQLAlchemy, Alembic, and PostgreSQL.

Full Physics loading additionally requires the independent Storage Budget
Gate. Normal public map/API reads continue on the bounded production dataset.

The first compact dataset launch reuses this scientific processing and publishes
only certified, versioned Atlas observations and necessary entity/provenance
metadata to the existing frontend. Raw provider and intermediate build material
is ephemeral, not a new permanent scholarly mirror. That dataset is not yet the
ordinary public source; implementation support does not imply deployment.

The compact frontend export keeps the complete entity catalog and observations
in its bounded core. Existing authorship, paper-time affiliation and external
resource records are retained once in immutable on-demand gzip shards, not
duplicated profile snapshots. `atlas-ui-shards-v1` verifies compressed and decoded
SHA-256/size, exact relationship indexes and known author counts. Each decoded
shard is limited to 4 MiB, the lossless dictionary index to 8 MiB, and the release
to 512 relationship shards; the core's 64 MiB cap is unchanged. Export streams
validated per-paper relationships and writes only final compressed assets inside
the single temporary build directory after the whole-output disk-budget check.
This changes delivery only, not evidence, metrics, missing semantics or coverage.
Existing source-native researcher IDs are retained exactly and escaped only in
navigation URLs; source record and snapshot references survive UI validation.

## Data and provenance

The normal public path is the integrated live API. Checked-in synthetic
fixtures and the bounded historical INSPIRE pilot remain available only for
tests, reproducibility, and explicit fallback; they are never silently mixed
with provider-backed live data.

Raw provider categories remain separate from the versioned Atlas field
ontology. Required source evidence, mappings, identity decisions, attribution
shares, normalization parameters, and dataset lineage are retained—either as
queryable canonical state or content-addressed warm/cold artifacts—so derived
results can be reconstructed. Provider data remains subject to its own terms
and licensing.

Conditional observed datasets use `unambiguous-observed-native-researchers-v1`
for institution/country researcher counts: conflicting or repeated native IDs
and ambiguous ORCID links are quarantined, while independently supported IDs
remain usable. Original author positions, conflicting assertions, and fractional
attribution denominators are retained. This certifies an observed subset, not a
complete byline; an empty subset means unknown people, not zero authors. The
minimum-five-researcher requirement and all five metric formulas/thresholds are
unchanged. Public profiles use the same admitted subset. See the
[automatic certification methodology](docs/automatic-certification.md).

## Public access

- Atlas: <https://atlas.techecho.org/>
- Production API: <https://physics-atlas-api-production.up.railway.app/api>
- Source: <https://github.com/Tech-Echo-Collective/atlas-physicus>

The dedicated Atlas hostname replaces the inherited
`https://techecho.org/Physics-Atlas-Web/` Pages path. During DNS and Pages
propagation, that legacy path and the underlying
`https://tech-echo-collective.github.io/Physics-Atlas-Web/` origin may remain
reachable. The backend accepts all three browser origins for this bounded
transition; remove the legacy origins only after the new hostname and redirects
have been verified in production.

## Documentation

- [Project state](docs/PROJECT_STATE.md), [durable decisions](docs/DECISIONS.md),
  [roadmap](docs/roadmap.md), [history summary](docs/HISTORY_SUMMARY.md), and
  [recent worklog](docs/WORKLOG.md)
- [Architecture](docs/architecture.md) and
  [live-data architecture](docs/live-data-architecture.md)
- [Scientific Attribution Policy](docs/scientific-attribution.md)
- [Physics Field Ontology v1](docs/field-ontology.md)
- [Metric System v1 specification](docs/metrics-spec-v1.md)
- [Metric System v1 validation](docs/metric-validation.md)
- [Scientific evidence certification](docs/evidence-certification.md) and
  [hot/warm/cold storage architecture](docs/storage-architecture.md)
- [Entity resolution](docs/entity-resolution.md),
  [data sources](docs/data-sources.md), and
  [knowledge graph](docs/knowledge-graph.md)
- [Production deployment](docs/production-deployment.md)

## Contributing

Issues and focused pull requests are welcome. Changes should preserve the
no-ranking/no-prediction boundary, explicit missing-data semantics, provenance,
dataset isolation, deterministic tests, and the current bounded acquisition
scope. Read the project state and durable decisions before proposing
architecture or methodology changes.

## License and citation

Atlas Physicus is released under the [Apache License 2.0](LICENSE). Copyright
(c) 2026 Tech Echo Collective; attribution information is preserved in
[NOTICE](NOTICE).

If Atlas Physicus supports research or teaching, cite it using
[CITATION.cff](CITATION.cff).
