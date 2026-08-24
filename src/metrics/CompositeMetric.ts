import {
  compositeMetricId,
  type MetricDefinition,
  type MetricId,
  type MetricObservation,
  type MetricWeightConfiguration,
} from '../domain/models';
import { metricWeightConfigurationSchema } from '../domain/schemas';
export { defaultMetricWeightConfiguration } from './MetricProfiles';

export function validateMetricWeightConfiguration(
  configuration: MetricWeightConfiguration,
): MetricWeightConfiguration {
  return metricWeightConfigurationSchema.parse(configuration);
}

export function hasCompositeMetricInputs(
  definitions: MetricDefinition[],
  configuration: MetricWeightConfiguration,
): boolean {
  return Object.keys(configuration.weights).every((metricId) =>
    definitions.some(
      (definition) =>
        definition.id === metricId &&
        definition.implementationStatus !== 'taxonomy-only',
    ),
  );
}

function observationScopeKey(observation: MetricObservation): string {
  return [
    observation.entityType,
    observation.entityId,
    observation.scienceDomainId ?? '',
    observation.fieldId ?? '',
    observation.period,
  ].join('|');
}

export function buildCompositeMetricObservations(
  observations: MetricObservation[],
  configuration: MetricWeightConfiguration,
): MetricObservation[] {
  const validatedConfiguration = validateMetricWeightConfiguration(configuration);
  const activeMetricIds = Object.entries(validatedConfiguration.weights)
    .filter(([, weight]) => weight > 0)
    .map(([metricId]) => metricId);
  const observationsByScope = new Map<
    string,
    Map<MetricId, MetricObservation>
  >();

  observations.forEach((observation) => {
    if (!activeMetricIds.includes(observation.metricId)) {
      return;
    }
    const scopeKey = observationScopeKey(observation);
    const scopedObservations = observationsByScope.get(scopeKey) ?? new Map();
    scopedObservations.set(observation.metricId, observation);
    observationsByScope.set(scopeKey, scopedObservations);
  });

  return Array.from(observationsByScope.entries()).flatMap(
    ([scopeKey, scopedObservations]) => {
      if (
        activeMetricIds.some((metricId) => !scopedObservations.has(metricId))
      ) {
        return [];
      }

      const baselineObservation = scopedObservations.get(activeMetricIds[0]);
      if (!baselineObservation) {
        return [];
      }
      const value = activeMetricIds.reduce((sum, metricId) => {
        const observation = scopedObservations.get(metricId);
        const weight = validatedConfiguration.weights[metricId] / 100;
        return sum + (observation?.value ?? 0) * weight;
      }, 0);
      const safeScopeId = scopeKey
        .replaceAll('|', '-')
        .replace(/[^a-z0-9-]/g, '')
        .replace(/-+/g, '-');

      return [
        {
          ...baselineObservation,
          id: `composite-${safeScopeId}`,
          metricId: compositeMetricId,
          value: Math.round(value * 10) / 10,
          source: 'user-defined-synthetic-composite',
          algorithmVersion: 'metric-engine-weighted-sum-v1',
          calculationVersion: 'v3.0.1-alpha',
          provenance: {
            source: 'User-defined composite of synthetic demo metrics',
            sourceType: 'derived',
            version: 'v3.0.1-alpha',
            status: 'synthetic',
          },
        },
      ];
    },
  );
}
