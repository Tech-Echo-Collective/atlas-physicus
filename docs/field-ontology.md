# Physics Field Ontology v1

Status: **implemented classification foundation; not evidence of full-Physics
coverage or live metric readiness**.

Ontology version: `physics-field-ontology-v1`.

The Physics Atlas ontology is a stable internal vocabulary. Provider categories
remain source evidence and never become Atlas fields merely because a label
looks similar.

## Canonical hierarchy

```text
physics
├── hep                         High Energy Physics
│   ├── hep-th                  Theory
│   ├── hep-ph                  Phenomenology
│   ├── hep-ex                  Experiment
│   └── hep-lat                 Lattice
├── gr-qc                       Gravitation & Cosmology
├── astro-ph                    Astrophysics
├── cond-mat                    Condensed Matter
├── amo                         Atomic, Molecular & Optical Physics
├── quant-ph                    Quantum Science
├── nuclear                     Nuclear Physics
│   ├── nucl-th                 Theory
│   └── nucl-ex                 Experiment
├── plasma                      Plasma Physics
├── math-ph                     Mathematical Physics
├── stat-nonlinear              Statistical & Nonlinear Physics
└── bio-soft-interdisciplinary  Biological / Soft / Interdisciplinary
    ├── biophysics
    └── soft-matter
```

Branch nodes provide stable grouping without forcing unsupported detail.
`hep`, `nuclear`, and `bio-soft-interdisciplinary` are branches; their children
are direct canonical fields. The remaining root nodes are fields. This first
version deliberately avoids a deep, exhaustive taxonomy.

Every definition carries:

- a stable canonical ID and label;
- a description and aliases;
- an optional parent ID and node kind;
- deterministic display order;
- ontology version and provenance.

Aliases support discovery and review. An alias is not, by itself, provider
classification evidence.

## Direct assignments and parent aggregation

A provider rule assigns a paper to the exact Atlas target named by that rule.
A child assignment can later contribute to a parent-level view through a
versioned derived aggregation. The child and derived parent must not both be
counted as independent paper shares in the same calculation.

If a provider supplies only a broad category, a reviewed rule may assign the
broad branch without inventing a child. Conversely, an assignment to `hep-th`
does not silently assert membership in an unrelated sibling. The parent
relationship is structural, not a second provider classification.

## Provider-to-Atlas mapping

Current mapping versions:

- mapping catalog: `provider-field-mapping-v1`;
- field weighting: `provider-evidence-conservation-v2`;
- cross-provider reconciliation: `cross-provider-field-reconciliation-v1`;
- Atlas target ontology: `physics-field-ontology-v1`.

The boundary is:

```text
raw provider taxonomy
  → exact, versioned mapping rule
  → one or more canonical Atlas assignments
```

INSPIRE and arXiv are required live-source mappings for v1. Supporting rules
may exist for other providers, but they do not substitute for validation of
INSPIRE and arXiv coverage.

For every provider category, Physics Atlas retains:

- provider and provider taxonomy;
- exact raw category;
- primary, secondary, or unspecified role when supplied;
- matching rule ID, or explicit unmapped status;
- canonical target IDs;
- mapping, ontology, and weighting-policy versions;
- source metadata, uncertainty note, and uncalibrated confidence state.

Raw provider categories are never deleted after mapping. An unmatched category
stays visible as unmapped; it does not generate a guessed Atlas field.

### Multi-field papers

A paper may receive several canonical Atlas assignments. Duplicate rules or
provider categories supporting the same canonical field do not give that field
extra weight. When no reviewed evidence justifies unequal weights, the
conserved v2 ledger assigns:

```text
field share = mapped field mass / number of unique supported Atlas fields
```

Mapped field mass is one minus explicit unmapped mass. The mapped shares and
unmapped mass together total one. Primary and secondary roles remain
provenance and do not create an arbitrary permanent weight difference. A
future unequal policy must use a new, explicit policy version.

For example, a reviewed category can support both `astro-ph` and `gr-qc`; each
receives one half under the conserved v2 policy. This is classification
allocation, not paper-contribution attribution. It is multiplied by the
separate paper-time entity attribution only when a field-specific metric is
calculated.

### Cross-provider conservation

Provider classifications remain separate evidence records, but the selected
field-evidence ledger for one canonical paper must satisfy:

```text
Σ mapped canonical-field weights + explicit unmapped field mass = 1
```

Primary and secondary roles are preserved as provenance. A versioned,
configurable unequal policy may use them only after scientific justification;
otherwise the unique mapped Atlas fields receive equal shares of the mapped
mass. Evidence from a second provider can support or extend the unique field
set, but it cannot give the same paper another independent unit of mass.
Duplicate field support is collapsed without discarding its provider
provenance.

Cross-provider agreement is recorded as corroborating evidence, not silently
promoted to reviewed classification. Overlapping provider field sets can remain
multi-field; genuine unresolved conflicts enter `needs_review` rather than
being forced into one category. Crossref, OpenAlex, publisher or journal
metadata, abstracts, and keywords may contribute only when that source is
already integrated through a versioned evidence path. Their presence never
authorizes an unversioned inference.

If some provider evidence is unmapped, its share remains explicit ledger mass.
It is not reassigned to the mapped fields to make the source look complete. A
paper with no mapped field evidence has unmapped mass `1` and receives no
canonical field projection rather than an invented default field.

### Coverage and uncertainty

Mapping coverage is the proportion of unique supplied raw category evidence
matched by an exact rule. No supplied categories means coverage is missing,
not zero.
Exact rule matching is deterministic but does not provide a calibrated
probability that the scientific classification is correct. The provenance
therefore keeps uncertainty visible even for mapped categories.

The current rule catalog includes direct mappings for the deployed Physics
categories and conservative reviewed mappings where a source category spans
more than one Atlas field. It does not infer membership from provider prefixes,
free text, author affiliations, or citation networks.

## Evolution policy

The v1 IDs and meanings are immutable within `physics-field-ontology-v1`.
Corrections or semantic changes require a new ontology version and an explicit
migration/mapping record. Evolution must preserve:

- old raw provider evidence;
- the mapping rule used at calculation time;
- earlier paper-field assignments;
- reproducibility of prior metric observations;
- explicit split, merge, deprecation, and successor relationships.

Adding a field to a future ontology does not retroactively classify papers.
Those papers must be reprocessed under the new mapping version, with the new
result stored as a versioned derivation.

## Relationship to metrics

Metric calculation follows this order:

```text
paper-time entity attribution
× versioned paper-field share
→ field-specific raw metric
→ field-specific normalization
→ optional Physics-domain aggregation
```

The ontology supports that calculation but does not activate it. The present
live `hep-th-v1` acquisition scope is not representative Full Physics coverage,
and the broad ontology must not be used to imply that it is. In particular,
`hep-th-v1` cannot validate or activate production Diversity even when its
provider classifications are complete within the conditioned slice.

## Limitations

- Provider taxonomies encode different purposes and levels of granularity.
- Exact mapping rules can still be scientifically incomplete or debatable.
- Primary/secondary labels are provider-dependent and may be absent.
- Multi-label equal weighting is a transparent v1 convention, not a claim that
  the fields contribute equally to every paper.
- The ontology is intentionally broad and does not yet represent all specialty
  or interdisciplinary relationships.

Ontology and mapping tests verify canonical IDs, parent validity, acyclicity,
version consistency, raw-category preservation, multi-field conservation, role
preservation, cross-provider conservation, and explicit unmapped behavior.
