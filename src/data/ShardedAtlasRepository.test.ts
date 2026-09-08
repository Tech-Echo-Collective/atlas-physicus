import { createHash } from 'node:crypto';
import { gzipSync, gunzipSync } from 'node:zlib';
import { describe, expect, it, vi } from 'vitest';
import demoData from './demo/atlas.json';
import { atlasDatasetSchema } from '../domain/schemas';
import type { AtlasDataset, Authorship } from '../domain/models';
import { ProfileService } from '../profiles/ProfileService';
import { ShardedAtlasRepository, uiShardsSchema } from './ShardedAtlasRepository';
import { replaceEntityContext } from './ScopedAtlasRepository';
import { hydrateLiveNavigationDataset } from './LiveNavigationHydration';
import { buildAtlasUrl, resolveAtlasLocation } from '../navigation/AtlasNavigation';

const releaseVersion = 'ui-transport-test-v1';
const manifestUrl = new URL('https://atlas.example.test/data/ui-test/manifest.json');
const hash = (bytes: Uint8Array) => createHash('sha256').update(bytes).digest('hex');

/** Transport fixtures exercise no scientific gate and can never certify a release. */
function fixture(largeResourceShards = false, nativeResearcherIds = false) {
  const full = structuredClone(atlasDatasetSchema.parse(demoData));
  if (nativeResearcherIds) {
    const ids = new Map(full.researchers.map((row, index) => [row.id, `inspire-author:${123 + index}`]));
    full.researchers.forEach((row) => { row.id = ids.get(row.id)!; });
    full.affiliations.forEach((row) => { row.researcherId = ids.get(row.researcherId)!; });
    full.authorships.forEach((row) => { row.researcherId = ids.get(row.researcherId)!; });
    full.externalResources?.forEach((row) => { if (row.entityType === 'researcher') row.entityId = ids.get(row.entityId)!; });
    full.metricObservations.forEach((row) => { if (row.entityType === 'researcher') row.entityId = ids.get(row.entityId)!; });
    full.historicalEvents.forEach((row) => { row.relatedResearcherIds = row.relatedResearcherIds.map((id) => ids.get(id)!); });
  }
  full.metadata.datasetKind = 'live-api';
  full.metadata.deliveryMode = 'versioned-dataset';
  full.metadata.provenance.version = releaseVersion;
  for (const values of Object.values(full)) if (Array.isArray(values)) for (const row of values) {
    row.provenance = { source: 'transport test only', sourceType: 'derived', status: 'verified', version: 'original-source-version',
      sourceRecordId: 'original-provider-record-123', sourceSnapshotId: 'original-source-snapshot-456' };
  }
  if (largeResourceShards) {
    const sample = full.externalResources![0];
    full.externalResources = Array.from({ length: 7 }, (_, index) => ({ ...sample,
      id: `resource-cache-test-${index}`, entityType: 'researcher' as const,
      entityId: full.affiliations[0].researcherId, label: 'transport-cache-bound-test'.repeat(130_000),
    }));
  }
  const bodies = new Map<string, Uint8Array>();
  const encode = (path: string, value: unknown) => {
    const decoded = Buffer.from(JSON.stringify(value));
    const compressed = gzipSync(decoded);
    bodies.set(path, compressed);
    return { path, encoding: 'gzip' as const, sha256: hash(compressed), bytes: compressed.byteLength,
      decodedSha256: hash(decoded), decodedBytes: decoded.byteLength };
  };
  const index = {
    version: 'atlas-ui-shards-v1' as const, datasetVersion: releaseVersion,
    paperAuthorshipShards: {} as Record<string, string[]>, researcherPaperIds: {} as Record<string, string[]>,
    researcherAffiliationShards: {} as Record<string, string[]>, institutionAffiliationShards: {} as Record<string, string[]>,
    entityResourceShards: {} as Record<string, string[]>, paperAuthorCounts: Object.fromEntries(full.papers.map((row) => [row.id, 0])),
  };
  const add = (mapping: Record<string, string[]>, key: string, value: string) => {
    mapping[key] = [...new Set([...(mapping[key] ?? []), value])];
  };
  for (const row of full.authorships) {
    add(index.paperAuthorshipShards, row.paperId, 'authorships');
    add(index.researcherPaperIds, row.researcherId, row.paperId);
    index.paperAuthorCounts[row.paperId] += 1;
  }
  for (const row of full.affiliations) {
    add(index.researcherAffiliationShards, row.researcherId, 'affiliations');
    add(index.institutionAffiliationShards, row.institutionId, 'affiliations');
  }
  (full.externalResources ?? []).forEach((row, position) => add(index.entityResourceShards, `${row.entityType}:${row.entityId}`,
    largeResourceShards ? `externalResources-${position}` : 'externalResources'));
  const kinds = ['affiliations', 'authorships', 'externalResources'] as const;
  const shards = kinds.filter((kind) => (full[kind]?.length ?? 0) > 0 && !(largeResourceShards && kind === 'externalResources')).map((kind) => ({
    ...encode(`ui-${kind.toLowerCase()}-0000.json.gz`, { version: index.version, datasetVersion: releaseVersion, kind, records: full[kind] }),
    id: kind as string, kind, recordCount: full[kind]?.length ?? 0,
  }));
  if (largeResourceShards) (full.externalResources ?? []).forEach((row, position) => shards.push({
    ...encode(`ui-externalresources-${position}.json.gz`, { version: index.version, datasetVersion: releaseVersion, kind: 'externalResources', records: [row] }),
    id: `externalResources-${position}`, kind: 'externalResources', recordCount: 1,
  }));
  const storedIndex = () => {
    const paperIds = full.papers.map((row) => row.id).sort();
    const shardIds = shards.map((row) => row.id).sort();
    return { ...index, paperIds, shardIds, ...Object.fromEntries(
      (['paperAuthorshipShards', 'researcherPaperIds', 'researcherAffiliationShards', 'institutionAffiliationShards', 'entityResourceShards'] as const)
        .map((key) => [key, Object.fromEntries(Object.entries(index[key]).map(([id, values]) =>
          [id, values.map((value) => (key === 'researcherPaperIds' ? paperIds : shardIds).indexOf(value))]))]),
    ) };
  };
  const manifest = uiShardsSchema.parse({ version: index.version,
    index: encode('ui-index.json.gz', storedIndex()), shards,
    recordCounts: Object.fromEntries(kinds.map((kind) => [kind, full[kind]?.length ?? 0])),
  });
  const core: AtlasDataset = { ...full, affiliations: [], authorships: [], externalResources: [] };
  const fetcher = vi.fn(async (input: URL | RequestInfo, _options?: RequestInit) => {
    void _options;
    const path = new URL(String(input)).pathname.split('/').at(-1)!;
    const bytes = bodies.get(path);
    return bytes ? new Response(new Uint8Array(bytes)) : new Response(null, { status: 404 });
  });
  const updateIndex = () => { manifest.index = encode('ui-index.json.gz', storedIndex()); };
  const updateRecords = (kind: typeof kinds[number], records: unknown[]) => {
    const descriptor = manifest.shards.find((row) => row.kind === kind)!;
    Object.assign(descriptor, encode(descriptor.path, { version: index.version, datasetVersion: releaseVersion, kind, records }), { recordCount: records.length });
    manifest.recordCounts[kind] = records.length;
  };
  const create = () => ShardedAtlasRepository.create(core, manifest, manifestUrl, fetcher);
  return { full, core, manifest, index, bodies, encode, updateIndex, updateRecords, fetcher, create };
}

