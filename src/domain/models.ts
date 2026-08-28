export const defaultMetricId = 'research_activity_score' as const;
export const compositeMetricId = 'user_defined_composite' as const;

export type MetricId = string;
export type EntityType =
  | 'science-domain'
  | 'field'
  | 'country'
  | 'institution'
  | 'research-group'
  | 'researcher';

export type IdentityEntityType = 'institution' | 'researcher' | 'paper';

export type CanonicalEntityType =
  | EntityType
  | 'research-field'
  | 'paper';

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

/**
 * An authority-issued identifier. Resolvable URLs belong in ExternalResource,
 * not in canonical entity records.
 */
export interface ExternalIdentifier {
  scheme: string;
  value: string;
}

export interface CanonicalIdentityFields {
  canonicalName?: string;
  aliases?: string[];
  historicalNames?: string[];
  externalIds?: ExternalIdentifier[];
  /** Confidence in the canonical identity, not a scientific-quality score. */
  identityConfidence?: number;
}

export type RawEntityAttribute =
  | string
  | number
  | boolean
  | null
  | RawEntityAttribute[]
  | { [key: string]: RawEntityAttribute };

/** Immutable source-facing input to identity resolution. */
export interface RawEntityRecord extends Provenanced {
  id: string;
  entityType: IdentityEntityType;
  sourceRecordId: string;
  sourceSnapshotId?: string;
  rawName: string;
  externalIds: ExternalIdentifier[];
  attributes: Record<string, RawEntityAttribute>;
  ingestedAt: string;
}

export type IdentityResolutionStatus =
  | 'matched'
  | 'unresolved'
  | 'ambiguous';

export type IdentityResolutionMethod =
  | 'external-identifier'
  | 'canonical-name'
  | 'alias'
  | 'historical-name'
  | 'fuzzy-name'
  | 'source-record-identifier'
  | 'manual-review'
  | 'insufficient-metadata';

export type IdentityEvidenceMethod =
  | IdentityResolutionMethod
  | 'required-metadata';

export interface IdentityEvidence {
  method: IdentityEvidenceMethod;
  inputValue: string;
  candidateEntityId?: string;
  canonicalValue?: string;
  score: number;
}

