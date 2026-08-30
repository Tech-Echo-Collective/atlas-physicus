import { metricSystemV1Ids, type MetricDefinition } from '../domain/models';
import {
  getVisualizationReadyMetricDefinitions,
  hasCompleteVisualizationMetricSystem,
  isVisualizationReadyMetricDefinition,
  MetricRegistry,
} from './MetricRegistry';

const provenance = {
  source: 'Synthetic metric test',
  sourceType: 'synthetic-demo' as const,
  version: 'metric-system-test-v1',
  status: 'synthetic' as const,
};

function definition(
  id: string,
  implementationStatus: MetricDefinition['implementationStatus'] =
    'synthetic-demo',
): MetricDefinition {
  return {
    id,
    name: id,
    category: id,
    description: 'Synthetic metric test definition.',
    interpretation: 'Synthetic test interpretation.',
    unit: 'index',
    version: `${id}-v1`,
    requiredData: ['demo fixture'],
    implementationStatus,
    provenance,
  };
}

const completeDefinitions = metricSystemV1Ids.map((id) => definition(id));
const candidateDefinition = definition(
  'candidate-connectivity',
  'experimental-candidate',
);
const taxonomyDefinition = definition('talent-ecosystem', 'taxonomy-only');
const definitions = [
  ...completeDefinitions,
  candidateDefinition,
  taxonomyDefinition,
];

describe('MetricRegistry', () => {
  it('publishes exactly the five canonical dimensions in canonical order', () => {
    const registry = new MetricRegistry(definitions);

    expect(registry.getMetrics()).toHaveLength(7);
    expect(registry.getMetricDefinition('research_impact')).toEqual(
      completeDefinitions[1],
    );
    expect(registry.getMetricsByCategory('research_impact')).toEqual([
      completeDefinitions[1],
    ]);
    expect(registry.getVisualizationMetrics().map(({ id }) => id)).toEqual(
      metricSystemV1Ids,
    );
    expect(registry.getExperimentalCandidateMetrics()).toEqual([
      candidateDefinition,
    ]);
    expect(registry.getTaxonomyOnlyMetrics()).toEqual([taxonomyDefinition]);
    expect(registry.getMetricDefinition('missing')).toBeNull();
  });

  it('withholds every visualization metric when the system is partial', () => {
    const partialDefinitions = completeDefinitions.slice(0, -1);

    expect(hasCompleteVisualizationMetricSystem(partialDefinitions)).toBe(false);
    expect(getVisualizationReadyMetricDefinitions(partialDefinitions)).toEqual(
      [],
    );
    expect(
      new MetricRegistry(partialDefinitions).getVisualizationMetrics(),
    ).toEqual([]);
  });

  it('withholds every visualization metric when one canonical dimension is only a candidate', () => {
    const definitionsWithCandidate = completeDefinitions.map((item) =>
      item.id === 'research_diversity'
        ? { ...item, implementationStatus: 'experimental-candidate' as const }
        : item,
    );

    expect(
      getVisualizationReadyMetricDefinitions(definitionsWithCandidate),
    ).toEqual([]);
  });

  it('withholds a mixed synthetic/live definition set', () => {
    const mixedDefinitions = completeDefinitions.map((item, index) =>
      index === 0
        ? { ...item, implementationStatus: 'live-calculated' as const }
        : item,
    );

    expect(getVisualizationReadyMetricDefinitions(mixedDefinitions)).toEqual(
      [],
    );
  });

  it('uses an explicit visualization-ready status allowlist', () => {
    expect(isVisualizationReadyMetricDefinition(completeDefinitions[0])).toBe(
      true,
    );
    expect(isVisualizationReadyMetricDefinition(candidateDefinition)).toBe(
      false,
    );
    expect(isVisualizationReadyMetricDefinition(taxonomyDefinition)).toBe(
      false,
    );
    expect(
      isVisualizationReadyMetricDefinition({
        implementationStatus: 'live-calculated',
      }),
    ).toBe(true);
  });

  it('rejects duplicate metric identifiers', () => {
    expect(
      getVisualizationReadyMetricDefinitions([
        ...completeDefinitions,
        completeDefinitions[0],
      ]),
    ).toEqual([]);
    expect(
      () =>
        new MetricRegistry([completeDefinitions[0], completeDefinitions[0]]),
    ).toThrow(/unique identifiers/);
  });
});
