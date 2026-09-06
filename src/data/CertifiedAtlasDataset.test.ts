import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import demoData from './demo/atlas.json';
import { metricSystemV1Ids, type AtlasDataset } from '../domain/models';
import { atlasDatasetSchema } from '../domain/schemas';
import { buildCompositeMetricObservations, defaultMetricWeightConfiguration } from '../metrics/CompositeMetric';
import { resolveAtlasLocation } from '../navigation/AtlasNavigation';
import { getDatasetPresentation } from './DatasetPresentation';
import { certifiedAtlasReleaseVersion, loadCertifiedAtlasRepository } from './CertifiedAtlasDataset';

const origin = 'https://atlas.example.test';
const manifestUrl = `${origin}/data/test-only/manifest.json`;
const provenance = {
  source: 'transport test fixture, not scientific evidence',
  sourceType: 'derived' as const,
  version: 'transport-test-only-v1',
  acquisitionScope: 'transport-test-only-scope-v1',
  status: 'verified' as const,
};

/** This mocks an already published transport, never certification or a real release. */
function transportFixture(): AtlasDataset {
  const dataset = structuredClone(atlasDatasetSchema.parse(demoData));
  for (const records of Object.values(dataset)) {
    if (Array.isArray(records)) {
      for (const record of records) record.provenance = { ...provenance };
    }
  }
  dataset.rawEntityRecords = [];
  dataset.identityResolutions = [];
  dataset.metadata = {
    schemaVersion: certifiedAtlasReleaseVersion,
    datasetKind: 'live-api', deliveryMode: 'versioned-dataset',
    period: '2025', generatedAt: '2026-09-05T00:00:00Z',
    sourceSnapshotIds: [], updateSequence: 0,
    disclaimer: 'Explicit transport fixture; never deploy.', provenance,
  };
  dataset.metricDefinitions = metricSystemV1Ids.map((id) => ({
    id, name: id, category: id, description: 'Transport fixture',
    interpretation: 'No scientific result', unit: '0–100', version: 'test-definition-v1',
    requiredData: ['explicit transport fixture'], implementationStatus: 'live-calculated', provenance,
  }));
  dataset.metricObservations = ['2024', '2025'].flatMap((period) =>
    [dataset.countries[0], dataset.institutions[0]].flatMap((entity, index) =>
      metricSystemV1Ids.map((metricId) => ({
        id: `test-${entity.id}-${metricId.replaceAll('_', '-')}-${period}`,
        entityType: index === 0 ? 'country' as const : 'institution' as const,
        entityId: entity.id, scienceDomainId: 'physics', metricId, period, value: 50,
        source: 'transport-test-only', metricDefinitionVersion: 'test-definition-v1',
        algorithmVersion: 'test-algorithm-v1', calculationVersion: certifiedAtlasReleaseVersion,
        dataSourceVersion: provenance.version, acquisitionScope: provenance.acquisitionScope,
        rawValue: 10, rawUnit: 'test units', normalizationMethod: 'test-normalization-v1',
        normalizationParameters: { atlasScaleVersion: 'normalized-atlas-scale-v1',
          certificationManifestDigest: 'a'.repeat(64), inputManifestDigest: 'b'.repeat(64) },
        inputCount: 10, qualityFlags: [], calculatedAt: '2026-09-05T00:00:00Z', provenance,
      })),
    ),
  );
  return dataset;
}

