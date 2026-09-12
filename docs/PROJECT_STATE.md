# Atlas Physicus project state

Last reviewed: 2026-09-12

## Archived (PA-066)

The owner ended active development on 12 September 2026. Preserve the public
interactive map, source, historical releases, acquisition evidence and methods.
No further data acquisition, Full Physics expansion, certification launch or
v3.1 work is scheduled. The prior [September 8 state](archive/project-state-2026-09-08.md)
is historical context, not an active task list.

The frozen public data was captured on 8 September 2026. It contains 61,846
INSPIRE source records, 46,524 attributed dated papers, 4,569 institutions and
135 countries/regions across 51 native arXiv physics categories and 2018–2026.
This bounded corpus is not a representative census. Missing attribution,
retrospective citations and partial-year limitations remain disclosed.

The Pages wrapper loads same-origin static map partitions and relationships;
Railway is not part of its data path. The frozen explorer source pin remains
`f8c2c06800a18c6a544919ee697b529d19e1b353`. Web archive commit
`28426577b93211eae3dc4fc9b10bd6eb5c8cb148` passed 24 adapter tests, lint, types,
a build without an API URL and Pages run `34685002284`.
The official website archive wording passed 105 tests, format, lint, types and
build at `c5fb8f2579a909f8098d284aa5a5050071d3f904`; its Sites publication
succeeded and GitHub CI run `34685770361` passed.

## Retirement state

Railway API and worker deployments are stopped and their source integrations
are disconnected. The database and its volume are retained until a backup is
restored and verified. Subscription cancellation remains pending.
See [the archive record](ARCHIVE.md) for the final operating state.

## Immediate next action

Finish the authorized database backup and restore verification before removing
Railway resources; then cancel the subscription. Do not resume development or
acquisition without a new owner request.
