import type {
  MetricDefinition,
  MetricId,
  MetricImplementationStatus,
} from '../domain/models';

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
    return this.getMetrics().filter(isVisualizationReadyMetricDefinition);
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
