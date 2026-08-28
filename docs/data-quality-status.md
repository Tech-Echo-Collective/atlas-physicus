# Data quality and public status

Physics Atlas exposes a compact methodology/status surface behind the existing
information control. It is evidence about the current dataset, not an
operations dashboard and not a scientific score.

The public surface reports:

- dataset kind, version, acquisition scope, and last successful update;
- bounded source health and consecutive-failure state;
- matched, unresolved, ambiguous, and open-review identity counts;
- experimental or visualization-ready metric-definition versions; and
- the explicit rule that missing data is not zero.

The backend keeps raw snapshots, provider cursors, update runs, review evidence,
and resource checks for audit. Public status exposes aggregates and sanitized
state only; it does not publish raw provider payloads, review names, checkpoint
URLs, credentials, or internal errors.

`Healthy` means that the most recent bounded connector state has no recorded
consecutive failure. It does not prove completeness. `Targeted` means a source
is only queried for known reviewed IDs; it must not imply that every entity is
covered. A successful update likewise does not imply that metric or geographic
activation gates have passed.

Metric definitions marked experimental are visible as methodology, but their
observations are not visualization-ready. Only explicitly validated
implementation statuses may enter the map or user-defined composite. The
frontend does not substitute synthetic or pilot observations into a live
dataset.
