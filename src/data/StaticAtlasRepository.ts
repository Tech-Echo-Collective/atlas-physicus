import demoData from './demo/atlas.json';
import type {
  AtlasDataset,
  AtlasRepository,
  MetricObservation,
  MetricQuery,
} from '../domain/models';
import { atlasDatasetSchema } from '../domain/schemas';

export class StaticAtlasRepository implements AtlasRepository {
  private readonly dataset: AtlasDataset;

  constructor(source: unknown = demoData) {
    this.dataset = atlasDatasetSchema.parse(source);
  }

  async loadDataset(): Promise<AtlasDataset> {
    return this.dataset;
  }

  async findMetricObservations(
    query: MetricQuery,
  ): Promise<MetricObservation[]> {
    return this.dataset.metricObservations.filter(
      (observation) =>
        observation.entityType === query.entityType &&
        (query.scienceDomainId === undefined ||
          observation.scienceDomainId === query.scienceDomainId) &&
        observation.fieldId === query.fieldId &&
        observation.metricId === query.metricId &&
        observation.period === query.period,
    );
  }
}

export const atlasRepository = new StaticAtlasRepository();
