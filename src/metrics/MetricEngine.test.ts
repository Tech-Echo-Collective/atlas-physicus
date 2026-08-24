import { StaticAtlasRepository } from '../data/StaticAtlasRepository';

describe('synthetic Metric Engine integration', () => {
  it('emits versioned observations for every registered demo metric', async () => {
    const repository = new StaticAtlasRepository();
    const definitions = await repository.getMetricDefinitions();
    const observations = await repository.getMetricObservations();
    const metricIds = new Set(observations.map((observation) => observation.metricId));

    expect(definitions).toHaveLength(7);
    expect(metricIds).toEqual(
      new Set([
        'research_activity_score',
        'research_impact',
        'collaboration',
        'research_diversity',
        'momentum',
      ]),
    );
    expect(observations).toHaveLength(332 * 5);
    expect(
      definitions.filter(
        (definition) => definition.implementationStatus === 'taxonomy-only',
      ).map((definition) => definition.id),
    ).toEqual(['talent_ecosystem', 'concentration_vulnerability']);
    expect(
      observations.every(
        (observation) =>
          observation.source &&
          observation.algorithmVersion &&
          observation.calculationVersion,
      ),
    ).toBe(true);
  });
});
