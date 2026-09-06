import { z } from 'zod';
import { metricSystemV1Ids, type AtlasDataset } from '../domain/models';
import { atlasDatasetSchema } from '../domain/schemas';
import { hasCompleteVisualizationMetricSystem } from '../metrics/MetricRegistry';
import { StaticAtlasRepository } from './StaticAtlasRepository';

export const certifiedAtlasReleaseVersion = 'certified-atlas-dataset-v1';
const maximumDatasetBytes = 64 * 1024 * 1024;
const maximumManifestBytes = 8 * 1024 * 1024;
const sha256 = z.string().regex(/^[a-f0-9]{64}$/);
const datasetScopeSchema = z.object({
  version: z.literal('certified-ontology-branch-release-v1'),
  // This release version names the currently certified two-leaf branch.
  // A different acquisition scope requires a newly reviewed release contract.
  rootFieldId: z.literal('nuclear'),
  leafFieldIds: z.array(z.enum(['nucl-ex', 'nucl-th'])).length(2),
  boundaryKind: z.literal('ontology-branch'),
  certificationDigest: sha256,
  sourceYearProofs: z.array(z.object({
    entityType: z.enum(['country', 'institution', 'researcher']),
    year: z.number().int(),
    certificationId: z.string().regex(/^source-year-[a-f0-9]{64}$/),
  })).min(6),
});

const manifestSchema = z.object({
  schemaVersion: z.literal(certifiedAtlasReleaseVersion),
  datasetPath: z.literal('atlas-dataset.json'),
  datasetSha256: sha256,
  datasetBytes: z.number().int().positive().max(maximumDatasetBytes),
  dataSourceVersion: z.string().min(1),
  acquisitionScope: z.string().min(1),
  atlasScaleVersion: z.literal('normalized-atlas-scale-v1'),
  metricIds: z.array(z.string()),
  observationCounts: z.record(z.string(), z.number().int().positive()),
  periods: z.array(z.string().regex(/^\d{4}$/)).min(1),
  jointGateDecision: z.object({
    metric_system_version: z.literal('physics-atlas-metric-system-v1'),
    status: z.literal('eligible-for-reviewed-activation'),
    metric_ids: z.array(z.string()),
    reasons: z.array(z.string()).length(0),
  }),
  jointGateEvidence: z.object({
    metric_system_version: z.literal('physics-atlas-metric-system-v1'),
    acquisition_scope: z.string().min(1),
    data_source_version: z.string().min(1),
    algorithms: z.array(z.object({
      metric_id: z.string(),
      definition_version: z.string().min(1),
      algorithm_version: z.string().min(1),
      normalization_version: z.string().min(1),
      implemented: z.literal(true),
      deterministic_reproduction_passed: z.literal(true),
    })),
  }),
  scientificEvidence: z.object({
    storage_reference: z.string().min(1),
    sha256,
    byte_length: z.number().int().positive(),
    schema_version: z.string().min(1),
  }),
  // Retain explicit missing states in the published manifest. They are never
  // turned into zero-valued MetricObservation rows for the map or composite.
  missingObservations: z.array(z.object({
    id: z.string(),
    metricId: z.string(),
    value: z.null(),
    qualityFlags: z.array(z.string()).min(1),
  })),
  datasetScope: datasetScopeSchema.optional(),
});

