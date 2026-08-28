import type {
  Country,
  Institution,
  MetricObservation,
} from '../../domain/models';
import {
  getDatasetPresentation,
  type AtlasDatasetKind,
} from '../../data/DatasetPresentation';

interface CountryPanelProps {
  country: Country | null;
  institutions: Institution[];
  countryObservation: MetricObservation | null;
  institutionObservations: MetricObservation[];
  metricLabel: string;
  activeScopeLabel: string;
  selectedYear: number;
  datasetKind: AtlasDatasetKind;
  onBackToWorld: () => void;
  onInstitutionSelect: (institutionId: string) => void;
}

export function CountryPanel({
  country,
  institutions,
  countryObservation,
  institutionObservations,
  metricLabel,
  activeScopeLabel,
  selectedYear,
  datasetKind,
  onBackToWorld,
  onInstitutionSelect,
}: CountryPanelProps) {
  const presentation = getDatasetPresentation(datasetKind);
  const valuesByInstitution = new Map(
    institutionObservations.map((observation) => [
      observation.entityId,
      observation.value,
    ]),
  );

  if (!country) {
    return (
      <aside className="country-panel country-panel--empty" aria-live="polite">
        <span className="target-mark" aria-hidden="true" />
        <p className="section-kicker">World view</p>
        <h2>Select a luminous country</h2>
        <p>
          Enter a country to reveal its{' '}
          {presentation.dataLabelLower} institution landscape for{' '}
          {selectedYear}.
        </p>
      </aside>
    );
  }

  return (
    <aside className="country-panel" aria-live="polite">
      <button className="panel-back" onClick={onBackToWorld} type="button">
        ← World
      </button>
      <p className="section-kicker">
        Country view · {presentation.dataLabel}
      </p>
      <div className="country-heading">
        <span>{country.isoAlpha3}</span>
        <h2>{country.name}</h2>
        <p>{country.region}</p>
      </div>

      <div className="metric-card">
        <div>
          <span className="metric-label">{metricLabel}</span>
          <strong>{countryObservation?.value ?? '—'}</strong>
        </div>
        <p>{activeScopeLabel}</p>
      </div>

      <div className="country-level-meta">
        <span>{selectedYear}</span>
        <span>{institutions.length} major institution nodes</span>
      </div>

      <div className="institution-list">
        <p className="section-kicker">Institution nodes</p>
        {institutions.length > 0 ? (
          institutions.map((institution) => (
            <button
              key={institution.id}
              className="institution-item"
              type="button"
              onClick={() => onInstitutionSelect(institution.id)}
            >
              <span>
                <strong>{institution.name}</strong>
                <small>{institution.city}</small>
              </span>
              <b>{valuesByInstitution.get(institution.id) ?? '—'}</b>
            </button>
          ))
        ) : (
          <p className="muted-copy">
            No institution observations for this scope and year.
          </p>
        )}
      </div>

      <p className="panel-disclaimer">
        {presentation.disclaimer}
      </p>
    </aside>
  );
}