/** Auditable decision connecting a raw record to one canonical entity. */
export interface IdentityResolution extends Provenanced {
  id: string;
  rawEntityRecordId: string;
  entityType: IdentityEntityType;
  status: IdentityResolutionStatus;
  canonicalEntityId?: string;
  method?: IdentityResolutionMethod;
  confidence: number;
  evidence: IdentityEvidence[];
  resolverVersion: string;
  resolvedAt: string;
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

export interface Institution extends Provenanced, CanonicalIdentityFields {
  id: string;
  /** @deprecated Prefer canonicalName. Retained for alpha UI compatibility. */
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

export interface Researcher extends Provenanced, CanonicalIdentityFields {
  id: string;
  /** @deprecated Prefer canonicalName. Retained for alpha UI compatibility. */
  name: string;
  fieldIds: string[];
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
  /** ISO 8601 date or reduced-precision year/month. */
  startDate?: string;
  /** Omitted for a current/open-ended affiliation. */
  endDate?: string;
  /** Source assertion for this time-dependent relationship. */
  source?: string;
  /** Confidence in this affiliation assertion. */
  confidence?: number;
  /** @deprecated Prefer startDate. */
  startYear?: number;
  /** @deprecated Prefer endDate. */
  endYear?: number;
}

export type ExternalResourceType =
  | 'official-institution-website'
  | 'department-website'
  | 'research-group-website'
  | 'institutional-profile'
  | 'researcher-homepage'
  | 'ror'
  | 'wikidata'
  | 'orcid'
  | 'inspire'
  | 'arxiv'
  | 'doi'
  | 'publisher-landing-page';

/** URLs are isolated here so canonical entities remain source-independent. */
export interface ExternalResource extends Provenanced {
  id: string;
  entityType: 'institution' | 'research-group' | 'researcher' | 'paper';
  entityId: string;
  resourceType: ExternalResourceType;
  label: string;
  url: string;
  externalId?: ExternalIdentifier;
  isPrimary: boolean;
  validFrom?: string;
  validTo?: string;
  lastVerifiedAt?: string;
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

export interface MetricDefinition extends Provenanced {
  id: MetricId;
  name: string;
  category: string;
  description: string;
  interpretation: string;
  unit: string;
  version: string;
  requiredData: string[];
  implementationStatus:
    | 'synthetic-demo'
    | 'pilot-calculated'
    | 'live-calculated'
    | 'taxonomy-only';
}

export interface MetricObservation extends Provenanced {
  id: string;
  entityType: EntityType;
  entityId: string;
  scienceDomainId?: string;
  fieldId?: string;
  metricId: MetricId;
  period: string;
  value: number;
  source: string;
  algorithmVersion: string;
  calculationVersion: string;
  calculatedAt?: string;
}

export interface MetricWeightConfiguration {
  id: string;
  name: string;
  weights: Record<MetricId, number>;
}

export interface DatasetMetadata extends Provenanced {
  schemaVersion: string;
  datasetKind: 'synthetic-demo' | 'inspire-hep-pilot' | 'live-api';
  period: string;
  generatedAt: string;
  latestUpdateAt?: string;
  sourceSnapshotIds?: string[];
  updateSequence?: number;
  disclaimer: string;
}

export type SnapshotUpdateMode = 'full-snapshot' | 'incremental';

/** Metadata for an immutable raw-source capture that can be reprocessed. */
export interface SourceSnapshot extends Provenanced {
  id: string;
  source: string;
  sourceVersion: string;
  capturedAt: string;
  updateMode: SnapshotUpdateMode;
  recordCount: number;
  previousSnapshotId?: string;
  contentChecksum?: string;
  storageReference?: string;
}

export interface EntityChangeSummary {
  created: number;
  updated: number;
  unchanged: number;
  unresolved: number;
  failed: number;
}

/** Append-only record of a dataset update or deterministic reprocessing run. */
export interface DatasetUpdate extends Provenanced {
  id: string;
  appliedAt: string;
  updateMode: SnapshotUpdateMode | 'reprocess';
  sourceSnapshotIds: string[];
  previousDatasetVersion?: string;
  datasetVersion: string;
  resolverVersion: string;
  metricCalculationVersion?: string;
  changes: EntityChangeSummary;
  affectedEntities: Array<{
    entityType: IdentityEntityType;
    entityId: string;
  }>;
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
  externalResources?: ExternalResource[];
  rawEntityRecords?: RawEntityRecord[];
  identityResolutions?: IdentityResolution[];
  sourceSnapshots?: SourceSnapshot[];
  datasetUpdates?: DatasetUpdate[];
  historicalEvents: HistoricalEvent[];
  metricDefinitions: MetricDefinition[];
  metricObservations: MetricObservation[];
}

export interface MetricQuery {
  entityType: EntityType;
  scienceDomainId?: string;
  fieldId?: string;
  metricId?: MetricId;
  period: string;
}

export interface AtlasRepository {
  /** Optional efficient snapshot load used by static and API-backed adapters. */
  loadDataset?(): Promise<AtlasDataset>;
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
  getMetricDefinitions(): Promise<MetricDefinition[]>;
  getMetricDefinition(id: MetricId): Promise<MetricDefinition | null>;
  getMetricObservations(metricId?: MetricId): Promise<MetricObservation[]>;
  getMetricsForEntity(entityId: string): Promise<MetricObservation[]>;
  getMetricsForField(fieldId: string): Promise<MetricObservation[]>;
  getMetricsForPeriod(period: string): Promise<MetricObservation[]>;
  findMetricObservations(query: MetricQuery): Promise<MetricObservation[]>;
  searchEntities(query: string, limit?: number): Promise<AtlasSearchResult[]>;
}

export type AtlasSearchEntityType =
  | 'science-domain'
  | 'research-field'
  | 'country'
  | 'institution'
  | 'research-group'
  | 'researcher'
  | 'paper';

export type AtlasSearchMatchMethod =
  | 'external-identifier'
  | 'canonical-name'
  | 'alias'
  | 'historical-name'
  | 'abbreviation'
  | 'fuzzy-name';

export interface AtlasSearchResult {
  entityId: string;
  entityType: AtlasSearchEntityType;
  label: string;
  context: string;
  matchConfidence: number;
  matchedOn: AtlasSearchMatchMethod;
  matchedValue?: string;
  identityConfidence?: number;
}
