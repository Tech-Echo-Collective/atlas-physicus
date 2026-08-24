import { createHash } from 'node:crypto';

function slug(value) {
  return (
    String(value ?? '')
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-|-$/g, '') || 'snapshot'
  );
}

function recordKey(record) {
  return String(record.id ?? record.metadata?.control_number ?? 'unresolved');
}

function mergeByKey(baseItems, incomingItems, key) {
  const merged = new Map(baseItems.map((item) => [key(item), item]));
  incomingItems.forEach((item) => merged.set(key(item), item));
  return [...merged.values()];
}

export function snapshotIdFor(rawSnapshot) {
  const timestamp =
    rawSnapshot.metadata?.retrievedAt ??
    rawSnapshot.metadata?.sourceVersion ??
    'unknown';
  return `inspire-hep-${slug(timestamp)}`;
}

export function canonicalSnapshotDigest(rawSnapshot) {
  return createHash('sha256')
    .update(JSON.stringify(rawSnapshot))
    .digest('hex');
}

export function createSnapshotManifest(
  rawSnapshot,
  config,
  {
    rawPath = 'data/raw/inspire-hep-hep-th-2000-2026.json',
    parentSnapshotId = null,
  } = {},
) {
  const snapshotId = snapshotIdFor(rawSnapshot);
  const capturedAt = rawSnapshot.metadata.retrievedAt;
  const appliedAt =
    rawSnapshot.metadata.calculatedAt ?? rawSnapshot.metadata.retrievedAt;
  const canonicalContentSha256 = canonicalSnapshotDigest(rawSnapshot);
  const literatureRecordCount = rawSnapshot.yearQueries.reduce(
    (sum, query) => sum + query.records.length,
    0,
  );
  const snapshotProvenance = {
    source: rawSnapshot.metadata.source,
    sourceType: 'external-api',
    version: rawSnapshot.metadata.sourceVersion,
    status: 'unverified',
    confidence: 1,
    retrievedAt: capturedAt,
  };
  const snapshotEntry = {
    id: snapshotId,
    snapshotId,
    source: rawSnapshot.metadata.source,
    sourceVersion: rawSnapshot.metadata.sourceVersion,
    capturedAt,
    retrievedAt: capturedAt,
    calculatedAt: appliedAt,
    updateMode: parentSnapshotId ? 'incremental' : 'full-snapshot',
    recordCount: literatureRecordCount,
    ...(parentSnapshotId ? { previousSnapshotId: parentSnapshotId } : {}),
    contentChecksum: `sha256:${canonicalContentSha256}`,
    storageReference: rawPath,
    fieldId: rawSnapshot.metadata.fieldId,
    coverage: {
      startYear: rawSnapshot.metadata.startYear,
      endYear: rawSnapshot.metadata.endYear,
      recordsPerYear: rawSnapshot.metadata.recordsPerYear,
    },
    rawPath,
    canonicalContentSha256,
    recordCounts: {
      literature: literatureRecordCount,
      institutions: rawSnapshot.institutions.length,
    },
    provenance: snapshotProvenance,
    processing: {
      pipelineVersion: config.pilotVersion,
      identityResolutionVersion: config.identityResolutionVersion,
      status: 'processed',
      normalizedPath: 'data/processed/normalized-hep-th-pilot.json',
      identityPath: 'data/processed/identity-resolution-hep-th-pilot.json',
      externalResourcesPath:
        'data/processed/external-resources-hep-th-pilot.json',
      atlasExportPath: 'export/hep-th-pilot.json',
    },
  };
  const unresolvedCount =
    (rawSnapshot.failedInstitutionFetches?.length ?? 0) +
    (rawSnapshot.unresolvedInstitutionReferences?.length ?? 0);
  const datasetUpdate = {
    id: `dataset-update-${slug(config.pilotVersion)}-${slug(appliedAt)}`,
    appliedAt,
    updateMode: 'reprocess',
    sourceSnapshotIds: [snapshotId],
    previousDatasetVersion: 'v3.0.2-alpha-pilot.1',
    datasetVersion: config.pilotVersion,
    resolverVersion: config.identityResolutionVersion,
    metricCalculationVersion: config.pilotVersion,
    changes: {
      created: 0,
      updated: 0,
      unchanged: literatureRecordCount,
      unresolved: unresolvedCount,
    },
    provenance: {
      source: 'Physics Atlas pipeline reprocessing',
      sourceType: 'derived',
      version: config.pilotVersion,
      status: 'unverified',
      confidence: unresolvedCount === 0 ? 1 : 0.9,
      retrievedAt: appliedAt,
    },
  };
  return {
    schemaVersion: '1.0.0',
    manifestVersion: config.snapshotManifestVersion,
    datasetId: `inspire-hep-${config.fieldId}-pilot`,
    activeSnapshotId: snapshotId,
    generatedAt: appliedAt,
    updatePolicy: {
      mode: 'append-versioned-snapshot',
      rawSnapshotsImmutable: true,
      mergeKey: 'INSPIRE control_number',
      conflictPolicy:
        'A newer record revision is selected only while deriving a new snapshot; prior raw snapshots are never modified.',
      reprocessing:
        'Any preserved snapshot may be reprocessed into an isolated version directory.',
    },
    snapshots: [snapshotEntry],
    datasetUpdates: [datasetUpdate],
  };
}

