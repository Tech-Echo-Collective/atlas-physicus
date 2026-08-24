import { mkdir, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const pipelineRoot = path.dirname(path.dirname(fileURLToPath(import.meta.url)));

export const pipelineOutputPaths = Object.freeze({
  rawSnapshot: path.join(
    pipelineRoot,
    'data/raw/inspire-hep-hep-th-2000-2026.json',
  ),
  normalizedPilot: path.join(
    pipelineRoot,
    'data/processed/normalized-hep-th-pilot.json',
  ),
  identityResolution: path.join(
    pipelineRoot,
    'data/processed/identity-resolution-hep-th-pilot.json',
  ),
  externalResources: path.join(
    pipelineRoot,
    'data/processed/external-resources-hep-th-pilot.json',
  ),
  resolutionReport: path.join(
    pipelineRoot,
    'data/reports/entity-resolution.json',
  ),
  metricSummary: path.join(
    pipelineRoot,
    'data/reports/metric-summary.json',
  ),
  atlasDataset: path.join(pipelineRoot, 'export/hep-th-pilot.json'),
  snapshotManifest: path.join(
    pipelineRoot,
    'data/manifests/inspire-hep-hep-th-snapshots.json',
  ),
  incrementalUpdatePlan: path.join(
    pipelineRoot,
    'data/manifests/incremental-update-plan.json',
  ),
});

export async function writeJson(targetPath, value) {
  await mkdir(path.dirname(targetPath), { recursive: true });
  await writeFile(targetPath, `${JSON.stringify(value, null, 2)}\n`, 'utf8');
}

export async function writeRawSnapshot(
  rawSnapshot,
  paths = pipelineOutputPaths,
) {
  await writeJson(paths.rawSnapshot, rawSnapshot);
}

export async function writeDerivedArtifacts(
  {
    normalizedPilot,
    identityResolution,
    externalResources,
    resolutionReport,
    metricResult,
    atlasDataset,
    snapshotManifest,
    incrementalUpdatePlan,
  },
  paths = pipelineOutputPaths,
) {
  const outputs = [
    [paths.normalizedPilot, normalizedPilot],
    [paths.identityResolution, identityResolution],
    [paths.externalResources, externalResources],
    [paths.resolutionReport, resolutionReport],
    [paths.metricSummary, metricResult.summary],
    [paths.atlasDataset, atlasDataset],
    [paths.snapshotManifest, snapshotManifest],
    [paths.incrementalUpdatePlan, incrementalUpdatePlan],
  ].filter(([targetPath]) => Boolean(targetPath));
  await Promise.all(
    outputs.map(([targetPath, value]) => writeJson(targetPath, value)),
  );
}
