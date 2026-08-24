export const prototypeMetricId = 'research_activity_score' as const;

export type PrototypeMetricId = typeof prototypeMetricId;
export type EntityType = 'country' | 'institution' | 'researcher' | 'field';

export interface ScienceDomain {
  id: string;
  label: string;
  description: string;
  fieldIds: string[];
}

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

export interface GeographicView {
  id: string;
  countryId: string;
  geometryIsoNumerics: string[];
  locationCountryIds: string[];
  provenance: 'synthetic-demo';
}

export interface Institution {
  id: string;
  name: string;
  countryId: string;
  city: string;
  fieldIds: string[];
  location?: InstitutionLocation;
}

export interface InstitutionLocation {
  longitude: number;
  latitude: number;
}

export interface Researcher {
  id: string;
  name: string;
  /** @deprecated Phase 2.1 compatibility fallback. Prefer Affiliation records. */
  institutionId?: string;
  fieldIds: string[];
  externalLinks?: ResearcherExternalLinks;
}

export interface ResearcherExternalLinks {
  institutionalHomepage?: string;
  personalWebsite?: string;
  arxiv?: string;
  github?: string;
}

export interface ResearchGroup {
  id: string;
  name: string;
  institutionId: string;
  description: string;
  fieldIds: string[];
}

export interface Affiliation {
  id: string;
  researcherId: string;
  institutionId: string;
  researchGroupId?: string;
  startYear?: number;
  endYear?: number;
  provenance: 'synthetic-demo';
}

export interface Paper {
  id: string;
  title: string;
  summary: string;
  year: number;
  fieldIds: string[];
  provenance: 'synthetic-demo';
}

export interface Authorship {
  id: string;
  paperId: string;
  researcherId: string;
  authorPosition: number;
}

export interface HistoricalEvent {
  id: string;
  title: string;
  summary: string;
  year: number;
  fieldId: string;
  relatedResearcherIds: string[];
  relatedInstitutionIds: string[];
  provenance: 'synthetic-demo';
}

export interface MetricObservation {
  id: string;
  entityType: EntityType;
  entityId: string;
  scienceDomainId?: string;
  fieldId?: string;
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
  scienceDomains: ScienceDomain[];
  fields: ResearchField[];
  countries: Country[];
  geographicViews: GeographicView[];
  institutions: Institution[];
  researchers: Researcher[];
  researchGroups: ResearchGroup[];
  affiliations: Affiliation[];
  papers: Paper[];
  authorships: Authorship[];
  historicalEvents: HistoricalEvent[];
  metricObservations: MetricObservation[];
}

export interface MetricQuery {
  entityType: EntityType;
  scienceDomainId?: string;
  fieldId?: string;
  metricId: PrototypeMetricId;
  period: string;
}

export interface AtlasRepository {
  loadDataset(): Promise<AtlasDataset>;
  findMetricObservations(query: MetricQuery): Promise<MetricObservation[]>;
}
