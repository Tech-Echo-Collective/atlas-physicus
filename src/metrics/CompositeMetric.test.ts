import type { MetricObservation } from '../domain/models';
import {
  buildCompositeMetricObservations,
  defaultMetricWeightConfiguration,
  validateMetricWeightConfiguration,
} from './CompositeMetric';
import { metricProfiles } from './MetricProfiles';

const provenance = {
  source: 'Synthetic metric test',
  sourceType: 'synthetic-demo' as const,
  version: 'v3.0.1-alpha',
  status: 'synthetic' as const,
};

function observation(metricId: string, value: number): MetricObservation {
  return {
    id: `observation-${metricId.replaceAll('_', '-')}`,
    entityType: 'country',
    entityId: 'country-test',
    scienceDomainId: 'physics',
    metricId,
    value,
    period: '2026',
    source: 'synthetic-demo',
    algorithmVersion: 'metric-engine-test-v1',
    calculationVersion: 'v3.0.1-alpha',
    provenance,
  };
}

describe('composite metric weighting', () => {
  it('provides valid predefined profiles that each total exactly 100%', () => {
    expect(metricProfiles).toHaveLength(4);
    metricProfiles.forEach((profile) => {
      const total = Object.values(profile.weights).reduce(
        (sum, weight) => sum + weight,
        0,
      );
      expect(total).toBe(100);
      expect(() => validateMetricWeightConfiguration(profile)).not.toThrow();
    });
  });

  it('builds a user profile without modifying raw observations', () => {
    const rawObservations = [
      observation('research_activity_score', 80),
      observation('research_impact', 60),
      observation('collaboration', 40),
      observation('research_diversity', 30),
      observation('momentum', 20),
    ];
    const originalValues = rawObservations.map((item) => item.value);
    const composite = buildCompositeMetricObservations(
      rawObservations,
      defaultMetricWeightConfiguration,
    );

    expect(composite).toEqual([
      expect.objectContaining({
        metricId: 'user_defined_composite',
        value: 50.5,
        source: 'user-defined-synthetic-composite',
        algorithmVersion: 'metric-engine-weighted-sum-v1',
      }),
    ]);
    expect(rawObservations.map((item) => item.value)).toEqual(originalValues);
  });

  it('accepts direct decimal inputs and rejects invalid totals or negatives', () => {
    expect(() =>
      validateMetricWeightConfiguration({
        id: 'decimal-profile',
        name: 'Decimal profile',
        weights: { research_activity_score: 33.3, research_impact: 66.7 },
      }),
    ).not.toThrow();
    expect(() =>
      validateMetricWeightConfiguration({
        ...defaultMetricWeightConfiguration,
        weights: { research_activity_score: 99.7 },
      }),
    ).toThrow();
    expect(() =>
      validateMetricWeightConfiguration({
        id: 'negative-profile',
        name: 'Negative profile',
        weights: { research_activity_score: -10, research_impact: 110 },
      }),
    ).toThrow();
  });
});
