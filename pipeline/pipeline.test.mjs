import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { buildLiteratureUrl } from './ingestion/inspireClient.mjs';
import { normalizeLiterature } from './normalization/normalizeLiterature.mjs';
import { summarizeEntityResolution } from './entity_resolution/resolutionReport.mjs';
import { calculatePilotMetrics } from './metrics/calculatePilotMetrics.mjs';
import { buildPilotAtlasDataset } from './export/buildAtlasExport.mjs';
import { rebuildFromStoredSnapshot } from './rebuild.mjs';
import { writeJson } from './export/writePilotArtifacts.mjs';
import {
  appendSnapshotToManifest,
  createSnapshotManifest,
  mergeIncrementalSnapshot,
  planIncrementalUpdate,
} from './updates/incrementalUpdate.mjs';
import { reprocessVersionedSnapshot } from './reprocess.mjs';

const config = {
  pilotVersion: 'test-pilot-v1',
  identityResolutionVersion: 'identity-test-v1',
  snapshotManifestVersion: 'manifest-test-v1',
  sourceName: 'INSPIRE-HEP REST API',
  sourceDocumentationVersion: 'test-docs',
  apiBaseUrl: 'https://inspirehep.net/api',
  apiDocumentation: 'https://github.com/inspirehep/rest-api-doc',
  fieldId: 'hep-th',
  scienceDomainId: 'physics',
  startYear: 2000,
  endYear: 2001,
  recordsPerYear: 1,
  literatureSort: 'mostrecent',
  literatureFields: ['titles', 'authors.full_name'],
  algorithms: {
    activity: 'activity-test-v1',
    impact: 'impact-test-v1',
    collaboration: 'collaboration-test-v1',
    momentum: 'momentum-test-v1',
  },
};

const institutionReference =
  'https://inspirehep.net/api/institutions/902632';
const authorReference = 'https://inspirehep.net/api/authors/1048187';
const retrievedAt = '2026-08-24T12:00:00.000Z';
const calculatedAt = '2026-08-24T12:01:00.000Z';
const rawSnapshot = {
  metadata: {
    source: 'INSPIRE-HEP REST API',
    sourceVersion: `inspire-hep-snapshot:${retrievedAt}`,
    retrievedAt,
    calculatedAt,
    fieldId: 'hep-th',
    startYear: 2000,
    endYear: 2001,
  },
  yearQueries: [
    {
      year: 2000,
      records: [
        {
          id: '1001',
          metadata: {
            titles: [{ title: 'Pilot paper one' }],
            earliest_date: '2000-04',
            citation_count: 12,
            citation_count_without_self_citations: 10,
            arxiv_eprints: [{ value: 'hep-th/0004001' }],
            authors: [
              {
                full_name: 'Example, Ada',
                record: { $ref: authorReference },
                ids: [
                  { schema: 'INSPIRE BAI', value: 'A.Example.1' },
                  { schema: 'ORCID', value: '0000-0001-2345-6789' },
                ],
                affiliations: [
                  { value: 'Alabama U.', record: { $ref: institutionReference } },
                ],
              },
            ],
          },
        },
      ],
    },
    { year: 2001, records: [] },
  ],
  institutions: [
    {
      url: institutionReference,
      record: {
        id: '902632',
        metadata: {
          legacy_ICN: 'Alabama U.',
          ICN: ['Alabama U.'],
          institution_hierarchy: [
            { name: 'University of Alabama', acronym: 'UA' },
          ],
          external_system_identifiers: [
            { schema: 'ROR', value: 'https://ror.org/03m2x1q45' },
          ],
          urls: [{ value: 'https://www.ua.edu/' }],
          addresses: [
            {
              country_code: 'US',
              country: 'United States',
              cities: ['Tuscaloosa'],
              longitude: -87.569167,
              latitude: 33.209722,
            },
          ],
        },
      },
    },
  ],
  unresolvedInstitutionReferences: [],
};

