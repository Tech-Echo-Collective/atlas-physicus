import demoData from './demo/atlas.json';
import type {
  Affiliation,
  AtlasDataset,
  AtlasSearchResult,
  Authorship,
  Country,
  DatasetUpdate,
  DatasetMetadata,
  ExternalResource,
  GeographicView,
  HistoricalEvent,
  IdentityEntityType,
  IdentityResolution,
  IdentityResolutionStatus,
  Institution,
  MetricDefinition,
  MetricId,
  MetricObservation,
  MetricQuery,
  Paper,
  Researcher,
  ResearchField,
  ResearchGroup,
  RawEntityRecord,
  ScienceDomain,
  SourceSnapshot,
} from '../domain/models';
import { atlasDatasetSchema } from '../domain/schemas';
import {
  KnowledgeGraphService,
  type ScientificKnowledgeGraph,
} from '../knowledge/KnowledgeGraph';
import { MetricRegistry } from '../metrics/MetricRegistry';
import { createSyntheticDemoMetricEngine } from '../metrics/SyntheticDemoMetricCalculator';
import {
  ProfileService,
  type InstitutionProfileData,
  type ResearcherProfileData,
  type ResearchGroupProfileData,
} from '../profiles/ProfileService';
import { EntitySearchIndex } from '../search/EntitySearchIndex';
import type { ScientificAtlasRepository } from './ScientificAtlasRepository';

export class StaticAtlasRepository implements ScientificAtlasRepository {
  private readonly dataset: AtlasDataset;
  private readonly metricRegistry: MetricRegistry;
  private readonly searchIndex: EntitySearchIndex;
  private readonly profileService: ProfileService;
  private readonly knowledgeGraph: ScientificKnowledgeGraph;

  constructor(source: unknown = demoData) {
    const validatedDataset = atlasDatasetSchema.parse(source);
    this.metricRegistry = new MetricRegistry(
      validatedDataset.metricDefinitions,
    );
    if (validatedDataset.metadata.datasetKind !== 'synthetic-demo') {
      this.dataset = validatedDataset;
      this.searchIndex = new EntitySearchIndex(this.dataset);
      this.profileService = new ProfileService(this.dataset);
      this.knowledgeGraph = new KnowledgeGraphService().build(this.dataset);
      return;
    }

    const metricEngine = createSyntheticDemoMetricEngine(this.metricRegistry);
    this.dataset = atlasDatasetSchema.parse({
      ...validatedDataset,
      metricObservations: metricEngine.calculateAll(validatedDataset),
    });
    this.searchIndex = new EntitySearchIndex(this.dataset);
    this.profileService = new ProfileService(this.dataset);
    this.knowledgeGraph = new KnowledgeGraphService().build(this.dataset);
  }

  async loadDataset(): Promise<AtlasDataset> {
    return this.dataset;
  }

  async getMetadata(): Promise<DatasetMetadata> {
    return this.dataset.metadata;
  }

  async getScienceDomains(): Promise<ScienceDomain[]> {
    return [...this.dataset.scienceDomains];
  }

  async getResearchFields(
    scienceDomainId?: string,
  ): Promise<ResearchField[]> {
    if (!scienceDomainId) {
      return [...this.dataset.fields];
    }

    const fieldIds = new Set(
      this.dataset.scienceDomains.find(
        (domain) => domain.id === scienceDomainId,
      )?.fieldIds ?? [],
    );
    return this.dataset.fields.filter((field) => fieldIds.has(field.id));
  }

  async getCountries(): Promise<Country[]> {
    return [...this.dataset.countries];
  }

  async getCountry(id: string): Promise<Country | null> {
    return this.dataset.countries.find((country) => country.id === id) ?? null;
  }

  async getGeographicViews(): Promise<GeographicView[]> {
    return [...this.dataset.geographicViews];
  }

  async getInstitutions(countryId?: string): Promise<Institution[]> {
    return this.dataset.institutions.filter(
      (institution) => !countryId || institution.countryId === countryId,
    );
  }

  async getInstitution(id: string): Promise<Institution | null> {
    return (
      this.dataset.institutions.find((institution) => institution.id === id) ??
      null
    );
  }

  async getResearchGroups(institutionId?: string): Promise<ResearchGroup[]> {
    return this.dataset.researchGroups.filter(
      (group) => !institutionId || group.institutionId === institutionId,
    );
  }

