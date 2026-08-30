import {
  compositeMetricId,
  metricSystemV1Ids,
  type MetricDefinition,
  type MetricId,
  type MetricObservation,
  type MetricWeightConfiguration,
} from '../domain/models';
import { metricWeightConfigurationSchema } from '../domain/schemas';
import {
  hasCompleteVisualizationMetricSystem,
  isVisualizationReadyMetricDefinition,
} from './MetricRegistry';
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
  try {
    validateMetricWeightConfiguration(configuration);
  } catch {
    return false;
  }
  return hasCompleteVisualizationMetricSystem(definitions);
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
  definitions: MetricDefinition[],
): MetricObservation[] {
  const validatedConfiguration = validateMetricWeightConfiguration(configuration);
  if (!hasCompleteVisualizationMetricSystem(definitions)) {
    return [];
  }
  const activeMetricIds = Object.entries(validatedConfiguration.weights)
    .filter(([, weight]) => weight > 0)
    .map(([metricId]) => metricId);
  if (
    activeMetricIds.some(
      (metricId) =>
        !definitions.some(
          (definition) =>
            definition.id === metricId &&
            isVisualizationReadyMetricDefinition(definition),
        ),
    )
  ) {
    return [];
  }
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
      const componentObservations = activeMetricIds.map(
        (metricId) => scopedObservations.get(metricId)!,
      );
      const dataSourceVersions = new Set(
        componentObservations.map((observation) =>
          observation.dataSourceVersion ?? null,
        ),
      );
      const acquisitionScopes = new Set(
        componentObservations.map((observation) =>
          observation.acquisitionScope ??
          observation.provenance.acquisitionScope ??
          null,
        ),
      );
      if (dataSourceVersions.size !== 1 || acquisitionScopes.size !== 1) {
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
      const componentStatuses = new Set(
        componentObservations.map(
          (observation) => observation.provenance.status,
        ),
      );
      const provenanceStatus =
        componentStatuses.size === 1 && componentStatuses.has('synthetic')
          ? 'synthetic'
          : 'unverified';
      const dataSourceVersion = baselineObservation.dataSourceVersion;
      const acquisitionScope =
        baselineObservation.acquisitionScope ??
        baselineObservation.provenance.acquisitionScope;

      return [
        {
          id: `composite-${safeScopeId}`,
          entityType: baselineObservation.entityType,
          entityId: baselineObservation.entityId,
          scienceDomainId: baselineObservation.scienceDomainId,
          fieldId: baselineObservation.fieldId,
          metricId: compositeMetricId,
          period: baselineObservation.period,
          value: Math.round(value * 10) / 10,
          source: 'user-defined-composite',
          metricDefinitionVersion: 'user-defined-composite-v1',
          algorithmVersion: 'metric-engine-weighted-sum-v1',
          calculationVersion: 'user-defined-composite-v1',
          dataSourceVersion,
          acquisitionScope,
          normalizationMethod: 'weighted-sum-of-normalized-inputs-v1',
          normalizationParameters: Object.fromEntries(
            [
              ['profileId', validatedConfiguration.id],
              ['profileName', validatedConfiguration.name],
              ...metricSystemV1Ids.map((metricId) => [
                `weight:${metricId}`,
                validatedConfiguration.weights[metricId],
              ]),
              [
                'componentManifestVersion',
                'composite-component-manifest-v1',
              ],
              [
                'componentManifest',
                Object.fromEntries(
                  componentObservations.map((observation) => [
                    observation.metricId,
                    {
                      observationId: observation.id,
                      normalizedValue: observation.value,
                      metricDefinitionVersion:
                        observation.metricDefinitionVersion ?? 'legacy-v1',
                      algorithmVersion: observation.algorithmVersion,
                      calculationVersion: observation.calculationVersion,
                      dataSourceVersion: observation.dataSourceVersion ?? null,
                      acquisitionScope:
                        observation.acquisitionScope ??
                        observation.provenance.acquisitionScope ??
                        null,
                      provenanceVersion: observation.provenance.version,
                      provenanceStatus: observation.provenance.status,
                    },
                  ]),
                ),
              ],
            ],
          ),
          inputCount: activeMetricIds.length,
          qualityFlags: [
            'user-defined-perspective',
            'not-an-official-ranking',
            ...new Set(
              componentObservations.flatMap(
                (observation) => observation.qualityFlags ?? [],
              ),
            ),
          ],
          provenance: {
            source:
              'User-defined composite of visualization-ready metric observations',
            sourceType: 'derived',
            version: 'user-defined-composite-v1',
            status: provenanceStatus,
            acquisitionScope,
          },
        },
      ];
    },
  );
}

export interface PreparedMetricObservationBatch {
  observationsForState: MetricObservation[];
  observationsForVisualization: MetricObservation[];
}

/**
 * Keeps fetched base observations intact so later weighting changes can
 * re-derive a composite without another request. A composite exists only at
 * the visualization boundary; it is never persisted back into dataset state.
 */
export function prepareMetricObservationBatch(
  observations: MetricObservation[],
  selectedMetricId: MetricId,
  configuration: MetricWeightConfiguration,
  definitions: MetricDefinition[],
): PreparedMetricObservationBatch {
  return {
    observationsForState: observations,
    observationsForVisualization:
      selectedMetricId === compositeMetricId
        ? buildCompositeMetricObservations(
            observations,
            configuration,
            definitions,
          )
        : observations,
  };
}
