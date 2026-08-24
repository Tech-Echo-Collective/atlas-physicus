import demoData from '../data/demo/atlas.json';
import { atlasDatasetSchema } from './schemas';

describe('atlasDatasetSchema', () => {
  it('accepts the Phase 1 synthetic dataset', () => {
    const dataset = atlasDatasetSchema.parse(demoData);

    expect(dataset.metadata.datasetKind).toBe('synthetic-demo');
    expect(dataset.fields.map((field) => field.id)).toEqual([
      'hep-th',
      'gr-qc',
      'quant-ph',
      'cond-mat',
    ]);
    expect(dataset.metricObservations).toHaveLength(32);
    expect(
      dataset.metricObservations.every(
        (observation) => observation.provenance === 'synthetic-demo',
      ),
    ).toBe(true);
  });

  it('rejects an institution with an unknown country', () => {
    const invalidDataset = structuredClone(demoData);
    invalidDataset.institutions[0].countryId = 'country-missing';

    expect(() => atlasDatasetSchema.parse(invalidDataset)).toThrow(
      /Unknown country/,
    );
  });
});
