# Production deployment runbook

## Status and safety boundary

`compose.production.yml` is a provider-neutral, single-host deployment definition for PostgreSQL, the one-shot Alembic migration, FastAPI, the incremental worker, and Caddy automatic HTTPS. It is configuration only: the repository contains no production hostname, credentials, server binding, managed database, or deployed backend.

The production stack fixes `PHYSICS_ATLAS_ACQUISITION_SCOPE` to `hep-th-v1`, the only scope accepted by the current backend. That policy queries `subject:Theory-HEP` in INSPIRE and `cat:hep-th` in arXiv. ROR uses targeted record retrieval and is disabled when `PHYSICS_ATLAS_ROR_RECORD_IDS` is empty. Populate that list only with ROR IDs already evidenced by the bounded corpus; it must not become a registry-wide import.

## Host and DNS prerequisites

- One maintained Linux host with Docker Engine and the Docker Compose plugin.
- A public DNS A/AAAA record for the API hostname pointing to that host.
- Inbound TCP 80 and TCP/UDP 443 permitted. PostgreSQL and FastAPI ports must remain unpublished.
- Outbound HTTPS permitted for ACME and the approved scientific providers.
- A host firewall, provider/network rate protection, monitoring, log retention,
  and an operator-managed encrypted off-host backup destination.
- Enough persistent storage for PostgreSQL and Caddy certificate state.

Caddy obtains and renews the TLS certificate automatically. The only browser origin accepted by FastAPI is `https://tech-echo-collective.github.io`. An origin contains scheme and host only, so the `/Physics-Atlas-Web/` path must not be added to the CORS value.

## Configure and start the API

On the production host, from a reviewed Physics Atlas checkout:

```bash
cp .env.production.example .env.production
chmod 600 .env.production
```

Replace every placeholder in `.env.production`. Use a long random PostgreSQL password and its URL-encoded form in `PHYSICS_ATLAS_DATABASE_URL`. Set the real API hostname and an ACME contact address. ORCID values are optional and are used only for known-ID retrieval.

Validate interpolation before creating containers:

```bash
docker compose --env-file .env.production -f compose.production.yml config --quiet
docker compose --env-file .env.production -f compose.production.yml build api migrate
```

Start the database, migration, API, and HTTPS edge first, without the worker:

```bash
docker compose --env-file .env.production -f compose.production.yml up -d db migrate api caddy
docker compose --env-file .env.production -f compose.production.yml ps
```

Confirm both the direct service health and public TLS path:

```bash
curl --fail --show-error --silent https://API_HOSTNAME/api/health
curl --fail --show-error --silent https://API_HOSTNAME/api/updates/status
```

Replace `API_HOSTNAME` explicitly; do not paste a shell command containing unreviewed environment substitution. The health response must report both service and database status as `ok`. A new database can legitimately have no successful source update before the worker is enabled.

## Start bounded ingestion after the activation gate passes

Before starting the worker, confirm the backend tests prove that INSPIRE and arXiv requests are bounded to `hep-th`, unsupported scope IDs fail closed, ROR is skipped without configured targets, and fixture/live provenance cannot mix in one database. Use an empty `PHYSICS_ATLAS_ROR_RECORD_IDS` value for the first live run; add reviewed, corpus-linked ROR IDs later.

After those checks and a staging ingestion pass, start the worker:

```bash
docker compose --env-file .env.production -f compose.production.yml up -d worker
docker compose --env-file .env.production -f compose.production.yml logs --follow worker
```

After a successful batch, inspect `/api/dataset` and `/api/updates/status`.
Dataset provenance must report `acquisitionScope: hep-th-v1`, and each source
cursor must expose the expected `scopeVersion`. Treat a missing or different
scope as an activation failure rather than relabeling the data.

The existing scheduler wakes hourly. INSPIRE and arXiv are due daily, ROR weekly, advisory locking prevents concurrent workers, and checkpoint state is stored in PostgreSQL. ORCID and Crossref remain targeted known-ID lookups rather than scheduled global sources.

Do not configure the public frontend yet. First verify real source snapshots, provenance, identity-resolution state, update status, restart/checkpoint behavior, and that no live metric scores are written without reviewed formulas.

## Activate the GitHub Pages frontend

After the HTTPS API and bounded live dataset are verified, build `Physics-Atlas-Web` with:

```text
VITE_ATLAS_API_URL=https://API_HOSTNAME/api
```

This value is a public build-time URL, not a secret. Configure it in the deployment repository workflow/environment; never copy database or provider credentials into `VITE_*` variables. Validate a Pages deep link, browser CORS, loading/error recovery, and an actual API request before making live data the normal public source.

## Operations

Inspect service state and structured JSON logs:

```bash
docker compose --env-file .env.production -f compose.production.yml ps
docker compose --env-file .env.production -f compose.production.yml logs --since 1h api worker caddy
```

Restart one stateless service at a time. The database volume and Caddy volumes are durable. Never use `docker compose down --volumes` in production.

Exercise and record recovery behavior in staging before activation: provider timeout, rate limiting, duplicate payloads, malformed records, partial update, worker restart, API restart, and database restart. Confirm checkpoints resume without duplicate canonical records.

## Backup

Create a PostgreSQL custom-format dump before every deployment and on a regular
schedule:

```bash
install -d -m 700 /var/backups/physics-atlas
umask 077
docker compose --env-file .env.production -f compose.production.yml exec -T db sh -c 'pg_dump --format=custom --no-owner --username="$POSTGRES_USER" --dbname="$POSTGRES_DB"' > /var/backups/physics-atlas/physics-atlas.dump
```

This command writes an **unencrypted local file**. Protect it immediately with
the operator's approved encryption and transfer tooling, verify the encrypted
off-host copy, restrict permissions on the transient file, and remove that file
under the host's reviewed retention procedure. The repository does not invent
an encryption key, cloud destination, or retention policy.

Record the source commit, migration revision, UTC time, and checksum next to the
protected backup. Periodically restore backups into an isolated non-production
database and verify `/api/health` plus representative queries; an untested dump
is not a recovery plan.

Back up the Caddy data volume only if certificate continuity is operationally important. Caddy can obtain a replacement certificate when DNS and ACME limits permit.

## Restore

Restoring with `--clean` replaces database objects and is destructive. Stop the worker and API, verify the exact target, preserve a second current-state backup, and restore only during an approved recovery window:

```bash
docker compose --env-file .env.production -f compose.production.yml stop worker api
docker compose --env-file .env.production -f compose.production.yml exec -T db sh -c 'pg_restore --clean --if-exists --no-owner --username="$POSTGRES_USER" --dbname="$POSTGRES_DB"' < /var/backups/physics-atlas/physics-atlas.dump
docker compose --env-file .env.production -f compose.production.yml up -d migrate api
```

Run the health/status checks and inspect representative provenance and identity records before restarting the worker.

## Rollback

1. Stop the worker so it cannot advance checkpoints during the rollback.
2. Preserve a fresh database backup and current service logs.
3. Check out the previously verified commit without moving or force-updating any release tag.
4. Review migration compatibility before starting old application images. Do not blindly downgrade schema.
5. If the old application is incompatible with the current schema, restore the matching pre-deployment backup instead.
6. Rebuild and start `migrate`, `api`, then `caddy`; validate health and representative reads.
7. Restart the worker only when its code, schema, and bounded scope match the restored database.

Keep the public Pages build pointed at the last known-good HTTPS API during a backend rollback, or remove `VITE_ATLAS_API_URL` in a reviewed frontend deployment to return to the retained static/pilot fallback. Do not silently mix fallback and live observations.
