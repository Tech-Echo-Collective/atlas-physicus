import { useState } from 'react';
import type {
  AtlasUpdateStatus,
  DatasetMetadata,
  IdentityResolutionSummary,
  MetricDefinition,
} from '../../domain/models';

export interface LiveAtlasStatusSnapshot {
  updateStatus: AtlasUpdateStatus;
  identityResolutionSummary: IdentityResolutionSummary;
}

interface DataProvenancePanelProps {
  metadata: DatasetMetadata;
  metricDefinitions?: MetricDefinition[];
  loadLiveStatus?: () => Promise<LiveAtlasStatusSnapshot>;
  /** Used by deterministic server-rendered component tests. */
  defaultOpen?: boolean;
}

interface LiveDataStatusDetailsProps extends LiveAtlasStatusSnapshot {
  metricDefinitions: MetricDefinition[];
}

function formatTimestamp(value?: string): string {
  return value ? new Date(value).toLocaleString() : 'Not recorded';
}

export function LiveDataStatusDetails({
  updateStatus,
  identityResolutionSummary,
  metricDefinitions,
}: LiveDataStatusDetailsProps) {
  const candidateDefinitions = metricDefinitions.filter(
    (definition) =>
      definition.implementationStatus === 'experimental-candidate',
  );

  return (
    <div className="live-methodology-status">
      <h3>Live status &amp; methodology</h3>
      <dl>
        <div>
          <dt>Last successful update</dt>
          <dd>{formatTimestamp(updateStatus.lastSuccessfulUpdate)}</dd>
        </div>
        <div>
          <dt>Open identity reviews</dt>
          <dd>{identityResolutionSummary.workflowCounts.needsReview}</dd>
        </div>
        <div>
          <dt>Matched identities</dt>
          <dd>{identityResolutionSummary.statusCounts.matched}</dd>
        </div>
        <div>
          <dt>Unresolved identities</dt>
          <dd>{identityResolutionSummary.statusCounts.unresolved}</dd>
        </div>
        <div>
          <dt>Ambiguous identities</dt>
          <dd>{identityResolutionSummary.statusCounts.ambiguous}</dd>
        </div>
      </dl>

      <div className="live-source-health">
        <h4>Source health</h4>
        {updateStatus.sources.length > 0 ? (
          <ul>
            {updateStatus.sources.map((source) => (
              <li key={`${source.source}:${source.scopeVersion}`}>
                <span>{source.source}</span>
                <strong data-status={source.status}>{source.status}</strong>
                <small>{source.scopeVersion}</small>
              </li>
            ))}
          </ul>
        ) : (
          <p>No source health reports are available.</p>
        )}
      </div>

      <div className="candidate-metric-status">
        <h4>Candidate metric methods</h4>
        {candidateDefinitions.length > 0 ? (
          <ul>
            {candidateDefinitions.map((definition) => (
              <li key={definition.id}>
                <span>{definition.name}</span>
                <small>{definition.version}</small>
                <strong>Experimental candidate · withheld</strong>
              </li>
            ))}
          </ul>
        ) : (
          <p>No candidate metric definitions are published in this dataset.</p>
        )}
        <p>
          Candidate definitions document methods under review. They are not
          loaded into, composed for, or rendered on the public map.
        </p>
      </div>
    </div>
  );
}

export function DataProvenancePanel({
  metadata,
  metricDefinitions = [],
  loadLiveStatus,
  defaultOpen = false,
}: DataProvenancePanelProps) {
  const [isOpen, setIsOpen] = useState(defaultOpen);
  const [liveStatus, setLiveStatus] = useState<LiveAtlasStatusSnapshot | null>(
    null,
  );
  const [liveStatusState, setLiveStatusState] = useState<
    'idle' | 'loading' | 'loaded' | 'error'
  >('idle');
  const { provenance } = metadata;

  const togglePanel = () => {
    const willOpen = !isOpen;
    setIsOpen(willOpen);
    if (
      !willOpen ||
      !loadLiveStatus ||
      liveStatusState === 'loading' ||
      liveStatusState === 'loaded'
    ) {
      return;
    }

    setLiveStatusState('loading');
    loadLiveStatus()
      .then((status) => {
        setLiveStatus(status);
        setLiveStatusState('loaded');
      })
      .catch(() => {
        setLiveStatusState('error');
      });
  };

  return (
    <div className="provenance-control" data-open={isOpen}>
      <button
        className="atlas-utility-button"
        type="button"
        onClick={togglePanel}
        aria-label="View atlas data provenance"
        aria-expanded={isOpen}
        title="Data provenance"
      >
        <span aria-hidden="true">i</span>
      </button>
      {isOpen && (
        <section className="provenance-panel" aria-live="polite">
          <p className="section-kicker">Data provenance</p>
          <h2>{provenance.sourceType.replace('-', ' ')}</h2>
          <dl>
            <div>
              <dt>Dataset</dt>
              <dd>{metadata.datasetKind.replaceAll('-', ' ')}</dd>
            </div>
            <div>
              <dt>Source</dt>
              <dd>{provenance.source}</dd>
            </div>
            <div>
              <dt>Dataset version</dt>
              <dd>{provenance.version}</dd>
            </div>
            <div>
              <dt>Status</dt>
              <dd>{provenance.status}</dd>
            </div>
            {(provenance.acquisitionScope ||
              metadata.datasetKind === 'live-api') && (
              <div>
                <dt>Acquisition scope</dt>
                <dd>{provenance.acquisitionScope ?? 'Not declared'}</dd>
              </div>
            )}
            <div>
              <dt>Generated</dt>
              <dd>{formatTimestamp(metadata.generatedAt)}</dd>
            </div>
            {metadata.latestUpdateAt && (
              <div>
                <dt>Last updated</dt>
                <dd>{formatTimestamp(metadata.latestUpdateAt)}</dd>
              </div>
            )}
            <div>
              <dt>Update sequence</dt>
              <dd>{metadata.updateSequence ?? 0}</dd>
            </div>
            <div>
              <dt>Source snapshots</dt>
              <dd>{metadata.sourceSnapshotIds?.length ?? 0}</dd>
            </div>
            {provenance.confidence !== undefined && (
              <div>
                <dt>Confidence</dt>
                <dd>{Math.round(provenance.confidence * 100)}%</dd>
              </div>
            )}
          </dl>

          {loadLiveStatus && liveStatusState === 'loading' && (
            <p className="live-status-message" role="status">
              Loading live status…
            </p>
          )}
          {loadLiveStatus && liveStatusState === 'error' && (
            <p className="live-status-message" data-error="true" role="alert">
              Live status is temporarily unavailable. Atlas data remains
              unchanged.
            </p>
          )}
          {loadLiveStatus && liveStatus && (
            <LiveDataStatusDetails
              {...liveStatus}
              metricDefinitions={metricDefinitions}
            />
          )}

          <p>{metadata.disclaimer}</p>
          {metadata.deliveryMode === 'versioned-dataset' && metadata.releaseManifestUrl && (
            <p>
              <a href={metadata.releaseManifestUrl} target="_blank" rel="noreferrer">
                Release manifest, missing evidence and scientific provenance
              </a>
            </p>
          )}
        </section>
      )}
    </div>
  );
}
