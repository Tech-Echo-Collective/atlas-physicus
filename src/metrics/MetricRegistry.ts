import type {
  MetricDefinition,
  MetricId,
  MetricImplementationStatus,
} from '../domain/models';
import { metricSystemV1Ids } from '../domain/models';

const visualizationReadyMetricStatuses: ReadonlySet<MetricImplementationStatus> =
  new Set(['synthetic-demo', 'pilot-calculated', 'live-calculated']);

/**
 * Single scientific activation gate for map layers and composites. Candidate
 * definitions remain reviewable metadata, but cannot become observations merely
 * because an API happens to return rows for them.
 */
export function isVisualizationReadyMetricDefinition(
  definition: Pick<MetricDefinition, 'implementationStatus'>,
): boolean {
  return visualizationReadyMetricStatuses.has(definition.implementationStatus);
}

/** A public metric layer is all five dimensions or none of them. */
export function hasCompleteVisualizationMetricSystem(
  definitions: readonly MetricDefinition[],
): boolean {
  const canonicalDefinitions = metricSystemV1Ids.map((metricId) => {
    const matches = definitions.filter(
      (definition) => definition.id === metricId,
    );
    return matches.length === 1 ? matches[0] : null;
  });
  if (
    canonicalDefinitions.some(
      (definition) =>
        definition === null ||
        !isVisualizationReadyMetricDefinition(definition),
    )
  ) {
    return false;
  }

  return (
    new Set(
      canonicalDefinitions.map(
        (definition) => definition!.implementationStatus,
      ),
    ).size === 1
  );
}

/**
 * Returns the coherent Metric System v1 in its canonical display order.
 * Candidate, taxonomy-only, extra, or partial definitions never leak into a
 * public visualization layer.
 */
export function getVisualizationReadyMetricDefinitions(
  definitions: readonly MetricDefinition[],
): MetricDefinition[] {
  if (!hasCompleteVisualizationMetricSystem(definitions)) {
    return [];
  }

  return metricSystemV1Ids.map(
    (metricId) => definitions.find((definition) => definition.id === metricId)!,
  );
}

export class MetricRegistry {
  private readonly definitions: Map<MetricId, MetricDefinition>;

  constructor(definitions: MetricDefinition[]) {
    this.definitions = new Map(
      definitions.map((definition) => [definition.id, definition]),
    );

    if (this.definitions.size !== definitions.length) {
      throw new Error('Metric definitions must use unique identifiers.');
    }
  }

  getMetrics(): MetricDefinition[] {
    return Array.from(this.definitions.values());
  }

  getVisualizationMetrics(): MetricDefinition[] {
    return getVisualizationReadyMetricDefinitions(this.getMetrics());
  }

  getTaxonomyOnlyMetrics(): MetricDefinition[] {
    return this.getMetrics().filter(
      (definition) => definition.implementationStatus === 'taxonomy-only',
    );
  }

  getExperimentalCandidateMetrics(): MetricDefinition[] {
    return this.getMetrics().filter(
      (definition) =>
        definition.implementationStatus === 'experimental-candidate',
    );
  }

  getMetricDefinition(id: MetricId): MetricDefinition | null {
    return this.definitions.get(id) ?? null;
  }

  getMetricsByCategory(category: string): MetricDefinition[] {
    const normalizedCategory = category.trim().toLocaleLowerCase();
    return this.getMetrics().filter(
      (definition) =>
        definition.category.toLocaleLowerCase() === normalizedCategory,
    );
  }
}
