export const prototypeMetricId = 'research_activity_score' as const;

export type PrototypeMetricId = typeof prototypeMetricId;
export type EntityType = 'country' | 'institution' | 'researcher' | 'field';

export type ProvenanceSourceType =
  | 'synthetic-demo'
  | 'external-api'
  | 'institutional-source'
  | 'derived';
export type ProvenanceStatus =
  | 'synthetic'
  | 'unverified'
  | 'verified'
  | 'deprecated';

export interface DataProvenance {
  source: string;
  sourceType: ProvenanceSourceType;
  version: string;
  status: ProvenanceStatus;
  confidence?: number;
  retrievedAt?: string;
}

export interface Provenanced {
  provenance: DataProvenance;
}

export interface ScienceDomain extends Provenanced {
  id: string;
  label: string;
  description: string;
  fieldIds: string[];
}

export interface ResearchField extends Provenanced {
  id: string;
  label: string;
  description: string;
}

export interface Country extends Provenanced {
  id: string;
  isoAlpha3: string;
  isoNumeric: string;
  name: string;
  region: string;
}

export interface GeographicView extends Provenanced {
  id: string;
  countryId: string;
  geometryIsoNumerics: string[];
  locationCountryIds: string[];
}

export interface Institution extends Provenanced {
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

export interface Researcher extends Provenanced {
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

export interface ResearchGroup extends Provenanced {
  id: string;
  name: string;
  institutionId: string;
  description: string;
  fieldIds: string[];
}

export interface Affiliation extends Provenanced {
  id: string;
  researcherId: string;
  institutionId: string;
  researchGroupId?: string;
  startYear?: number;
  endYear?: number;
}

export interface ExternalIdentifier {
  scheme: string;
  value: string;
  url?: string;
}

export interface Paper extends Provenanced {
  id: string;
  title: string;
  summary: string;
  year: number;
  fieldIds: string[];
  doi?: string;
  arxivId?: string;
  externalIdentifiers?: ExternalIdentifier[];
}

export interface Authorship extends Provenanced {
  id: string;
  paperId: string;
  researcherId: string;
  authorPosition: number;
}

export interface HistoricalEvent extends Provenanced {
  id: string;
  title: string;
  summary: string;
  year: number;
  fieldId: string;
  relatedResearcherIds: string[];
  relatedInstitutionIds: string[];
}

export interface MetricObservation extends Provenanced {
  id: string;
  entityType: EntityType;
  entityId: string;
  scienceDomainId?: string;
  fieldId?: string;
  metricId: PrototypeMetricId;
  period: string;
  value: number;
}

export interface DatasetMetadata extends Provenanced {
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
  getMetadata(): Promise<DatasetMetadata>;
  getScienceDomains(): Promise<ScienceDomain[]>;
  getResearchFields(scienceDomainId?: string): Promise<ResearchField[]>;
  getCountries(): Promise<Country[]>;
  getCountry(id: string): Promise<Country | null>;
  getGeographicViews(): Promise<GeographicView[]>;
  getInstitutions(countryId?: string): Promise<Institution[]>;
  getInstitution(id: string): Promise<Institution | null>;
  getResearchGroups(institutionId?: string): Promise<ResearchGroup[]>;
  getResearchers(institutionId?: string): Promise<Researcher[]>;
  getResearcher(id: string): Promise<Researcher | null>;
  getAffiliations(institutionId?: string): Promise<Affiliation[]>;
  getPapers(researcherId?: string): Promise<Paper[]>;
  getAuthorships(researcherId?: string): Promise<Authorship[]>;
  getHistoricalEvents(fieldId?: string): Promise<HistoricalEvent[]>;
  getMetricObservations(): Promise<MetricObservation[]>;
  findMetricObservations(query: MetricQuery): Promise<MetricObservation[]>;
  searchEntities(query: string, limit?: number): Promise<AtlasSearchResult[]>;
}

export type AtlasSearchEntityType =
  | 'science-domain'
  | 'research-field'
  | 'country'
  | 'institution'
  | 'researcher';

export interface AtlasSearchResult {
  entityId: string;
  entityType: AtlasSearchEntityType;
  label: string;
  context: string;
}
