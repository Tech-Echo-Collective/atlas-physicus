import { prototypeMetricId } from '../domain/models';
import {
  buildInstitutionFeatureCollection,
  selectMajorInstitutionsForMap,
} from '../components/atlas/InstitutionLayer';
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

  it('provides renderable institution activity when entering a country', async () => {
    const repository = new StaticAtlasRepository();
    const institutions = await repository.getInstitutions('country-au');
    const observations = await repository.findMetricObservations({
      entityType: 'institution',
      scienceDomainId: 'physics',
      metricId: prototypeMetricId,
      period: '2026',
    });
    const visibleInstitutions = selectMajorInstitutionsForMap(
      institutions,
      observations,
    );
    const collection = buildInstitutionFeatureCollection(
      visibleInstitutions,
      observations,
    );

    expect(visibleInstitutions).toEqual([
      expect.objectContaining({ id: 'institution-southern-cross' }),
    ]);
    expect(collection.features).toEqual([
      expect.objectContaining({
        geometry: {
          type: 'Point',
          coordinates: [144.9631, -37.8136],
        },
        properties: expect.objectContaining({ score: 68 }),
      }),
    ]);
  });

  it('exposes granular entity queries for a future API adapter', async () => {
    const repository = new StaticAtlasRepository();

    await expect(repository.getCountry('country-us')).resolves.toEqual(
      expect.objectContaining({ name: 'United States' }),
    );
    await expect(
      repository.getInstitutions('country-us'),
    ).resolves.toHaveLength(4);
    await expect(
      repository.getResearchGroups('institution-mit'),
    ).resolves.toHaveLength(2);
    await expect(
      repository.getResearchers('institution-mit'),
    ).resolves.toEqual(
      expect.arrayContaining([
        expect.objectContaining({ id: 'researcher-jonah-okafor' }),
      ]),
    );
    await expect(
      repository.getPapers('researcher-jonah-okafor'),
    ).resolves.toEqual(
      expect.arrayContaining([
        expect.objectContaining({ id: 'paper-boundary-symmetries' }),
      ]),
    );
  });

  it('searches only existing atlas entities and not paper content', async () => {
    const repository = new StaticAtlasRepository();

    await expect(repository.searchEntities('caltech')).resolves.toEqual([
      expect.objectContaining({
        entityId: 'institution-caltech',
        entityType: 'institution',
      }),
    ]);
    await expect(repository.searchEntities('boundary symmetries')).resolves.toEqual(
      [],
    );
  });
});
