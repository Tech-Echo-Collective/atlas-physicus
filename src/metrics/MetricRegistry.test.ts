import type { MetricDefinition } from '../domain/models';
import {
  isVisualizationReadyMetricDefinition,
  MetricRegistry,
} from './MetricRegistry';

const provenance = {
  source: 'Synthetic metric test',
  sourceType: 'synthetic-demo' as const,
  version: 'v3.0.1-alpha',
  status: 'synthetic' as const,
};

const definitions: MetricDefinition[] = [
  {
    id: 'activity',
    name: 'Activity',
    category: 'Activity',
    description: 'Synthetic activity test metric.',
    interpretation: 'Synthetic test interpretation.',
    unit: 'index',
    version: 'v1',
    requiredData: ['demo fixture'],
    implementationStatus: 'synthetic-demo',
    provenance,
  },
  {
    id: 'impact',
    name: 'Impact',
    category: 'Impact',
    description: 'Synthetic impact test metric.',
    interpretation: 'Synthetic test interpretation.',
    unit: 'index',
    version: 'v1',
    requiredData: ['demo fixture'],
    implementationStatus: 'synthetic-demo',
    provenance,
  },
  {
    id: 'candidate-connectivity',
    name: 'Candidate Connectivity',
    category: 'Collaboration',
    description: 'Candidate method under scientific review.',
    interpretation: 'Not yet available as an observation.',
    unit: 'normalized score',
    version: 'connectivity-distinct-partners-v1',
    requiredData: ['source-scope:hep-th-v1'],
    implementationStatus: 'experimental-candidate',
    provenance,
  },
  {
    id: 'talent-ecosystem',
    name: 'Talent Ecosystem',
    category: 'Talent Ecosystem',
    description: 'Future taxonomy test definition.',
    interpretation: 'No observation is calculated in this test.',
    unit: 'taxonomy definition only',
    version: 'v1',
    requiredData: ['future data'],
    implementationStatus: 'taxonomy-only',
    provenance,
  },
];

describe('MetricRegistry', () => {
  it('discovers metrics by identifier and category', () => {
    const registry = new MetricRegistry(definitions);

    expect(registry.getMetrics()).toHaveLength(4);
    expect(registry.getMetricDefinition('impact')).toEqual(definitions[1]);
    expect(registry.getMetricsByCategory('activity')).toEqual([
      definitions[0],
    ]);
    expect(registry.getVisualizationMetrics()).toEqual(definitions.slice(0, 2));
    expect(registry.getExperimentalCandidateMetrics()).toEqual([definitions[2]]);
    expect(registry.getTaxonomyOnlyMetrics()).toEqual([definitions[3]]);
    expect(registry.getMetricDefinition('missing')).toBeNull();
  });

  it('uses an explicit visualization-ready allowlist', () => {
    expect(isVisualizationReadyMetricDefinition(definitions[0])).toBe(true);
    expect(isVisualizationReadyMetricDefinition(definitions[1])).toBe(true);
    expect(isVisualizationReadyMetricDefinition(definitions[2])).toBe(false);
    expect(isVisualizationReadyMetricDefinition(definitions[3])).toBe(false);
    expect(
      isVisualizationReadyMetricDefinition({
        implementationStatus: 'live-calculated',
      }),
    ).toBe(true);
  });

  it('rejects duplicate metric identifiers', () => {
    expect(() => new MetricRegistry([definitions[0], definitions[0]])).toThrow(
      /unique identifiers/,
    );
  });
});
