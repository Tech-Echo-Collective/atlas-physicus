import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { pilotConfig } from './config.mjs';
import { ingestInspirePilot } from './ingestion/inspireClient.mjs';
import { buildPilotArtifacts } from './buildPilotArtifacts.mjs';
import {
  pipelineOutputPaths,
  writeDerivedArtifacts,
  writeRawSnapshot,
} from './export/writePilotArtifacts.mjs';
import { snapshotIdFor } from './updates/incrementalUpdate.mjs';

export async function runPilotPipeline(config = pilotConfig) {
  const ingestedSnapshot = await ingestInspirePilot(config);
  const rawSnapshot = {
    ...ingestedSnapshot,
    metadata: {
      ...ingestedSnapshot.metadata,
      calculatedAt: new Date().toISOString(),
    },
  };
  const snapshotId = snapshotIdFor(rawSnapshot);
  const rawPath = path.join(
    path.dirname(pipelineOutputPaths.rawSnapshot),
    'snapshots',
    `${snapshotId}.json`,
  );
  await writeRawSnapshot(rawSnapshot, {
    ...pipelineOutputPaths,
    rawSnapshot: rawPath,
  });

  const artifacts = buildPilotArtifacts(rawSnapshot, config, {
    rawPath: `data/raw/snapshots/${snapshotId}.json`,
  });
  await writeDerivedArtifacts(artifacts);

  return {
    rawPath,
    atlasExportPath: pipelineOutputPaths.atlasDataset,
    sourceRecords: artifacts.normalizedPilot.papers.length,
    resolutionReport: artifacts.resolutionReport,
    metricSummary: artifacts.metricResult.summary,
  };
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const result = await runPilotPipeline();
  process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
}
