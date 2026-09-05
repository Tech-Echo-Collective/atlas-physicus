# Entity-resolution validation

Entity resolution decides whether source evidence refers to a canonical
research entity. It does not evaluate scientific contribution. Atlas Physicus
prefers a reviewable unresolved record to an unjustified merge.

## Outcomes and workflow state

Resolution outcomes are `matched`, `unresolved`, and `ambiguous`. The separate
review workflow state `needs_review` means that a human decision is still open;
it must not be presented as another resolution outcome.

Tracked methods are authority/external identifier, canonical name, alias,
historical name, source-record identifier, fuzzy/contextual evidence, manual
review, and insufficient metadata. Public aggregate status contains counts,
not raw names or provider payloads.

An unresolved record can mean either:

- **metadata quarantine:** required evidence is missing or invalid, so the
  record cannot enter the canonical graph; or
- **identity abstention:** a source assertion exists, but available authority,
  name, alias, or contextual evidence does not justify a match.

Those categories have different remediation paths and must not be collapsed
into a resolver error rate.

## Deterministic review sample

The validation framework builds a bounded, reproducible review manifest. It
stratifies by source, entity type, outcome, method, and evidence reason, then
orders candidates by a SHA-256 key derived from the sample version and
resolution ID. Input order therefore cannot change the selected sample.

The manifest is for human labeling; it never treats the resolver's own output
as truth. A reviewer records the supported canonical answer or correct
abstention, the evidence inspected, and a decision note. Common names,
historical institution names, aliases, fuzzy/contextual cases, authority
conflicts, ORCID/INSPIRE consistency, ROR mappings, and deprecated identifiers
belong in the challenge set.

## Measures

Where sufficient independent labels exist, report:

- match precision;
- recall over cases independently labeled resolvable;
- coverage of resolvable cases;
- abstention correctness;
- unresolved and ambiguous rates;
- method-specific slices; and
- confidence calibration in predeclared confidence bins.

Precision, recall, and decision-rate statistics require at least 30 independent
labels by default; confidence calibration separately requires at least 30
eligible predicted matches. Smaller deterministic fixtures may lower these
thresholds only to test arithmetic and must not be reported as scientific
validation. Overall unresolved rate is an operational fact, not proof of low
accuracy. Unlabeled cases never enter a truth denominator.

## Versioning and reversibility

Samples carry a sample version; reports carry a validation-method version;
resolution decisions carry a resolver version and source-snapshot lineage. A
future re-resolution must append a new decision and explicitly supersede the
older review state. It must not mutate history to improve reported statistics.

## Current production limitation

The v3.0.5 evidence snapshot has authority-confirmed paper/researcher matches
and explicit abstentions but no independently labeled live truth sample.
Precision, recall, and confidence calibration are therefore intentionally
withheld. Institution aliases and ROR mapping cannot yet be validated from the
canonical live graph because no canonical institutions or affiliations have
been materialized.
