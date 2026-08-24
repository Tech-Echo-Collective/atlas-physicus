import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { atlasRepository } from '../../data/StaticAtlasRepository';
import { loadAtlasDataset } from '../../data/loadAtlasDataset';
import {
  buildDataSourceAwareAtlasUrl,
  resolveAtlasDataSource,
  type AtlasDataSourceId,
} from '../../data/AtlasDataSources';
import type {
  AtlasDataset,
  AtlasRepository,
  AtlasSearchResult,
  MetricId,
} from '../../domain/models';
import { compositeMetricId, defaultMetricId } from '../../domain/models';
import {
  buildCompositeMetricObservations,
  defaultMetricWeightConfiguration,
  hasCompositeMetricInputs,
} from '../../metrics/CompositeMetric';
import { ProfileService } from '../../profiles/ProfileService';
import {
  buildAtlasUrl,
  getExplorationCountryId,
  resolveAtlasLocation,
  type AtlasNavigationState,
} from '../../navigation/AtlasNavigation';
import { AtlasSearch } from './AtlasSearch';
import { CountryPanel } from './CountryPanel';
import { DataProvenancePanel } from './DataProvenancePanel';
import { DataSourceSelector } from './DataSourceSelector';
import { FieldOverview } from './FieldOverview';
import { FieldSelector } from './FieldSelector';
import { FullscreenControl } from './FullscreenControl';
import { getInstitutionsForGeographicView } from './GeographicEntityMapping';
import {
  GuidedExploration,
  type GuidedAction,
} from './GuidedExploration';
import { InstitutionView } from './InstitutionView';
import { selectMajorInstitutionsForMap } from './InstitutionLayer';
import { MetricWeightingPanel } from './MetricWeightingPanel';
import { ResearcherProfile } from './ResearcherProfile';
import { ScienceDomainSelector } from './ScienceDomainSelector';
import { Timeline } from './Timeline';
import { WorldMap } from './WorldMap';

