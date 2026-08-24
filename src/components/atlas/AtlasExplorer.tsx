import { useEffect, useMemo, useRef, useState } from 'react';
import { atlasRepository } from '../../data/StaticAtlasRepository';
import type { AtlasDataset } from '../../domain/models';
import { prototypeMetricId } from '../../domain/models';
import { CountryPanel } from './CountryPanel';
import { FieldOverview } from './FieldOverview';
import { FieldSelector } from './FieldSelector';
import { FullscreenControl } from './FullscreenControl';
import { getInstitutionsForGeographicView } from './GeographicEntityMapping';
import { GlobalViewControl } from './GlobalViewControl';
import { InstitutionView } from './InstitutionView';
import { ResearcherProfile } from './ResearcherProfile';
import { ScienceDomainSelector } from './ScienceDomainSelector';
import { Timeline } from './Timeline';
import { WorldMap } from './WorldMap';

export function AtlasExplorer() {
  const shellRef = useRef<HTMLElement>(null);
  const [dataset, setDataset] = useState<AtlasDataset | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedDomainId, setSelectedDomainId] = useState('physics');
  const [selectedFieldId, setSelectedFieldId] = useState<string | null>(null);
  const [selectedYear, setSelectedYear] = useState(2026);
  const [selectedCountryId, setSelectedCountryId] = useState<string | null>(
    null,
  );
  const [selectedInstitutionId, setSelectedInstitutionId] = useState<
    string | null
  >(null);
  const [selectedResearchGroupId, setSelectedResearchGroupId] = useState<
    string | null
  >(null);
  const [selectedResearcherId, setSelectedResearcherId] = useState<
    string | null
  >(null);
  const [isFieldOverviewOpen, setIsFieldOverviewOpen] = useState(false);
  const [globalResetToken, setGlobalResetToken] = useState(0);

  useEffect(() => {
    atlasRepository
      .loadDataset()
      .then(setDataset)
      .catch(() =>
        setError('The local demonstration dataset could not be loaded.'),
      );
  }, []);

  const availableYears = useMemo(() => {
    if (!dataset) {
      return [];
    }

    return Array.from(
      new Set(
        dataset.metricObservations
          .filter(
            (observation) =>
              observation.entityType === 'country' &&
              observation.metricId === prototypeMetricId,
          )
          .map((observation) => Number(observation.period)),
      ),
    ).sort((left, right) => left - right);
  }, [dataset]);

  const countryObservations = useMemo(
    () =>
      dataset?.metricObservations.filter(
        (observation) =>
          observation.entityType === 'country' &&
          (selectedFieldId
            ? observation.fieldId === selectedFieldId
            : observation.scienceDomainId === selectedDomainId &&
              observation.fieldId === undefined) &&
          observation.metricId === prototypeMetricId &&
          observation.period === String(selectedYear),
      ) ?? [],
    [dataset, selectedDomainId, selectedFieldId, selectedYear],
  );

  const selectedCountry =
    dataset?.countries.find((country) => country.id === selectedCountryId) ??
    null;

  const geographicInstitutions = useMemo(() => {
    if (!dataset || !selectedCountryId) {
      return [];
    }

    return getInstitutionsForGeographicView(
      dataset.institutions,
      selectedCountryId,
      dataset.geographicViews,
    );
  }, [dataset, selectedCountryId]);

  const institutionObservations = useMemo(() => {
    if (!dataset || !selectedCountryId) {
      return [];
    }

    const countryInstitutionIds = new Set(
      geographicInstitutions.map((institution) => institution.id),
    );

    return dataset.metricObservations.filter(
      (observation) =>
        observation.entityType === 'institution' &&
        countryInstitutionIds.has(observation.entityId) &&
        (selectedFieldId
          ? observation.fieldId === selectedFieldId
          : observation.scienceDomainId === selectedDomainId &&
            observation.fieldId === undefined) &&
        observation.metricId === prototypeMetricId &&
        observation.period === String(selectedYear),
    );
  }, [
    dataset,
    geographicInstitutions,
    selectedCountryId,
    selectedDomainId,
    selectedFieldId,
    selectedYear,
  ]);

  if (error) {
    return <main className="state-screen">{error}</main>;
  }

  if (!dataset) {
    return <main className="state-screen">Loading the atlas…</main>;
  }

  const activeDomain =
    dataset.scienceDomains.find(
      (domain) => domain.id === selectedDomainId,
    ) ?? dataset.scienceDomains[0];
  const visibleFields = activeDomain
    ? dataset.fields.filter((field) => activeDomain.fieldIds.includes(field.id))
    : dataset.fields;
  const activeField = selectedFieldId
    ? visibleFields.find((field) => field.id === selectedFieldId) ?? null
    : null;
  const institutionObservationIds = new Set(
    institutionObservations.map((observation) => observation.entityId),
  );
  const visibleInstitutions = selectedCountry
    ? geographicInstitutions.filter(
        (institution) =>
          institution.location &&
          institutionObservationIds.has(institution.id),
      )
    : [];
  const selectedInstitution =
    visibleInstitutions.find(
      (institution) => institution.id === selectedInstitutionId,
    ) ?? null;
  const selectedInstitutionGroups = selectedInstitution
    ? dataset.researchGroups.filter(
        (group) =>
          group.institutionId === selectedInstitution.id &&
          (!selectedFieldId || group.fieldIds.includes(selectedFieldId)),
      )
    : [];
  const selectedResearchGroup =
    selectedInstitutionGroups.find(
      (group) => group.id === selectedResearchGroupId,
    ) ?? selectedInstitutionGroups[0] ?? null;
  const selectedResearcher =
    dataset.researchers.find(
      (researcher) => researcher.id === selectedResearcherId,
    ) ?? null;
  const selectedResearcherAffiliation = selectedResearcher
    ? dataset.affiliations.find(
        (affiliation) =>
          affiliation.researcherId === selectedResearcher.id &&
          affiliation.institutionId === selectedInstitution?.id,
      ) ?? null
    : null;
  const selectedResearcherGroup = selectedResearcherAffiliation?.researchGroupId
    ? dataset.researchGroups.find(
        (group) => group.id === selectedResearcherAffiliation.researchGroupId,
      ) ?? null
    : null;
  const selectedCountryObservation =
    countryObservations.find(
      (observation) => observation.entityId === selectedCountryId,
    ) ?? null;
  const selectedInstitutionActivity = selectedInstitution
    ? dataset.metricObservations.filter(
        (observation) =>
          observation.entityType === 'institution' &&
          observation.entityId === selectedInstitution.id &&
          (selectedFieldId
            ? observation.fieldId === selectedFieldId
            : observation.scienceDomainId === selectedDomainId &&
              observation.fieldId === undefined) &&
          observation.metricId === prototypeMetricId,
      )
    : [];
  const selectedInstitutionLocationCountry = selectedInstitution
    ? dataset.countries.find(
        (country) => country.id === selectedInstitution.countryId,
      ) ?? selectedCountry
    : null;
  const atlasView = isFieldOverviewOpen
    ? 'field'
    : selectedResearcher
      ? 'researcher'
      : selectedInstitution
        ? 'institution'
        : selectedCountry
          ? 'country'
          : 'world';

  const clearEntitySelection = () => {
    setSelectedInstitutionId(null);
    setSelectedResearchGroupId(null);
    setSelectedResearcherId(null);
  };

  const selectDomain = (domainId: string) => {
    setSelectedDomainId(domainId);
    setSelectedFieldId(null);
    clearEntitySelection();
    setIsFieldOverviewOpen(false);
  };

  const selectField = (fieldId: string) => {
    setSelectedFieldId(fieldId);
    clearEntitySelection();
    setIsFieldOverviewOpen(false);
  };

  const selectYear = (year: number) => {
    setSelectedYear(year);
    clearEntitySelection();
  };

  const selectCountry = (countryId: string) => {
    setSelectedCountryId(countryId);
    clearEntitySelection();
    setIsFieldOverviewOpen(false);
  };

  const selectInstitution = (institutionId: string) => {
    const firstGroup = dataset.researchGroups.find(
      (group) =>
        group.institutionId === institutionId &&
        (!selectedFieldId || group.fieldIds.includes(selectedFieldId)),
    );
    setSelectedInstitutionId(institutionId);
    setSelectedResearchGroupId(firstGroup?.id ?? null);
    setSelectedResearcherId(null);
  };

  const selectResearchGroup = (groupId: string) => {
    setSelectedResearchGroupId(groupId);
    setSelectedResearcherId(null);
  };

  const returnToWorld = () => {
    setSelectedCountryId(null);
    clearEntitySelection();
    setIsFieldOverviewOpen(false);
    setGlobalResetToken((token) => token + 1);
  };

  const returnToCountry = () => {
    clearEntitySelection();
  };

  const returnToInstitution = () => {
    setSelectedResearcherId(null);
  };

  const openFieldOverview = () => {
    if (!activeField) {
      return;
    }
    setSelectedCountryId(null);
    clearEntitySelection();
    setIsFieldOverviewOpen(true);
  };

  return (
    <main className="atlas-shell" data-view={atlasView} ref={shellRef}>
      <WorldMap
        countries={dataset.countries}
        geographicViews={dataset.geographicViews}
        countryObservations={countryObservations}
        institutions={visibleInstitutions}
        institutionObservations={institutionObservations}
        selectedCountryId={selectedCountryId}
        selectedInstitutionId={selectedInstitutionId}
        globalResetToken={globalResetToken}
        onCountrySelect={selectCountry}
        onInstitutionSelect={selectInstitution}
      />

      <header className="atlas-header">
        <div className="brand-mark" aria-hidden="true">
          <span />
        </div>
        <div>
          <p>Tech Echo Collective</p>
          <h1>Physics Atlas</h1>
        </div>
        <span className="alpha-badge">Entity alpha</span>
      </header>

      <nav className="atlas-path" aria-label="Current atlas location">
        <strong>{activeDomain?.label}</strong>
        <span>/</span>
        {activeField ? (
          <button type="button" onClick={openFieldOverview}>
            {activeField.id}
          </button>
        ) : (
          <strong>All Physics</strong>
        )}
        {isFieldOverviewOpen ? (
          <>
            <span>/</span>
            <strong>Field overview</strong>
          </>
        ) : (
          <>
            <span>/</span>
            <strong>{selectedYear}</strong>
            <span>/</span>
            <button type="button" onClick={returnToWorld}>
              World
            </button>
            {selectedCountry && (
              <>
                <span>/</span>
                <button type="button" onClick={returnToCountry}>
                  {selectedCountry.isoAlpha3}
                </button>
              </>
            )}
            {selectedInstitution && (
              <>
                <span>/</span>
                <button type="button" onClick={returnToInstitution}>
                  {selectedInstitution.name}
                </button>
              </>
            )}
            {selectedResearchGroup && (
              <>
                <span>/</span>
                <strong>{selectedResearchGroup.name}</strong>
              </>
            )}
            {selectedResearcher && (
              <>
                <span>/</span>
                <strong>{selectedResearcher.name}</strong>
              </>
            )}
          </>
        )}
      </nav>

      <FullscreenControl targetRef={shellRef} />
      <GlobalViewControl
        isGlobalView={atlasView === 'world'}
        onReturn={returnToWorld}
      />

      {selectedCountry && !selectedInstitution && (
        <button
          className="country-view-back"
          type="button"
          onClick={returnToWorld}
        >
          <span aria-hidden="true">←</span>
          <span>
            <small>Country view</small>
            <strong>Back to World</strong>
          </span>
        </button>
      )}

      <section className="field-panel">
        <div className="panel-intro">
          <p className="section-kicker">Atlas coordinates</p>
          <h2>Trace research through space and time</h2>
        </div>
        <ScienceDomainSelector
          domains={dataset.scienceDomains}
          selectedDomainId={selectedDomainId}
          isDomainView={!selectedFieldId}
          onSelect={selectDomain}
        />
        <FieldSelector
          fields={visibleFields}
          selectedFieldId={selectedFieldId}
          onSelect={selectField}
        />
        <div className="active-field-note">
          <span>{activeField ? 'Active field' : 'Domain heatmap'}</span>
          <strong>{activeField?.label ?? activeDomain?.label}</strong>
          <p>{activeField?.description ?? activeDomain?.description}</p>
          {activeField && (
            <button
              className="field-overview-trigger"
              type="button"
              onClick={openFieldOverview}
            >
              Open field overview <i aria-hidden="true">→</i>
            </button>
          )}
        </div>
      </section>

      {!selectedInstitution && !isFieldOverviewOpen && (
        <CountryPanel
          country={selectedCountry}
          institutions={visibleInstitutions}
          countryObservation={selectedCountryObservation}
          institutionObservations={institutionObservations}
          activeScopeLabel={
            activeField?.label ?? activeDomain?.label ?? 'Physics'
          }
          selectedYear={selectedYear}
          onBackToWorld={returnToWorld}
          onInstitutionSelect={selectInstitution}
        />
      )}

      {selectedInstitution &&
        selectedCountry &&
        selectedInstitutionLocationCountry &&
        !selectedResearcher && (
        <InstitutionView
          institution={selectedInstitution}
          explorationCountry={selectedCountry}
          locationCountry={selectedInstitutionLocationCountry}
          fields={dataset.fields}
          activeFieldId={selectedFieldId}
          groups={selectedInstitutionGroups}
          affiliations={dataset.affiliations}
          researchers={dataset.researchers}
          papers={dataset.papers}
          authorships={dataset.authorships}
          historicalEvents={dataset.historicalEvents}
          activityObservations={selectedInstitutionActivity}
          selectedGroupId={selectedResearchGroup?.id ?? null}
          onGroupSelect={selectResearchGroup}
          onResearcherSelect={setSelectedResearcherId}
          onBackToCountry={returnToCountry}
        />
      )}

      {selectedResearcher && selectedInstitution && (
        <ResearcherProfile
          researcher={selectedResearcher}
          affiliation={selectedResearcherAffiliation}
          institution={selectedInstitution}
          group={selectedResearcherGroup}
          fields={dataset.fields}
          papers={dataset.papers}
          authorships={dataset.authorships}
          historicalEvents={dataset.historicalEvents}
          onBackToInstitution={returnToInstitution}
        />
      )}

      {isFieldOverviewOpen && activeField && (
        <FieldOverview
          field={activeField}
          institutions={dataset.institutions}
          researchers={dataset.researchers}
          affiliations={dataset.affiliations}
          papers={dataset.papers}
          authorships={dataset.authorships}
          historicalEvents={dataset.historicalEvents}
          onClose={() => setIsFieldOverviewOpen(false)}
        />
      )}

      <section className="map-legend" aria-label="Map legend">
        <div className="legend-header">
          <span>research_activity_score</span>
          <span>
            {selectedYear} · {activeField?.id ?? activeDomain?.label}
          </span>
        </div>
        <div className="legend-gradient" aria-hidden="true" />
        <div className="legend-scale">
          <span>0</span>
          <span>25</span>
          <span>50</span>
          <span>75</span>
          <span>100</span>
        </div>
        <div className="missing-data-key">
          <i aria-hidden="true" />
          Missing data ≠ zero activity
        </div>
        <p className="legend-disclaimer">
          Demo visualization only. Not a scientific ranking.
        </p>
      </section>

      <Timeline
        years={availableYears}
        selectedYear={selectedYear}
        onChange={selectYear}
      />
    </main>
  );
}
