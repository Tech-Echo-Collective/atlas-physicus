# Physics Atlas durable decisions

Last reviewed: 2026-08-28

These decisions constrain implementation and public communication. Add a dated superseding entry when a durable decision changes; do not silently rewrite project history.

| ID | Decision | Consequence |
| --- | --- | --- |
| PA-001 | Physics Atlas is descriptive and exploratory, not predictive. | Do not add prediction claims, forecasting, or interfaces that imply future scientific performance. |
| PA-002 | Physics Atlas does not rank researchers, institutions, universities, countries, or fields. | Metrics, ordering, labels, and visual emphasis must not be presented as statements of scientific worth. |
| PA-003 | Physics Atlas does not provide personalized researcher or paper recommendations. | Discovery follows explicit atlas exploration and search, not behavioral profiling or recommendation scoring. |
| PA-004 | Metrics are reference and exploration tools, not judgments of scientific value. | Every implemented metric needs an explicit definition, interpretation, version, source, method, and limitation. Taxonomy categories alone do not imply formulas. |
| PA-005 | Missing data must never silently become zero. | Missing observations use a distinct neutral state. Interpolation or imputation requires a reviewed, documented method and visible labeling. |
| PA-006 | Provenance and uncertainty remain explicit. | Provider records, mappings, identity decisions, derived observations, and public status must preserve source and confidence information. Ambiguity enters review rather than being silently merged. |
| PA-007 | Map-first exploration is a core product principle. | Preserve the domain → field → time → world → country → institution → researcher path. Avoid flattening the experience into a ranking dashboard. |
| PA-008 | Geographic display and scientific attribution are separate layers. | Geometry defines an exploration canvas; institutional location metadata and temporal affiliations define scientific relationships. Multi-institution work is attributed to each supported affiliation rather than forced into single-country ownership. |
| PA-009 | Synthetic data is only for testing, development, and clearly labeled demonstration. | Synthetic entities and observations must never be represented as scientific evidence or silently inserted into provider-backed datasets. |
| PA-010 | Historical pilot datasets are retained for reproducibility. | Keep the bounded INSPIRE pilot, its provenance, and deterministic rebuild path even after live activation. It does not become the live corpus. |
| PA-011 | Synthetic, pilot, fixture-live, and provider-backed live datasets must not be silently mixed. | A source change replaces the repository boundary. Stored dataset provenance includes fixture/live identity, and mismatched writes fail. |
| PA-012 | The final normal public experience uses one integrated live dataset without requiring ordinary users to choose providers or development datasets. | Provider selection remains an operator concern. Remove the public source selector only after the integrated backend is operational and verified; preserve static repositories for offline and regression use. |
| PA-013 | Unvalidated live metric scores are not enabled. | The update engine may identify affected partitions, but it writes no scientific values until a reviewed calculator is supplied. A neutral map is preferable to a fabricated heatmap. |
| PA-014 | Identity resolution is authority-led, ambiguity-gated, and reversible. | Valid authority identifiers dominate; names and fuzzy evidence cannot silently merge ambiguous people or organizations. Preserve raw evidence and resolution history. |
| PA-015 | Affiliations are temporal relationships, not permanent ownership fields. | Researcher–institution and optional group relationships retain known time bounds and uncertainty. Provider affiliation evidence requires reviewed promotion rules. |
| PA-016 | PostgreSQL remains the current canonical relational graph store. | Do not introduce a separate graph database without demonstrated query or operational need. FastAPI exposes transport schemas, not raw ORM records. |
| PA-017 | Scientific providers are contacted only by backend connectors. | Browsers receive the integrated Atlas API contract and never hold provider secrets, rate-limit logic, or identity-resolution rules. |
| PA-018 | Production claims require operating evidence. | Deployment-ready code is not a live service. Verify HTTPS API reachability, CORS, database and worker health, update freshness, provenance, and frontend repository use before calling the Atlas live. |
| PA-019 | Acquisition scope is a versioned dataset boundary. | Provider filters belong in backend connector policy. Cursors, snapshots, and live-dataset provenance record that scope and fail closed on mismatch; changing configuration must not silently reinterpret or mix an older corpus. |

## Current activation decision

The v3.0.4 production activation begins with the implemented `hep-th-v1`
corpus policy. INSPIRE-HEP and arXiv supply literature evidence; ROR refreshes
only reviewed, explicitly configured institution IDs; ORCID and Crossref are
queried only for already-known identifiers. The boundary is enforced in backend
connector, cursor, snapshot, and dataset policy rather than by presentation-layer
filtering.

Existing default cadence remains INSPIRE daily, arXiv daily, ROR weekly, with the worker checking due work hourly unless measured provider or operational evidence justifies a change.
