import {
  atlasDataSourceOptions,
  type AtlasDataSourceId,
} from '../../data/AtlasDataSources';

interface DataSourceSelectorProps {
  selectedSourceId: AtlasDataSourceId;
  onSelect: (sourceId: AtlasDataSourceId) => void;
}

export function DataSourceSelector({
  selectedSourceId,
  onSelect,
}: DataSourceSelectorProps) {
  const isPilot = selectedSourceId === 'inspire-hep-pilot';

  return (
    <section className="data-source-selector" aria-label="Atlas data source">
      <p className="section-kicker">Data source</p>
      <div className="data-source-options">
        {atlasDataSourceOptions.map((source) => (
          <button
            type="button"
            key={source.id}
            data-active={source.id === selectedSourceId}
            aria-pressed={source.id === selectedSourceId}
            onClick={() => onSelect(source.id)}
          >
            <strong>{source.label}</strong>
            <small>{source.description}</small>
          </button>
        ))}
      </div>
      {isPilot && (
        <p className="pilot-source-note" role="note">
          <strong>Real-data pilot · hep-th · 2000–2026</strong>
          <span>
            2026 is year to date. This bounded pilot is not a scientific
            ranking.
          </span>
        </p>
      )}
    </section>
  );
}
