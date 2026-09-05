import { z } from 'zod';
import type {
  Affiliation,
  AtlasUpdateStatus,
  AtlasDataset,
  AtlasSearchResult,
  Authorship,
  Country,
  DatasetMetadata,
  DatasetUpdate,
  ExternalResource,
  GeographicView,
  HistoricalEvent,
  IdentityEntityType,
  IdentityResolution,
  IdentityResolutionSummary,
  IdentityResolutionStatus,
  Institution,
  MetricDefinition,
  MetricId,
  MetricObservation,
  MetricQuery,
  Paper,
  RawEntityRecord,
  Researcher,
  ResearchField,
  ResearchGroup,
  ScienceDomain,
  SourceSnapshot,
} from '../domain/models';
import { defaultMetricId } from '../domain/models';
import {
  affiliationSchema,
  atlasUpdateStatusSchema,
  authorshipSchema,
  countrySchema,
  datasetUpdateSchema,
  externalResourceSchema,
  geographicViewSchema,
  historicalEventSchema,
  identityResolutionSchema,
  identityResolutionSummarySchema,
  institutionSchema,
  metricDefinitionSchema,
  metricObservationSchema,
  optionalFromNullable,
  paperSchema,
  provenanceSchema,
  rawEntityRecordSchema,
  researcherSchema,
  researchFieldSchema,
  researchGroupSchema,
  scienceDomainSchema,
  sourceSnapshotSchema,
} from '../domain/schemas';
import { KnowledgeGraphService } from '../knowledge/KnowledgeGraph';
import { getVisualizationReadyMetricDefinitions } from '../metrics/MetricRegistry';
import type { ScientificKnowledgeGraph } from '../knowledge/KnowledgeGraph';
import type {
  InstitutionProfileData,
  ResearcherProfileData,
  ResearchGroupProfileData,
} from '../profiles/ProfileService';
import type {
  AtlasApiTransport,
  ScientificAtlasRepository,
} from './ScientificAtlasRepository';

export interface APIRepositoryOptions {
  baseUrl?: string;
  fetch?: typeof fetch;
  cacheTtlMs?: number;
  bootstrapWorldMap?: boolean;
}

export interface InstitutionMapData {
  institutions: Institution[];
  observations: MetricObservation[];
}

export interface CountryMapQuery {
  scienceDomainId: string;
  fieldId?: string;
  metricIds: MetricId[];
  period: string;
}

/**
 * Accept an absolute HTTP(S) endpoint or a root-relative same-origin path.
 * Empty or malformed configuration leaves live mode unavailable instead of
 * making the static GitHub Pages build issue requests to an accidental URL.
 */
export function normalizeAtlasApiBaseUrl(value: unknown): string | null {
  if (typeof value !== 'string') {
    return null;
  }

  const candidate = value.trim().replace(/\/+$/, '');
  if (!candidate) {
    return null;
  }
  if (candidate.startsWith('/')) {
    return candidate;
  }

  try {
    const url = new URL(candidate);
    return url.protocol === 'http:' || url.protocol === 'https:'
      ? candidate
      : null;
  } catch {
    return null;
  }
}

interface CacheEntry {
  expiresAt: number;
  value: unknown;
}

const pageSchema = <T extends z.ZodType>(item: T) =>
  z.object({
    items: z.array(item),
    total: z.number().int().nonnegative(),
    limit: z.number().int().positive(),
    offset: z.number().int().nonnegative(),
  });

const metadataSchema = z.object({
  schemaVersion: z.string().min(1),
  datasetKind: z.enum(['synthetic-demo', 'inspire-hep-pilot', 'live-api']),
  period: z.string().regex(/^\d{4}$/),
  generatedAt: z.string().datetime(),
  latestUpdateAt: optionalFromNullable(z.string().datetime()),
  sourceSnapshotIds: z.array(z.string()).default([]),
  updateSequence: z.number().int().nonnegative().default(0),
  disclaimer: z.string().min(1),
  provenance: provenanceSchema,
});

