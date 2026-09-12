# Atlas Physicus archive

Active development ended on **12 September 2026** by the owner's decision (PA-066).

## Preserved work

- [Interactive Atlas](https://atlas.techecho.org/): static September 8 research
  snapshot, category/year map, search, and institution/researcher/paper exploration.
- [Source](https://github.com/Tech-Echo-Collective/atlas-physicus): application,
  methods, historical releases and unfinished scientific validation evidence.
- [Pages wrapper and public assets](https://github.com/Tech-Echo-Collective/Physics-Atlas-Web):
  frozen explorer pin `f8c2c06800a18c6a544919ee697b529d19e1b353`, data files,
  acquisition receipts and coverage disclosures.
- The owner's evidence workspace retains the original acquired SQLite snapshot.

No further acquisition, expansion, certification launch or feature development
is scheduled. The bounded INSPIRE sample does not establish the overall
distribution of physics research. Existing observed metrics retain their original
meaning and limitations; closure does not certify unfinished methods.

## Hosting and retirement

The map uses GitHub Pages and reads same-origin static files. The main Tech Echo
website uses its existing Sites hosting. Neither requires Railway for Atlas.

The former Railway API and acquisition worker are stopped, with GitHub source
integrations disconnected. PostgreSQL and its volume are preserved pending a
verified database backup and restore. The paid subscription is still active;
cancellation is pending. This document does not yet claim full retirement.

## Release evidence

Web `28426577b93211eae3dc4fc9b10bd6eb5c8cb148`: 24 tests, lint, types and build
without an API URL pass; [Pages publication succeeded](https://github.com/Tech-Echo-Collective/Physics-Atlas-Web/actions/runs/34685002284).
Website `c5fb8f2579a909f8098d284aa5a5050071d3f904`: 105 tests, format, lint,
types and build pass. Archive wording covers English, Chinese, French and Spanish.

The official website was published successfully through its existing Sites host
on 12 September 2026. GitHub CI run `34685770361` also passed.

The retained source SQLite snapshot passes `PRAGMA integrity_check` (`ok`),
measures 73,084,928 bytes, and has SHA-256
`6bd1803be614759491e31f0edbb14553025da372a6e27b04fcb5eda5cc3b364c`.
This file backs the public capture; it is not a backup of the separate Railway
PostgreSQL database.