function scopedTransportFixture() {
  const dataset = transportFixture();
  const ontologyVersion = 'physics-field-ontology-v1';
  dataset.fields.push(
    { id: 'nuclear', label: 'Nuclear Physics', description: 'Transport fixture branch',
      parentFieldId: 'physics', nodeKind: 'branch', ontologyVersion, provenance },
    ...['nucl-ex', 'nucl-th'].map((id) => ({ id, label: id, description: 'Transport fixture leaf',
      parentFieldId: 'nuclear', nodeKind: 'field' as const, ontologyVersion, provenance })),
  );
  dataset.scienceDomains.find((domain) => domain.id === 'physics')!.fieldIds.push('nuclear', 'nucl-ex', 'nucl-th');
  for (const entity of [...dataset.institutions, ...dataset.researchers]) entity.fieldIds.push('nuclear');
  dataset.metadata.period = '2023';
  dataset.metricObservations = dataset.metricObservations.map((observation) => ({
    ...observation, fieldId: 'nuclear', period: String(Number(observation.period) - 2),
  }));
  const scope = {
    version: 'certified-ontology-branch-release-v1' as const,
    rootFieldId: 'nuclear' as const,
    leafFieldIds: ['nucl-ex', 'nucl-th'],
    boundaryKind: 'ontology-branch' as const,
    certificationDigest: 'd'.repeat(64),
    sourceYearProofs: ['country', 'institution'].flatMap((entityType, index) =>
      [2018, 2019, 2020, 2021, 2022, 2023].map((year) => ({
        entityType, year, certificationId: `source-year-${`${index}${year}`.padStart(64, '0')}`,
      }))),
  };
  return { dataset, scope };
}

async function fixtureTransport(
  dataset = transportFixture(),
  corrupt = false,
  datasetScope?: ReturnType<typeof scopedTransportFixture>['scope'],
) {
  const text = JSON.stringify(dataset);
  const bytes = new TextEncoder().encode(text);
  const hash = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)),
    (byte) => byte.toString(16).padStart(2, '0')).join('');
  const manifest = {
    schemaVersion: certifiedAtlasReleaseVersion,
    datasetPath: 'atlas-dataset.json', datasetSha256: hash, datasetBytes: bytes.byteLength,
    dataSourceVersion: provenance.version, acquisitionScope: provenance.acquisitionScope,
    atlasScaleVersion: 'normalized-atlas-scale-v1', metricIds: [...metricSystemV1Ids],
    observationCounts: Object.fromEntries(metricSystemV1Ids.map((id) => [id, 4])),
    periods: [...new Set(dataset.metricObservations.map((observation) => observation.period))].sort(),
    jointGateDecision: { metric_system_version: 'physics-atlas-metric-system-v1',
      status: 'eligible-for-reviewed-activation', metric_ids: [...metricSystemV1Ids], reasons: [] },
    jointGateEvidence: { metric_system_version: 'physics-atlas-metric-system-v1',
      acquisition_scope: provenance.acquisitionScope, data_source_version: provenance.version,
      algorithms: metricSystemV1Ids.map((id) => ({ metric_id: id,
        definition_version: 'test-definition-v1', algorithm_version: 'test-algorithm-v1',
        normalization_version: 'test-normalization-v1', implemented: true,
        deterministic_reproduction_passed: true })) },
    scientificEvidence: { storage_reference: 'scientific-evidence.json', sha256: 'c'.repeat(64),
      byte_length: 10, schema_version: 'test-only-facts-v1' },
    missingObservations: [],
    ...(datasetScope ? { datasetScope } : {}),
  };
  const fetcher = vi.fn(async (input: RequestInfo | URL) => {
    if (String(input) === manifestUrl) return new Response(JSON.stringify(manifest));
    if (String(input) === new URL('atlas-dataset.json', manifestUrl).href) {
      return new Response(corrupt ? text.replace('transport-test-only-v1', 'transport-test-evil-v1') : text);
    }
    throw new Error('Unexpected network request');
  });
  return { fetcher, manifest };
}

beforeEach(() => vi.stubGlobal('window', { location: { href: `${origin}/atlas`, origin } }));
afterEach(() => vi.unstubAllGlobals());