  async getResearchers(institutionId?: string): Promise<Researcher[]> {
    if (!institutionId) {
      return [...this.dataset.researchers];
    }

    const researcherIds = new Set(
      this.dataset.affiliations
        .filter((affiliation) => affiliation.institutionId === institutionId)
        .map((affiliation) => affiliation.researcherId),
    );
    return this.dataset.researchers.filter((researcher) =>
      researcherIds.has(researcher.id),
    );
  }

  async getResearcher(id: string): Promise<Researcher | null> {
    return (
      this.dataset.researchers.find((researcher) => researcher.id === id) ??
      null
    );
  }

  async getAffiliations(institutionId?: string): Promise<Affiliation[]> {
    return this.dataset.affiliations.filter(
      (affiliation) =>
        !institutionId || affiliation.institutionId === institutionId,
    );
  }

  async getPapers(researcherId?: string): Promise<Paper[]> {
    if (!researcherId) {
      return [...this.dataset.papers];
    }

    const paperIds = new Set(
      this.dataset.authorships
        .filter((authorship) => authorship.researcherId === researcherId)
        .map((authorship) => authorship.paperId),
    );
    return this.dataset.papers.filter((paper) => paperIds.has(paper.id));
  }

  async getAuthorships(researcherId?: string): Promise<Authorship[]> {
    return this.dataset.authorships.filter(
      (authorship) =>
        !researcherId || authorship.researcherId === researcherId,
    );
  }

  async getHistoricalEvents(fieldId?: string): Promise<HistoricalEvent[]> {
    return this.dataset.historicalEvents.filter(
      (event) => !fieldId || event.fieldId === fieldId,
    );
  }

  async getMetricDefinitions(): Promise<MetricDefinition[]> {
    return this.metricRegistry.getMetrics();
  }

  async getMetricDefinition(id: MetricId): Promise<MetricDefinition | null> {
    return this.metricRegistry.getMetricDefinition(id);
  }

  async getMetricObservations(
    metricId?: MetricId,
  ): Promise<MetricObservation[]> {
    return this.dataset.metricObservations.filter(
      (observation) => !metricId || observation.metricId === metricId,
    );
  }

  async getMetricsForEntity(entityId: string): Promise<MetricObservation[]> {
    return this.dataset.metricObservations.filter(
      (observation) => observation.entityId === entityId,
    );
  }

  async getMetricsForField(fieldId: string): Promise<MetricObservation[]> {
    return this.dataset.metricObservations.filter(
      (observation) => observation.fieldId === fieldId,
    );
  }

  async getMetricsForPeriod(period: string): Promise<MetricObservation[]> {
    return this.dataset.metricObservations.filter(
      (observation) => observation.period === period,
    );
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
        (query.metricId === undefined ||
          observation.metricId === query.metricId) &&
        observation.period === query.period,
    );
  }

  async searchEntities(query: string, limit = 8): Promise<AtlasSearchResult[]> {
    return this.searchIndex.search(query, limit);
  }

  async getRawEntityRecords(
    entityType?: IdentityEntityType,
  ): Promise<RawEntityRecord[]> {
    return (this.dataset.rawEntityRecords ?? []).filter(
      (record) => !entityType || record.entityType === entityType,
    );
  }

  async getIdentityResolutions(
    status?: IdentityResolutionStatus,
  ): Promise<IdentityResolution[]> {
    return (this.dataset.identityResolutions ?? []).filter(
      (resolution) => !status || resolution.status === status,
    );
  }

  async getExternalResources(
    entityType?: ExternalResource['entityType'],
    entityId?: string,
  ): Promise<ExternalResource[]> {
    return (this.dataset.externalResources ?? []).filter(
      (resource) =>
        (!entityType || resource.entityType === entityType) &&
        (!entityId || resource.entityId === entityId),
    );
  }

  async getSourceSnapshots(): Promise<SourceSnapshot[]> {
    return [...(this.dataset.sourceSnapshots ?? [])];
  }

  async getDatasetUpdates(): Promise<DatasetUpdate[]> {
    return [...(this.dataset.datasetUpdates ?? [])];
  }

  async getKnowledgeGraph(): Promise<ScientificKnowledgeGraph> {
    return this.knowledgeGraph;
  }

  async getInstitutionProfile(
    id: string,
  ): Promise<InstitutionProfileData | null> {
    return this.profileService.getInstitutionProfile(id);
  }

  async getResearcherProfile(id: string): Promise<ResearcherProfileData | null> {
    return this.profileService.getResearcherProfile(id);
  }

  async getResearchGroupProfile(
    id: string,
  ): Promise<ResearchGroupProfileData | null> {
    return this.profileService.getResearchGroupProfile(id);
  }
}

export const atlasRepository = new StaticAtlasRepository();