describe('immutable UI shard transport', () => {
  it('bootstraps only catalog, metrics and compact index; no relationship or API requests', async () => {
    const f = fixture(); const repository = await f.create();
    expect(await repository.loadDataset()).toEqual(f.core);
    expect(f.fetcher).toHaveBeenCalledTimes(1);
    expect(String(f.fetcher.mock.calls[0][0])).toBe(new URL('ui-index.json.gz', manifestUrl).href);
    expect((await repository.loadDataset()).authorships).toEqual([]);
    expect(repository.paperAuthorCounts).toEqual(f.index.paperAuthorCounts);
    expect((await repository.searchEntities(f.full.papers[0].title))[0].entityType).toBe('paper');
  });

  it('verifies decoded hashes when the static host applies gzip Content-Encoding', async () => {
    const f = fixture();
    f.fetcher.mockImplementation(async (input) => {
      const bytes = f.bodies.get(new URL(String(input)).pathname.split('/').at(-1)!)!;
      return new Response(new Uint8Array(gunzipSync(bytes)), {
        headers: { 'Content-Encoding': 'gzip', 'Content-Length': String(bytes.byteLength) },
      });
    });
    const repository = await f.create();
    expect(repository.paperAuthorCounts).toEqual(f.index.paperAuthorCounts);
    const context = await repository.loadEntityContext({ entityType: 'researcher', id: f.full.authorships[0].researcherId });
    expect(context.authorships.length).toBeGreaterThan(0);
  });

  it('recovers exact researcher profile, provenance and all paper coauthors without API mixing', async () => {
    const f = fixture(); const repository = await f.create();
    const id = f.full.authorships[0].researcherId;
    const expected = new ProfileService(f.full).getResearcherProfile(id)!;
    const actual = await repository.getResearcherProfile(id);
    // Stable source order is not scientific meaning; compare identities/records exactly.
    expect(actual?.researcher).toEqual(expected.researcher);
    expect(actual?.collaborators.map((row) => row.id).sort()).toEqual(expected.collaborators.map((row) => row.id).sort());
    expect(actual?.papers.map((row) => row.id).sort()).toEqual(expected.papers.map((row) => row.id).sort());
    const context = await repository.loadEntityContext({ entityType: 'researcher', id });
    const papers = new Set(f.index.researcherPaperIds[id]);
    expect(context.authorships).toEqual(f.full.authorships.filter((row) => papers.has(row.paperId)).sort((a, b) => a.id.localeCompare(b.id)));
    expect(context.affiliations).toEqual(f.full.affiliations.filter((row) => row.researcherId === id).sort((a, b) => a.id.localeCompare(b.id)));
    expect(context.authorships[0].provenance).toMatchObject({ version: 'original-source-version',
      sourceRecordId: 'original-provider-record-123', sourceSnapshotId: 'original-source-snapshot-456' });
    expect(f.fetcher.mock.calls.every(([url]) => String(url).startsWith('https://atlas.example.test/data/ui-test/'))).toBe(true);
    expect(f.fetcher.mock.calls.every(([, options]) => options?.credentials === 'omit')).toBe(true);
  });

  it('coalesces concurrent shared-shard requests and does not retain relations in its bootstrap snapshot', async () => {
    const f = fixture(); const repository = await f.create(); const id = f.full.authorships[0].researcherId;
    await Promise.all([repository.getResearcherProfile(id), repository.getResearcherProfile(id)]);
    const paths = f.fetcher.mock.calls.map(([url]) => String(url));
    expect(new Set(paths).size).toBe(paths.length);
    expect((await repository.loadDataset()).affiliations).toEqual([]);
    expect((await repository.loadDataset()).authorships).toEqual([]);
    await expect(repository.getAuthorships()).rejects.toThrow('explicit entity scope');
    await expect(repository.getKnowledgeGraph()).rejects.toThrow('scoped profiles');
  });

  it('cancels obsolete context work without cancelling a shared shard needed by the new view', async () => {
    const f = fixture(); const repository = await f.create();
    const original = f.fetcher.getMockImplementation()!;
    let release!: () => void;
    const barrier = new Promise<void>((resolve) => { release = resolve; });
    f.fetcher.mockImplementation(async (url, options) => {
      if (String(url).includes('ui-affiliations')) await barrier;
      return original(url, options);
    });
    const id = f.full.affiliations[0].researcherId;
    const controller = new AbortController();
    const old = repository.loadEntityContext({ entityType: 'researcher', id }, controller.signal);
    const rejected = expect(old).rejects.toMatchObject({ name: 'AbortError' });
    await vi.waitFor(() => expect(f.fetcher).toHaveBeenCalledTimes(2));
    const current = repository.loadEntityContext({ entityType: 'researcher', id });
    controller.abort();
    await rejected;
    // Old scope cannot advance to authorship/resources while its first shard is pending.
    expect(f.fetcher).toHaveBeenCalledTimes(2);
    release();
    expect((await current).affiliations.some((row) => row.researcherId === id)).toBe(true);
    expect(f.fetcher.mock.calls.filter(([url]) => String(url).includes('ui-affiliations'))).toHaveLength(1);
    const stopped = new AbortController(); stopped.abort();
    const count = f.fetcher.mock.calls.length;
    await expect(repository.loadEntityContext({ entityType: 'institution', id: f.full.institutions[0].id }, stopped.signal)).rejects.toMatchObject({ name: 'AbortError' });
    expect(f.fetcher).toHaveBeenCalledTimes(count);
  });

  it('bounds requests at four and evicts decoded-wire cache entries while preserving complete selected context', async () => {
    const f = fixture(true); const repository = await f.create();
    const original = f.fetcher.getMockImplementation()!;
    let active = 0, maximum = 0;
    f.fetcher.mockImplementation(async (url, options) => {
      active += 1; maximum = Math.max(active, maximum);
      await new Promise((resolve) => setTimeout(resolve, 5));
      try { return await original(url, options); } finally { active -= 1; }
    });
    const context = await repository.loadEntityContext({ entityType: 'researcher', id: f.full.affiliations[0].researcherId });
    expect(context.externalResources).toHaveLength(7);
    expect(maximum).toBe(4);
    // Inspect cache bookkeeping only; this is not a claim about total JS object memory.
    const state = repository as unknown as { cacheBytes: number; cache: Map<string, unknown> };
    expect(state.cacheBytes).toBeLessThanOrEqual(16 * 1024 * 1024);
    expect(state.cache.size).toBeLessThan(f.manifest.shards.length);
    expect((await repository.loadDataset()).externalResources).toEqual([]);
  });

  it('replaces selected context, retains core catalog and handles direct researcher routes', async () => {
    const f = fixture(); const repository = await f.create(); const id = f.full.authorships[0].researcherId;
    const hydrated = await hydrateLiveNavigationDataset(repository, f.core, `/atlas/researcher/${id}`);
    expect(hydrated.affiliations.some((row) => row.researcherId === id)).toBe(true);
    const context = await repository.loadEntityContext({ entityType: 'researcher', id });
    const entered = replaceEntityContext(f.core, context);
    const returned = replaceEntityContext(entered, { affiliations: [], authorships: [], externalResources: [] });
    expect(returned).toEqual(f.core);
    expect(returned.metricObservations).toBe(f.core.metricObservations);
  });

  it('preserves real source-native researcher IDs in core, shards, search and escaped branch deep routes', async () => {
    const f = fixture(false, true);
    const leaf = f.core.fields[0];
    const branch = { ...leaf, id: 'test-parent-branch', label: 'Test branch', nodeKind: 'branch' as const };
    leaf.parentFieldId = branch.id; f.core.fields.push(branch); f.core.scienceDomains[0].fieldIds.push(branch.id);
    const repository = await f.create();
    const id = 'inspire-author:123';
    const profile = await repository.getResearcherProfile(id);
    expect(profile?.researcher.id).toBe(id);
    const context = await repository.loadEntityContext({ entityType: 'researcher', id });
    expect(context.affiliations.some((row) => row.researcherId === id)).toBe(true);
    expect(context.authorships.some((row) => row.researcherId === id)).toBe(true);
    expect((await repository.searchEntities(id))[0].entityId).toBe(id);
    const path = '/atlas/researcher/inspire-author%3A123';
    const hydrated = await hydrateLiveNavigationDataset(repository, f.core, path);
    const state = resolveAtlasLocation({ pathname: path, search: `?domain=physics&field=${branch.id}&year=2026` }, hydrated);
    expect(state.selectedResearcherId).toBe(id);
    expect(state.selectedFieldId).toBe(branch.id);
    const url = buildAtlasUrl(state, hydrated);
    expect(url).toContain(path);
    const parsed = new URL(url, manifestUrl);
    expect(resolveAtlasLocation(parsed, hydrated)).toEqual(state);
  });

  it('loads field overview only displayed researcher affiliations, with exact known-link counts', async () => {
    const f = fixture(); const repository = await f.create(); const id = f.full.fields[0].id;
    const context = await repository.loadEntityContext({ entityType: 'research-field', id });
    const researchers = new Set(f.full.researchers.filter((row) => row.fieldIds.includes(id)).slice(0, 8).map((row) => row.id));
    expect(context.affiliations.every((row) => researchers.has(row.researcherId))).toBe(true);
    expect(context.authorships).toEqual([]);
    expect(repository.paperAuthorCounts).toEqual(f.index.paperAuthorCounts);
    expect(f.fetcher.mock.calls.some(([url]) => String(url).includes('ui-authorships'))).toBe(false);
  });

  it('hydrates the displayed leaf community when a parent ontology branch is selected', async () => {
    const f = fixture();
    const leaf = f.core.fields[0];
    const branch = { ...leaf, id: 'test-parent-branch', label: 'Test branch', nodeKind: 'branch' as const };
    leaf.parentFieldId = branch.id;
    f.core.fields.push(branch);
    const context = await (await f.create()).loadEntityContext({ entityType: 'research-field', id: branch.id });
    const ids = new Set(f.core.researchers.filter((row) => row.fieldIds.includes(leaf.id)).slice(0, 8).map((row) => row.id));
    expect(context.affiliations).toHaveLength(f.full.affiliations.filter((row) => ids.has(row.researcherId)).length);
    expect(context.affiliations.length).toBeGreaterThan(0);
  });

  it('rejects missing artifacts without falling back to another source', async () => {
    const f = fixture(); const repository = await f.create();
    f.bodies.delete(f.manifest.shards.find((row) => row.kind === 'affiliations')!.path);
    await expect(repository.getResearcherProfile(f.full.affiliations[0].researcherId)).rejects.toThrow('unavailable');
  });

  it.each(['checksum', 'truncated', 'decoded-checksum', 'decoded-size'])('fails closed on %s failure', async (failure) => {
    const f = fixture(); const ref = f.manifest.index;
    if (failure === 'checksum') ref.sha256 = '0'.repeat(64);
    if (failure === 'truncated') {
      const bytes = f.bodies.get(ref.path)!.slice(0, -5); f.bodies.set(ref.path, bytes);
      ref.bytes = bytes.length; ref.sha256 = hash(bytes);
    }
    if (failure === 'decoded-checksum') ref.decodedSha256 = '0'.repeat(64);
    if (failure === 'decoded-size') ref.decodedBytes = 10;
    await expect(f.create()).rejects.toThrow();
  });

  it.each(['foreign-lineage', 'unknown-shard', 'missing-count', 'wrong-kind', 'duplicate-id'])('rejects invalid %s index', async (failure) => {
    const f = fixture();
    if (failure === 'foreign-lineage') f.index.datasetVersion = 'another-release';
    if (failure === 'unknown-shard') f.index.paperAuthorshipShards[f.full.papers[0].id] = ['unknown'];
    if (failure === 'missing-count') delete f.index.paperAuthorCounts[f.full.papers[0].id];
    if (failure === 'wrong-kind') f.index.paperAuthorshipShards[f.full.papers[0].id] = ['affiliations'];
    if (failure === 'duplicate-id') f.manifest.shards.push(f.manifest.shards[0]);
    f.updateIndex();
    await expect(f.create()).rejects.toThrow();
  });

  it('rejects undeclared or synthetic relationships even with valid transport hashes', async () => {
    const f = fixture();
    const records = structuredClone(f.full.authorships);
    records[0].researcherId = 'researcher-not-in-the-core';
    f.updateRecords('authorships', records);
    const repository = await f.create();
    await expect(repository.loadEntityContext({ entityType: 'paper', id: records[0].paperId })).rejects.toThrow('canonical relationship index');
    const g = fixture();
    const synthetic = structuredClone(g.full.authorships); synthetic[0].provenance.status = 'synthetic';
    g.updateRecords('authorships', synthetic);
    await expect((await g.create()).loadEntityContext({ entityType: 'paper', id: synthetic[0].paperId })).rejects.toThrow('scientific lineage');
  });

  it('does not use another paper by the same researcher as institution affiliation evidence', async () => {
    const f = fixture(); const first = f.full.authorships[0];
    const otherPaper = { ...f.full.papers[0], id: 'paper-test-unrelated' };
    f.full.papers.push(otherPaper); f.index.paperAuthorCounts[otherPaper.id] = 0;
    const affiliation = f.full.affiliations.find((row) => row.researcherId === first.researcherId)!;
    if (!affiliation) throw new Error('Fixture must supply a resolved author');
    for (const row of f.full.affiliations) row.paperId = f.index.researcherPaperIds[row.researcherId]?.[0];
    const extra: Authorship = { ...first, id: 'authorship-test-unrelated', paperId: otherPaper.id };
    f.full.authorships.push(extra);
    f.index.researcherPaperIds[first.researcherId] = [...new Set([...(f.index.researcherPaperIds[first.researcherId] ?? []), otherPaper.id])];
    f.index.paperAuthorshipShards[otherPaper.id] = ['authorships']; f.index.paperAuthorCounts[otherPaper.id] += 1;
    f.updateRecords('affiliations', f.full.affiliations); f.updateRecords('authorships', f.full.authorships); f.updateIndex();
    const context = await (await f.create()).loadEntityContext({ entityType: 'institution', id: affiliation.institutionId });
    expect(context.authorships.some((row) => row.paperId === first.paperId)).toBe(true);
    expect(context.authorships.some((row) => row.paperId === otherPaper.id)).toBe(false);
  });

  it('rejects a paper-time affiliation without that exact researcher-paper link', async () => {
    const f = fixture(); const rows = structuredClone(f.full.affiliations);
    const linkedPapers = new Set(f.index.researcherPaperIds[rows[0].researcherId]);
    rows[0].paperId = f.full.papers.find((row) => !linkedPapers.has(row.id))!.id;
    f.updateRecords('affiliations', rows);
    await expect((await f.create()).getResearcherProfile(rows[0].researcherId)).rejects.toThrow('canonical relationship index');
  });
});
