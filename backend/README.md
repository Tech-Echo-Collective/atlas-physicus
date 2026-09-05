# Atlas Physicus API

This package contains the read-oriented FastAPI service, PostgreSQL models,
incremental scientific-source connectors, update worker, and resource monitor
for Atlas Physicus v3.0.5-alpha.

Part of Tech Echo Physica, a Tech Echo Collective project family for exploring physics through research mapping, knowledge structures, and interactive physical systems.

The `physics_atlas_api` package, installed `physics-atlas-api` distribution,
command names, environment variables, database identifiers and API URLs remain
unchanged for deployed compatibility. See the
[naming audit](../docs/production-deployment.md#naming-and-deployment-compatibility).

The public service is operated separately on Railway. Deterministic fixture
mode remains the default for local development and automated tests; no
production credential is stored in this repository.

See [`../docs/backend.md`](../docs/backend.md) for setup and operational
guidance.