export function AtlasExplorer() {
  const shellRef = useRef<HTMLElement>(null);
  const [dataset, setDataset] = useState<AtlasDataset | null>(null);
  const [repository, setRepository] =
    useState<AtlasRepository>(atlasRepository);
  const [selectedDataSourceId, setSelectedDataSourceId] =
    useState<AtlasDataSourceId>(() =>
      typeof window === 'undefined'
        ? 'synthetic-framework'
        : resolveAtlasDataSource(window.location.search),
    );
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
  const [selectedMetricId, setSelectedMetricId] =
    useState<MetricId>(defaultMetricId);
  const [metricWeightConfiguration, setMetricWeightConfiguration] = useState(
    defaultMetricWeightConfiguration,
  );
  const [hasConfirmedMetricProfile, setHasConfirmedMetricProfile] =
    useState(false);

  const applyNavigationState = useCallback(
    (navigation: AtlasNavigationState) => {
      setSelectedDomainId(navigation.selectedDomainId);
      setSelectedFieldId(navigation.selectedFieldId);
      setSelectedYear(navigation.selectedYear);
      setSelectedCountryId(navigation.selectedCountryId);
      setSelectedInstitutionId(navigation.selectedInstitutionId);
      setSelectedResearchGroupId(navigation.selectedResearchGroupId);
      setSelectedResearcherId(navigation.selectedResearcherId);
      setIsFieldOverviewOpen(navigation.isFieldOverviewOpen);
    },
    [],
  );

  const navigationState = useMemo<AtlasNavigationState>(
    () => ({
      selectedDomainId,
      selectedFieldId,
      selectedYear,
      selectedCountryId,
      selectedInstitutionId,
      selectedResearchGroupId,
      selectedResearcherId,
      isFieldOverviewOpen,
    }),
    [
      isFieldOverviewOpen,
      selectedCountryId,
      selectedDomainId,
      selectedFieldId,
      selectedInstitutionId,
      selectedResearchGroupId,
      selectedResearcherId,
      selectedYear,
    ],
  );

  const navigateTo = useCallback(
    (navigation: AtlasNavigationState, replace = false) => {
      applyNavigationState(navigation);
      if (!dataset || typeof window === 'undefined') {
        return;
      }
      const url = buildDataSourceAwareAtlasUrl(
        buildAtlasUrl(navigation, dataset),
        selectedDataSourceId,
      );
      if (url === `${window.location.pathname}${window.location.search}`) {
        return;
      }
      window.history[replace ? 'replaceState' : 'pushState'](null, '', url);
    },
    [applyNavigationState, dataset, selectedDataSourceId],
  );

  const searchAtlas = useCallback(
    (query: string) => repository.searchEntities(query),
    [repository],
  );

  useEffect(() => {
    let isActive = true;

    const repositoryPromise =
      selectedDataSourceId === 'inspire-hep-pilot'
        ? import('../../data/PilotAtlasRepository').then(
            ({ pilotAtlasRepository }) => pilotAtlasRepository,
          )
        : Promise.resolve(atlasRepository);

    repositoryPromise
      .then((nextRepository) => {
        if (!isActive) {
          return null;
        }
        setRepository(nextRepository);
        return loadAtlasDataset(nextRepository);
      })
      .then((nextDataset) => {
        if (isActive && nextDataset) {
          setDataset(nextDataset);
        }
      })
      .catch(() => {
        if (isActive) {
          setError('The selected Atlas dataset could not be loaded.');
        }
      });

    return () => {
      isActive = false;
    };
  }, [selectedDataSourceId]);

  useEffect(() => {
    if (!dataset || typeof window === 'undefined') {
      return;
    }

    const restoreLocation = () => {
      const resolvedNavigation = resolveAtlasLocation(window.location, dataset);
      const navigation =
        dataset.metadata.datasetKind === 'inspire-hep-pilot' &&
        !resolvedNavigation.selectedFieldId
          ? {
              ...resolvedNavigation,
              selectedFieldId: dataset.fields[0]?.id ?? null,
            }
          : resolvedNavigation;
      applyNavigationState(navigation);
      const canonicalUrl = buildDataSourceAwareAtlasUrl(
        buildAtlasUrl(navigation, dataset),
        selectedDataSourceId,
      );
      if (canonicalUrl !== `${window.location.pathname}${window.location.search}`) {
        window.history.replaceState(null, '', canonicalUrl);
      }
    };

    restoreLocation();
    window.addEventListener('popstate', restoreLocation);
    return () => window.removeEventListener('popstate', restoreLocation);
  }, [applyNavigationState, dataset, selectedDataSourceId]);

  const visualizationObservations = useMemo(() => {
    if (!dataset) {
      return [];
    }

    return selectedMetricId === compositeMetricId
      ? buildCompositeMetricObservations(
          dataset.metricObservations,
          metricWeightConfiguration,
        )
      : dataset.metricObservations.filter(
          (observation) => observation.metricId === selectedMetricId,
        );
  }, [dataset, metricWeightConfiguration, selectedMetricId]);

  const availableYears = useMemo(() => {
    if (!dataset) {
      return [];
    }

    return Array.from(
      new Set(
        visualizationObservations
          .filter(
            (observation) =>
              observation.entityType === 'country',
          )
          .map((observation) => Number(observation.period)),
      ),
    ).sort((left, right) => left - right);
  }, [dataset, visualizationObservations]);

  const countryObservations = useMemo(
    () =>
      visualizationObservations.filter(
        (observation) =>
          observation.entityType === 'country' &&
          (selectedFieldId
            ? observation.fieldId === selectedFieldId
            : observation.scienceDomainId === selectedDomainId &&
              observation.fieldId === undefined) &&
          observation.period === String(selectedYear),
      ),
    [
      selectedDomainId,
      selectedFieldId,
      selectedYear,
      visualizationObservations,
    ],
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

    return visualizationObservations.filter(
      (observation) =>
        observation.entityType === 'institution' &&
        countryInstitutionIds.has(observation.entityId) &&
        (selectedFieldId
          ? observation.fieldId === selectedFieldId
          : observation.scienceDomainId === selectedDomainId &&
            observation.fieldId === undefined) &&
        observation.period === String(selectedYear),
    );
  }, [
    dataset,
    geographicInstitutions,
    selectedCountryId,
    selectedDomainId,
    selectedFieldId,
    selectedYear,
    visualizationObservations,
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
  const activeMetricDefinition = dataset.metricDefinitions.find(
    (definition) => definition.id === selectedMetricId,
  );
  const visualizationMetricDefinitions = dataset.metricDefinitions.filter(
    (definition) => definition.implementationStatus !== 'taxonomy-only',
  );
  const compositeAvailable = hasCompositeMetricInputs(
    visualizationMetricDefinitions,
    defaultMetricWeightConfiguration,
  );
  const isPilotDataset = dataset.metadata.datasetKind === 'inspire-hep-pilot';
  const activeMetricLabel =
    selectedMetricId === compositeMetricId
      ? metricWeightConfiguration.name
      : (activeMetricDefinition?.name ?? selectedMetricId);
  const visibleInstitutions = selectedCountry
    ? selectMajorInstitutionsForMap(
        geographicInstitutions,
        institutionObservations,
      )
    : [];
  const selectedInstitution =
    geographicInstitutions.find(
      (institution) => institution.id === selectedInstitutionId,
    ) ?? null;
  const mapInstitutions =
    selectedInstitution &&
    !visibleInstitutions.some(
      (institution) => institution.id === selectedInstitution.id,
    )
      ? [...visibleInstitutions, selectedInstitution]
      : visibleInstitutions;
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
  const selectedInstitutionMetricObservations = selectedInstitution
    ? visualizationObservations.filter(
        (observation) =>
          observation.entityType === 'institution' &&
          observation.entityId === selectedInstitution.id &&
          (selectedFieldId
            ? observation.fieldId === selectedFieldId
            : observation.scienceDomainId === selectedDomainId &&
              observation.fieldId === undefined),
      )
    : [];
  const selectedInstitutionLocationCountry = selectedInstitution
    ? dataset.countries.find(
        (country) => country.id === selectedInstitution.countryId,
      ) ?? selectedCountry
    : null;
  const profileService = new ProfileService(dataset);
  const selectedInstitutionProfile = selectedInstitution
    ? profileService.getInstitutionProfile(selectedInstitution.id)
    : null;
  const selectedResearcherProfile = selectedResearcher
    ? profileService.getResearcherProfile(selectedResearcher.id)
    : null;
  const selectedInstitutionIdentityResolutions = selectedInstitution
    ? (dataset.identityResolutions ?? []).filter(
        (resolution) =>
          resolution.status === 'matched' &&
          resolution.canonicalEntityId === selectedInstitution.id,
      )
    : [];
  const selectedResearcherIdentityResolutions = selectedResearcher
    ? (dataset.identityResolutions ?? []).filter(
        (resolution) =>
          resolution.status === 'matched' &&
          resolution.canonicalEntityId === selectedResearcher.id,
      )
    : [];
  const atlasView = isFieldOverviewOpen
    ? 'field'
    : selectedResearcher
      ? 'researcher'
      : selectedInstitution
        ? 'institution'
        : selectedCountry
          ? 'country'
          : 'world';

  const selectDataSource = (sourceId: AtlasDataSourceId) => {
    if (sourceId === selectedDataSourceId) {
      return;
    }

    setSelectedDataSourceId(sourceId);
    setDataset(null);
    setError(null);
    setSelectedDomainId('physics');
    setSelectedFieldId(
      sourceId === 'inspire-hep-pilot' ? 'hep-th' : null,
    );
    setSelectedYear(2026);
    setSelectedCountryId(null);
    setSelectedInstitutionId(null);
    setSelectedResearchGroupId(null);
    setSelectedResearcherId(null);
    setIsFieldOverviewOpen(false);
    setSelectedMetricId(defaultMetricId);
    setMetricWeightConfiguration(defaultMetricWeightConfiguration);
    setHasConfirmedMetricProfile(false);
    setGlobalResetToken((token) => token + 1);

    if (typeof window !== 'undefined') {
      window.history.replaceState(null, '',
        buildDataSourceAwareAtlasUrl(
          sourceId === 'inspire-hep-pilot'
            ? '/atlas/physics/hep-th?year=2026'
            : '/atlas/physics?year=2026',
          sourceId,
        ),
      );
    }
  };

  const selectDomain = (domainId: string) => {
    const domain = dataset.scienceDomains.find(
      (candidate) => candidate.id === domainId,
    );
    navigateTo({
      ...navigationState,
      selectedDomainId: domainId,
      selectedFieldId: isPilotDataset ? (domain?.fieldIds[0] ?? null) : null,
      selectedCountryId: null,
      selectedInstitutionId: null,
      selectedResearchGroupId: null,
      selectedResearcherId: null,
      isFieldOverviewOpen: false,
    });
  };

  const selectField = (fieldId: string) => {
    navigateTo({
      ...navigationState,
      selectedFieldId: fieldId,
      selectedInstitutionId: null,
      selectedResearchGroupId: null,
      selectedResearcherId: null,
      isFieldOverviewOpen: false,
    });
  };

  const selectYear = (year: number) => {
    navigateTo({
      ...navigationState,
      selectedYear: year,
      selectedInstitutionId: null,
      selectedResearchGroupId: null,
      selectedResearcherId: null,
    });
  };

  const selectCountry = (countryId: string) => {
    navigateTo({
      ...navigationState,
      selectedCountryId: countryId,
      selectedInstitutionId: null,
      selectedResearchGroupId: null,
      selectedResearcherId: null,
      isFieldOverviewOpen: false,
    });
  };

  const selectInstitution = (institutionId: string) => {
    const firstGroup = dataset.researchGroups.find(
      (group) =>
        group.institutionId === institutionId &&
        (!selectedFieldId || group.fieldIds.includes(selectedFieldId)),
    );
    navigateTo({
      ...navigationState,
      selectedInstitutionId: institutionId,
      selectedResearchGroupId: firstGroup?.id ?? null,
      selectedResearcherId: null,
      isFieldOverviewOpen: false,
    });
  };

  const selectResearchGroup = (groupId: string) => {
    navigateTo({
      ...navigationState,
      selectedResearchGroupId: groupId,
      selectedResearcherId: null,
    });
  };

  const selectResearcher = (researcherId: string) => {
    navigateTo({
      ...navigationState,
      selectedResearcherId: researcherId,
    });
  };

  const returnToWorld = () => {
    navigateTo({
      ...navigationState,
      selectedCountryId: null,
      selectedInstitutionId: null,
      selectedResearchGroupId: null,
      selectedResearcherId: null,
      isFieldOverviewOpen: false,
    });
    setGlobalResetToken((token) => token + 1);
  };

  const returnToCountry = () => {
    navigateTo({
      ...navigationState,
      selectedInstitutionId: null,
      selectedResearchGroupId: null,
      selectedResearcherId: null,
    });
  };

  const returnToInstitution = () => {
    navigateTo({
      ...navigationState,
      selectedResearcherId: null,
    });
  };

  const openFieldOverview = () => {
    if (!activeField) {
      return;
    }
    navigateTo({
      ...navigationState,
      selectedCountryId: null,
      selectedInstitutionId: null,
      selectedResearchGroupId: null,
      selectedResearcherId: null,
      isFieldOverviewOpen: true,
    });
  };

  const selectMetric = (metricId: MetricId) => {
    if (
      metricId === compositeMetricId &&
      (!hasConfirmedMetricProfile || !compositeAvailable)
    ) {
      return;
    }
    setSelectedMetricId(metricId);
  };

  const applyMetricProfile = (configuration: typeof metricWeightConfiguration) => {
    if (!compositeAvailable) {
      return;
    }
    setMetricWeightConfiguration(configuration);
    setHasConfirmedMetricProfile(true);
    setSelectedMetricId(compositeMetricId);
  };

  const selectSearchResult = (result: AtlasSearchResult) => {
    if (result.entityType === 'science-domain') {
      selectDomain(result.entityId);
      return;
    }

    if (result.entityType === 'research-field') {
      const domain = dataset.scienceDomains.find((candidate) =>
        candidate.fieldIds.includes(result.entityId),
      );
      navigateTo({
        ...navigationState,
        selectedDomainId: domain?.id ?? selectedDomainId,
        selectedFieldId: result.entityId,
        selectedCountryId: null,
        selectedInstitutionId: null,
        selectedResearchGroupId: null,
        selectedResearcherId: null,
        isFieldOverviewOpen: false,
      });
      return;
    }

    if (result.entityType === 'country') {
      selectCountry(getExplorationCountryId(result.entityId, dataset));
      return;
    }

    if (result.entityType === 'institution') {
      const institution = dataset.institutions.find(
        (candidate) => candidate.id === result.entityId,
      );
      if (!institution) {
        return;
      }
      const firstGroup = dataset.researchGroups.find(
        (group) => group.institutionId === institution.id,
      );
      navigateTo({
        ...navigationState,
        selectedFieldId:
          selectedFieldId && institution.fieldIds.includes(selectedFieldId)
            ? selectedFieldId
            : null,
        selectedCountryId: getExplorationCountryId(
          institution.countryId,
          dataset,
        ),
        selectedInstitutionId: institution.id,
        selectedResearchGroupId: firstGroup?.id ?? null,
        selectedResearcherId: null,
        isFieldOverviewOpen: false,
      });
      return;
    }

    if (result.entityType === 'research-group') {
      const group = dataset.researchGroups.find(
        (candidate) => candidate.id === result.entityId,
      );
      const institution = dataset.institutions.find(
        (candidate) => candidate.id === group?.institutionId,
      );
      if (!group || !institution) {
        return;
      }
      navigateTo({
        ...navigationState,
        selectedFieldId:
          selectedFieldId && group.fieldIds.includes(selectedFieldId)
            ? selectedFieldId
            : group.fieldIds[0] ?? null,
        selectedCountryId: getExplorationCountryId(
          institution.countryId,
          dataset,
        ),
        selectedInstitutionId: institution.id,
        selectedResearchGroupId: group.id,
        selectedResearcherId: null,
        isFieldOverviewOpen: false,
      });
      return;
    }

    const researcher = dataset.researchers.find(
      (candidate) => candidate.id === result.entityId,
    );
    const affiliation = dataset.affiliations.find(
      (candidate) => candidate.researcherId === researcher?.id,
    );
    const institution = dataset.institutions.find(
      (candidate) => candidate.id === affiliation?.institutionId,
    );
    if (!researcher || !affiliation || !institution) {
      return;
    }
    navigateTo({
      ...navigationState,
      selectedFieldId:
        selectedFieldId && researcher.fieldIds.includes(selectedFieldId)
          ? selectedFieldId
          : null,
      selectedCountryId: getExplorationCountryId(
        institution.countryId,
        dataset,
      ),
      selectedInstitutionId: institution.id,
      selectedResearchGroupId: affiliation.researchGroupId ?? null,
      selectedResearcherId: researcher.id,
      isFieldOverviewOpen: false,
    });
  };

  const runGuidedAction = (action: GuidedAction) => {
    const guidedStates: Partial<Record<GuidedAction, AtlasNavigationState>> = {
      physics: {
        ...navigationState,
        selectedDomainId: 'physics',
        selectedFieldId: null,
        selectedCountryId: null,
        selectedInstitutionId: null,
        selectedResearchGroupId: null,
        selectedResearcherId: null,
        isFieldOverviewOpen: false,
      },
      'hep-th': {
        ...navigationState,
        selectedDomainId: 'physics',
        selectedFieldId: 'hep-th',
        selectedCountryId: null,
        selectedInstitutionId: null,
        selectedResearchGroupId: null,
        selectedResearcherId: null,
        isFieldOverviewOpen: false,
      },
      year: { ...navigationState, selectedYear: 2026 },
      country: {
        ...navigationState,
        selectedDomainId: 'physics',
        selectedFieldId: 'hep-th',
        selectedYear: 2026,
        selectedCountryId: 'country-us',
        selectedInstitutionId: null,
        selectedResearchGroupId: null,
        selectedResearcherId: null,
        isFieldOverviewOpen: false,
      },
      institution: {
        ...navigationState,
        selectedDomainId: 'physics',
        selectedFieldId: 'hep-th',
        selectedYear: 2026,
        selectedCountryId: 'country-us',
        selectedInstitutionId: 'institution-mit',
        selectedResearchGroupId: 'group-mit-fields',
        selectedResearcherId: null,
        isFieldOverviewOpen: false,
      },
      researcher: {
        ...navigationState,
        selectedDomainId: 'physics',
        selectedFieldId: 'hep-th',
        selectedYear: 2026,
        selectedCountryId: 'country-us',
        selectedInstitutionId: 'institution-mit',
        selectedResearchGroupId: 'group-mit-fields',
        selectedResearcherId: 'researcher-jonah-okafor',
        isFieldOverviewOpen: false,
      },
    };

    if (action === 'history') {
      document
        .querySelector('.researcher-profile .event-list')
        ?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      return;
    }

    const navigation = guidedStates[action];
    if (navigation) {
      navigateTo(navigation);
    }
  };

  return (
    <main className="atlas-shell" data-view={atlasView} ref={shellRef}>
      <WorldMap
        countries={dataset.countries}
        geographicViews={dataset.geographicViews}
        countryObservations={countryObservations}
        institutions={mapInstitutions}
        institutionObservations={institutionObservations}
        metricLabel={activeMetricLabel}
        isPilotDataset={isPilotDataset}
        selectedCountryId={selectedCountryId}
        selectedInstitutionId={selectedInstitutionId}
        globalResetToken={globalResetToken}
        onGlobalReset={returnToWorld}
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
        <span className="alpha-badge" data-pilot={isPilotDataset}>
          {isPilotDataset ? 'INSPIRE-HEP pilot' : 'Metric Engine alpha'}
        </span>
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
      <div className="atlas-utility-controls" aria-label="Atlas tools">
        <MetricWeightingPanel
          key={`${dataset.metadata.datasetKind}:${dataset.metadata.provenance.version}`}
          definitions={visualizationMetricDefinitions}
          selectedMetricId={selectedMetricId}
          configuration={metricWeightConfiguration}
          hasConfirmedProfile={hasConfirmedMetricProfile}
          compositeAvailable={compositeAvailable}
          onMetricSelect={selectMetric}
          onApply={applyMetricProfile}
        />
        <AtlasSearch onSearch={searchAtlas} onSelect={selectSearchResult} />
        {!isPilotDataset && <GuidedExploration onNavigate={runGuidedAction} />}
        <DataProvenancePanel metadata={dataset.metadata} />
      </div>

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
        <DataSourceSelector
          selectedSourceId={selectedDataSourceId}
          onSelect={selectDataSource}
        />
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
          metricLabel={activeMetricLabel}
          activeScopeLabel={
            activeField?.label ?? activeDomain?.label ?? 'Physics'
          }
          selectedYear={selectedYear}
          isPilotDataset={isPilotDataset}
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
          metricObservations={selectedInstitutionMetricObservations}
          metricLabel={activeMetricLabel}
          isPilotDataset={isPilotDataset}
          externalResources={selectedInstitutionProfile?.resources ?? []}
          identityResolutions={selectedInstitutionIdentityResolutions}
          selectedGroupId={selectedResearchGroup?.id ?? null}
          onGroupSelect={selectResearchGroup}
          onResearcherSelect={selectResearcher}
          onBackToCountry={returnToCountry}
        />
      )}

      {selectedResearcher && selectedInstitution && (
        <ResearcherProfile
          researcher={selectedResearcher}
          affiliationHistory={
            selectedResearcherProfile?.affiliationHistory.map(
              (entry) => entry.affiliation,
            ) ?? []
          }
          institution={selectedInstitution}
          institutions={dataset.institutions}
          group={selectedResearcherGroup}
          fields={dataset.fields}
          papers={dataset.papers}
          authorships={dataset.authorships}
          historicalEvents={dataset.historicalEvents}
          externalResources={selectedResearcherProfile?.resources ?? []}
          identityResolutions={selectedResearcherIdentityResolutions}
          collaborators={selectedResearcherProfile?.collaborators ?? []}
          isPilotDataset={isPilotDataset}
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
          isPilotDataset={isPilotDataset}
          onClose={() =>
            navigateTo({
              ...navigationState,
              isFieldOverviewOpen: false,
            })
          }
        />
      )}

      <section className="map-legend" aria-label="Map legend">
        <div className="legend-header">
          <span>
            {selectedCountry ? 'institutions' : 'countries'} ·{' '}
            {activeMetricLabel}
          </span>
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
          Missing data ≠ zero value
        </div>
        <p className="legend-disclaimer">
          {isPilotDataset
            ? 'Bounded INSPIRE-HEP pilot. Not a scientific ranking.'
            : 'Demo visualization only. Not a scientific ranking.'}
        </p>
      </section>

      <Timeline
        years={availableYears}
        selectedYear={selectedYear}
        isPilotDataset={isPilotDataset}
        onChange={selectYear}
      />
    </main>
  );
}
