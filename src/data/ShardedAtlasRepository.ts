import { z } from 'zod';
import type { Affiliation, AtlasDataset, Authorship, ExternalResource } from '../domain/models';
import { affiliationSchema, authorshipSchema, externalResourceSchema } from '../domain/schemas';
import { ProfileService } from '../profiles/ProfileService';
import { EntitySearchIndex } from '../search/EntitySearchIndex';
import { fieldsWithinSelection } from './ObservedScope';
import { StaticAtlasRepository } from './StaticAtlasRepository';
import type { AtlasEntityContext, AtlasEntityScope, ScopedAtlasRepository } from './ScopedAtlasRepository';

const version = 'atlas-ui-shards-v1';
const maximumShardBytes = 4 * 1024 * 1024;
const maximumIndexBytes = 8 * 1024 * 1024;
const maximumCacheBytes = 16 * 1024 * 1024;
const sha256 = z.string().regex(/^[a-f0-9]{64}$/);
const referenceSchema = z.object({
  path: z.string().regex(/^ui-[a-z0-9-]+\.json\.gz$/), encoding: z.literal('gzip'),
  sha256, bytes: z.number().int().positive().max(maximumIndexBytes),
  decodedSha256: sha256, decodedBytes: z.number().int().positive().max(maximumIndexBytes),
});
const kindSchema = z.enum(['affiliations', 'authorships', 'externalResources']);
const shardSchema = referenceSchema.extend({
  id: z.string().min(1), kind: kindSchema,
  bytes: z.number().int().positive().max(maximumShardBytes),
  decodedBytes: z.number().int().positive().max(maximumShardBytes),
  recordCount: z.number().int().positive(),
});
export const uiShardsSchema = z.object({
  version: z.literal(version), index: referenceSchema,
  shards: z.array(shardSchema).max(512),
  recordCounts: z.object({ affiliations: z.number().int().nonnegative(),
    authorships: z.number().int().nonnegative(), externalResources: z.number().int().nonnegative() }),
});
const idMap = z.record(z.string(), z.array(z.number().int().nonnegative()));
const indexSchema = z.object({
  version: z.literal(version), datasetVersion: z.string().min(1),
  paperIds: z.array(z.string()), shardIds: z.array(z.string()),
  paperAuthorshipShards: idMap, researcherPaperIds: idMap,
  researcherAffiliationShards: idMap, institutionAffiliationShards: idMap,
  entityResourceShards: idMap,
  paperAuthorCounts: z.record(z.string(), z.number().int().nonnegative()),
});
type ShardReference = z.infer<typeof shardSchema>;
type IndexMapKey = 'paperAuthorshipShards' | 'researcherPaperIds' | 'researcherAffiliationShards' | 'institutionAffiliationShards' | 'entityResourceShards';
type ShardIndex = Omit<z.infer<typeof indexSchema>, IndexMapKey> & Record<IndexMapKey, Record<string, string[]>>;
type Relation = Affiliation | Authorship | ExternalResource;

function awaitScope<T>(promise: Promise<T>, signal?: AbortSignal): Promise<T> {
  if (!signal) return promise;
  signal.throwIfAborted();
  return new Promise<T>((resolve, reject) => {
    const abort = () => { signal.removeEventListener('abort', abort); reject(signal.reason); };
    signal.addEventListener('abort', abort, { once: true });
    promise.then((value) => { signal.removeEventListener('abort', abort); resolve(value); },
      (error: unknown) => { signal.removeEventListener('abort', abort); reject(error); });
  });
}

async function readBytes(stream: ReadableStream<Uint8Array>, maximum: number): Promise<Uint8Array> {
  const reader = stream.getReader();
  const parts: Uint8Array[] = [];
  let count = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      count += value.byteLength;
      if (count > maximum) { await reader.cancel(); throw new Error('Atlas shard exceeds its verified size limit.'); }
      parts.push(value);
    }
  } finally { reader.releaseLock(); }
  const result = new Uint8Array(count);
  let offset = 0;
  for (const part of parts) { result.set(part, offset); offset += part.byteLength; }
  return result;
}

