# Atlas Physicus repository context

Atlas Physicus is the canonical product name within Tech Echo Physica. The
primary GitHub repository and frontend package are `atlas-physicus` (PA-050).
Preserve historical names/releases and deployed compatibility identifiers: Python
package/import/CLI names, schemas, services, databases, environment variables,
artifact identifiers and API URLs. See the naming audit in
`docs/production-deployment.md` before changing any operational identifier.

The nominal 5 GB storage budget covers **all persistent Atlas data combined**:
PostgreSQL, archives, required history/metadata and retained backups/copies.
Externalizing bytes is not total savings unless the representation is smaller.
Report ephemeral/peak workspace separately; never call retained history free.
See PA-048 and the current total-storage review before planning migration/load.

Before any major implementation, architecture, deployment, or release task, read these files in order:

1. `docs/PROJECT_STATE.md` — factual current state and immediate task;
2. `docs/DECISIONS.md` — durable product and architecture decisions;
3. `docs/roadmap.md` — canonical release sequence and current milestone;
4. `docs/HISTORY_SUMMARY.md` — compact milestone provenance and historical context;
5. `docs/WORKLOG.md` — recent completed work, validation, and unresolved issues.

Then read the technical document directly relevant to the task. Do not infer that deployment-ready infrastructure is publicly operating: verify the backend, worker, database, API URL, update status, and frontend configuration before making a live-data claim.

## Current status — archived

PA-066: the owner ended active development on 12 September 2026 and authorized
preserving the static public map and source, updating the official website,
and retiring Railway after a verified recoverable database backup. This
supersedes PA-065 and earlier active milestone/release instructions. Do not
resume acquisition, certification or feature development without a new owner
request. See `docs/PROJECT_STATE.md` and `docs/ARCHIVE.md`.

## Context maintenance

After substantial work:

- update `docs/PROJECT_STATE.md` with factual state, limitations, and the immediate next action;
- update `docs/DECISIONS.md` only when a durable decision is added or deliberately superseded;
- update `docs/roadmap.md` when milestone status or sequencing changes;
- append a concise recent entry to `docs/WORKLOG.md`; when older entries stop
  being active context, compress them under `docs/archive/` and update
  `docs/HISTORY_SUMMARY.md` instead of accumulating duplicate detail;
- cite actual commits and validation results, and distinguish uncommitted work from released work.

Never invent a deployment URL, credential, successful update, metric result, or production status. Synthetic, pilot, fixture-live, and provider-backed live data must remain explicitly labeled and isolated.