test('builds a primary-category yearly INSPIRE query', () => {
  const url = new URL(buildLiteratureUrl(2000, config));
  assert.equal(url.searchParams.get('q'), 'primarch:hep-th and de:2000');
  assert.equal(url.searchParams.get('sort'), 'mostrecent');
});

test('normalizes linked entities and reports resolution confidence', () => {
  const normalized = normalizeLiterature(rawSnapshot, config);
  const report = summarizeEntityResolution(normalized);

  assert.equal(normalized.papers.length, 1);
  assert.deepEqual(
    normalized.fields.map((field) => field.id),
    ['hep-th'],
  );
  assert.equal(normalized.researchers[0].id, 'researcher-inspire-1048187');
  assert.equal(normalized.institutions[0].countryId, 'country-usa');
  assert.equal(normalized.countries[0].isoNumeric, '840');
  assert.equal(report.affiliationResolutionRate, 1);
  assert.deepEqual(report.matchedEntities, {
    researchers: 1,
    institutions: 1,
    affiliations: 1,
    affiliationMentions: 1,
  });
  assert.deepEqual(report.unresolvedEntities, {
    researchers: 0,
    institutions: 0,
    affiliationMentions: 0,
  });
  assert.equal(report.provenance.sourceVersion, rawSnapshot.metadata.sourceVersion);
  assert.equal(normalized.identityResolution.rawEntities.institutionRecords.length, 1);
  assert.equal(normalized.identityResolution.rawEntities.institutionMentions.length, 1);
  assert.equal(normalized.identityResolution.rawEntities.researcherAppearances.length, 1);
  assert.equal(
    normalized.identityResolution.resolvedIdentities.researchers[0].status,
    'matched',
  );
  assert.equal(
    normalized.identityResolution.canonicalEntities.institutions[0]
      .canonicalName,
    'University of Alabama',
  );
  assert.ok(
    normalized.identityResolution.canonicalEntities.institutions[0].aliases.includes(
      'Alabama U.',
    ),
  );
  assert.deepEqual(
    normalized.identityResolution.canonicalEntities.institutions[0].externalIds.find(
      (identifier) => identifier.scheme === 'ROR',
    ),
    { scheme: 'ROR', value: '03m2x1q45' },
    'canonical external identifiers must not embed registry URLs',
  );
  assert.ok(
    normalized.externalResources.some(
      (resource) =>
        resource.entityId === 'institution-inspire-902632' &&
        resource.resourceType === 'official-institution-website' &&
        resource.url === 'https://www.ua.edu/',
    ),
  );
  assert.equal(normalized.temporalAffiliationObservations.length, 1);
  assert.deepEqual(
    {
      startDate: normalized.temporalAffiliationObservations[0].startDate,
      endDate: normalized.temporalAffiliationObservations[0].endDate,
      relationshipStatus:
        normalized.temporalAffiliationObservations[0].relationshipStatus,
    },
    {
      startDate: '2000-04',
      endDate: '2000-04',
      relationshipStatus: 'observed-on-publication',
    },
  );
  assert.ok(
    normalized.papers[0].externalIdentifiers.every(
      (identifier) => !Object.hasOwn(identifier, 'url'),
    ),
  );
});

test('keeps name-only researcher candidates outside the canonical graph', () => {
  const unresolvedSnapshot = structuredClone(rawSnapshot);
  const author = unresolvedSnapshot.yearQueries[0].records[0].metadata.authors[0];
  delete author.record;
  author.ids = [];
  author.full_name = 'Unresolved, Example';

  const normalized = normalizeLiterature(unresolvedSnapshot, config);
  const decision = normalized.identityResolution.resolvedIdentities.researchers[0];
  const metrics = calculatePilotMetrics(
    normalized,
    unresolvedSnapshot,
    config,
    calculatedAt,
  );
  const atlasDataset = buildPilotAtlasDataset(
    normalized,
    metrics,
    unresolvedSnapshot,
    config,
  );
  const exportedDecision = atlasDataset.identityResolutions.find(
    (candidate) => candidate.rawEntityRecordId === decision.rawEntityId,
  );

  assert.equal(decision.status, 'inferred');
  assert.equal(Object.hasOwn(decision, 'canonicalEntityId'), false);
  assert.equal(normalized.identityResolution.canonicalEntities.researchers.length, 0);
  assert.equal(normalized.researchers.length, 0);
  assert.equal(normalized.authorships.length, 0);
  assert.equal(exportedDecision?.status, 'ambiguous');
  assert.equal(Object.hasOwn(exportedDecision, 'canonicalEntityId'), false);
  assert.equal(
    atlasDataset.knowledgeGraph.canonicalEntities.researchers.length,
    0,
  );
});

