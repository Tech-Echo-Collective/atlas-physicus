# Physics Atlas API

This package contains the read-oriented FastAPI service, PostgreSQL models,
incremental scientific-source connectors, update worker, and resource monitor
for Physics Atlas v3.0.5-alpha.

The public service is operated separately on Railway. Deterministic fixture
mode remains the default for local development and automated tests; no
production credential is stored in this repository.

See [`../docs/backend.md`](../docs/backend.md) for setup and operational
guidance.
