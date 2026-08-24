import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { pilotConfig } from './config.mjs';
import { buildPilotArtifacts } from './buildPilotArtifacts.mjs';
import { writeDerivedArtifacts } from './export/writePilotArtifacts.mjs';
import { snapshotIdFor } from './updates/incrementalUpdate.mjs';

const pipelineRoot = path.dirname(fileURLToPath(import.meta.url));

export function versionedOutputPaths(snapshotId, outputRoot = pipelineRoot) {
  const versionRoot = path.join(outputRoot, 'data/versions', snapshotId);
  return {
    normalizedPilot: path.join(versionRoot, 'normalized.json'),
    identityResolution: path.join(versionRoot, 'identity-resolution.json'),
    externalResources: path.join(versionRoot, 'external-resources.json'),
    resolutionReport: path.join(versionRoot, 'entity-resolution-report.json'),
    metricSummary: path.join(versionRoot, 'metric-summary.json'),
    atlasDataset: path.join(versionRoot, 'atlas-export.json'),
    snapshotManifest: path.join(versionRoot, 'snapshot-manifest.json'),
    incrementalUpdatePlan: path.join(
      versionRoot,
      'incremental-update-plan.json',
    ),
  };
}

export async function reprocessVersionedSnapshot({
  rawPath,
  config = pilotConfig,
  outputRoot = pipelineRoot,
}) {
  const rawText = await readFile(rawPath, 'utf8');
  const rawSnapshot = JSON.parse(rawText);
  const snapshotId = snapshotIdFor(rawSnapshot);
  const relativeRawPath = path.relative(pipelineRoot, rawPath);
  const artifacts = buildPilotArtifacts(rawSnapshot, config, {
    rawPath: relativeRawPath,
  });
  const outputPaths = versionedOutputPaths(snapshotId, outputRoot);
  await writeDerivedArtifacts(artifacts, outputPaths);
  return {
    snapshotId,
    sourceVersion: rawSnapshot.metadata.sourceVersion,
    rawPath,
    rawSnapshotModified: false,
    outputPaths,
    sourceRecords: artifacts.normalizedPilot.papers.length,
    identitySummary: artifacts.resolutionReport.identityArchitecture,
    metricSummary: artifacts.metricResult.summary,
  };
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const rawPath = process.argv[2];
  if (!rawPath) {
    throw new Error(
      'Usage: node pipeline/reprocess.mjs <preserved-raw-snapshot.json>',
    );
  }
  const result = await reprocessVersionedSnapshot({
    rawPath: path.resolve(rawPath),
  });
  process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
}
