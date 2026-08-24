export const pilotConfig = Object.freeze({
  pilotVersion: 'v3.0.3-alpha-pilot.1',
  identityResolutionVersion: 'identity-resolution-v1',
  snapshotManifestVersion: 'snapshot-manifest-v1',
  sourceName: 'INSPIRE-HEP REST API',
  sourceDocumentationVersion:
    'INSPIRE REST API documentation accessed 2026-08-24',
  apiBaseUrl: 'https://inspirehep.net/api',
  apiDocumentation: 'https://github.com/inspirehep/rest-api-doc',
  sourceTerms: 'https://help.inspirehep.net/knowledge-base/terms-of-use/',
  sourceCitation: 'https://doi.org/10.5281/zenodo.5788550',
  fieldId: 'hep-th',
  scienceDomainId: 'physics',
  startYear: 2000,
  endYear: 2026,
  recordsPerYear: 3,
  literatureSort: 'mostrecent',
  maxInstitutionRecords: 240,
  literatureRequestPauseMs: 600,
  requestConcurrency: 2,
  requestBatchPauseMs: 1_000,
  literatureFields: [
    'control_number',
    'titles',
    'authors.full_name',
    'authors.ids',
    'authors.record',
    'authors.curated_relation',
    'authors.affiliations',
    'authors.affiliations_identifiers',
    'authors.raw_affiliations',
    'arxiv_eprints',
    'preprint_date',
    'earliest_date',
    'citation_count',
    'citation_count_without_self_citations',
    'dois',
    'document_type',
  ],
  algorithms: {
    activity: 'pilot-activity-full-participation-active-minmax-v1',
    impact: 'pilot-impact-log-citations-active-minmax-v1',
    collaboration: 'pilot-connectivity-unique-partners-active-minmax-v1',
    momentum: 'pilot-momentum-rolling-participation-active-minmax-v1',
  },
});

export function pilotYears(config = pilotConfig) {
  return Array.from(
    { length: config.endYear - config.startYear + 1 },
    (_, index) => config.startYear + index,
  );
}
