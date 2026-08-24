import demoData from './demo/atlas.json';
import type {
  Affiliation,
  AtlasDataset,
  AtlasRepository,
  AtlasSearchResult,
  Authorship,
  Country,
  DatasetMetadata,
  GeographicView,
  HistoricalEvent,
  Institution,
  MetricObservation,
  MetricQuery,
  Paper,
  Researcher,
  ResearchField,
  ResearchGroup,
  ScienceDomain,
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

  async getMetricObservations(): Promise<MetricObservation[]> {
    return [...this.dataset.metricObservations];
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

  async searchEntities(query: string, limit = 8): Promise<AtlasSearchResult[]> {
    const normalizedQuery = query.trim().toLocaleLowerCase();
    if (!normalizedQuery) {
      return [];
    }

    const candidates: Array<AtlasSearchResult & { searchable: string }> = [
      ...this.dataset.scienceDomains.map((domain) => ({
        entityId: domain.id,
        entityType: 'science-domain' as const,
        label: domain.label,
        context: 'Science domain',
        searchable: `${domain.id} ${domain.label}`.toLocaleLowerCase(),
      })),
      ...this.dataset.fields.map((field) => ({
        entityId: field.id,
        entityType: 'research-field' as const,
        label: field.label,
        context: `Research field · ${field.id}`,
        searchable: `${field.id} ${field.label}`.toLocaleLowerCase(),
      })),
      ...this.dataset.countries.map((country) => ({
        entityId: country.id,
        entityType: 'country' as const,
        label: country.name,
        context: `Country · ${country.region}`,
        searchable:
          `${country.name} ${country.isoAlpha3} ${country.region}`.toLocaleLowerCase(),
      })),
      ...this.dataset.institutions.map((institution) => ({
        entityId: institution.id,
        entityType: 'institution' as const,
        label: institution.name,
        context: `Institution · ${institution.city}`,
        searchable:
          `${institution.id} ${institution.name} ${institution.city}`.toLocaleLowerCase(),
      })),
      ...this.dataset.researchers.map((researcher) => ({
        entityId: researcher.id,
        entityType: 'researcher' as const,
        label: researcher.name,
        context: `Researcher · ${researcher.fieldIds.join(' · ')}`,
        searchable:
          `${researcher.name} ${researcher.fieldIds.join(' ')}`.toLocaleLowerCase(),
      })),
    ];

    return candidates
      .filter((candidate) => candidate.searchable.includes(normalizedQuery))
      .sort((left, right) => {
        const leftStarts = left.label.toLocaleLowerCase().startsWith(normalizedQuery);
        const rightStarts = right.label
          .toLocaleLowerCase()
          .startsWith(normalizedQuery);
        return Number(rightStarts) - Number(leftStarts) ||
          left.label.localeCompare(right.label);
      })
      .slice(0, limit)
      .map((candidate) => ({
        entityId: candidate.entityId,
        entityType: candidate.entityType,
        label: candidate.label,
        context: candidate.context,
      }));
  }
}

export const atlasRepository = new StaticAtlasRepository();
