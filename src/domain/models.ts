export const prototypeMetricId = 'research_activity_score' as const;

export type PrototypeMetricId = typeof prototypeMetricId;
export type EntityType = 'country' | 'institution' | 'researcher' | 'field';

export interface ResearchField {
  id: string;
  label: string;
  description: string;
}

export interface Country {
  id: string;
  isoAlpha3: string;
  isoNumeric: string;
  name: string;
  region: string;
}

export interface Institution {
  id: string;
  name: string;
  countryId: string;
  city: string;
  fieldIds: string[];
}

export interface Researcher {
  id: string;
  name: string;
  institutionId: string;
  fieldIds: string[];
}

export interface MetricObservation {
  id: string;
  entityType: EntityType;
  entityId: string;
  fieldId: string;
  metricId: PrototypeMetricId;
  period: string;
  value: number;
  provenance: 'synthetic-demo';
}

export interface DatasetMetadata {
  schemaVersion: string;
  datasetKind: 'synthetic-demo';
  period: string;
  generatedAt: string;
  disclaimer: string;
}

export interface AtlasDataset {
  metadata: DatasetMetadata;
  fields: ResearchField[];
  countries: Country[];
  institutions: Institution[];
  researchers: Researcher[];
  metricObservations: MetricObservation[];
}

export interface MetricQuery {
  entityType: EntityType;
  fieldId: string;
  metricId: PrototypeMetricId;
  period: string;
}

export interface AtlasRepository {
  loadDataset(): Promise<AtlasDataset>;
  findMetricObservations(query: MetricQuery): Promise<MetricObservation[]>;
}