async function checkHash(bytes: Uint8Array, expected: string, length: number): Promise<void> {
  const digest = await crypto.subtle.digest('SHA-256', new Uint8Array(bytes));
  const actual = [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, '0')).join('');
  if (bytes.byteLength !== length || actual !== expected) throw new Error('Atlas shard checksum or length mismatch.');
}

async function recover(reference: z.infer<typeof referenceSchema>, manifestUrl: URL, fetcher: typeof fetch): Promise<unknown> {
  const url = new URL(reference.path, manifestUrl);
  if (url.origin !== manifestUrl.origin || url.pathname.slice(0, url.pathname.lastIndexOf('/') + 1) !==
    manifestUrl.pathname.slice(0, manifestUrl.pathname.lastIndexOf('/') + 1)) {
    throw new Error('Atlas shard must belong to this exact immutable release.');
  }
  const response = await fetcher(url, { credentials: 'omit', redirect: 'error', cache: 'no-store', signal: AbortSignal.timeout(60_000) });
  if (!response.ok || !response.body || Number(response.headers.get('content-length')) > reference.bytes) {
    throw new Error('Atlas profile evidence is unavailable.');
  }
  const compressed = await readBytes(response.body, reference.bytes);
  await checkHash(compressed, reference.sha256, reference.bytes);
  if (typeof DecompressionStream === 'undefined') throw new Error('This browser cannot decode the verified Atlas dataset. Please use a current browser.');
  const decoded = await readBytes(new Blob([new Uint8Array(compressed)]).stream()
    .pipeThrough(new DecompressionStream('gzip')), reference.decodedBytes);
  await checkHash(decoded, reference.decodedSha256, reference.decodedBytes);
  return JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(decoded));
}

/** Canonical catalog/metrics are eager; scientific relationship rows are stored once and scoped. */
export class ShardedAtlasRepository extends StaticAtlasRepository implements ScopedAtlasRepository {
  readonly paperAuthorCounts: Readonly<Record<string, number>>;
  private readonly descriptors: Map<string, ShardReference>;
  private readonly cache = new Map<string, { records: Relation[]; bytes: number }>();
  private readonly inflight = new Map<string, Promise<Relation[]>>();
  private cacheBytes = 0;
  private activeFetches = 0;
  private readonly waiters: (() => void)[] = [];
  private readonly paperIds: Set<string>;
  private readonly researcherIds: Set<string>;
  private readonly institutionIds: Set<string>;
  private readonly entitySearch: EntitySearchIndex;

  private constructor(private readonly core: AtlasDataset, private readonly index: ShardIndex,
    manifest: z.infer<typeof uiShardsSchema>, private readonly manifestUrl: URL, private readonly fetcher: typeof fetch) {
    super(core);
    this.paperAuthorCounts = Object.freeze({ ...index.paperAuthorCounts });
    this.descriptors = new Map(manifest.shards.map((item) => [item.id, item]));
    this.paperIds = new Set(core.papers.map((item) => item.id));
    this.researcherIds = new Set(core.researchers.map((item) => item.id));
    this.institutionIds = new Set(core.institutions.map((item) => item.id));
    this.entitySearch = new EntitySearchIndex(core, { includePapers: true });
  }

