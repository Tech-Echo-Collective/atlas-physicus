import demoData from '../data/demo/atlas.json';
import { atlasDatasetSchema } from './schemas';

describe('atlasDatasetSchema', () => {
  it('accepts the Phase 2.3 normalized synthetic entity dataset', () => {
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
          observation.provenance.version === 'v2.3-alpha',
      ),
    ).toBe(true);
    expect(dataset.metadata.provenance).toEqual(
      expect.objectContaining({
        sourceType: 'synthetic-demo',
        version: 'v2.3-alpha',
        status: 'synthetic',
      }),
    );
    expect(dataset.institutions[0].provenance.sourceType).toBe(
      'synthetic-demo',
    );
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
});