const institutionMapNodeSchema = z.object({
  institution: institutionSchema,
  observation: metricObservationSchema,
});

const searchResultSchema = z.object({
  entityId: z.string().min(1),
  entityType: z.enum([
    'science-domain',
    'research-field',
    'country',
    'institution',
    'research-group',
    'researcher',
    'paper',
  ]),
  label: z.string().min(1),
  context: z.string(),
  matchConfidence: z.number().min(0).max(1),
  matchedOn: z.enum([
    'external-identifier',
    'canonical-name',
    'alias',
    'historical-name',
    'abbreviation',
    'fuzzy-name',
  ]),
  matchedValue: optionalFromNullable(z.string()),
  identityConfidence: optionalFromNullable(z.number().min(0).max(1)),
});

export class APIRepositoryError extends Error {
  constructor(
    message: string,
    readonly status?: number,
    readonly code = 'api_repository_error',
  ) {
    super(message);
    this.name = 'APIRepositoryError';
  }
}

/**
 * HTTP adapter for the existing repository boundary. Requests with the same
 * key supersede stale in-flight work, and validated GET responses use a short
 * bounded cache. It contains no visualization or selection state.
 */
export class APIRepository
  implements ScientificAtlasRepository, AtlasApiTransport
{
  private readonly baseUrl: string;
  private readonly fetcher: typeof fetch;
  private readonly cacheTtlMs: number;
  private readonly bootstrapWorldMap: boolean;
  private readonly cache = new Map<string, CacheEntry>();
  private readonly inFlight = new Map<string, AbortController>();

  constructor(options: APIRepositoryOptions = {}) {
    const configuredUrl = import.meta.env.VITE_ATLAS_API_URL as
      | string
      | undefined;
    this.baseUrl =
      normalizeAtlasApiBaseUrl(options.baseUrl ?? configuredUrl) ?? '/api';
    this.fetcher = options.fetch ?? globalThis.fetch.bind(globalThis);
    this.cacheTtlMs = options.cacheTtlMs ?? 30_000;
    this.bootstrapWorldMap = options.bootstrapWorldMap ?? true;
  }

  clearCache(): void {
    this.cache.clear();
  }

  cancelPending(): void {
    this.inFlight.forEach((controller) => controller.abort());
    this.inFlight.clear();
  }

  private url(path: string, parameters?: Record<string, string | undefined>): string {
    const query = new URLSearchParams();
    Object.entries(parameters ?? {}).forEach(([key, value]) => {
      if (value !== undefined) query.set(key, value);
    });
    const serialized = query.toString();
    return `${this.baseUrl}${path}${serialized ? `?${serialized}` : ''}`;
  }

  private async request(
    path: string,
    parameters?: Record<string, string | undefined>,
    options: { allowNotFound?: boolean; cache?: boolean } = {},
  ): Promise<unknown | null> {
    const url = this.url(path, parameters);
    const cached = this.cache.get(url);
    if (options.cache !== false && cached && cached.expiresAt > Date.now()) {
      return cached.value;
    }

    this.inFlight.get(url)?.abort();
    const controller = new AbortController();
    this.inFlight.set(url, controller);
    try {
      const response = await this.fetcher(url, {
        headers: { Accept: 'application/json' },
        signal: controller.signal,
      });
      if (response.status === 404 && options.allowNotFound) return null;
      if (!response.ok) {
        let message = `Atlas Physica API returned ${response.status}`;
        let code = 'http_error';
        try {
          const body = (await response.json()) as {
            error?: { message?: string; code?: string };
            detail?: { message?: string; code?: string };
          };
          message = body.error?.message ?? body.detail?.message ?? message;
          code = body.error?.code ?? body.detail?.code ?? code;
        } catch {
          // The status is still sufficient when a proxy returns non-JSON.
        }
        throw new APIRepositoryError(message, response.status, code);
      }
      const value: unknown = await response.json();
      if (options.cache !== false) {
        this.cache.set(url, { value, expiresAt: Date.now() + this.cacheTtlMs });
      }
      return value;
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') {
        throw new APIRepositoryError('Superseded Atlas API request was cancelled', undefined, 'request_cancelled');
      }
      if (error instanceof APIRepositoryError) throw error;
      throw new APIRepositoryError(
        error instanceof Error ? error.message : 'Atlas Physica API request failed',
        undefined,
        'network_error',
      );
    } finally {
      if (this.inFlight.get(url) === controller) this.inFlight.delete(url);
    }
  }

  private async collection<T>(
    path: string,
    schema: z.ZodType<T>,
    parameters?: Record<string, string | undefined>,
  ): Promise<T[]> {
    const first = pageSchema(schema).parse(
      await this.request(path, { ...parameters, limit: '200', offset: '0' }),
    );
    const items = [...first.items];
    for (let offset = first.limit; offset < first.total; offset += first.limit) {
      const next = pageSchema(schema).parse(
        await this.request(path, {
          ...parameters,
          limit: String(first.limit),
          offset: String(offset),
        }),
      );
      items.push(...next.items);
    }
    return items;
  }

  private async visualizationMetricDefinitions(
    requestedMetricIds: MetricId[],
  ): Promise<Map<MetricId, MetricDefinition>> {
    const requestedIds = new Set(requestedMetricIds);
    const visualizationDefinitions = getVisualizationReadyMetricDefinitions(
      await this.getMetricDefinitions(),
    );
    return new Map(
      visualizationDefinitions
        .filter((definition) => requestedIds.has(definition.id))
        .map((definition) => [definition.id, definition]),
    );
  }

  async getDatasetVersion(): Promise<string> {
    const metadata = await this.getMetadata();
    return metadata.provenance.version;
  }

  async fetchRepositorySnapshot(): Promise<unknown> {
    return this.loadDataset();
  }

  async searchCanonicalEntities(query: string, limit = 8): Promise<unknown> {
    return this.searchEntities(query, limit);
  }

  async loadDataset(): Promise<AtlasDataset> {
    const [
      metadata,
      scienceDomains,
      fields,
      countries,
      geographicViews,
      historicalEvents,
      metricDefinitions,
    ] = await Promise.all([
      this.getMetadata(),
      this.getScienceDomains(),
      this.getResearchFields(),
      this.getCountries(),
      this.getGeographicViews(),
      this.getHistoricalEvents(),
      this.getMetricDefinitions(),
    ]);
    const implementedMetricIds = getVisualizationReadyMetricDefinitions(
      metricDefinitions,
    )
      .map((definition) => definition.id);
    const bootstrapMetricId = implementedMetricIds.includes(defaultMetricId)
      ? defaultMetricId
      : implementedMetricIds[0];
    const bootstrapDomainId = scienceDomains[0]?.id;
    const metricObservations =
      this.bootstrapWorldMap && bootstrapMetricId && bootstrapDomainId
        ? await this.getCountryMapData({
            scienceDomainId: bootstrapDomainId,
            metricIds: [bootstrapMetricId],
            period: metadata.period,
          })
        : [];

    // The live bootstrap is intentionally map-only. Country institutions and
    // entity profiles are fetched through scoped repository queries when the
    // user enters those views; researchers, papers, raw records, and the full
    // graph are never downloaded during source selection.
    return {
      metadata,
      scienceDomains,
      fields,
      countries,
      geographicViews,
      institutions: [],
      researchers: [],
      researchGroups: [],
      affiliations: [],
      papers: [],
      authorships: [],
      externalResources: [],
      rawEntityRecords: [],
      identityResolutions: [],
      sourceSnapshots: [],
      datasetUpdates: [],
      historicalEvents,
      metricDefinitions,
      metricObservations,
    };
  }

  async getMetadata(): Promise<DatasetMetadata> {
    return metadataSchema.parse(await this.request('/dataset'));
  }

  async getScienceDomains(): Promise<ScienceDomain[]> {
    return z.array(scienceDomainSchema).parse(await this.request('/domains'));
  }

  async getResearchFields(scienceDomainId?: string): Promise<ResearchField[]> {
    return z.array(researchFieldSchema).parse(
      await this.request('/fields', { domain_id: scienceDomainId }),
    );
  }

  async getCountries(): Promise<Country[]> {
    return z.array(countrySchema).parse(await this.request('/countries'));
  }

  async getCountry(id: string): Promise<Country | null> {
    const value = await this.request(`/countries/${encodeURIComponent(id)}`, undefined, { allowNotFound: true });
    return value === null ? null : countrySchema.parse(value);
  }

  async getGeographicViews(): Promise<GeographicView[]> {
    return z.array(geographicViewSchema).parse(await this.request('/geographic-views'));
  }

  async getInstitutions(countryId?: string): Promise<Institution[]> {
    return this.collection('/institutions', institutionSchema, { country_id: countryId });
  }

  async getInstitution(id: string): Promise<Institution | null> {
    const value = await this.request(`/institutions/${encodeURIComponent(id)}`, undefined, { allowNotFound: true });
    return value === null ? null : institutionSchema.parse(value);
  }

  async getInstitutionMapData(
    countryIds: string[],
    query: {
      scienceDomainId: string;
      fieldId?: string;
      metricIds: MetricId[];
      period: string;
      limit?: number;
    },
  ): Promise<InstitutionMapData> {
    const [metricDefinitions, metadata] = await Promise.all([
      this.visualizationMetricDefinitions(query.metricIds),
      this.getMetadata(),
    ]);
    const metricIds = [...metricDefinitions.keys()];
    if (metricIds.length === 0) {
      return { institutions: [], observations: [] };
    }
    const requests = countryIds.flatMap((countryId) =>
      metricIds.map((metricId) =>
        this.request('/map/institutions', {
          country_id: countryId,
          science_domain_id: query.scienceDomainId,
          field_id: query.fieldId,
          metric_id: metricId,
          period: query.period,
          limit: String(query.limit ?? 50),
        }),
      ),
    );
    const nodes = (
      await Promise.all(requests)
    ).flatMap((payload) => z.array(institutionMapNodeSchema).parse(payload));
    const institutions = new Map<string, Institution>();
    const observations = new Map<string, MetricObservation>();
    nodes.forEach((node) => {
      if (
        node.observation.metricDefinitionVersion !==
          metricDefinitions.get(node.observation.metricId)?.version ||
        node.observation.dataSourceVersion !== metadata.provenance.version ||
        (metadata.provenance.acquisitionScope !== undefined &&
          node.observation.acquisitionScope !==
            metadata.provenance.acquisitionScope)
      ) {
        return;
      }
      institutions.set(node.institution.id, node.institution);
      observations.set(node.observation.id, node.observation);
    });
    return {
      institutions: [...institutions.values()],
      observations: [...observations.values()],
    };
  }

  async getCountryMapData(query: CountryMapQuery): Promise<MetricObservation[]> {
    const [metricDefinitions, metadata] = await Promise.all([
      this.visualizationMetricDefinitions(query.metricIds),
      this.getMetadata(),
    ]);
    const metricIds = [...metricDefinitions.keys()];
    if (metricIds.length === 0) {
      return [];
    }
    const observations = (
      await Promise.all(
        metricIds.map((metricId) =>
          this.collection('/metric-observations', metricObservationSchema, {
            entity_type: 'country',
            science_domain_id: query.fieldId
              ? undefined
              : query.scienceDomainId,
            field_id: query.fieldId,
            metric_id: metricId,
            period: query.period,
          }),
        ),
      )
    ).flat();
    const exactScope = observations.filter(
      (observation) =>
        observation.entityType === 'country' &&
        observation.period === query.period &&
        observation.metricDefinitionVersion ===
          metricDefinitions.get(observation.metricId)?.version &&
        observation.dataSourceVersion === metadata.provenance.version &&
        (metadata.provenance.acquisitionScope === undefined ||
          observation.acquisitionScope ===
            metadata.provenance.acquisitionScope) &&
        (query.fieldId
          ? observation.fieldId === query.fieldId
          : observation.scienceDomainId === query.scienceDomainId &&
            observation.fieldId === undefined),
    );
    return [
      ...new Map(
        exactScope.map((observation) => [observation.id, observation]),
      ).values(),
    ].sort((left, right) => left.id.localeCompare(right.id));
  }

  async getResearchGroups(institutionId?: string): Promise<ResearchGroup[]> {
    return this.collection('/groups', researchGroupSchema, { institution_id: institutionId });
  }

  async getResearchers(institutionId?: string): Promise<Researcher[]> {
    return this.collection('/researchers', researcherSchema, { institution_id: institutionId });
  }

  async getResearcher(id: string): Promise<Researcher | null> {
    const value = await this.request(`/researchers/${encodeURIComponent(id)}`, undefined, { allowNotFound: true });
    return value === null ? null : researcherSchema.parse(value);
  }

  async getAffiliations(institutionId?: string): Promise<Affiliation[]> {
    return this.collection('/affiliations', affiliationSchema, {
      institution_id: institutionId,
    });
  }

  async getPapers(researcherId?: string): Promise<Paper[]> {
    return this.collection('/papers', paperSchema, { researcher_id: researcherId });
  }

  async getPaper(id: string): Promise<Paper | null> {
    const value = await this.request(
      `/papers/${encodeURIComponent(id)}`,
      undefined,
      { allowNotFound: true },
    );
    return value === null ? null : paperSchema.parse(value);
  }

  async getAuthorships(
    researcherId?: string,
    paperId?: string,
  ): Promise<Authorship[]> {
    return this.collection('/authorships', authorshipSchema, {
      researcher_id: researcherId,
      paper_id: paperId,
    });
  }

  async getHistoricalEvents(fieldId?: string): Promise<HistoricalEvent[]> {
    return z.array(historicalEventSchema).parse(
      await this.request('/historical-events', { field_id: fieldId }),
    );
  }

  async getMetricDefinitions(): Promise<MetricDefinition[]> {
    return z.array(metricDefinitionSchema).parse(await this.request('/metrics'));
  }

  async getMetricDefinition(id: MetricId): Promise<MetricDefinition | null> {
    const value = await this.request(`/metrics/${encodeURIComponent(id)}`, undefined, { allowNotFound: true });
    return value === null ? null : metricDefinitionSchema.parse(value);
  }

  async getMetricObservations(metricId?: MetricId): Promise<MetricObservation[]> {
    return this.collection('/metric-observations', metricObservationSchema, { metric_id: metricId });
  }

  async getMetricsForEntity(entityId: string): Promise<MetricObservation[]> {
    return this.collection('/metric-observations', metricObservationSchema, { entity_id: entityId });
  }

  async getMetricsForField(fieldId: string): Promise<MetricObservation[]> {
    return this.collection('/metric-observations', metricObservationSchema, { field_id: fieldId });
  }

  async getMetricsForPeriod(period: string): Promise<MetricObservation[]> {
    return this.collection('/metric-observations', metricObservationSchema, { period });
  }

  async findMetricObservations(query: MetricQuery): Promise<MetricObservation[]> {
    return this.collection('/metric-observations', metricObservationSchema, {
      entity_type: query.entityType,
      science_domain_id: query.scienceDomainId,
      field_id: query.fieldId,
      metric_id: query.metricId,
      period: query.period,
    });
  }

  async searchEntities(query: string, limit = 8): Promise<AtlasSearchResult[]> {
    return z.array(searchResultSchema).parse(
      await this.request('/search', { q: query, limit: String(limit) }, { cache: false }),
    );
  }

  async getRawEntityRecords(entityType?: IdentityEntityType): Promise<RawEntityRecord[]> {
    return this.collection('/raw-entity-records', rawEntityRecordSchema, {
      entity_type: entityType,
    });
  }

  async getIdentityResolutions(status?: IdentityResolutionStatus): Promise<IdentityResolution[]> {
    return this.collection('/identity-resolutions', identityResolutionSchema, {
      resolution_status: status,
    });
  }

  async getExternalResources(
    entityType?: ExternalResource['entityType'],
    entityId?: string,
  ): Promise<ExternalResource[]> {
    return this.collection('/external-resources', externalResourceSchema, {
      entity_type: entityType,
      entity_id: entityId,
    });
  }

  async getSourceSnapshots(): Promise<SourceSnapshot[]> {
    return this.collection('/source-snapshots', sourceSnapshotSchema);
  }

  async getDatasetUpdates(): Promise<DatasetUpdate[]> {
    return this.collection('/dataset-updates', datasetUpdateSchema);
  }

  async getUpdateStatus(): Promise<AtlasUpdateStatus> {
    return atlasUpdateStatusSchema.parse(
      await this.request('/updates/status', undefined, { cache: false }),
    );
  }

  async getIdentityResolutionSummary(): Promise<IdentityResolutionSummary> {
    return identityResolutionSummarySchema.parse(
      await this.request('/identity-resolutions/summary', undefined, {
        cache: false,
      }),
    );
  }

  async getKnowledgeGraph(): Promise<ScientificKnowledgeGraph> {
    return new KnowledgeGraphService().build(await this.loadDataset());
  }

  async getInstitutionProfile(id: string): Promise<InstitutionProfileData | null> {
    const value = await this.request(`/profiles/institutions/${encodeURIComponent(id)}`, undefined, { allowNotFound: true });
    if (value === null) return null;
    const record = value as Record<string, unknown>;
    return {
      institution: institutionSchema.parse(record.institution),
      resources: z.array(externalResourceSchema).parse(record.resources),
      researchGroups: z.array(researchGroupSchema).parse(record.researchGroups),
      affiliations: z.array(affiliationSchema).parse(record.affiliations),
      researchers: z.array(researcherSchema).parse(record.researchers),
      papers: z.array(paperSchema).parse(record.papers),
      metrics: z.array(metricObservationSchema).parse(record.metrics),
    };
  }

  async getResearcherProfile(id: string): Promise<ResearcherProfileData | null> {
    const value = await this.request(`/profiles/researchers/${encodeURIComponent(id)}`, undefined, { allowNotFound: true });
    if (value === null) return null;
    const record = value as Record<string, unknown>;
    return {
      researcher: researcherSchema.parse(record.researcher),
      resources: z.array(externalResourceSchema).parse(record.resources),
      fields: z.array(researchFieldSchema).parse(record.fields),
      affiliationHistory: z.array(z.object({
        affiliation: affiliationSchema,
        institution: institutionSchema,
        researchGroup: researchGroupSchema.nullable(),
      })).parse(record.affiliationHistory),
      papers: z.array(paperSchema).parse(record.papers),
      collaborators: z.array(researcherSchema).parse(record.collaborators),
      metrics: z.array(metricObservationSchema).parse(record.metrics),
    };
  }

  async getResearchGroupProfile(id: string): Promise<ResearchGroupProfileData | null> {
    const value = await this.request(`/profiles/groups/${encodeURIComponent(id)}`, undefined, { allowNotFound: true });
    if (value === null) return null;
    const record = value as Record<string, unknown>;
    return {
      researchGroup: researchGroupSchema.parse(record.researchGroup),
      institution: institutionSchema.parse(record.institution),
      resources: z.array(externalResourceSchema).parse(record.resources),
      fields: z.array(researchFieldSchema).parse(record.fields),
      affiliations: z.array(affiliationSchema).parse(record.affiliations),
      members: z.array(researcherSchema).parse(record.members),
      papers: z.array(paperSchema).parse(record.papers),
    };
  }
}
