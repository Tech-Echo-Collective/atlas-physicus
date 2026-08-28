import { describe, expect, it, vi } from 'vitest';
import demoData from './demo/atlas.json';
import { defaultMetricId } from '../domain/models';
import { atlasDatasetSchema } from '../domain/schemas';
import { APIRepository, APIRepositoryError } from './APIRepository';

const provenance = {
  source: 'test API fixture',
  sourceType: 'external-api',
  version: 'test-v1',
  status: 'unverified',
} as const;
const demoDataset = atlasDatasetSchema.parse(demoData);

function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function liveDatasetFetcher() {
  const urls: URL[] = [];
  const fetcher = vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input));
    urls.push(url);
    const directResponses: Record<string, unknown> = {
      '/api/dataset': {
        ...demoDataset.metadata,
        datasetKind: 'live-api',
      },
      '/api/domains': demoDataset.scienceDomains,
      '/api/fields': demoDataset.fields,
      '/api/countries': demoDataset.countries,
      '/api/geographic-views': demoDataset.geographicViews,
      '/api/historical-events': demoDataset.historicalEvents,
      '/api/metrics': demoDataset.metricDefinitions,
    };
    if (url.pathname in directResponses) {
      return jsonResponse(directResponses[url.pathname]);
    }
    if (url.pathname === '/api/metric-observations') {
      const items = demoDataset.metricObservations.filter(
        (observation) =>
          observation.entityType === 'country' &&
          observation.metricId === url.searchParams.get('metric_id') &&
          observation.period === url.searchParams.get('period') &&
          (!url.searchParams.has('science_domain_id') ||
            observation.scienceDomainId ===
              url.searchParams.get('science_domain_id')) &&
          (url.searchParams.has('field_id')
            ? observation.fieldId === url.searchParams.get('field_id')
            : true),
      );
      return jsonResponse({
        items,
        total: items.length,
        limit: 200,
        offset: 0,
      });
    }
    return jsonResponse({ detail: 'not found' }, 404);
  });
  return { fetcher, urls };
}