function assertDatasetScope(dataset: AtlasDataset, scope: z.infer<typeof datasetScopeSchema>): void {
  const root = dataset.fields.find((item) => item.id === scope.rootFieldId);
  const domain = dataset.scienceDomains.find((item) => item.id === 'physics');
  const leaves = dataset.fields.filter((item) => item.parentFieldId === scope.rootFieldId && item.nodeKind === 'field');
  const declaredLeaves = new Set<string>(scope.leafFieldIds);
  if (!root || root.nodeKind !== 'branch' || root.ontologyVersion !== 'physics-field-ontology-v1' ||
    !domain?.fieldIds.includes(root.id) || declaredLeaves.size !== 2 ||
    leaves.length !== 2 || leaves.some((item) => !declaredLeaves.has(item.id) ||
      item.ontologyVersion !== root.ontologyVersion || !domain.fieldIds.includes(item.id))) {
    throw new Error('The certified branch catalog does not match the release scope.');
  }
  const yearsByType = new Map<string, Set<number>>();
  for (const proof of scope.sourceYearProofs) {
    const years = yearsByType.get(proof.entityType) ?? new Set<number>();
    if (years.has(proof.year)) throw new Error('The certified branch source-year proofs are duplicated.');
    years.add(proof.year);
    yearsByType.set(proof.entityType, years);
  }
  if ([...yearsByType.values()].some((years) => years.size !== 6 ||
    [2018, 2019, 2020, 2021, 2022, 2023].some((year) => !years.has(year)))) {
    throw new Error('The certified branch historical source-year inventory is incomplete.');
  }
  const allowedFields = new Set<string>([scope.rootFieldId, ...scope.leafFieldIds]);
  if (dataset.metricObservations.some((item) => !item.fieldId || !allowedFields.has(item.fieldId) ||
    !yearsByType.has(item.entityType))) {
    throw new Error('Scoped branch observations cannot be relabeled as overall Physics values.');
  }
  // Mirror the exporter: five positive global counts do not establish a
  // usable five-way composite for even one entity/year in the release branch.
  const compositeGroups = new Map<string, Set<string>>();
  for (const observation of dataset.metricObservations) {
    if (observation.fieldId !== scope.rootFieldId) continue;
    const key = JSON.stringify([observation.entityType, observation.entityId, observation.period]);
    const metrics = compositeGroups.get(key) ?? new Set<string>();
    metrics.add(observation.metricId);
    compositeGroups.set(key, metrics);
  }
  if (![...compositeGroups.values()].some((metrics) => exactMetricIds([...metrics]))) {
    throw new Error('The certified branch requires co-located observations for all five metrics.');
  }
}

function exactMetricIds(ids: readonly string[]): boolean {
  return ids.length === metricSystemV1Ids.length &&
    new Set(ids).size === ids.length &&
    metricSystemV1Ids.every((id) => ids.includes(id));
}

async function readBounded(response: Response, maximum: number): Promise<Uint8Array> {
  if (!response.ok || !response.body) {
    throw new Error('The certified Atlas release is unavailable.');
  }
  const declaredSize = Number(response.headers.get('Content-Length'));
  if (Number.isFinite(declaredSize) && declaredSize > maximum) {
    throw new Error('The certified Atlas response exceeds its size limit.');
  }
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      total += value.byteLength;
      if (total > maximum) {
        await reader.cancel();
        throw new Error('The certified Atlas response exceeds its size limit.');
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }
  const bytes = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return bytes;
}

