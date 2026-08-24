import {
  defaultMetricId,
  type AtlasDataset,
  type MetricDefinition,
  type MetricObservation,
} from '../domain/models';
import type { MetricCalculator } from './MetricEngine';
import { MetricEngine } from './MetricEngine';
import { MetricRegistry } from './MetricRegistry';

interface SyntheticTransform {
  baselineWeight: number;
  variationAmplitude: number;
}

const syntheticTransforms: Record<string, SyntheticTransform> = {
  research_impact: { baselineWeight: 0.88, variationAmplitude: 8 },
  collaboration: { baselineWeight: 0.74, variationAmplitude: 12 },
  research_diversity: { baselineWeight: 0.7, variationAmplitude: 10 },
  momentum: { baselineWeight: 0.64, variationAmplitude: 16 },
};

function stableVariation(seed: string): number {
  let hash = 0;
  for (const character of seed) {
    hash = (hash * 31 + character.charCodeAt(0)) >>> 0;
  }
  return (hash % 2_001) / 1_000 - 1;
}

function clampMetricValue(value: number): number {
  return Math.min(100, Math.max(0, Math.round(value * 10) / 10));
}

export class StoredObservationCalculator implements MetricCalculator {
  calculate(
    dataset: AtlasDataset,
    definition: MetricDefinition,
  ): MetricObservation[] {
    return dataset.metricObservations.filter(
      (observation) => observation.metricId === definition.id,
    );
  }
}

export class SyntheticDemoMetricCalculator implements MetricCalculator {
  constructor(
    private readonly baselineMetricId: string,
    private readonly transform: SyntheticTransform,
  ) {}

  calculate(
    dataset: AtlasDataset,
    definition: MetricDefinition,
  ): MetricObservation[] {
    const storedObservations = dataset.metricObservations.filter(
      (observation) => observation.metricId === definition.id,
    );
    if (storedObservations.length > 0) {
      return storedObservations;
    }

    return dataset.metricObservations
      .filter(
        (observation) => observation.metricId === this.baselineMetricId,
      )
      .map((observation) => {
        const variation =
          stableVariation(
            `${definition.id}:${observation.entityId}:${observation.period}:${observation.fieldId ?? observation.scienceDomainId}`,
          ) * this.transform.variationAmplitude;
        const transformedValue =
          observation.value * this.transform.baselineWeight +
          50 * (1 - this.transform.baselineWeight) +
          variation;

        return {
          ...observation,
          id: `${observation.id}-${definition.id.replaceAll('_', '-')}`,
          metricId: definition.id,
          value: clampMetricValue(transformedValue),
          source: 'synthetic-demo',
          algorithmVersion: 'metric-engine-synthetic-transform-v1',
          calculationVersion: definition.version,
          provenance: {
            source: 'Physics Atlas synthetic Metric Engine demonstration',
            sourceType: 'derived',
            version: 'v3.0.1-alpha',
            status: 'synthetic',
          },
        };
      });
  }
}

export function createSyntheticDemoMetricEngine(
  registry: MetricRegistry,
): MetricEngine {
  const engine = new MetricEngine(registry);

  registry.getVisualizationMetrics().forEach((definition) => {
    if (definition.id === defaultMetricId) {
      engine.registerCalculator(
        definition.id,
        new StoredObservationCalculator(),
      );
      return;
    }

    const transform = syntheticTransforms[definition.id];
    engine.registerCalculator(
      definition.id,
      transform
        ? new SyntheticDemoMetricCalculator(defaultMetricId, transform)
        : new StoredObservationCalculator(),
    );
  });

  return engine;
}
