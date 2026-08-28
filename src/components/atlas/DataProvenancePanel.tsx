import { useState } from 'react';
import type { DatasetMetadata } from '../../domain/models';

interface DataProvenancePanelProps {
  metadata: DatasetMetadata;
}

export function DataProvenancePanel({ metadata }: DataProvenancePanelProps) {
  const [isOpen, setIsOpen] = useState(false);
  const { provenance } = metadata;

  return (
    <div className="provenance-control" data-open={isOpen}>
      <button
        className="atlas-utility-button"
        type="button"
        onClick={() => setIsOpen((current) => !current)}
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
              <dt>Source</dt>
              <dd>{provenance.source}</dd>
            </div>
            <div>
              <dt>Version</dt>
              <dd>{provenance.version}</dd>
            </div>
            <div>
              <dt>Status</dt>
              <dd>{provenance.status}</dd>
            </div>
            {provenance.acquisitionScope && (
              <div>
                <dt>Acquisition scope</dt>
                <dd>{provenance.acquisitionScope}</dd>
              </div>
            )}
            <div>
              <dt>Generated</dt>
              <dd>{new Date(metadata.generatedAt).toLocaleString()}</dd>
            </div>
            {metadata.latestUpdateAt && (
              <div>
                <dt>Last updated</dt>
                <dd>{new Date(metadata.latestUpdateAt).toLocaleString()}</dd>
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
          <p>{metadata.disclaimer}</p>
        </section>
      )}
    </div>
  );
}
