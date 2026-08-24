import type {
  AtlasDataset,
  MetricDefinition,
  MetricId,
  MetricObservation,
} from '../domain/models';
import { MetricRegistry } from './MetricRegistry';

export interface MetricCalculator {
  calculate(
    dataset: AtlasDataset,
    metricDefinition: MetricDefinition,
  ): MetricObservation[];
}

export class MetricEngine {
  private readonly calculators = new Map<MetricId, MetricCalculator>();

  constructor(private readonly registry: MetricRegistry) {}

  registerCalculator(
    metricId: MetricId,
    calculator: MetricCalculator,
  ): void {
    if (!this.registry.getMetricDefinition(metricId)) {
      throw new Error(`Cannot register unknown metric: ${metricId}`);
    }
    this.calculators.set(metricId, calculator);
  }

  calculate(dataset: AtlasDataset, metricId: MetricId): MetricObservation[] {
    const definition = this.registry.getMetricDefinition(metricId);
    if (!definition) {
      throw new Error(`Unknown metric definition: ${metricId}`);
    }

    const calculator = this.calculators.get(metricId);
    if (!calculator) {
      throw new Error(`No calculator registered for metric: ${metricId}`);
    }

    return calculator.calculate(dataset, definition);
  }

  calculateAll(dataset: AtlasDataset): MetricObservation[] {
    return this.registry
      .getVisualizationMetrics()
      .filter((definition) => this.calculators.has(definition.id))
      .flatMap((definition) => this.calculate(dataset, definition.id));
  }
}
