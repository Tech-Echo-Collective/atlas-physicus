import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import demoData from '../../data/demo/atlas.json';
import { atlasDatasetSchema } from '../../domain/schemas';
import {
  DataProvenancePanel,
  LiveDataStatusDetails,
  type LiveAtlasStatusSnapshot,
} from './DataProvenancePanel';

const dataset = atlasDatasetSchema.parse(demoData);
const liveStatus: LiveAtlasStatusSnapshot = {
  updateStatus: {
    lastSuccessfulUpdate: '2026-08-29T00:00:00Z',
    unresolvedEntityCount: 99,
    resourceCheckFailures: 0,
    metricRecalculationStatus: 'idle',
    sources: [
      {
        source: 'inspire',
        status: 'healthy',
        scopeVersion: 'hep-th-v1',
        lastSuccessAt: '2026-08-29T00:00:00Z',
        consecutiveFailures: 0,
      },
    ],
  },
  identityResolutionSummary: {
    total: 20,
    statusCounts: { matched: 15, unresolved: 3, ambiguous: 2 },
    workflowCounts: { needsReview: 4 },
    methodCounts: [{ method: 'external-identifier', count: 15 }],
    entityTypeCounts: [],
    reasonCounts: [{ reason: 'unclassified', count: 5 }],
    resolverVersionCounts: [
      { resolverVersion: 'identity-resolver-v1', count: 20 },
    ],
  },
};

describe('DataProvenancePanel', () => {
  it('keeps static provenance offline and does not fetch while the panel is closed', () => {
    const loadLiveStatus = vi.fn(async () => liveStatus);
    const markup = renderToStaticMarkup(
      <DataProvenancePanel
        metadata={dataset.metadata}
        loadLiveStatus={loadLiveStatus}
      />,
    );

    expect(loadLiveStatus).not.toHaveBeenCalled();
    expect(markup).not.toContain('Live status &amp; methodology');
  });

  it('renders compact live health, identity review, and candidate method status', () => {
    const candidateDefinition = {
      ...dataset.metricDefinitions[0]!,
      version: 'activity-output-participation-v1',
      implementationStatus: 'experimental-candidate' as const,
    };
    const markup = renderToStaticMarkup(
      <LiveDataStatusDetails
        {...liveStatus}
        metricDefinitions={[candidateDefinition]}
      />,
    );

    expect(markup).toContain('Live status &amp; methodology');
    expect(markup).toContain('Open identity reviews');
    expect(markup).toMatch(/Open identity reviews<\/dt><dd>4<\/dd>/);
    expect(markup).toContain('Matched identities');
    expect(markup).toContain('Unresolved identities');
    expect(markup).toContain('Ambiguous identities');
    expect(markup).toContain('inspire');
    expect(markup).toContain('healthy');
    expect(markup).toContain('activity-output-participation-v1');
    expect(markup).toContain('Experimental candidate · withheld');
    expect(markup).toContain('not loaded into, composed for, or rendered');
    expect(markup).not.toMatch(/Open identity reviews<\/dt><dd>99<\/dd>/);
  });

  it('preserves the static dataset provenance surface without a live status section', () => {
    const markup = renderToStaticMarkup(
      <DataProvenancePanel metadata={dataset.metadata} defaultOpen />,
    );

    expect(markup).toContain('Data provenance');
    expect(markup).toContain('Dataset');
    expect(markup).toContain('Dataset version');
    expect(markup).toContain('synthetic demo');
    expect(markup).not.toContain('Loading live status');
    expect(markup).not.toContain('Live status &amp; methodology');
  });
});