test('calculates versioned pilot observations and an Atlas-compatible export', () => {
  const normalized = normalizeLiterature(rawSnapshot, config);
  const metrics = calculatePilotMetrics(
    normalized,
    rawSnapshot,
    config,
    calculatedAt,
  );
  const atlasDataset = buildPilotAtlasDataset(
    normalized,
    metrics,
    rawSnapshot,
    config,
  );

  assert.equal(metrics.observations.length, 8);
  assert.deepEqual(metrics.summary.sampledEntityYears, {
    countries: 1,
    institutions: 1,
  });
  assert.ok(
    metrics.observations.every((observation) => observation.period === '2000'),
    'years without sampled participation must remain missing, not become zeroes',
  );
  assert.ok(
    metrics.observations.every(
      (observation) =>
        observation.source === 'INSPIRE-HEP REST API' &&
        observation.provenance.version ===
          rawSnapshot.metadata.sourceVersion &&
        observation.provenance.retrievedAt === retrievedAt &&
        observation.calculationVersion === config.pilotVersion &&
        Object.values(config.algorithms).includes(
          observation.algorithmVersion,
        ) &&
        observation.calculatedAt === calculatedAt &&
        observation.fieldId === 'hep-th',
    ),
  );
  assert.equal(atlasDataset.metadata.datasetKind, 'inspire-hep-pilot');
  assert.equal(atlasDataset.metadata.latestUpdateAt, calculatedAt);
  assert.deepEqual(atlasDataset.metadata.sourceSnapshotIds, []);
  assert.equal(atlasDataset.metadata.updateSequence, 0);
  assert.equal(
    atlasDataset.metricDefinitions.filter(
      (definition) => definition.implementationStatus === 'pilot-calculated',
    ).length,
    4,
  );
  assert.equal(
    atlasDataset.knowledgeGraph.canonicalEntities.researchers.length,
    1,
  );
});