  static async create(core: AtlasDataset, source: z.infer<typeof uiShardsSchema>, manifestUrl: URL,
    fetcher: typeof fetch = fetch): Promise<ShardedAtlasRepository> {
    const manifest = uiShardsSchema.parse(source);
    if (core.affiliations.length || core.authorships.length || (core.externalResources?.length ?? 0)) {
      throw new Error('A sharded release cannot mix inline and deferred relationship records.');
    }
    const descriptors = new Map(manifest.shards.map((item) => [item.id, item]));
    const paths = new Set([manifest.index.path, ...manifest.shards.map((item) => item.path)]);
    if (descriptors.size !== manifest.shards.length || paths.size !== manifest.shards.length + 1) {
      throw new Error('Atlas shard inventory contains duplicate identifiers or paths.');
    }
    for (const kind of kindSchema.options) {
      if (manifest.shards.filter((item) => item.kind === kind).reduce((count, item) => count + item.recordCount, 0) !== manifest.recordCounts[kind]) {
        throw new Error('Atlas shard inventory does not conserve its record counts.');
      }
    }
    const storedIndex = indexSchema.parse(await recover(manifest.index, manifestUrl, fetcher));
    if (storedIndex.datasetVersion !== core.metadata.provenance.version) throw new Error('Atlas shard index has different release lineage.');
    const paperIds = new Set(core.papers.map((item) => item.id));
    const researcherIds = new Set(core.researchers.map((item) => item.id));
    const institutionIds = new Set(core.institutions.map((item) => item.id));
    for (const [dictionary, inventory] of [[storedIndex.paperIds, paperIds], [storedIndex.shardIds, new Set(descriptors.keys())]] as const) {
      if (dictionary.length !== inventory.size || new Set(dictionary).size !== dictionary.length ||
        dictionary.some((id) => !inventory.has(id)) || JSON.stringify(dictionary) !== JSON.stringify([...dictionary].sort())) {
        throw new Error('Atlas compact index dictionary does not match its exact release inventory.');
      }
    }
    const expand = (key: IndexMapKey, dictionary: string[]): Record<string, string[]> => Object.fromEntries(
      Object.entries(storedIndex[key]).map(([id, offsets]) => {
        if (new Set(offsets).size !== offsets.length || offsets.some((offset) => offset >= dictionary.length)) {
          throw new Error('Atlas compact index has an invalid or duplicated offset.');
        }
        return [id, offsets.map((offset) => dictionary[offset])];
      }),
    );
    const index: ShardIndex = { ...storedIndex,
      paperAuthorshipShards: expand('paperAuthorshipShards', storedIndex.shardIds),
      researcherPaperIds: expand('researcherPaperIds', storedIndex.paperIds),
      researcherAffiliationShards: expand('researcherAffiliationShards', storedIndex.shardIds),
      institutionAffiliationShards: expand('institutionAffiliationShards', storedIndex.shardIds),
      entityResourceShards: expand('entityResourceShards', storedIndex.shardIds),
    };
    const resourceIds = new Set([
      ...core.institutions.map((item) => `institution:${item.id}`),
      ...core.researchers.map((item) => `researcher:${item.id}`),
      ...core.researchGroups.map((item) => `research-group:${item.id}`),
      ...core.papers.map((item) => `paper:${item.id}`),
    ]);
    const referenced = new Set<string>();
    for (const [mapping, allowed, kind] of [
      [index.paperAuthorshipShards, paperIds, 'authorships'],
      [index.researcherAffiliationShards, researcherIds, 'affiliations'],
      [index.institutionAffiliationShards, institutionIds, 'affiliations'],
      [index.entityResourceShards, resourceIds, 'externalResources'],
    ] as const) {
      for (const [id, shardIds] of Object.entries(mapping)) {
        if (!allowed.has(id) || new Set(shardIds).size !== shardIds.length || shardIds.some((shardId) => descriptors.get(shardId)?.kind !== kind)) {
          throw new Error('Atlas shard index has an invalid entity or shard reference.');
        }
        shardIds.forEach((shardId) => referenced.add(shardId));
      }
    }
    if (referenced.size !== descriptors.size) throw new Error('Atlas shard index omits retained records.');
    for (const [id, papers] of Object.entries(index.researcherPaperIds)) {
      if (!researcherIds.has(id) || new Set(papers).size !== papers.length || papers.some((paper) => !paperIds.has(paper))) {
        throw new Error('Atlas researcher-paper index has invalid canonical identities.');
      }
    }
    if (Object.keys(index.paperAuthorCounts).length !== paperIds.size ||
      Object.keys(index.paperAuthorCounts).some((id) => !paperIds.has(id)) ||
      Object.entries(index.paperAuthorCounts).some(([id, count]) => count > 0 && !(index.paperAuthorshipShards[id]?.length)) ||
      Object.values(index.paperAuthorCounts).reduce((sum, count) => sum + count, 0) !== manifest.recordCounts.authorships) {
      throw new Error('Atlas paper author counts do not match its complete canonical catalog.');
    }
    return new ShardedAtlasRepository(core, index, manifest, manifestUrl, fetcher);
  }

