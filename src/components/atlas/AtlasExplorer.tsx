import { useEffect, useMemo, useState } from 'react';
import { atlasRepository } from '../../data/StaticAtlasRepository';
import type { AtlasDataset } from '../../domain/models';
import { prototypeMetricId } from '../../domain/models';
import { CountryPanel } from './CountryPanel';
import { FieldSelector } from './FieldSelector';
import { WorldMap } from './WorldMap';

export function AtlasExplorer() {
  const [dataset, setDataset] = useState<AtlasDataset | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedFieldId, setSelectedFieldId] = useState('hep-th');
  const [selectedCountryId, setSelectedCountryId] = useState<string | null>(
    null,
  );

  useEffect(() => {
    atlasRepository
      .loadDataset()
      .then(setDataset)
      .catch(() => setError('The local demonstration dataset could not be loaded.'));
  }, []);

  const observations = useMemo(
    () =>
      dataset?.metricObservations.filter(
        (observation) =>
          observation.entityType === 'country' &&
          observation.fieldId === selectedFieldId &&
          observation.metricId === prototypeMetricId &&
          observation.period === dataset.metadata.period,
      ) ?? [],
    [dataset, selectedFieldId],
  );

  if (error) {
    return <main className="state-screen">{error}</main>;
  }

  if (!dataset) {
    return <main className="state-screen">Loading the atlas…</main>;
  }

  const activeField =
    dataset.fields.find((field) => field.id === selectedFieldId) ??
    dataset.fields[0];
  const selectedCountry =
    dataset.countries.find((country) => country.id === selectedCountryId) ??
    null;
  const countryInstitutions = selectedCountry
    ? dataset.institutions.filter(
        (institution) => institution.countryId === selectedCountry.id,
      )
    : [];
  const institutionIds = new Set(
    countryInstitutions.map((institution) => institution.id),
  );
  const countryResearchers = dataset.researchers.filter((researcher) =>
    institutionIds.has(researcher.institutionId),
  );
  const selectedObservation =
    observations.find(
      (observation) => observation.entityId === selectedCountryId,
    ) ?? null;

  return (
    <main className="atlas-shell">
      <WorldMap
        countries={dataset.countries}
        observations={observations}
        selectedCountryId={selectedCountryId}
        onCountrySelect={setSelectedCountryId}
      />

      <header className="atlas-header">
        <div className="brand-mark" aria-hidden="true">
          <span />
        </div>
        <div>
          <p>Tech Echo Collective</p>
          <h1>Physics Atlas</h1>
        </div>
        <span className="alpha-badge">Alpha prototype</span>
      </header>

      <section className="field-panel">
        <div className="panel-intro">
          <p className="section-kicker">Global research landscape</p>
          <h2>Explore the structure of physics</h2>
          <p>
            Select a field to redraw the synthetic research activity layer.
          </p>
        </div>
        <FieldSelector
          fields={dataset.fields}
          selectedFieldId={selectedFieldId}
          onSelect={setSelectedFieldId}
        />
        <div className="active-field-note">
          <span>Viewing</span>
          <strong>{activeField.label}</strong>
          <p>{activeField.description}</p>
        </div>
      </section>

      <CountryPanel
        country={selectedCountry}
        institutions={countryInstitutions}
        researchers={countryResearchers}
        observation={selectedObservation}
        activeFieldLabel={activeField.label}
        onClose={() => setSelectedCountryId(null)}
      />

      <section className="map-legend" aria-label="Map legend">
        <div className="legend-header">
          <span>research_activity_score</span>
          <span>2025 · synthetic</span>
        </div>
        <div className="legend-gradient" aria-hidden="true" />
        <div className="legend-scale">
          <span>0</span>
          <span>25</span>
          <span>50</span>
          <span>75</span>
          <span>100</span>
        </div>
      </section>

      <footer className="demo-notice">
        <span className="notice-dot" aria-hidden="true" />
        <p>
          <strong>Demonstration data.</strong> Synthetic values for interface
          evaluation only — not rankings, predictions, or measured research
          performance.
        </p>
      </footer>
    </main>
  );
}
