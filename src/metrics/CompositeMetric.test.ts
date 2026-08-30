import {
  metricSystemV1Ids,
  type MetricObservation,
} from '../domain/models';
import {
  buildCompositeMetricObservations,
  defaultMetricWeightConfiguration,
  hasCompositeMetricInputs,
  prepareMetricObservationBatch,
  validateMetricWeightConfiguration,
} from './CompositeMetric';
import { mergeMetricObservationsById } from '../data/AtlasDataSources';
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

function definition(
  metricId: string,
  implementationStatus:
    | 'synthetic-demo'
    | 'experimental-candidate'
    | 'live-calculated' = 'synthetic-demo',
) {
  return {
    id: metricId,
    name: metricId,
    category: metricId,
    description: 'Metric test definition.',
    interpretation: 'Metric test interpretation.',
    unit: 'index',
    version: 'test-v1',
    requiredData: ['test fixture'],
    implementationStatus,
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
      expect(Object.keys(profile.weights).sort()).toEqual(
        [...metricSystemV1Ids].sort(),
      );
      expect(
        Object.values(profile.weights).every((weight) => weight * 2 % 1 === 0),
      ).toBe(true);
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
      rawObservations.map((item) => definition(item.metricId)),
    );

    expect(composite).toEqual([
      expect.objectContaining({
        metricId: 'user_defined_composite',
        value: 50.5,
        source: 'user-defined-composite',
        algorithmVersion: 'metric-engine-weighted-sum-v1',
        normalizationParameters: expect.objectContaining({
          profileId: defaultMetricWeightConfiguration.id,
          profileName: defaultMetricWeightConfiguration.name,
          'weight:research_activity_score': 25,
          'weight:research_impact': 25,
          'weight:collaboration': 20,
          'weight:research_diversity': 15,
          'weight:momentum': 15,
          componentManifestVersion: 'composite-component-manifest-v1',
          componentManifest: expect.objectContaining({
            research_activity_score: expect.objectContaining({
              observationId: 'observation-research-activity-score',
              normalizedValue: 80,
              metricDefinitionVersion: 'legacy-v1',
              algorithmVersion: 'metric-engine-test-v1',
              calculationVersion: 'v3.0.1-alpha',
              dataSourceVersion: null,
              acquisitionScope: null,
              provenanceVersion: 'v3.0.1-alpha',
              provenanceStatus: 'synthetic',
            }),
          }),
        }),
        inputCount: 5,
      }),
    ]);
    expect(rawObservations.map((item) => item.value)).toEqual(originalValues);
  });

  it('never composes candidate definitions even when observations exist', () => {
    const observations = [
      observation('research_activity_score', 80),
      observation('research_impact', 60),
      observation('collaboration', 40),
      observation('research_diversity', 30),
      observation('momentum', 20),
    ];
    const definitions = observations.map((item) =>
      definition(
        item.metricId,
        item.metricId === 'research_activity_score'
          ? 'experimental-candidate'
          : 'synthetic-demo',
      ),
    );

    expect(
      buildCompositeMetricObservations(
        observations,
        defaultMetricWeightConfiguration,
        definitions,
      ),
    ).toEqual([]);
  });

  it('rejects a partial metric system even when omitted dimensions have zero weight', () => {
    const observations = [
      observation('research_activity_score', 80),
      observation('research_impact', 60),
      observation('collaboration', 40),
      observation('research_diversity', 30),
    ];
    const configuration = {
      id: 'partial-zero-profile',
      name: 'Partial zero profile',
      weights: {
        research_activity_score: 50,
        research_impact: 50,
        collaboration: 0,
        research_diversity: 0,
        momentum: 0,
      },
    };
    const definitions = observations.map((item) => definition(item.metricId));

    expect(hasCompositeMetricInputs(definitions, configuration)).toBe(false);
    expect(
      buildCompositeMetricObservations(
        observations,
        configuration,
        definitions,
      ),
    ).toEqual([]);
  });

  it('retains live base inputs in state and derives a confirmed composite at render time', () => {
    const liveInputs = [
      observation('research_activity_score', 80),
      observation('research_impact', 60),
      observation('collaboration', 40),
      observation('research_diversity', 30),
      observation('momentum', 20),
    ].map((item) => ({
      ...item,
      source: 'live-api',
      metricDefinitionVersion: 'test-v1',
      dataSourceVersion: 'live-test-v1',
      acquisitionScope: 'hep-th-v1',
      provenance: {
        source: 'Reviewed live test observation',
        sourceType: 'derived' as const,
        version: 'live-test-v1',
        status: 'verified' as const,
        acquisitionScope: 'hep-th-v1',
      },
    }));
    const definitions = liveInputs.map((item) =>
      definition(item.metricId, 'live-calculated'),
    );
    const prepared = prepareMetricObservationBatch(
      liveInputs,
      'user_defined_composite',
      defaultMetricWeightConfiguration,
      definitions,
    );

    expect(prepared.observationsForState).toEqual(liveInputs);
    expect(
      prepared.observationsForState.some(
        (item) => item.metricId === 'user_defined_composite',
      ),
    ).toBe(false);
    expect(prepared.observationsForVisualization).toEqual([
      expect.objectContaining({
        metricId: 'user_defined_composite',
        value: 50.5,
        source: 'user-defined-composite',
        dataSourceVersion: 'live-test-v1',
        acquisitionScope: 'hep-th-v1',
        provenance: expect.objectContaining({
          sourceType: 'derived',
          status: 'unverified',
          acquisitionScope: 'hep-th-v1',
        }),
        normalizationParameters: expect.objectContaining({
          componentManifest: expect.objectContaining({
            research_activity_score: expect.objectContaining({
              observationId: 'observation-research-activity-score',
              normalizedValue: 80,
              metricDefinitionVersion: 'test-v1',
              algorithmVersion: 'metric-engine-test-v1',
              calculationVersion: 'v3.0.1-alpha',
              dataSourceVersion: 'live-test-v1',
              acquisitionScope: 'hep-th-v1',
              provenanceVersion: 'live-test-v1',
              provenanceStatus: 'verified',
            }),
          }),
        }),
      }),
    ]);
    expect(prepared.observationsForVisualization[0]).not.toHaveProperty(
      'rawValue',
    );

    const stateAfterScopedFetch = mergeMetricObservationsById(
      [],
      prepared.observationsForState,
    );
    expect(
      buildCompositeMetricObservations(
        stateAfterScopedFetch,
        defaultMetricWeightConfiguration,
        definitions,
      ),
    ).toEqual([
      expect.objectContaining({
        metricId: 'user_defined_composite',
        value: 50.5,
      }),
    ]);
  });

  it('refuses to combine otherwise compatible observations from different dataset versions', () => {
    const observations = [
      observation('research_activity_score', 80),
      observation('research_impact', 60),
      observation('collaboration', 40),
      observation('research_diversity', 30),
      observation('momentum', 20),
    ].map((item, index) => ({
      ...item,
      dataSourceVersion: index === 0 ? 'dataset-old' : 'dataset-current',
    }));

    expect(
      buildCompositeMetricObservations(
        observations,
        defaultMetricWeightConfiguration,
        observations.map((item) => definition(item.metricId)),
      ),
    ).toEqual([]);
  });

  it('accepts 0.5% resolution and rejects partial, off-grid, invalid-total, or negative configurations', () => {
    expect(() =>
      validateMetricWeightConfiguration({
        id: 'decimal-profile',
        name: 'Decimal profile',
        weights: {
          research_activity_score: 33.5,
          research_impact: 31.5,
          collaboration: 15,
          research_diversity: 10,
          momentum: 10,
        },
      }),
    ).not.toThrow();
    expect(() =>
      validateMetricWeightConfiguration({
        id: 'off-grid-profile',
        name: 'Off-grid profile',
        weights: {
          research_activity_score: 33.3,
          research_impact: 31.7,
          collaboration: 15,
          research_diversity: 10,
          momentum: 10,
        },
      }),
    ).toThrow();
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
        weights: {
          research_activity_score: -10,
          research_impact: 80,
          collaboration: 10,
          research_diversity: 10,
          momentum: 10,
        },
      }),
    ).toThrow();
    expect(() =>
      validateMetricWeightConfiguration({
        id: 'wrong-total-profile',
        name: 'Wrong total profile',
        weights: {
          research_activity_score: 30,
          research_impact: 30,
          collaboration: 20,
          research_diversity: 15,
          momentum: 10,
        },
      }),
    ).toThrow();
  });
});
