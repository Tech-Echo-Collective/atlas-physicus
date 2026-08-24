import { prototypeMetricId } from '../domain/models';
import { StaticAtlasRepository } from './StaticAtlasRepository';

describe('StaticAtlasRepository', () => {
  it('filters observations through the future-compatible repository boundary', async () => {
    const repository = new StaticAtlasRepository();
    const observations = await repository.findMetricObservations({
      entityType: 'country',
      fieldId: 'quant-ph',
      metricId: prototypeMetricId,
      period: '2025',
    });

    expect(observations).toHaveLength(8);
    expect(
      observations.every(
        (observation) => observation.fieldId === 'quant-ph',
      ),
    ).toBe(true);
  });
});
