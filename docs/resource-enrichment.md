# External-resource enrichment and monitoring

## Resource model

External links are independent, provenance-bearing records attached to canonical entities. They are not copied into identity fields and are not treated as scientific truth merely because a URL exists.

Supported examples include:

| Entity | Resource types |
| --- | --- |
| Institution | official website, physics department, research-group page, ROR, Wikidata where appropriate |
| Researcher | official homepage, institutional profile, ORCID, INSPIRE, arXiv author resource where appropriate |
| Research group | official group website, institutional page |
| Paper | DOI, arXiv, INSPIRE, publisher landing page |

`ExternalResource` records include canonical entity type/ID, resource type, URL, source and source record, verification state and method, last check, HTTP status, redirect target, timestamps, and provenance. `ResourceCheck` preserves each check result as history. A changed or broken link therefore does not require rewriting the canonical entity.

Enrichment prefers authoritative provider metadata. ROR can supply an official institution website, ORCID can link an identifier explicitly associated with a researcher, and paper identifiers can generate canonical DOI/arXiv/INSPIRE links. An external URL is never used by itself to merge identities or calculate research metrics.

## Safe health checks

`ResourceMonitor` runs a bounded set of stale or unchecked resources. It:

1. accepts only public HTTP(S) URLs without embedded credentials;
2. restricts checks to an operator-configured authority-host allowlist, permits only the standard port for the URL scheme, and requires every resolved address to be globally routable;
3. tries `HEAD`, falling back to a streamed one-byte range `GET` only for servers that reject `HEAD`;
4. records reachable, redirect, permanent redirect, broken, timeout, or unknown;
5. retries transient failures with exponential backoff;
6. caches successful checks for seven days by default;
7. respects per-run bounds, timeouts, and a request interval;
8. writes an immutable check-history row.

The monitor validates the source immediately before each request and validates redirect targets under the same URL/host policy, but does not fetch redirects automatically during the same check. It does not follow a site graph, scrape page content, bypass access controls, or ignore robots/access restrictions. Production operators should choose a respectful cadence and identify the service in the user agent.

The default host allowlist contains only known authority-provider domains. Arbitrary institution or researcher websites are therefore stored and displayed with provenance, but remain `unknown` until an operator deliberately adds their host to the monitoring policy. This is a safety boundary, not a claim that those links are unhealthy.

Temporary failures do not revoke prior verification or delete the resource. Only explicit 404/410 responses are classified as broken; rate limits and 5xx/timeouts remain temporary or unknown. A permanent redirect is recorded for later reviewed canonicalization rather than silently changing the stored URL.

## Profile behavior

Profiles query resources by canonical entity ID. Active, verified, authoritative resources can be preferred for display while older or failing records and their provenance remain available for audit. The existence, status, or order of a link does not rank the entity.

The API exposes bounded external-resource queries, and `/api/updates/status` reports the number currently classified as broken or timed out. The worker can include monitoring with `--check-resources`; `PHYSICS_ATLAS_RESOURCE_CHECK_MAX_PER_RUN` controls the bound.

## Limitations

- HTTP reachability cannot verify ownership, scientific accuracy, or page content.
- Some sites block automated `HEAD`/`GET` checks and may remain `unknown` even when browser-accessible.
- DNS and status can change after a check.
- Revalidation narrows, but cannot eliminate, the DNS-rebinding window between name resolution and the HTTP connection. Production deployment requires a restricted egress proxy or network policy that blocks non-public destinations independently of application code.
- The alpha has no human resource-review UI, certificate-expiry monitor, or content-change tracker.
- ORCID and provider links remain subject to provider-specific display and reuse terms.