function assertScientificDataset(
  dataset: AtlasDataset,
  manifest: z.infer<typeof manifestSchema>,
): void {
  if (
    dataset.metadata.datasetKind !== 'live-api' ||
    dataset.metadata.deliveryMode !== 'versioned-dataset' ||
    dataset.metadata.schemaVersion !== certifiedAtlasReleaseVersion ||
    dataset.metadata.provenance.version !== manifest.dataSourceVersion ||
    dataset.metadata.provenance.acquisitionScope !== manifest.acquisitionScope ||
    manifest.jointGateEvidence.data_source_version !== manifest.dataSourceVersion ||
    manifest.jointGateEvidence.acquisition_scope !== manifest.acquisitionScope ||
    !exactMetricIds(manifest.metricIds) ||
    !exactMetricIds(manifest.jointGateDecision.metric_ids) ||
    !exactMetricIds(manifest.jointGateEvidence.algorithms.map((item) => item.metric_id)) ||
    !exactMetricIds(Object.keys(manifest.observationCounts)) ||
    !hasCompleteVisualizationMetricSystem(dataset.metricDefinitions) ||
    (dataset.rawEntityRecords?.length ?? 0) > 0
  ) {
    throw new Error('The certified Atlas release lineage or five-metric proof is invalid.');
  }
  const recordGroups = Object.entries(dataset).filter(([key]) => key !== 'metadata');
  const allRecords = [dataset.metadata, ...recordGroups.flatMap(([, records]) => records)];
  if (allRecords.some((record) => record.provenance?.status === 'synthetic' ||
    record.provenance?.sourceType === 'synthetic-demo')) {
    throw new Error('Synthetic data cannot appear in a certified Atlas release.');
  }
  const scopes = new Set<string>();
  if (manifest.datasetScope) assertDatasetScope(dataset, manifest.datasetScope);
  else if (dataset.metadata.datasetScope || dataset.metadata.defaultFieldId) {
    throw new Error('The default field must be declared by the certified release scope.');
  }
  for (const observation of dataset.metricObservations) {
    const algorithm = manifest.jointGateEvidence.algorithms.find(
      (item) => item.metric_id === observation.metricId,
    );
    const definition = dataset.metricDefinitions.find((item) => item.id === observation.metricId);
    const key = [observation.entityType, observation.entityId, observation.fieldId ?? '',
      observation.scienceDomainId ?? '', observation.period, observation.metricId].join('|');
    if (
      scopes.has(key) || !algorithm || !definition ||
      definition.implementationStatus !== 'live-calculated' ||
      definition.version !== algorithm.definition_version ||
      observation.metricDefinitionVersion !== algorithm.definition_version ||
      observation.algorithmVersion !== algorithm.algorithm_version ||
      observation.normalizationMethod !== algorithm.normalization_version ||
      observation.dataSourceVersion !== manifest.dataSourceVersion ||
      observation.acquisitionScope !== manifest.acquisitionScope ||
      observation.provenance.status !== 'verified' ||
      observation.rawValue === undefined || observation.rawUnit === undefined ||
      observation.inputCount === undefined ||
      observation.normalizationParameters?.atlasScaleVersion !== manifest.atlasScaleVersion ||
      !sha256.safeParse(observation.normalizationParameters?.certificationManifestDigest).success ||
      !sha256.safeParse(observation.normalizationParameters?.inputManifestDigest).success
    ) {
      throw new Error('A certified Atlas observation has inconsistent scientific metadata.');
    }
    scopes.add(key);
  }
  for (const metricId of metricSystemV1Ids) {
    if (dataset.metricObservations.filter((item) => item.metricId === metricId).length !==
      manifest.observationCounts[metricId]) {
      throw new Error('The five-metric observation counts do not match the release.');
    }
  }
  const periods = [...new Set(dataset.metricObservations.map((item) => item.period))].sort();
  if (JSON.stringify(periods) !== JSON.stringify(manifest.periods) ||
    dataset.metadata.period !== periods.at(-1)) {
    throw new Error('The certified historical timeline does not match the release.');
  }
}

/** Trusted deployment manifest + checksum; not a browser-side scientific review. */
export async function loadCertifiedAtlasRepository(
  manifestReference: string,
  fetcher: typeof fetch = fetch,
): Promise<StaticAtlasRepository> {
  const manifestUrl = new URL(manifestReference, window.location.href);
  if (manifestUrl.origin !== window.location.origin || manifestUrl.username ||
    manifestUrl.password || manifestUrl.hash || manifestUrl.search) {
    throw new Error('The certified Atlas manifest must use this deployment origin.');
  }
  const options: RequestInit = { credentials: 'omit', cache: 'no-store', redirect: 'error' };
  const manifestBytes = await readBounded(await fetcher(manifestUrl, options), maximumManifestBytes);
  const manifest = manifestSchema.parse(JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(manifestBytes)));
  const evidencePath = manifest.scientificEvidence.storage_reference;
  if (evidencePath.split('/').some((part) => !part || part === '.' || part === '..') ||
    /[\\:%?#]/.test(evidencePath)) {
    throw new Error('The scientific evidence reference is not release-relative.');
  }
  const datasetUrl = new URL(manifest.datasetPath, manifestUrl);
  const bytes = await readBounded(await fetcher(datasetUrl, options), manifest.datasetBytes);
  const digest = await crypto.subtle.digest('SHA-256', new Uint8Array(bytes));
  const actualHash = Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0')).join('');
  if (bytes.byteLength !== manifest.datasetBytes || actualHash !== manifest.datasetSha256) {
    throw new Error('The certified Atlas dataset checksum does not match its release.');
  }
  const dataset = atlasDatasetSchema.parse(JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes)));
  assertScientificDataset(dataset, manifest);
  dataset.metadata.releaseManifestUrl = manifestUrl.href;
  if (manifest.datasetScope) {
    const scope = manifest.datasetScope;
    dataset.metadata.datasetScope = {
      version: scope.version,
      rootFieldId: scope.rootFieldId,
      leafFieldIds: scope.leafFieldIds,
      boundaryKind: scope.boundaryKind,
      certificationDigest: scope.certificationDigest,
    };
    dataset.metadata.defaultFieldId = scope.rootFieldId;
  }
  return new StaticAtlasRepository(dataset);
}