  private async acquire(signal?: AbortSignal): Promise<void> {
    signal?.throwIfAborted();
    if (this.activeFetches < 4) { this.activeFetches += 1; return; }
    await new Promise<void>((resolve, reject) => {
      const start = () => { signal?.removeEventListener('abort', cancel); this.activeFetches += 1; resolve(); };
      const cancel = () => { const index = this.waiters.indexOf(start); if (index >= 0) this.waiters.splice(index, 1); reject(signal?.reason); };
      signal?.addEventListener('abort', cancel, { once: true });
      this.waiters.push(start);
    });
  }

  private release(): void { this.activeFetches -= 1; this.waiters.shift()?.(); }

  private async shard(id: string, signal?: AbortSignal): Promise<Relation[]> {
    signal?.throwIfAborted();
    const cached = this.cache.get(id);
    if (cached) { this.cache.delete(id); this.cache.set(id, cached); return cached.records; }
    const pending = this.inflight.get(id);
    if (pending) return awaitScope(pending, signal);
    const descriptor = this.descriptors.get(id);
    if (!descriptor) throw new Error('Atlas relationship index references a missing shard.');
    await this.acquire(signal);
    const acquiredCache = this.cache.get(id);
    if (acquiredCache) { this.release(); return acquiredCache.records; }
    const acquiredPending = this.inflight.get(id);
    if (acquiredPending) { this.release(); return awaitScope(acquiredPending, signal); }
    const request = (async () => {
      try {
        const envelope = z.object({ version: z.literal(version), datasetVersion: z.literal(this.core.metadata.provenance.version),
          kind: z.literal(descriptor.kind), records: z.array(z.unknown()).length(descriptor.recordCount) })
          .parse(await recover(descriptor, this.manifestUrl, this.fetcher));
        const records: Relation[] = descriptor.kind === 'affiliations' ? z.array(affiliationSchema).parse(envelope.records)
          : descriptor.kind === 'authorships' ? z.array(authorshipSchema).parse(envelope.records)
          : z.array(externalResourceSchema).parse(envelope.records);
        const ids = new Set<string>();
        for (const record of records) {
          if (ids.has(record.id) || record.provenance.status === 'synthetic' || record.provenance.sourceType === 'synthetic-demo') throw new Error('Atlas shard has duplicate or inconsistent scientific lineage.');
          ids.add(record.id);
          if (descriptor.kind === 'authorships') {
            const row = record as Authorship;
            if (!this.paperIds.has(row.paperId) || !this.researcherIds.has(row.researcherId) ||
              !this.index.paperAuthorshipShards[row.paperId]?.includes(id) ||
              !this.index.researcherPaperIds[row.researcherId]?.includes(row.paperId)) {
              throw new Error('Atlas authorship does not match its canonical relationship index.');
            }
          } else if (descriptor.kind === 'affiliations') {
            const row = record as Affiliation;
            if (!this.institutionIds.has(row.institutionId) || !this.researcherIds.has(row.researcherId) ||
              (row.paperId !== undefined && !this.paperIds.has(row.paperId)) ||
              (row.paperId !== undefined && !this.index.researcherPaperIds[row.researcherId]?.includes(row.paperId)) ||
              !this.index.institutionAffiliationShards[row.institutionId]?.includes(id) ||
              !this.index.researcherAffiliationShards[row.researcherId]?.includes(id)) {
              throw new Error('Atlas affiliation does not match its canonical relationship index.');
            }
          } else {
            const row = record as ExternalResource;
            if (!this.index.entityResourceShards[`${row.entityType}:${row.entityId}`]?.includes(id)) {
              throw new Error('Atlas resource does not match its canonical relationship index.');
            }
          }
        }
        while (this.cacheBytes + descriptor.decodedBytes > maximumCacheBytes && this.cache.size) {
          const oldest = this.cache.keys().next().value as string;
          this.cacheBytes -= this.cache.get(oldest)!.bytes; this.cache.delete(oldest);
        }
        this.cache.set(id, { records, bytes: descriptor.decodedBytes }); this.cacheBytes += descriptor.decodedBytes;
        return records;
      } finally { this.release(); }
    })();
    this.inflight.set(id, request);
    void request.then(() => this.inflight.delete(id), () => this.inflight.delete(id));
    return awaitScope(request, signal);
  }