export function planIncrementalUpdate({
  manifest,
  config,
  plannedAt = new Date().toISOString(),
  overlapYears = 1,
}) {
  const active = manifest.snapshots.find(
    (snapshot) => snapshot.snapshotId === manifest.activeSnapshotId,
  );
  if (!active) {
    throw new Error('The active snapshot is missing from the manifest.');
  }
  const firstRefreshYear = Math.max(
    config.startYear,
    active.coverage.endYear - Math.max(0, overlapYears - 1),
  );
  const years = Array.from(
    { length: config.endYear - firstRefreshYear + 1 },
    (_, index) => firstRefreshYear + index,
  );
  const plannedSnapshotId = `inspire-hep-${slug(plannedAt)}`;

  return {
    schemaVersion: '1.0.0',
    mode: 'append-versioned-snapshot',
    plannedAt,
    baseSnapshotId: active.snapshotId,
    baseSourceVersion: active.sourceVersion,
    plannedSnapshotId,
    targetRawPath: `data/raw/snapshots/${plannedSnapshotId}.json`,
    queryPlan: years.map((year) => ({
      entityType: 'literature',
      year,
      query: `primarch:${config.fieldId} and de:${year}`,
      reason:
        year <= active.coverage.endYear
          ? 'refresh mutable source records inside the configured overlap window'
          : 'extend snapshot coverage',
    })),
    institutionPlan:
      'Fetch only institution references not already captured or whose upstream revision changed.',
    safety: {
      modifiesBaseSnapshot: false,
      requiresExplicitIngestion: true,
      schedulerConfigured: false,
      cloudServiceConfigured: false,
    },
    nextSteps: [
      'Ingest the query plan into a new raw snapshot path.',
      'Merge by authoritative source identifiers into a new snapshot object.',
      'Append the new snapshot entry to the manifest.',
      'Reprocess the new snapshot into an isolated version directory.',
      'Promote it only after validation; retain every previous snapshot.',
    ],
  };
}

export function mergeIncrementalSnapshot(
  baseSnapshot,
  incrementalSnapshot,
) {
  const yearQueries = new Map(
    baseSnapshot.yearQueries.map((query) => [query.year, structuredClone(query)]),
  );
  incrementalSnapshot.yearQueries.forEach((incomingQuery) => {
    const existing = yearQueries.get(incomingQuery.year);
    if (!existing) {
      yearQueries.set(incomingQuery.year, structuredClone(incomingQuery));
      return;
    }
    yearQueries.set(incomingQuery.year, {
      ...existing,
      ...structuredClone(incomingQuery),
      records: mergeByKey(
        existing.records,
        incomingQuery.records,
        recordKey,
      ),
    });
  });

  const mergedInstitutions = mergeByKey(
    baseSnapshot.institutions,
    incrementalSnapshot.institutions,
    (entry) => String(entry.record?.id ?? entry.url),
  );
  const componentSourceVersions = [
    ...(baseSnapshot.metadata.componentSourceVersions ?? [
      baseSnapshot.metadata.sourceVersion,
    ]),
    incrementalSnapshot.metadata.sourceVersion,
  ].filter((value, index, values) => values.indexOf(value) === index);

  return {
    metadata: {
      ...structuredClone(baseSnapshot.metadata),
      ...structuredClone(incrementalSnapshot.metadata),
      snapshotKind: 'incremental-merge',
      parentSourceVersion: baseSnapshot.metadata.sourceVersion,
      componentSourceVersions,
      updateTimestamp: incrementalSnapshot.metadata.retrievedAt,
    },
    yearQueries: [...yearQueries.values()].sort((left, right) => left.year - right.year),
    institutions: mergedInstitutions,
    failedInstitutionFetches: mergeByKey(
      baseSnapshot.failedInstitutionFetches ?? [],
      incrementalSnapshot.failedInstitutionFetches ?? [],
      (failure) => failure.url,
    ),
    unresolvedInstitutionReferences: [
      ...new Set([
        ...(baseSnapshot.unresolvedInstitutionReferences ?? []),
        ...(incrementalSnapshot.unresolvedInstitutionReferences ?? []),
      ]),
    ].sort(),
  };
}

export function appendSnapshotToManifest(manifest, snapshotEntry) {
  if (
    manifest.snapshots.some(
      (snapshot) => snapshot.snapshotId === snapshotEntry.snapshotId,
    )
  ) {
    throw new Error(`Snapshot ${snapshotEntry.snapshotId} already exists.`);
  }
  return {
    ...structuredClone(manifest),
    activeSnapshotId: snapshotEntry.snapshotId,
    generatedAt: snapshotEntry.calculatedAt ?? snapshotEntry.retrievedAt,
    snapshots: [...manifest.snapshots, structuredClone(snapshotEntry)],
  };
}