describe('APIRepository', () => {
  it('bounds live bootstrap observations to the current world-map scope', async () => {
    const { fetcher, urls } = liveDatasetFetcher();
    const repository = new APIRepository({
      baseUrl: 'https://atlas.test/api',
      fetch: fetcher as typeof fetch,
    });

    const snapshot = await repository.loadDataset();
    const metricRequests = urls.filter(
      (url) => url.pathname === '/api/metric-observations',
    );

    expect(metricRequests).toHaveLength(1);
    expect(metricRequests[0]?.searchParams.get('entity_type')).toBe('country');
    expect(metricRequests[0]?.searchParams.get('science_domain_id')).toBe(
      'physics',
    );
    expect(metricRequests[0]?.searchParams.get('metric_id')).toBe(
      defaultMetricId,
    );
    expect(metricRequests[0]?.searchParams.get('period')).toBe(
      demoDataset.metadata.period,
    );
    expect(snapshot.metricObservations.every(
      (observation) =>
        observation.entityType === 'country' &&
        observation.scienceDomainId === 'physics' &&
        observation.fieldId === undefined &&
        observation.metricId === defaultMetricId &&
        observation.period === demoDataset.metadata.period,
    )).toBe(true);
  });

  it('skips country rows when bootstrapping a focused entity route', async () => {
    const { fetcher, urls } = liveDatasetFetcher();
    const repository = new APIRepository({
      baseUrl: 'https://atlas.test/api',
      fetch: fetcher as typeof fetch,
      bootstrapWorldMap: false,
    });

    const snapshot = await repository.loadDataset();

    expect(snapshot.metricObservations).toEqual([]);
    expect(
      urls.some((url) => url.pathname === '/api/metric-observations'),
    ).toBe(false);
  });

  it('requests and deterministically filters a selected world scope', async () => {
    const { fetcher, urls } = liveDatasetFetcher();
    const repository = new APIRepository({
      baseUrl: 'https://atlas.test/api',
      fetch: fetcher as typeof fetch,
    });

    const observations = await repository.getCountryMapData({
      scienceDomainId: 'physics',
      fieldId: 'hep-th',
      metricIds: [defaultMetricId, 'research_impact'],
      period: '2000',
    });
    const requests = urls.filter(
      (url) => url.pathname === '/api/metric-observations',
    );
    const request = requests[0];

    expect(requests).toHaveLength(2);
    expect(
      requests.map((candidate) => candidate.searchParams.get('metric_id')).sort(),
    ).toEqual([defaultMetricId, 'research_impact'].sort());
    expect(request?.searchParams.get('field_id')).toBe('hep-th');
    expect(request?.searchParams.has('science_domain_id')).toBe(false);
    expect(request?.searchParams.get('period')).toBe('2000');
    expect(observations.length).toBeGreaterThan(0);
    expect(observations.every(
      (observation) =>
        observation.entityType === 'country' &&
        observation.fieldId === 'hep-th' &&
        observation.period === '2000',
    )).toBe(true);
    expect(observations.map((observation) => observation.id)).toEqual(
      [...observations]
        .sort((left, right) => left.id.localeCompare(right.id))
        .map((observation) => observation.id),
    );
  });

  it('validates, paginates, and caches repository collections', async () => {
    const institutions = [
      {
        id: 'institution-one',
        name: 'Institution One',
        canonicalName: 'Institution One',
        aliases: [],
        historicalNames: [],
        externalIds: [],
        countryId: 'country-test',
        city: 'Test City',
        fieldIds: ['hep-th'],
        provenance,
      },
      {
        id: 'institution-two',
        name: 'Institution Two',
        canonicalName: 'Institution Two',
        aliases: [],
        historicalNames: [],
        externalIds: [],
        countryId: 'country-test',
        city: 'Test City',
        fieldIds: ['hep-th'],
        provenance,
      },
    ];
    const fetcher = vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(String(input));
      const offset = Number(url.searchParams.get('offset') ?? 0);
      return jsonResponse({
        items: institutions.slice(offset, offset + 1),
        total: 2,
        limit: 1,
        offset,
      });
    });
    const repository = new APIRepository({
      baseUrl: 'https://atlas.test/api',
      fetch: fetcher as typeof fetch,
    });

    const first = await repository.getInstitutions('country-test');
    const second = await repository.getInstitutions('country-test');

    expect(first.map((item) => item.id)).toEqual([
      'institution-one',
      'institution-two',
    ]);
    expect(second).toEqual(first);
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it('retrieves authorship relationships through the scoped endpoint', async () => {
    const fetcher = vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(String(input));
      expect(url.pathname).toBe('/api/authorships');
      expect(url.searchParams.get('researcher_id')).toBe('researcher-one');
      return jsonResponse({
        items: [
          {
            id: 'authorship-one',
            paperId: 'paper-one',
            researcherId: 'researcher-one',
            authorPosition: 1,
            provenance,
          },
        ],
        total: 1,
        limit: 200,
        offset: 0,
      });
    });
    const repository = new APIRepository({
      baseUrl: 'https://atlas.test/api',
      fetch: fetcher as typeof fetch,
    });

    await expect(repository.getAuthorships('researcher-one')).resolves.toMatchObject([
      { paperId: 'paper-one', researcherId: 'researcher-one' },
    ]);
  });

  it('loads a canonical paper and paper-scoped authorships for search navigation', async () => {
    const fetcher = vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(String(input));
      if (url.pathname === '/api/papers/paper-one') {
        return jsonResponse({
          id: 'paper-one',
          title: 'A canonical paper',
          summary: '',
          year: 2026,
          fieldIds: [],
          doi: null,
          arxivId: null,
          provenance,
        });
      }
      expect(url.pathname).toBe('/api/authorships');
      expect(url.searchParams.get('researcher_id')).toBeNull();
      expect(url.searchParams.get('paper_id')).toBe('paper-one');
      return jsonResponse({
        items: [
          {
            id: 'authorship-one',
            paperId: 'paper-one',
            researcherId: 'researcher-one',
            authorPosition: 1,
            provenance,
          },
        ],
        total: 1,
        limit: 200,
        offset: 0,
      });
    });
    const repository = new APIRepository({
      baseUrl: 'https://atlas.test/api',
      fetch: fetcher as typeof fetch,
    });

    await expect(repository.getPaper('paper-one')).resolves.toMatchObject({
      id: 'paper-one',
      summary: '',
      fieldIds: [],
      doi: undefined,
    });
    await expect(
      repository.getAuthorships(undefined, 'paper-one'),
    ).resolves.toMatchObject([{ researcherId: 'researcher-one' }]);
  });

  it('normalizes nullable API metadata and search evidence', async () => {
    const fetcher = vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(String(input));
      if (url.pathname === '/api/dataset') {
        return jsonResponse({
          schemaVersion: '3.0.4-alpha',
          datasetKind: 'live-api',
          period: '2026',
          generatedAt: '2026-08-28T00:00:00Z',
          latestUpdateAt: null,
          sourceSnapshotIds: [],
          updateSequence: 0,
          disclaimer: 'No records ingested.',
          provenance: { ...provenance, confidence: null, retrievedAt: null },
        });
      }
      return jsonResponse([
        {
          entityId: 'paper-one',
          entityType: 'paper',
          label: 'A canonical paper',
          context: 'Paper · 2026',
          matchConfidence: 1,
          matchedOn: 'external-identifier',
          matchedValue: null,
          identityConfidence: null,
        },
      ]);
    });
    const repository = new APIRepository({
      baseUrl: 'https://atlas.test/api',
      fetch: fetcher as typeof fetch,
    });

    await expect(repository.getMetadata()).resolves.toMatchObject({
      latestUpdateAt: undefined,
      provenance: { confidence: undefined, retrievedAt: undefined },
    });
    await expect(repository.searchEntities('10.1234/test')).resolves.toEqual([
      expect.objectContaining({
        entityId: 'paper-one',
        matchedValue: undefined,
        identityConfidence: undefined,
      }),
    ]);
  });

  it('returns null for missing profiles and exposes structured failures', async () => {
    const fetcher = vi.fn(async (input: RequestInfo | URL) => {
      const path = new URL(String(input)).pathname;
      return path.endsWith('/missing')
        ? jsonResponse({ detail: { code: 'entity_not_found' } }, 404)
        : jsonResponse(
            { error: { code: 'source_unavailable', message: 'Source unavailable' } },
            503,
          );
    });
    const repository = new APIRepository({
      baseUrl: 'https://atlas.test/api',
      fetch: fetcher as typeof fetch,
    });

    await expect(repository.getInstitutionProfile('missing')).resolves.toBeNull();
    await expect(repository.getCountries()).rejects.toEqual(
      expect.objectContaining<Partial<APIRepositoryError>>({
        code: 'source_unavailable',
        status: 503,
      }),
    );
  });
});