  private async rows<T extends Relation>(ids: string[], kind: ShardReference['kind'], include: (row: T) => boolean, signal?: AbortSignal): Promise<T[]> {
    signal?.throwIfAborted();
    const records = new Map<string, T>();
    // Four bounded workers; retain only selected rows, not all fetched shard arrays.
    const unique = [...new Set(ids)];
    let next = 0;
    await Promise.all(Array.from({ length: Math.min(4, unique.length) }, async () => {
      while (next < unique.length) {
        signal?.throwIfAborted();
        const id = unique[next++];
        if (this.descriptors.get(id)?.kind !== kind) throw new Error('Atlas relationship index kind mismatch.');
        const rows = await this.shard(id, signal) as T[];
        signal?.throwIfAborted();
        for (const row of rows) {
          if (!include(row)) continue;
          if (records.has(row.id)) throw new Error('Atlas relationship is duplicated across immutable shards.');
          records.set(row.id, row);
        }
      }
    }));
    return [...records.values()].sort((left, right) => left.id.localeCompare(right.id));
  }

  async loadEntityContext(scope: AtlasEntityScope, signal?: AbortSignal): Promise<AtlasEntityContext> {
    signal?.throwIfAborted();
    const known = scope.entityType === 'paper' ? this.paperIds.has(scope.id)
      : scope.entityType === 'researcher' ? this.researcherIds.has(scope.id)
        : scope.entityType === 'institution' ? this.institutionIds.has(scope.id)
          : scope.entityType === 'research-group' ? this.core.researchGroups.some((row) => row.id === scope.id)
            : this.core.fields.some((row) => row.id === scope.id);
    if (!known) throw new Error('The requested canonical entity is not in this Atlas release.');
    let researcherIds = new Set<string>();
    let institutionId: string | undefined;
    let paperId: string | undefined;
    if (scope.entityType === 'researcher') researcherIds.add(scope.id);
    else if (scope.entityType === 'institution') institutionId = scope.id;
    else if (scope.entityType === 'research-group') institutionId = this.core.researchGroups.find((item) => item.id === scope.id)?.institutionId;
    else if (scope.entityType === 'paper') paperId = scope.id;
    else {
      const selectedFields = fieldsWithinSelection(this.core.fields, scope.id);
      researcherIds = new Set(this.core.researchers.filter((item) => item.fieldIds.some((id) => selectedFields.has(id)))
        .slice(0, 8).map((item) => item.id));
    }
    if (paperId) researcherIds = new Set(Object.entries(this.index.researcherPaperIds).filter(([, papers]) => papers.includes(paperId!)).map(([id]) => id));
    const affiliationShardIds = institutionId ? this.index.institutionAffiliationShards[institutionId] ?? []
      : [...researcherIds].flatMap((id) => this.index.researcherAffiliationShards[id] ?? []);
    const affiliations = await this.rows<Affiliation>(affiliationShardIds, 'affiliations', (row) =>
      (institutionId ? row.institutionId === institutionId : researcherIds.has(row.researcherId)) &&
      (!paperId || row.paperId === paperId) &&
      (scope.entityType !== 'research-group' || row.researchGroupId === scope.id), signal);
    const paperIds = paperId ? new Set([paperId]) : institutionId
      ? new Set(affiliations.flatMap((row) => row.paperId ? [row.paperId] : this.index.researcherPaperIds[row.researcherId] ?? []))
      : scope.entityType === 'research-field' ? new Set<string>()
        : new Set([...researcherIds].flatMap((id) => this.index.researcherPaperIds[id] ?? []));
    const authorships = await this.rows<Authorship>([...paperIds].flatMap((id) => this.index.paperAuthorshipShards[id] ?? []),
      'authorships', (row) => paperIds.has(row.paperId), signal);
    for (const id of paperIds) {
      if (authorships.filter((row) => row.paperId === id).length !== this.paperAuthorCounts[id]) {
        throw new Error('Atlas paper relationships are incomplete; unloaded authors must not become zero.');
      }
    }
    const resourceKey = `${scope.entityType}:${scope.id}`;
    const externalResources = await this.rows<ExternalResource>(this.index.entityResourceShards[resourceKey] ?? [],
      'externalResources', (row) => `${row.entityType}:${row.entityId}` === resourceKey, signal);
    return { affiliations, authorships, externalResources };
  }

