import { normalizeLiterature } from './normalization/normalizeLiterature.mjs';
import { summarizeEntityResolution } from './entity_resolution/resolutionReport.mjs';
import { calculatePilotMetrics } from './metrics/calculatePilotMetrics.mjs';
import { buildPilotAtlasDataset } from './export/buildAtlasExport.mjs';
import {
  createSnapshotManifest,
  planIncrementalUpdate,
} from './updates/incrementalUpdate.mjs';

export function assertSnapshotMatchesConfig(rawSnapshot, config) {
  const snapshot = rawSnapshot.metadata ?? {};
  const mismatches = [
    ['fieldId', snapshot.fieldId, config.fieldId],
    ['startYear', snapshot.startYear, config.startYear],
    ['endYear', snapshot.endYear, config.endYear],
  ].filter(([, actual, expected]) => actual !== expected);

  if (mismatches.length > 0) {
    const details = mismatches
      .map(([name, actual, expected]) => `${name}: snapshot=${actual}, config=${expected}`)
      .join('; ');
    throw new Error(`Stored INSPIRE snapshot does not match pilot config (${details}).`);
  }
}

export function buildPilotArtifacts(
  rawSnapshot,
  config,
  { rawPath } = {},
) {
  assertSnapshotMatchesConfig(rawSnapshot, config);

  const normalizedPilot = normalizeLiterature(rawSnapshot, config);
  const resolutionReport = summarizeEntityResolution(normalizedPilot);
  const metricResult = calculatePilotMetrics(
    normalizedPilot,
    rawSnapshot,
    config,
    rawSnapshot.metadata.calculatedAt ?? rawSnapshot.metadata.retrievedAt,
  );
  const snapshotManifest = createSnapshotManifest(rawSnapshot, config, {
    ...(rawPath ? { rawPath } : {}),
  });
  const incrementalUpdatePlan = planIncrementalUpdate({
    manifest: snapshotManifest,
    config,
    plannedAt:
      rawSnapshot.metadata.calculatedAt ?? rawSnapshot.metadata.retrievedAt,
    overlapYears: 2,
  });
  const atlasDataset = buildPilotAtlasDataset(
    normalizedPilot,
    metricResult,
    rawSnapshot,
    config,
    snapshotManifest,
  );

  return {
    normalizedPilot,
    identityResolution: normalizedPilot.identityResolution,
    externalResources: normalizedPilot.externalResources,
    resolutionReport,
    metricResult,
    atlasDataset,
    snapshotManifest,
    incrementalUpdatePlan,
  };
}
