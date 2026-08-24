import type {
  Country,
  Institution,
  MetricObservation,
  Researcher,
} from '../../domain/models';

interface CountryPanelProps {
  country: Country | null;
  institutions: Institution[];
  researchers: Researcher[];
  observation: MetricObservation | null;
  activeFieldLabel: string;
  onClose: () => void;
}

export function CountryPanel({
  country,
  institutions,
  researchers,
  observation,
  activeFieldLabel,
  onClose,
}: CountryPanelProps) {
  if (!country) {
    return (
      <aside className="country-panel country-panel--empty" aria-live="polite">
        <span className="target-mark" aria-hidden="true" />
        <p className="section-kicker">Country profile</p>
        <h2>Select a highlighted country</h2>
        <p>
          Explore how the selected research field appears across the synthetic
          demonstration landscape.
        </p>
      </aside>
    );
  }

  return (
    <aside className="country-panel" aria-live="polite">
      <button
        className="panel-close"
        onClick={onClose}
        type="button"
        aria-label="Close country profile"
      >
        ×
      </button>
      <p className="section-kicker">Country profile · demo</p>
      <div className="country-heading">
        <span>{country.isoAlpha3}</span>
        <h2>{country.name}</h2>
        <p>{country.region}</p>
      </div>

      <div className="score-card">
        <div>
          <span className="score-label">research_activity_score</span>
          <strong>{observation?.value ?? '—'}</strong>
        </div>
        <p>{activeFieldLabel}</p>
      </div>

      <dl className="country-stats">
        <div>
          <dt>Institutions</dt>
          <dd>{institutions.length}</dd>
        </div>
        <div>
          <dt>Researchers</dt>
          <dd>{researchers.length}</dd>
        </div>
        <div>
          <dt>Period</dt>
          <dd>{observation?.period ?? '—'}</dd>
        </div>
      </dl>

      <div className="institution-list">
        <p className="section-kicker">Demo institutions</p>
        {institutions.length > 0 ? (
          institutions.map((institution) => (
            <div key={institution.id} className="institution-item">
              <strong>{institution.name}</strong>
              <span>{institution.city}</span>
            </div>
          ))
        ) : (
          <p className="muted-copy">No demo institutions for this country.</p>
        )}
      </div>

      <p className="panel-disclaimer">
        Synthetic interface data — not a ranking or measured research result.
      </p>
    </aside>
  );
}