describe('certified dataset transport', () => {
  it('preserves five layers, history, profiles, routes, search and user composite', async () => {
    const { fetcher } = await fixtureTransport();
    const repository = await loadCertifiedAtlasRepository(manifestUrl, fetcher);
    const dataset = await repository.loadDataset();
    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(dataset.metadata.releaseManifestUrl).toBe(manifestUrl);
    expect(await repository.getInstitutionProfile(dataset.institutions[0].id)).not.toBeNull();
    expect(await repository.getResearcherProfile(dataset.researchers[0].id)).not.toBeNull();
    expect(await repository.searchEntities(dataset.institutions[0].name)).not.toEqual([]);
    expect(resolveAtlasLocation({ pathname: `/atlas/country/${dataset.countries[0].id}`, search: '?year=2024&domain=physics' }, dataset)
      .selectedYear).toBe(2024);
    expect(await repository.getMetricsForPeriod('2024')).toHaveLength(10);
    expect(buildCompositeMetricObservations(dataset.metricObservations,
      defaultMetricWeightConfiguration, dataset.metricDefinitions)).toHaveLength(4);
    expect(getDatasetPresentation('live-api', 'versioned-dataset').badgeLabel).toBe('Certified Atlas dataset');
  });

  it('fails closed on corrupt, unavailable and cross-origin releases', async () => {
    const { fetcher } = await fixtureTransport(undefined, true);
    await expect(loadCertifiedAtlasRepository(manifestUrl, fetcher)).rejects.toThrow('checksum');
    await expect(loadCertifiedAtlasRepository('https://other.test/manifest.json', fetcher)).rejects.toThrow('origin');
    const unavailable = vi.fn(async () => new Response('Unavailable', { status: 503 }));
    await expect(loadCertifiedAtlasRepository(manifestUrl, unavailable)).rejects.toThrow('unavailable');
    expect(unavailable).toHaveBeenCalledTimes(1);
  });

  it('rejects partial activation and synthetic evidence even with correct transport hashes', async () => {
    const partial = transportFixture();
    partial.metricDefinitions[0].implementationStatus = 'experimental-candidate';
    await expect(loadCertifiedAtlasRepository(manifestUrl, (await fixtureTransport(partial)).fetcher))
      .rejects.toThrow('five-metric');
    const synthetic = transportFixture();
    synthetic.institutions[0].provenance.status = 'synthetic';
    await expect(loadCertifiedAtlasRepository(manifestUrl, (await fixtureTransport(synthetic)).fetcher))
      .rejects.toThrow('Synthetic');
  });

  it('rejects mixed lineage, count mismatch and missing-to-zero substitution', async () => {
    const mixed = transportFixture();
    mixed.metricObservations[0].dataSourceVersion = 'different-dataset';
    await expect(loadCertifiedAtlasRepository(manifestUrl, (await fixtureTransport(mixed)).fetcher))
      .rejects.toThrow('scientific metadata');
    const missing = transportFixture();
    missing.metricObservations.pop();
    await expect(loadCertifiedAtlasRepository(manifestUrl, (await fixtureTransport(missing)).fetcher))
      .rejects.toThrow('counts');
  });

  it('opens an explicitly labeled certified branch without fabricating overall Physics values', async () => {
    const { dataset: input, scope } = scopedTransportFixture();
    const { fetcher } = await fixtureTransport(input, false, scope);
    const repository = await loadCertifiedAtlasRepository(manifestUrl, fetcher);
    const dataset = await repository.loadDataset();
    expect(dataset.metadata.datasetScope?.rootFieldId).toBe('nuclear');
    expect(dataset.metadata.defaultFieldId).toBe('nuclear');
    const global = resolveAtlasLocation({ pathname: '/', search: '' }, dataset);
    expect(global.selectedDomainId).toBe('physics');
    expect(global.selectedFieldId).toBe('nuclear');
    expect(global.selectedYear).toBe(2023);
    expect(resolveAtlasLocation({ pathname: '/atlas', search: '?field=nucl-th&year=2022' }, dataset)
      .selectedFieldId).toBe('nucl-th');
    expect(resolveAtlasLocation({ pathname: '/atlas/physics', search: '' }, dataset)
      .selectedFieldId).toBeNull();
    expect(resolveAtlasLocation({ pathname: '/atlas', search: '?domain=physics' }, dataset)
      .selectedFieldId).toBeNull();
    expect(resolveAtlasLocation({ pathname: `/atlas/country/${dataset.countries[0].id}`, search: '?field=nuclear&year=2022' }, dataset)
      .selectedCountryId).toBe(dataset.countries[0].id);
    expect(resolveAtlasLocation({ pathname: `/atlas/institution/${dataset.institutions[0].id}`, search: '?field=nuclear&year=2022' }, dataset)
      .selectedFieldId).toBe('nuclear');
    expect(resolveAtlasLocation({ pathname: `/atlas/researcher/${dataset.researchers[0].id}`, search: '?field=nuclear&year=2022' }, dataset)
      .selectedFieldId).toBe('nuclear');
    expect(await repository.findMetricObservations({ entityType: 'country', scienceDomainId: 'physics', period: '2023' }))
      .toEqual([]);
    expect(await repository.findMetricObservations({ entityType: 'country', scienceDomainId: 'physics', fieldId: 'nuclear', period: '2023' }))
      .toHaveLength(5);
    expect(await repository.getMetricsForPeriod('2022')).toHaveLength(10);
    expect(buildCompositeMetricObservations(dataset.metricObservations,
      defaultMetricWeightConfiguration, dataset.metricDefinitions)).toHaveLength(4);
  });

  it('rejects incomplete branch catalogs and scope claims unsupported by the manifest', async () => {
    const wrongCatalog = scopedTransportFixture();
    wrongCatalog.scope.leafFieldIds = ['nucl-th', 'nucl-th'];
    await expect(loadCertifiedAtlasRepository(manifestUrl,
      (await fixtureTransport(wrongCatalog.dataset, false, wrongCatalog.scope)).fetcher))
      .rejects.toThrow('catalog');
    const relabeled = scopedTransportFixture();
    delete relabeled.dataset.metricObservations[0].fieldId;
    await expect(loadCertifiedAtlasRepository(manifestUrl,
      (await fixtureTransport(relabeled.dataset, false, relabeled.scope)).fetcher))
      .rejects.toThrow('overall Physics');
    const incomplete = scopedTransportFixture();
    incomplete.scope.sourceYearProofs.pop();
    await expect(loadCertifiedAtlasRepository(manifestUrl,
      (await fixtureTransport(incomplete.dataset, false, incomplete.scope)).fetcher))
      .rejects.toThrow('source-year');
    const unscoped = transportFixture();
    unscoped.metadata.defaultFieldId = 'hep-th';
    await expect(loadCertifiedAtlasRepository(manifestUrl, (await fixtureTransport(unscoped)).fetcher))
      .rejects.toThrow('default field');
  });

  it('rejects five globally present metrics without one co-located branch composite', async () => {
    const { dataset, scope } = scopedTransportFixture();
    for (const observation of dataset.metricObservations) {
      if (observation.metricId !== metricSystemV1Ids[0]) observation.fieldId = 'nucl-th';
    }
    // Retain all identities, years and each manifest count. Only their shared
    // entity/field/year support has disappeared; transport integrity still passes.
    for (const metricId of metricSystemV1Ids) {
      expect(dataset.metricObservations.filter((item) => item.metricId === metricId)).toHaveLength(4);
    }
    expect(buildCompositeMetricObservations(dataset.metricObservations,
      defaultMetricWeightConfiguration, dataset.metricDefinitions)).toHaveLength(0);
    await expect(loadCertifiedAtlasRepository(manifestUrl,
      (await fixtureTransport(dataset, false, scope)).fetcher))
      .rejects.toThrow('co-located');
  });
});
