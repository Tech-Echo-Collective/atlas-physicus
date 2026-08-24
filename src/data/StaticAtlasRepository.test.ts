import { prototypeMetricId } from '../domain/models';
import { StaticAtlasRepository } from './StaticAtlasRepository';

describe('StaticAtlasRepository', () => {
  it('filters observations through the future-compatible repository boundary', async () => {
    const repository = new StaticAtlasRepository();
    const observations = await repository.findMetricObservations({
      entityType: 'country',
      fieldId: 'quant-ph',
      metricId: prototypeMetricId,
      period: '2026',
    });

    expect(observations).toHaveLength(8);
    expect(
      observations.every(
        (observation) => observation.fieldId === 'quant-ph',
      ),
    ).toBe(true);
  });

  it('returns distinct synthetic observations for a historical year', async () => {
    const repository = new StaticAtlasRepository();
    const current = await repository.findMetricObservations({
      entityType: 'country',
      fieldId: 'hep-th',
      metricId: prototypeMetricId,
      period: '2026',
    });
    const historical = await repository.findMetricObservations({
      entityType: 'country',
      fieldId: 'hep-th',
      metricId: prototypeMetricId,
      period: '1900',
    });

    expect(historical).toHaveLength(8);
    expect(historical.map((observation) => observation.value)).not.toEqual(
      current.map((observation) => observation.value),
    );
  });

  it('queries explicit science-domain observations independently of fields', async () => {
    const repository = new StaticAtlasRepository();
    const observations = await repository.findMetricObservations({
      entityType: 'country',
      scienceDomainId: 'physics',
      metricId: prototypeMetricId,
      period: '2026',
    });

    expect(observations).toHaveLength(8);
    expect(
      observations.every(
        (observation) =>
          observation.scienceDomainId === 'physics' &&
          observation.fieldId === undefined,
      ),
    ).toBe(true);
  });
});