test('plans and merges non-destructive incremental snapshots', () => {
  const manifest = createSnapshotManifest(rawSnapshot, config);
  const plan = planIncrementalUpdate({
    manifest,
    config,
    plannedAt: '2026-08-25T00:00:00.000Z',
    overlapYears: 1,
  });
  assert.equal(plan.mode, 'append-versioned-snapshot');
  assert.equal(plan.safety.modifiesBaseSnapshot, false);
  assert.deepEqual(
    plan.queryPlan.map((query) => query.year),
    [2001],
  );
  assert.match(plan.targetRawPath, /^data\/raw\/snapshots\//);

  const baseBefore = JSON.stringify(rawSnapshot);
  const incrementalSnapshot = {
    metadata: {
      ...rawSnapshot.metadata,
      sourceVersion: 'inspire-hep-snapshot:2026-08-25T00:00:00.000Z',
      retrievedAt: '2026-08-25T00:00:00.000Z',
    },
    yearQueries: [
      {
        year: 2001,
        records: [
          {
            id: '1002',
            metadata: {
              titles: [{ title: 'Incremental paper' }],
              earliest_date: '2001',
              authors: [],
            },
          },
        ],
      },
    ],
    institutions: [],
    unresolvedInstitutionReferences: [],
    failedInstitutionFetches: [],
  };
  const merged = mergeIncrementalSnapshot(
    rawSnapshot,
    incrementalSnapshot,
  );
  assert.equal(JSON.stringify(rawSnapshot), baseBefore);
  assert.equal(merged.metadata.parentSourceVersion, rawSnapshot.metadata.sourceVersion);
  assert.equal(merged.yearQueries.find((query) => query.year === 2000).records.length, 1);
  assert.equal(merged.yearQueries.find((query) => query.year === 2001).records.length, 1);

  const nextEntry = {
    ...manifest.snapshots[0],
    snapshotId: 'next-snapshot',
    parentSnapshotId: manifest.activeSnapshotId,
    sourceVersion: incrementalSnapshot.metadata.sourceVersion,
  };
  const updatedManifest = appendSnapshotToManifest(manifest, nextEntry);
  assert.equal(updatedManifest.activeSnapshotId, 'next-snapshot');
  assert.equal(updatedManifest.snapshots.length, 2);
  assert.equal(manifest.snapshots.length, 1);
});

test('rebuilds all derived outputs byte-for-byte from the preserved raw snapshot', async () => {
  const temporaryRoot = await mkdtemp(
    path.join(os.tmpdir(), 'physics-atlas-pipeline-'),
  );
  const paths = {
    rawSnapshot: path.join(temporaryRoot, 'raw/snapshot.json'),
    normalizedPilot: path.join(temporaryRoot, 'processed/normalized.json'),
    resolutionReport: path.join(temporaryRoot, 'reports/resolution.json'),
    metricSummary: path.join(temporaryRoot, 'reports/metrics.json'),
    atlasDataset: path.join(temporaryRoot, 'export/atlas.json'),
  };

  try {
    await writeJson(paths.rawSnapshot, rawSnapshot);
    const rawBefore = await readFile(paths.rawSnapshot, 'utf8');
    const first = await rebuildFromStoredSnapshot(config, paths);
    const derivedPaths = [
      paths.normalizedPilot,
      paths.resolutionReport,
      paths.metricSummary,
      paths.atlasDataset,
    ];
    const firstOutputs = await Promise.all(
      derivedPaths.map((targetPath) => readFile(targetPath, 'utf8')),
    );
    const second = await rebuildFromStoredSnapshot(config, paths);
    const secondOutputs = await Promise.all(
      derivedPaths.map((targetPath) => readFile(targetPath, 'utf8')),
    );

    assert.deepEqual(firstOutputs, secondOutputs);
    assert.deepEqual(first.atlasDataset, second.atlasDataset);
    assert.equal(second.metricSummary.observationCount, 8);
    assert.equal(
      await readFile(paths.rawSnapshot, 'utf8'),
      rawBefore,
      'rebuild must never alter the preserved source snapshot',
    );
  } finally {
    await rm(temporaryRoot, { recursive: true, force: true });
  }
});

test('reprocesses a preserved snapshot into an isolated version directory', async () => {
  const temporaryRoot = await mkdtemp(
    path.join(os.tmpdir(), 'physics-atlas-reprocess-'),
  );
  const rawPath = path.join(temporaryRoot, 'preserved-raw.json');
  try {
    await writeJson(rawPath, rawSnapshot);
    const rawBefore = await readFile(rawPath, 'utf8');
    const result = await reprocessVersionedSnapshot({
      rawPath,
      config,
      outputRoot: temporaryRoot,
    });

    assert.equal(result.rawSnapshotModified, false);
    assert.equal(await readFile(rawPath, 'utf8'), rawBefore);
    assert.equal(result.sourceRecords, 1);
    assert.ok(
      Object.values(result.outputPaths).every((targetPath) =>
        targetPath.includes('/data/versions/'),
      ),
    );
    const identityArtifact = JSON.parse(
      await readFile(result.outputPaths.identityResolution, 'utf8'),
    );
    assert.equal(identityArtifact.canonicalEntities.researchers.length, 1);
  } finally {
    await rm(temporaryRoot, { recursive: true, force: true });
  }
});