  override async getInstitutionProfile(id: string) {
    if (!this.core.institutions.some((item) => item.id === id)) return null;
    const context = await this.loadEntityContext({ entityType: 'institution', id });
    return new ProfileService({ ...this.core, ...context }).getInstitutionProfile(id);
  }
  override async getResearcherProfile(id: string) {
    if (!this.core.researchers.some((item) => item.id === id)) return null;
    const context = await this.loadEntityContext({ entityType: 'researcher', id });
    return new ProfileService({ ...this.core, ...context }).getResearcherProfile(id);
  }
  override async getResearchGroupProfile(id: string) {
    if (!this.core.researchGroups.some((item) => item.id === id)) return null;
    const context = await this.loadEntityContext({ entityType: 'research-group', id });
    return new ProfileService({ ...this.core, ...context }).getResearchGroupProfile(id);
  }
  override async getAffiliations(institutionId?: string) {
    if (!institutionId) throw new Error('Atlas relationships require an explicit entity scope.');
    return (await this.loadEntityContext({ entityType: 'institution', id: institutionId })).affiliations;
  }
  override async getAuthorships(researcherId?: string) {
    if (!researcherId) throw new Error('Atlas authorships require an explicit entity scope.');
    return (await this.loadEntityContext({ entityType: 'researcher', id: researcherId })).authorships.filter((row) => row.researcherId === researcherId);
  }
  override async getExternalResources(entityType?: ExternalResource['entityType'], entityId?: string) {
    if (!entityType || !entityId) throw new Error('Atlas resources require an explicit entity scope.');
    return (await this.loadEntityContext({ entityType, id: entityId })).externalResources ?? [];
  }
  override async getResearchers(institutionId?: string) {
    if (!institutionId) return this.core.researchers;
    const ids = new Set((await this.getAffiliations(institutionId)).map((row) => row.researcherId));
    return this.core.researchers.filter((row) => ids.has(row.id));
  }
  override async getPapers(researcherId?: string) {
    if (!researcherId) return this.core.papers;
    const ids = new Set(this.index.researcherPaperIds[researcherId] ?? []);
    return this.core.papers.filter((row) => ids.has(row.id));
  }
  override async searchEntities(query: string, limit = 8) { return this.entitySearch.search(query, limit); }
  override async getKnowledgeGraph(): Promise<never> {
    throw new Error('The immutable Atlas uses scoped profiles, not an eagerly reconstructed corpus graph.');
  }
}
