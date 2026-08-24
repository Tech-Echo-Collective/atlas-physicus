import { defaultMetricId } from '../domain/models';
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
      metricId: defaultMetricId,
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
      metricId: defaultMetricId,
      period: '2026',
    });
    const historical = await repository.findMetricObservations({
      entityType: 'country',
      fieldId: 'hep-th',
      metricId: defaultMetricId,
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
      metricId: defaultMetricId,
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
      metricId: defaultMetricId,
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
        properties: expect.objectContaining({ metricValue: 68 }),
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

  it('exposes definitions and reproducible metric queries', async () => {
    const repository = new StaticAtlasRepository();

    await expect(repository.getMetricDefinitions()).resolves.toHaveLength(7);
    await expect(
      repository.getMetricDefinition('collaboration'),
    ).resolves.toEqual(
      expect.objectContaining({
        name: 'Collaboration / Connectivity',
        category: 'Collaboration',
      }),
    );
    await expect(
      repository.getMetricsForEntity('institution-mit'),
    ).resolves.toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          metricId: 'research_impact',
          algorithmVersion: 'metric-engine-synthetic-transform-v1',
        }),
      ]),
    );
    await expect(repository.getMetricsForField('hep-th')).resolves.not.toEqual(
      [],
    );
    await expect(repository.getMetricsForPeriod('2026')).resolves.not.toEqual(
      [],
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

  it('exposes canonical profiles and the knowledge graph through the repository', async () => {
    const repository = new StaticAtlasRepository();

    await expect(
      repository.getInstitutionProfile('institution-mit'),
    ).resolves.toEqual(
      expect.objectContaining({
        institution: expect.objectContaining({ id: 'institution-mit' }),
        researchGroups: expect.arrayContaining([
          expect.objectContaining({ id: 'group-mit-fields' }),
        ]),
      }),
    );
    await expect(
      repository.getExternalResources('researcher', 'researcher-jonah-okafor'),
    ).resolves.not.toEqual([]);

    const graph = await repository.getKnowledgeGraph();
    expect(graph.nodes).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          key: 'researcher:researcher-jonah-okafor',
        }),
      ]),
    );
    expect(graph.edges).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          edgeType: 'researcher-affiliated-with-institution',
        }),
      ]),
    );
  });
});
