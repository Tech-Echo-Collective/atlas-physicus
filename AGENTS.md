# Physics Atlas repository context

Before any major implementation, architecture, deployment, or release task, read these files in order:

1. `docs/PROJECT_STATE.md` — factual current state and immediate task;
2. `docs/DECISIONS.md` — durable product and architecture decisions;
3. `docs/roadmap.md` — canonical release sequence and current milestone;
4. `docs/WORKLOG.md` — recent completed work, validation, and unresolved issues.

Then read the technical document directly relevant to the task. Do not infer that deployment-ready infrastructure is publicly operating: verify the backend, worker, database, API URL, update status, and frontend configuration before making a live-data claim.

## Current milestone

The active milestone is **v3.0.4 Production Activation**. Do not begin v3.0.5 or introduce unrelated product features while this milestone is active.

## Context maintenance

After substantial work:

- update `docs/PROJECT_STATE.md` with factual state, limitations, and the immediate next action;
- update `docs/DECISIONS.md` only when a durable decision is added or deliberately superseded;
- update `docs/roadmap.md` when milestone status or sequencing changes;
- append a concise entry to `docs/WORKLOG.md` without rewriting prior entries;
- cite actual commits and validation results, and distinguish uncommitted work from released work.

Never invent a deployment URL, credential, successful update, metric result, or production status. Synthetic, pilot, fixture-live, and provider-backed live data must remain explicitly labeled and isolated.
