# Atlas Physica API

This package contains the read-oriented FastAPI service, PostgreSQL models,
incremental scientific-source connectors, update worker, and resource monitor
for Atlas Physica v3.0.5-alpha. Atlas Physica is developed and maintained by
Tech Echo Collective. The `physics_atlas_api` package, deployment service names,
database identifiers and API URLs remain unchanged.

The public service is operated separately on Railway. Deterministic fixture
mode remains the default for local development and automated tests; no
production credential is stored in this repository.

See [`../docs/backend.md`](../docs/backend.md) for setup and operational
guidance.
