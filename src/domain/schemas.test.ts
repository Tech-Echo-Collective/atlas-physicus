import demoData from '../data/demo/atlas.json';
import {
  affiliationSchema,
  atlasDatasetSchema,
  datasetUpdateSchema,
  externalIdentifierSchema,
  identityResolutionSchema,
  institutionSchema,
  metricObservationSchema,
  paperSchema,
  provenanceSchema,
  rawEntityRecordSchema,
  researcherSchema,
  sourceSnapshotSchema,
} from './schemas';

describe('atlasDatasetSchema', () => {
  it('accepts the v3.0.1 normalized synthetic metric dataset', () => {
    const dataset = atlasDatasetSchema.parse(demoData);

    expect(dataset.metadata.datasetKind).toBe('synthetic-demo');
    expect(dataset.scienceDomains).toEqual([
      expect.objectContaining({
        id: 'physics',
        fieldIds: ['hep-th', 'gr-qc', 'quant-ph', 'cond-mat'],
      }),
    ]);
    expect(dataset.fields.map((field) => field.id)).toEqual([
      'hep-th',
      'gr-qc',
      'quant-ph',
      'cond-mat',
    ]);
    expect(
      Array.from(
        new Set(dataset.metricObservations.map((observation) => observation.period)),
      ),
    ).toEqual(['1900', '1950', '2000', '2026']);
    expect(dataset.metricObservations).toHaveLength(332);
    expect(dataset.metricDefinitions.map((definition) => definition.id)).toEqual([
      'research_activity_score',
      'research_impact',
      'collaboration',
      'research_diversity',
      'momentum',
      'talent_ecosystem',
      'concentration_vulnerability',
    ]);
    expect(
      dataset.metricDefinitions.every(
        (definition) =>
          definition.interpretation.length > 0 &&
          definition.version === 'metric-definition-v1',
      ),
    ).toBe(true);
    expect(dataset.geographicViews).toHaveLength(8);
    expect(
      dataset.geographicViews.find((view) => view.countryId === 'country-cn'),
    ).toEqual(
      expect.objectContaining({
        geometryIsoNumerics: ['156', '158'],
        locationCountryIds: ['country-cn', 'country-tw'],
      }),
    );
    expect(dataset.researchGroups).toHaveLength(12);
    expect(dataset.affiliations).toHaveLength(13);
    expect(dataset.papers).toHaveLength(8);
    expect(dataset.authorships).toHaveLength(24);
    expect(dataset.historicalEvents).toHaveLength(8);
    expect(
      dataset.metricObservations.every(
        (observation) =>
          observation.provenance.sourceType === 'synthetic-demo' &&
          observation.provenance.version === 'v3.0.1-alpha' &&
          observation.source === 'synthetic-demo' &&
          observation.algorithmVersion === 'metric-engine-v1',
      ),
    ).toBe(true);
    expect(dataset.metadata.provenance).toEqual(
      expect.objectContaining({
        sourceType: 'synthetic-demo',
        version: 'v3.0.1-alpha',
        status: 'synthetic',
      }),
    );
    expect(dataset.institutions[0].provenance.sourceType).toBe(
      'synthetic-demo',
    );
    expect(dataset.institutions[0]).toEqual(
      expect.objectContaining({
        canonicalName: dataset.institutions[0].name,
        aliases: [],
        historicalNames: [],
        externalIds: [],
      }),
    );
    expect(dataset.researchers[0]).toEqual(
      expect.objectContaining({
        canonicalName: dataset.researchers[0].name,
        aliases: ['M. Chen'],
        historicalNames: [],
        externalIds: [],
        identityConfidence: 1,
      }),
    );
    expect(dataset.externalResources).toHaveLength(5);
    expect(
      dataset.externalResources.every((resource) => resource.url.length > 0),
    ).toBe(true);
    expect(dataset.rawEntityRecords).toEqual([]);
    expect(dataset.identityResolutions).toEqual([]);
    expect(dataset.sourceSnapshots).toEqual([]);
    expect(dataset.datasetUpdates).toEqual([]);
    expect(dataset.papers[0]).toEqual(
      expect.objectContaining({
        doi: '10.0000/physics-atlas.demo.001',
        arxivId: '2601.00001',
        externalIdentifiers: [
          { scheme: 'demo-catalog', value: 'PA-PAPER-001' },
        ],
      }),
    );
  });

  it('rejects invalid structured provenance confidence', () => {
    const invalidDataset = structuredClone(demoData);
    Object.assign(invalidDataset.metadata.provenance, { confidence: 1.5 });

    expect(() => atlasDatasetSchema.parse(invalidDataset)).toThrow();
  });

  it('accepts sparse live entities and normalizes transport nulls to missing values', () => {
    const provenance = {
      source: 'Physics Atlas API contract fixture',
      sourceType: 'external-api' as const,
      version: 'fixture-v1',
      status: 'unverified' as const,
      confidence: null,
      retrievedAt: null,
    };

    const parsedProvenance = provenanceSchema.parse(provenance);
    const institution = institutionSchema.parse({
      id: 'institution-sparse',
      name: 'Sparse Institute',
      canonicalName: 'Sparse Institute',
      aliases: [],
      historicalNames: [],
      externalIds: [],
      identityConfidence: null,
      countryId: 'country-us',
      city: 'Unknown',
      fieldIds: [],
      location: null,
      provenance,
    });
    const researcher = researcherSchema.parse({
      id: 'researcher-sparse',
      name: 'Sparse Researcher',
      canonicalName: 'Sparse Researcher',
      aliases: [],
      historicalNames: [],
      externalIds: [],
      identityConfidence: null,
      fieldIds: [],
      provenance,
    });
    const paper = paperSchema.parse({
      id: 'paper-sparse',
      title: 'Sparse source record',
      summary: '',
      year: 2026,
      fieldIds: [],
      doi: null,
      arxivId: null,
      provenance,
    });
    const affiliation = affiliationSchema.parse({
      id: 'affiliation-sparse',
      researcherId: researcher.id,
      institutionId: institution.id,
      researchGroupId: null,
      startDate: null,
      endDate: null,
      source: null,
      confidence: null,
      provenance,
    });
    const observation = metricObservationSchema.parse({
      id: 'observation-sparse',
      entityType: 'country',
      entityId: 'country-us',
      scienceDomainId: null,
      fieldId: null,
      metricId: 'research_activity_score',
      period: '2026',
      value: 42,
      source: 'fixture',
      algorithmVersion: 'fixture-v1',
      calculationVersion: 'fixture-v1',
      calculatedAt: null,
      provenance,
    });
    const snapshot = sourceSnapshotSchema.parse({
      id: 'snapshot-sparse',
      source: 'fixture',
      sourceVersion: 'fixture-v1',
      capturedAt: '2026-08-28T00:00:00.000Z',
      updateMode: 'incremental',
      recordCount: 1,
      previousSnapshotId: null,
      contentChecksum: null,
      storageReference: null,
      provenance,
    });
    const update = datasetUpdateSchema.parse({
      id: 'update-sparse',
      appliedAt: '2026-08-28T00:00:00.000Z',
      updateMode: 'incremental',
      sourceSnapshotIds: [snapshot.id],
      previousDatasetVersion: null,
      datasetVersion: 'fixture-v1',
      resolverVersion: 'fixture-v1',
      metricCalculationVersion: null,
      changes: { created: 1, updated: 0, unchanged: 0, unresolved: 0 },
      provenance,
    });
    const unresolved = identityResolutionSchema.parse({
      id: 'resolution-sparse',
      rawEntityRecordId: 'raw-sparse',
      entityType: 'researcher',
      status: 'unresolved',
      canonicalEntityId: null,
      method: null,
      confidence: 0,
      evidence: [],
      resolverVersion: 'fixture-v1',
      resolvedAt: '2026-08-28T00:00:00.000Z',
      provenance,
    });

    expect(parsedProvenance.confidence).toBeUndefined();
    expect(parsedProvenance.retrievedAt).toBeUndefined();
    expect(institution.fieldIds).toEqual([]);
    expect(institution.location).toBeUndefined();
    expect(institution.identityConfidence).toBeUndefined();
    expect(researcher.fieldIds).toEqual([]);
    expect(paper.summary).toBe('');
    expect(paper.fieldIds).toEqual([]);
    expect(paper.doi).toBeUndefined();
    expect(affiliation.researchGroupId).toBeUndefined();
    expect(observation.fieldId).toBeUndefined();
    expect(snapshot.previousSnapshotId).toBeUndefined();
    expect(update.previousDatasetVersion).toBeUndefined();
    expect(unresolved.canonicalEntityId).toBeUndefined();
  });

  it('represents collaborative papers through multiple affiliated authors', () => {
    const dataset = atlasDatasetSchema.parse(demoData);
    const paperAuthorships = dataset.authorships.filter(
      (authorship) => authorship.paperId === 'paper-boundary-symmetries',
    );
    const authorIds = new Set(
      paperAuthorships.map((authorship) => authorship.researcherId),
    );
    const institutionIds = new Set(
      dataset.affiliations
        .filter((affiliation) => authorIds.has(affiliation.researcherId))
        .map((affiliation) => affiliation.institutionId),
    );

    expect(institutionIds).toEqual(
      new Set([
        'institution-mit',
        'institution-princeton',
        'institution-northstar',
      ]),
    );
  });

  it('rejects an institution with an unknown country', () => {
    const invalidDataset = structuredClone(demoData);
    invalidDataset.institutions[0].countryId = 'country-missing';

    expect(() => atlasDatasetSchema.parse(invalidDataset)).toThrow(
      /Unknown country/,
    );
  });

  it('rejects a geographic view with an unknown location entity', () => {
    const invalidDataset = structuredClone(demoData);
    invalidDataset.geographicViews[0].locationCountryIds.push(
      'country-missing',
    );

    expect(() => atlasDatasetSchema.parse(invalidDataset)).toThrow(
      /Unknown location country/,
    );
  });

  it('rejects ambiguous geometry membership across geographic views', () => {
    const invalidDataset = structuredClone(demoData);
    invalidDataset.geographicViews[1].geometryIsoNumerics.push('840');

    expect(() => atlasDatasetSchema.parse(invalidDataset)).toThrow(
      /Geometry is assigned to multiple views/,
    );
  });

  it('rejects a research-group affiliation at a different institution', () => {
    const invalidDataset = structuredClone(demoData);
    invalidDataset.affiliations[0].researchGroupId = 'group-mit-fields';

    expect(() => atlasDatasetSchema.parse(invalidDataset)).toThrow(
      /Research group and affiliation institutions differ/,
    );
  });

  it('keeps Phase 1-shaped data compatible when science domains are absent', () => {
    const compatibleDataset: Record<string, unknown> = structuredClone(demoData);
    delete compatibleDataset.scienceDomains;
    delete compatibleDataset.geographicViews;
    delete compatibleDataset.researchGroups;
    delete compatibleDataset.affiliations;
    delete compatibleDataset.papers;
    delete compatibleDataset.authorships;
    delete compatibleDataset.historicalEvents;
    compatibleDataset.metricObservations = demoData.metricObservations.filter(
      (observation) => !('scienceDomainId' in observation),
    );

    const parsedDataset = atlasDatasetSchema.parse(compatibleDataset);

    expect(parsedDataset.scienceDomains).toEqual([]);
    expect(parsedDataset.geographicViews).toEqual([]);
    expect(parsedDataset.researchGroups).toEqual([]);
    expect(parsedDataset.affiliations).toEqual([]);
    expect(parsedDataset.papers).toEqual([]);
    expect(parsedDataset.authorships).toEqual([]);
    expect(parsedDataset.historicalEvents).toEqual([]);
  });

  it('validates an auditable raw-to-canonical identity chain and update snapshot', () => {
    const source = structuredClone(demoData) as Record<string, unknown>;
    source.sourceSnapshots = [
      {
        id: 'snapshot-inspire-one',
        source: 'INSPIRE-HEP',
        sourceVersion: '2026-08-24T10:00:00.000Z',
        capturedAt: '2026-08-24T10:00:00.000Z',
        updateMode: 'incremental',
        recordCount: 1,
        storageReference: 'pipeline/data/raw/snapshot.json',
        provenance: {
          source: 'INSPIRE-HEP',
          sourceType: 'external-api',
          version: 'api-v1',
          status: 'unverified',
        },
      },
    ];
    source.rawEntityRecords = [
      {
        id: 'raw-caltech-one',
        entityType: 'institution',
        sourceRecordId: '902704',
        sourceSnapshotId: 'snapshot-inspire-one',
        rawName: 'Caltech',
        externalIds: [{ scheme: 'ROR', value: '05dxps055' }],
        attributes: { city: 'Pasadena' },
        ingestedAt: '2026-08-24T10:01:00.000Z',
        provenance: {
          source: 'INSPIRE-HEP',
          sourceType: 'external-api',
          version: 'api-v1',
          status: 'unverified',
        },
      },
    ];
    source.identityResolutions = [
      {
        id: 'resolution-caltech-one',
        rawEntityRecordId: 'raw-caltech-one',
        entityType: 'institution',
        status: 'matched',
        canonicalEntityId: 'institution-caltech',
        method: 'external-identifier',
        confidence: 1,
        evidence: [
          {
            method: 'external-identifier',
            inputValue: 'ROR:05dxps055',
            canonicalValue: 'ROR:05dxps055',
            score: 1,
          },
        ],
        resolverVersion: 'identity-resolver-v1',
        resolvedAt: '2026-08-24T10:02:00.000Z',
        provenance: {
          source: 'Physics Atlas identity resolver',
          sourceType: 'derived',
          version: 'identity-resolver-v1',
          status: 'unverified',
          confidence: 1,
        },
      },
    ];
    source.externalResources = [
      {
        id: 'resource-caltech-official',
        entityType: 'institution',
        entityId: 'institution-caltech',
        resourceType: 'official-institution-website',
        label: 'Official website',
        url: 'https://www.caltech.edu/',
        externalId: { scheme: 'ROR', value: '05dxps055' },
        isPrimary: true,
        lastVerifiedAt: '2026-08-24T10:03:00.000Z',
        provenance: {
          source: 'institutional metadata fixture',
          sourceType: 'institutional-source',
          version: 'fixture-v1',
          status: 'verified',
        },
      },
    ];
    source.datasetUpdates = [
      {
        id: 'update-inspire-one',
        appliedAt: '2026-08-24T10:04:00.000Z',
        updateMode: 'incremental',
        sourceSnapshotIds: ['snapshot-inspire-one'],
        datasetVersion: 'v3.0.3-alpha',
        resolverVersion: 'identity-resolver-v1',
        changes: { created: 1, updated: 0, unchanged: 0, unresolved: 0 },
        provenance: {
          source: 'Physics Atlas update pipeline',
          sourceType: 'derived',
          version: 'update-pipeline-v1',
          status: 'unverified',
        },
      },
    ];
    const parsed = atlasDatasetSchema.parse(source);

    expect(parsed.identityResolutions[0]).toEqual(
      expect.objectContaining({
        status: 'matched',
        canonicalEntityId: 'institution-caltech',
      }),
    );
    expect(parsed.externalResources[0].url).toBe('https://www.caltech.edu/');
    expect(parsed.datasetUpdates[0].changes.failed).toBe(0);
    expect(parsed.datasetUpdates[0].affectedEntities).toEqual([]);
    expect(parsed.datasetUpdates[0].sourceSnapshotIds).toEqual([
      'snapshot-inspire-one',
    ]);
  });

  it('requires matched resolutions to identify a canonical entity', () => {
    expect(() =>
      identityResolutionSchema.parse({
        id: 'resolution-missing-canonical',
        rawEntityRecordId: 'raw-one',
        entityType: 'researcher',
        status: 'matched',
        confidence: 0.9,
        evidence: [],
        resolverVersion: 'resolver-v1',
        resolvedAt: '2026-08-24T10:00:00.000Z',
      }),
    ).toThrow(/requires a canonical entity/);
  });

  it('prevents unresolved records from silently referencing canonical entities', () => {
    expect(() =>
      identityResolutionSchema.parse({
        id: 'resolution-unresolved',
        rawEntityRecordId: 'raw-one',
        entityType: 'researcher',
        status: 'unresolved',
        canonicalEntityId: 'researcher-one',
        confidence: 0.2,
        evidence: [],
        resolverVersion: 'resolver-v1',
        resolvedAt: '2026-08-24T10:00:00.000Z',
      }),
    ).toThrow(/cannot silently reference/);
  });

  it('preserves missing-metadata quarantine evidence without inventing a canonical paper', () => {
    const resolution = identityResolutionSchema.parse({
      id: 'resolution-missing-year',
      rawEntityRecordId: 'raw-missing-year',
      entityType: 'paper',
      status: 'unresolved',
      canonicalEntityId: null,
      method: 'insufficient-metadata',
      confidence: 0,
      evidence: [
        {
          method: 'required-metadata',
          inputValue: 'publication_year',
          score: 0,
        },
      ],
      resolverVersion: 'resolver-v1',
      resolvedAt: '2026-08-28T00:00:00.000Z',
      provenance: {
        source: 'test fixture',
        sourceType: 'synthetic-demo',
        version: 'test-v1',
        status: 'synthetic',
      },
    });

    expect(resolution.canonicalEntityId).toBeUndefined();
    expect(resolution.evidence[0]?.method).toBe('required-metadata');
  });

  it('accepts nested paper evidence without flattening the raw attributes', () => {
    expect(
      rawEntityRecordSchema.parse({
        id: 'raw-paper-one',
        entityType: 'paper',
        sourceRecordId: 'source-paper-one',
        sourceSnapshotId: 'snapshot-one',
        rawName: 'A paper title',
        externalIds: [{ scheme: 'doi', value: '10.1000/example' }],
        attributes: {
          authors: [{ name: 'Ada Example', ids: [{ scheme: 'orcid' }] }],
          citationCount: 4,
        },
        ingestedAt: '2026-08-28T01:00:00.000Z',
        provenance: {
          source: 'test source',
          sourceType: 'external-api',
          version: 'test-v1',
          status: 'unverified',
        },
      }),
    ).toEqual(expect.objectContaining({ entityType: 'paper' }));
  });

  it('validates affiliation chronology at date precision', () => {
    expect(() =>
      affiliationSchema.parse({
        id: 'affiliation-one',
        researcherId: 'researcher-one',
        institutionId: 'institution-one',
        startDate: '2020-09',
        endDate: '2019-12',
      }),
    ).toThrow(/end date precedes/);
  });

  it('keeps authority identifiers URL-free', () => {
    expect(
      externalIdentifierSchema.parse({
        scheme: 'ORCID',
        value: '0000-0000-0000-0001',
        url: 'https://orcid.org/0000-0000-0000-0001',
      }),
    ).toEqual({ scheme: 'ORCID', value: '0000-0000-0000-0001' });
  });
});
