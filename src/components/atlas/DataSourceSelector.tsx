import {
  atlasDataSourceOptions,
  type AtlasDataSourceId,
} from '../../data/AtlasDataSources';

interface DataSourceSelectorProps {
  selectedSourceId: AtlasDataSourceId;
  liveApiAvailable: boolean;
  certifiedDataset?: boolean;
  isLoading?: boolean;
  loadingSourceId?: AtlasDataSourceId | null;
  error?: string | null;
  notice?: string | null;
  onSelect: (sourceId: AtlasDataSourceId) => void;
}

export function DataSourceSelector({
  selectedSourceId,
  liveApiAvailable,
  certifiedDataset = false,
  isLoading = false,
  loadingSourceId = null,
  error = null,
  notice = null,
  onSelect,
}: DataSourceSelectorProps) {
  const isPilot = selectedSourceId === 'inspire-hep-pilot';
  const isLive = selectedSourceId === 'live-api';

  return (
    <section
      className="data-source-selector"
      aria-label="Atlas data source"
      aria-busy={isLoading}
    >
      <p className="section-kicker">Data source</p>
      <div
        className="data-source-options"
        data-single-source={atlasDataSourceOptions.length === 1}
      >
        {atlasDataSourceOptions.map((source) => {
          const isUnavailable = Boolean(source.requiresApi && !liveApiAvailable);
          return (
            <button
              type="button"
              key={source.id}
              data-active={source.id === selectedSourceId}
              aria-pressed={source.id === selectedSourceId}
              disabled={isUnavailable}
              title={
                isUnavailable
                  ? 'Live API mode is available when an Atlas API URL is configured.'
                  : undefined
              }
              onClick={() => onSelect(source.id)}
            >
              <strong>{certifiedDataset && source.id === 'live-api' ? 'Certified Atlas dataset' : source.label}</strong>
              <small>
                {isUnavailable ? 'API deployment not configured' :
                  certifiedDataset && source.id === 'live-api' ? 'Immutable scientific release' : source.description}
              </small>
            </button>
          );
        })}
      </div>
      {isLoading && (
        <p className="data-source-status" role="status">
          Loading{' '}
          {atlasDataSourceOptions.find(
            (source) => source.id === loadingSourceId,
          )?.label ?? 'Atlas data'}
          … The current map remains active until validation completes.
        </p>
      )}
      {error && (
        <p className="data-source-status" data-error="true" role="alert">
          {error}
        </p>
      )}
      {notice && !error && (
        <p className="data-source-status" role="status">
          {notice}
        </p>
      )}
      {isPilot && (
        <p className="pilot-source-note" role="note">
          <strong>Real-data pilot · hep-th · 2000–2026</strong>
          <span>
            2026 is year to date. This bounded pilot is not a scientific
            ranking.
          </span>
        </p>
      )}
      {isLive && !isLoading && !error && !notice && (
        <p className="pilot-source-note" role="note">
          <strong>{certifiedDataset ? 'Certified versioned Atlas dataset' : 'API-backed Atlas metadata'}</strong>
          <span>
            Source provenance remains separate from synthetic and pilot data.
          </span>
        </p>
      )}
    </section>
  );
}
