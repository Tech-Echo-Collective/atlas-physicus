import type { MetricDefinition, MetricId } from '../domain/models';

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
    return this.getMetrics().filter(
      (definition) => definition.implementationStatus !== 'taxonomy-only',
    );
  }

  getTaxonomyOnlyMetrics(): MetricDefinition[] {
    return this.getMetrics().filter(
      (definition) => definition.implementationStatus === 'taxonomy-only',
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
