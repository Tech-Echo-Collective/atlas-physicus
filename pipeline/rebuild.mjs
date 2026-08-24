import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { pilotConfig } from './config.mjs';
import { buildPilotArtifacts } from './buildPilotArtifacts.mjs';
import {
  pipelineOutputPaths,
  writeDerivedArtifacts,
} from './export/writePilotArtifacts.mjs';

export async function rebuildFromStoredSnapshot(
  config = pilotConfig,
  paths = pipelineOutputPaths,
) {
  const rawSnapshot = JSON.parse(await readFile(paths.rawSnapshot, 'utf8'));
  const artifacts = buildPilotArtifacts(rawSnapshot, config, {
    rawPath: 'data/raw/inspire-hep-hep-th-2000-2026.json',
  });
  await writeDerivedArtifacts(artifacts, paths);

  return {
    rawPath: paths.rawSnapshot,
    atlasExportPath: paths.atlasDataset,
    sourceRecords: artifacts.normalizedPilot.papers.length,
    resolutionReport: artifacts.resolutionReport,
    metricSummary: artifacts.metricResult.summary,
    atlasDataset: artifacts.atlasDataset,
  };
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const result = await rebuildFromStoredSnapshot();
  const summary = {
    rawPath: result.rawPath,
    atlasExportPath: result.atlasExportPath,
    sourceRecords: result.sourceRecords,
    resolutionReport: result.resolutionReport,
    metricSummary: result.metricSummary,
  };
  process.stdout.write(`${JSON.stringify(summary, null, 2)}\n`);
}
