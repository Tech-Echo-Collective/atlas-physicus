import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { atlasRepository } from '../../data/StaticAtlasRepository';
import {
  APIRepository,
  normalizeAtlasApiBaseUrl,
} from '../../data/APIRepository';
import { loadAtlasDataset } from '../../data/loadAtlasDataset';
import { getDatasetPresentation } from '../../data/DatasetPresentation';
import {
  AtlasDataSourceRequestGate,
  assessDataSourceObservations,
  buildDataSourceAwareAtlasUrl,
  getInitialSourceFallback,
  mergeMetricObservationsById,
  neutralLiveMapNotice,
  reconcileNavigationForDataSource,
  resolveAtlasDataSource,
  resolveMetricForDataSource,
  type AtlasDataSourceId,
} from '../../data/AtlasDataSources';
import {
  hydrateLiveNavigationDataset,
  shouldBootstrapLiveWorldMap,
} from '../../data/LiveNavigationHydration';
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

function mergeById<T extends { id: string }>(current: T[], incoming: T[]): T[] {
  const merged = new Map(current.map((item) => [item.id, item]));
  incoming.forEach((item) => merged.set(item.id, item));
  return [...merged.values()];
}

const liveTimelineStartYear = 1900;

export function AtlasExplorer() {
  const atlasApiUrl = normalizeAtlasApiBaseUrl(
    import.meta.env.VITE_ATLAS_API_URL,
  );
  const liveApiAvailable = atlasApiUrl !== null;
  const shellRef = useRef<HTMLElement>(null);
  const sourceRequestGateRef = useRef(new AtlasDataSourceRequestGate());
  const restoreNavigationFromUrlRef = useRef(false);
  const preserveNextSourceNoticeRef = useRef(false);
  const [dataset, setDataset] = useState<AtlasDataset | null>(null);
  const [repository, setRepository] =
    useState<AtlasRepository>(atlasRepository);
  const [selectedDataSourceId, setSelectedDataSourceId] =
    useState<AtlasDataSourceId>(() =>
      typeof window === 'undefined'
        ? 'synthetic-framework'
        : resolveAtlasDataSource(
            window.location.search,
            liveApiAvailable,
          ),
    );
  const [requestedDataSourceId, setRequestedDataSourceId] =
    useState<AtlasDataSourceId>(selectedDataSourceId);
  const [isDataSourceLoading, setIsDataSourceLoading] = useState(true);
  const [sourceError, setSourceError] = useState<string | null>(null);
  const [sourceNotice, setSourceNotice] = useState<string | null>(null);
  const [settledLiveWorldRequestKey, setSettledLiveWorldRequestKey] = useState<
    string | null
  >(null);
  const [settledLiveScopeRequestKey, setSettledLiveScopeRequestKey] = useState<
    string | null
  >(null);
  const [settledLiveInstitutionRequestKey, setSettledLiveInstitutionRequestKey] =
    useState<string | null>(null);
  const [settledLiveResearcherRequestKey, setSettledLiveResearcherRequestKey] =
    useState<string | null>(null);
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
  const navigationStateRef = useRef(navigationState);
  const datasetRef = useRef(dataset);
  const selectedMetricIdRef = useRef(selectedMetricId);
  const selectedDataSourceIdRef = useRef(selectedDataSourceId);

  useEffect(() => {
    navigationStateRef.current = navigationState;
  }, [navigationState]);

  useEffect(() => {
    datasetRef.current = dataset;
  }, [dataset]);

  useEffect(() => {
    selectedMetricIdRef.current = selectedMetricId;
  }, [selectedMetricId]);

  useEffect(() => {
    selectedDataSourceIdRef.current = selectedDataSourceId;
  }, [selectedDataSourceId]);

  const navigateTo = useCallback(
    (
      navigation: AtlasNavigationState,
      replace = false,
      targetDataset: AtlasDataset | null = dataset,
    ) => {
      applyNavigationState(navigation);
      if (!targetDataset || typeof window === 'undefined') {
        return;
      }
      const url = buildDataSourceAwareAtlasUrl(
        buildAtlasUrl(navigation, targetDataset),
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
    if (
      datasetRef.current &&
      requestedDataSourceId === selectedDataSourceIdRef.current
    ) {
      setIsDataSourceLoading(false);
      return;
    }

    const requestId = sourceRequestGateRef.current.begin();
    let nextRepository: AtlasRepository | null = null;
    setIsDataSourceLoading(true);
    setSourceError(null);

    const repositoryPromise: Promise<AtlasRepository> = (() => {
      if (requestedDataSourceId === 'inspire-hep-pilot') {
        return import('../../data/PilotAtlasRepository').then(
          ({ pilotAtlasRepository }) => pilotAtlasRepository,
        );
      }
      if (requestedDataSourceId === 'live-api') {
        if (!atlasApiUrl) {
          return Promise.reject(
            new Error('No Atlas API URL is configured for this deployment.'),
          );
        }
        return Promise.resolve(
          new APIRepository({
            baseUrl: atlasApiUrl,
            bootstrapWorldMap:
              typeof window === 'undefined' ||
              shouldBootstrapLiveWorldMap(window.location.pathname),
          }),
        );
      }
      return Promise.resolve(atlasRepository);
    })();

    repositoryPromise
      .then((candidateRepository) => {
        nextRepository = candidateRepository;
        return loadAtlasDataset(candidateRepository);
      })
      .then(async (loadedDataset) => {
        if (!sourceRequestGateRef.current.isCurrent(requestId)) {
          return;
        }

        let nextDataset = loadedDataset;

        const expectedDatasetKind = {
          'synthetic-framework': 'synthetic-demo',
          'inspire-hep-pilot': 'inspire-hep-pilot',
          'live-api': 'live-api',
        }[requestedDataSourceId];
        if (nextDataset.metadata.datasetKind !== expectedDatasetKind) {
          throw new Error(
            `The ${requestedDataSourceId} repository returned ${nextDataset.metadata.datasetKind} data.`,
          );
        }

        if (
          requestedDataSourceId === 'live-api' &&
          nextRepository instanceof APIRepository &&
          typeof window !== 'undefined'
        ) {
          nextDataset = await hydrateLiveNavigationDataset(
            nextRepository,
            nextDataset,
            window.location.pathname,
          );
          if (!sourceRequestGateRef.current.isCurrent(requestId)) {
            return;
          }
        }

        const nextMetricId = resolveMetricForDataSource(
          nextDataset,
          selectedMetricIdRef.current,
        );
        const observationAssessment = assessDataSourceObservations(
          nextDataset,
          nextMetricId,
          requestedDataSourceId,
        );
        if (!observationAssessment.canActivate) {
          throw new Error(
            'The destination source has no country observations for a renderable metric.',
          );
        }

        const previousDataset = datasetRef.current;
        const navigationFromUrl =
          typeof window !== 'undefined'
            ? resolveAtlasLocation(window.location, nextDataset)
            : navigationStateRef.current;
        const requestedNavigation =
          !previousDataset || restoreNavigationFromUrlRef.current
            ? navigationFromUrl
            : navigationStateRef.current;
        const nextNavigation = reconcileNavigationForDataSource(
          requestedNavigation,
          nextDataset,
          nextMetricId,
          {
            allowMissingMetricObservations:
              requestedDataSourceId === 'live-api',
          },
        );

        restoreNavigationFromUrlRef.current = false;
        datasetRef.current = nextDataset;
        navigationStateRef.current = nextNavigation;
        selectedMetricIdRef.current = nextMetricId;
        selectedDataSourceIdRef.current = requestedDataSourceId;
        setRepository(nextRepository as AtlasRepository);
        setDataset(nextDataset);
        setSelectedDataSourceId(requestedDataSourceId);
        setSelectedMetricId(nextMetricId);
        setMetricWeightConfiguration(defaultMetricWeightConfiguration);
        setHasConfirmedMetricProfile(false);
        applyNavigationState(nextNavigation);
        setGlobalResetToken((token) => token + 1);
        setIsDataSourceLoading(false);
        setSourceError(null);
        if (preserveNextSourceNoticeRef.current) {
          preserveNextSourceNoticeRef.current = false;
        } else {
          setSourceNotice(observationAssessment.notice);
        }

        if (typeof window !== 'undefined') {
          const canonicalUrl = buildDataSourceAwareAtlasUrl(
            buildAtlasUrl(nextNavigation, nextDataset),
            requestedDataSourceId,
          );
          if (
            canonicalUrl !==
            `${window.location.pathname}${window.location.search}`
          ) {
            window.history.replaceState(null, '', canonicalUrl);
          }
        }
      })
      .catch((loadError: unknown) => {
        if (!sourceRequestGateRef.current.isCurrent(requestId)) {
          return;
        }
        setIsDataSourceLoading(false);
        setRequestedDataSourceId(selectedDataSourceIdRef.current);
        const reason =
          loadError instanceof Error && loadError.name !== 'AbortError'
            ? ` ${loadError.message}`
            : '';
        const message = `The selected Atlas dataset could not be loaded.${reason}`;
        const fallbackSourceId = getInitialSourceFallback(
          datasetRef.current !== null,
          requestedDataSourceId,
        );
        if (fallbackSourceId) {
          setSourceNotice(`${message} Showing the synthetic framework instead.`);
          preserveNextSourceNoticeRef.current = true;
          setRequestedDataSourceId(fallbackSourceId);
          return;
        }
        setSourceError(message);
      });

    return () => {
      if (nextRepository instanceof APIRepository) {
        nextRepository.cancelPending();
      }
    };
  }, [
    applyNavigationState,
    atlasApiUrl,
    requestedDataSourceId,
  ]);

  useEffect(() => {
    if (!dataset || typeof window === 'undefined') {
      return;
    }

    const restoreLocation = () => {
      const locationSource = resolveAtlasDataSource(
        window.location.search,
        liveApiAvailable,
      );
      if (locationSource !== selectedDataSourceIdRef.current) {
        restoreNavigationFromUrlRef.current = true;
        preserveNextSourceNoticeRef.current = false;
        setSourceNotice(null);
        setRequestedDataSourceId(locationSource);
        return;
      }
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
  }, [
    applyNavigationState,
    dataset,
    liveApiAvailable,
    selectedDataSourceId,
  ]);

  const datasetVersion = dataset?.metadata.provenance.version ?? null;
  const geographicViews = dataset?.geographicViews ?? null;
  const isLiveApiRepository =
    repository instanceof APIRepository && selectedDataSourceId === 'live-api';
  const liveMapMetricIds = useMemo<MetricId[]>(
    () =>
      selectedMetricId === compositeMetricId
        ? (Object.keys(metricWeightConfiguration.weights) as MetricId[]).filter(
            (metricId) =>
              dataset?.metricDefinitions.some(
                (definition) =>
                  definition.id === metricId &&
                  definition.implementationStatus !== 'taxonomy-only',
              ),
          )
        : dataset?.metricDefinitions.some(
              (definition) =>
                definition.id === selectedMetricId &&
                definition.implementationStatus !== 'taxonomy-only',
            )
          ? [selectedMetricId]
          : [],
    [dataset?.metricDefinitions, metricWeightConfiguration.weights, selectedMetricId],
  );
  const liveWorldRequestKey =
    datasetVersion &&
    isLiveApiRepository &&
    !selectedCountryId &&
    !isFieldOverviewOpen &&
    liveMapMetricIds.length > 0
      ? [
          datasetVersion,
          'world',
          selectedDomainId,
          selectedFieldId ?? 'domain',
          liveMapMetricIds.join(','),
          selectedYear,
          selectedMetricId === compositeMetricId
            ? JSON.stringify(metricWeightConfiguration.weights)
            : 'single',
        ].join(':')
      : null;
  const liveScopeRequestKey =
    datasetVersion &&
    geographicViews &&
    isLiveApiRepository &&
    selectedCountryId &&
    liveMapMetricIds.length > 0
      ? [
          datasetVersion,
          selectedCountryId,
          selectedDomainId,
          selectedFieldId ?? 'domain',
          selectedMetricId,
          selectedYear,
          JSON.stringify(metricWeightConfiguration.weights),
        ].join(':')
      : null;
  const liveInstitutionRequestKey =
    datasetVersion && isLiveApiRepository && selectedInstitutionId
      ? `${datasetVersion}:institution:${selectedInstitutionId}`
      : null;
  const liveResearcherRequestKey =
    datasetVersion && isLiveApiRepository && selectedResearcherId
      ? `${datasetVersion}:researcher:${selectedResearcherId}`
      : null;
  const isLiveWorldLoading =
    liveWorldRequestKey !== null &&
    settledLiveWorldRequestKey !== liveWorldRequestKey;
  const isLiveCountryLoading =
    liveScopeRequestKey !== null &&
    settledLiveScopeRequestKey !== liveScopeRequestKey;
  const isLiveScopeLoading = isLiveWorldLoading || isLiveCountryLoading;
  const isLiveProfileLoading =
    (liveInstitutionRequestKey !== null &&
      settledLiveInstitutionRequestKey !== liveInstitutionRequestKey) ||
    (liveResearcherRequestKey !== null &&
      settledLiveResearcherRequestKey !== liveResearcherRequestKey);

  useEffect(() => {
    if (!liveWorldRequestKey || liveMapMetricIds.length === 0) {
      return;
    }

    let active = true;
    const liveRepository = repository as APIRepository;
    const requestTimer = window.setTimeout(() => {
      liveRepository
        .getCountryMapData({
          scienceDomainId: selectedDomainId,
          fieldId: selectedFieldId ?? undefined,
          metricIds: liveMapMetricIds,
          period: String(selectedYear),
        })
        .then((mapObservations) => {
          if (!active) return;
          const observations =
            selectedMetricId === compositeMetricId
              ? buildCompositeMetricObservations(
                  mapObservations,
                  metricWeightConfiguration,
                )
              : mapObservations;
          setDataset((current) =>
            current?.metadata.datasetKind === 'live-api'
              ? {
                  ...current,
                  metricObservations: mergeMetricObservationsById(
                    current.metricObservations,
                    observations,
                  ),
                }
              : current,
          );
          setSourceError(null);
          setSourceNotice(
            observations.length > 0 ? null : neutralLiveMapNotice,
          );
        })
        .catch((error: unknown) => {
          if (!active) return;
          setSourceError(
            `World map data could not be loaded.${
              error instanceof Error ? ` ${error.message}` : ''
            }`,
          );
        })
        .finally(() => {
          if (active) setSettledLiveWorldRequestKey(liveWorldRequestKey);
        });
    }, 140);

    return () => {
      active = false;
      window.clearTimeout(requestTimer);
    };
  }, [
    liveMapMetricIds,
    liveWorldRequestKey,
    metricWeightConfiguration,
    repository,
    selectedDomainId,
    selectedFieldId,
    selectedMetricId,
    selectedYear,
  ]);

  useEffect(() => {
    if (!liveScopeRequestKey || !geographicViews || !selectedCountryId) {
      return;
    }

    let active = true;
    const geographicView = geographicViews.find(
      (view) => view.countryId === selectedCountryId,
    );
    const locationCountryIds = geographicView?.locationCountryIds ?? [
      selectedCountryId,
    ];
    const liveRepository = repository as APIRepository;
    liveRepository
      .getInstitutionMapData(locationCountryIds, {
        scienceDomainId: selectedDomainId,
        fieldId: selectedFieldId ?? undefined,
        metricIds: liveMapMetricIds,
        period: String(selectedYear),
        limit: 50,
      })
      .then((mapData) => {
        if (!active) return;
        const observations =
          selectedMetricId === compositeMetricId
            ? buildCompositeMetricObservations(
                mapData.observations,
                metricWeightConfiguration,
              )
            : mapData.observations;
        setDataset((current) =>
          current?.metadata.datasetKind === 'live-api'
            ? {
                ...current,
                institutions: mergeById(
                  current.institutions,
                  mapData.institutions,
                ),
                metricObservations: mergeMetricObservationsById(
                  current.metricObservations,
                  observations,
                ),
              }
            : current,
        );
        setSourceError(null);
        setSourceNotice(
          observations.length > 0 ? null : neutralLiveMapNotice,
        );
      })
      .catch((error: unknown) => {
        if (!active) return;
        setSourceError(
          `Institution map data could not be loaded.${
            error instanceof Error ? ` ${error.message}` : ''
          }`,
        );
      })
      .finally(() => {
        if (active) setSettledLiveScopeRequestKey(liveScopeRequestKey);
      });

    return () => {
      active = false;
    };
  }, [
    datasetVersion,
    geographicViews,
    liveMapMetricIds,
    liveScopeRequestKey,
    metricWeightConfiguration,
    repository,
    selectedCountryId,
    selectedDataSourceId,
    selectedDomainId,
    selectedFieldId,
    selectedMetricId,
    selectedYear,
  ]);

  useEffect(() => {
    if (!liveInstitutionRequestKey || !selectedInstitutionId) {
      return;
    }

    let active = true;
    const liveRepository = repository as APIRepository;
    liveRepository
      .getInstitutionProfile(selectedInstitutionId)
      .then(async (profile) => {
        if (!profile || !active) return;
        const authorships = (
          await Promise.all(
            profile.researchers.map((researcher) =>
              repository.getAuthorships(researcher.id),
            ),
          )
        ).flat();
        if (!active) return;
        setDataset((current) =>
          current?.metadata.datasetKind === 'live-api'
            ? {
                ...current,
                institutions: mergeById(current.institutions, [
                  profile.institution,
                ]),
                researchGroups: mergeById(
                  current.researchGroups,
                  profile.researchGroups,
                ),
                affiliations: mergeById(
                  current.affiliations,
                  profile.affiliations,
                ),
                researchers: mergeById(
                  current.researchers,
                  profile.researchers,
                ),
                papers: mergeById(current.papers, profile.papers),
                authorships: mergeById(current.authorships, authorships),
                externalResources: mergeById(
                  current.externalResources ?? [],
                  profile.resources,
                ),
                metricObservations: mergeById(
                  current.metricObservations,
                  profile.metrics,
                ),
              }
            : current,
        );
      })
      .catch((error: unknown) => {
        if (!active) return;
        setSourceError(
          `Institution profile data could not be loaded.${
            error instanceof Error ? ` ${error.message}` : ''
          }`,
        );
      })
      .finally(() => {
        if (active) {
          setSettledLiveInstitutionRequestKey(liveInstitutionRequestKey);
        }
      });

    return () => {
      active = false;
    };
  }, [
    datasetVersion,
    liveInstitutionRequestKey,
    repository,
    selectedDataSourceId,
    selectedInstitutionId,
  ]);

  useEffect(() => {
    if (!liveResearcherRequestKey || !selectedResearcherId) {
      return;
    }

    let active = true;
    const liveRepository = repository as APIRepository;
    Promise.all([
      liveRepository.getResearcherProfile(selectedResearcherId),
      liveRepository.getAuthorships(selectedResearcherId),
    ])
      .then(([profile, authorships]) => {
        if (!profile || !active) return;
        const affiliations = profile.affiliationHistory.map(
          (entry) => entry.affiliation,
        );
        const institutions = profile.affiliationHistory.map(
          (entry) => entry.institution,
        );
        const groups = profile.affiliationHistory.flatMap((entry) =>
          entry.researchGroup ? [entry.researchGroup] : [],
        );
        setDataset((current) =>
          current?.metadata.datasetKind === 'live-api'
            ? {
                ...current,
                institutions: mergeById(current.institutions, institutions),
                researchGroups: mergeById(current.researchGroups, groups),
                affiliations: mergeById(current.affiliations, affiliations),
                researchers: mergeById(current.researchers, [
                  profile.researcher,
                  ...profile.collaborators,
                ]),
                papers: mergeById(current.papers, profile.papers),
                authorships: mergeById(current.authorships, authorships),
                externalResources: mergeById(
                  current.externalResources ?? [],
                  profile.resources,
                ),
                metricObservations: mergeById(
                  current.metricObservations,
                  profile.metrics,
                ),
              }
            : current,
        );
      })
      .catch((error: unknown) => {
        if (!active) return;
        setSourceError(
          `Researcher profile data could not be loaded.${
            error instanceof Error ? ` ${error.message}` : ''
          }`,
        );
      })
      .finally(() => {
        if (active) {
          setSettledLiveResearcherRequestKey(liveResearcherRequestKey);
        }
      });

    return () => {
      active = false;
    };
  }, [
    datasetVersion,
    liveResearcherRequestKey,
    repository,
    selectedDataSourceId,
    selectedResearcherId,
  ]);

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
              observation.entityType === 'country' &&
              (selectedFieldId
                ? observation.fieldId === selectedFieldId
                : observation.scienceDomainId === selectedDomainId &&
                  observation.fieldId === undefined),
          )
          .map((observation) => Number(observation.period)),
      ),
    ).sort((left, right) => left - right);
  }, [
    dataset,
    selectedDomainId,
    selectedFieldId,
    visualizationObservations,
  ]);
  const timelineYears = useMemo(() => {
    if (dataset?.metadata.datasetKind !== 'live-api') {
      return availableYears;
    }
    const currentDatasetYear = Number(dataset.metadata.period);
    return [liveTimelineStartYear, currentDatasetYear, selectedYear].filter(
      Number.isFinite,
    );
  }, [availableYears, dataset, selectedYear]);

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

  if (!dataset) {
    return (
      <main className="state-screen" role="status">
        {sourceError ?? 'Loading the atlas…'}
      </main>
    );
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
  const datasetPresentation = getDatasetPresentation(
    dataset.metadata.datasetKind,
  );
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
    if (sourceId === requestedDataSourceId) {
      return;
    }
    setSourceError(null);
    setSourceNotice(null);
    preserveNextSourceNoticeRef.current = false;
    setRequestedDataSourceId(sourceId);
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

  const selectSearchResult = async (result: AtlasSearchResult) => {
    let searchDataset = dataset;
    if (repository instanceof APIRepository) {
      try {
        if (
          result.entityType === 'institution' &&
          !searchDataset.institutions.some(
            (institution) => institution.id === result.entityId,
          )
        ) {
          const institution = await repository.getInstitution(result.entityId);
          if (!institution) {
            throw new Error('The institution is no longer available.');
          }
          searchDataset = {
            ...searchDataset,
            institutions: mergeById(searchDataset.institutions, [institution]),
          };
        } else if (
          result.entityType === 'research-group' &&
          !searchDataset.researchGroups.some(
            (group) => group.id === result.entityId,
          )
        ) {
          const profile = await repository.getResearchGroupProfile(
            result.entityId,
          );
          if (!profile) {
            throw new Error('The research group is no longer available.');
          }
          searchDataset = {
            ...searchDataset,
            institutions: mergeById(searchDataset.institutions, [
              profile.institution,
            ]),
            researchGroups: mergeById(searchDataset.researchGroups, [
              profile.researchGroup,
            ]),
            affiliations: mergeById(
              searchDataset.affiliations,
              profile.affiliations,
            ),
            researchers: mergeById(
              searchDataset.researchers,
              profile.members,
            ),
            papers: mergeById(searchDataset.papers, profile.papers),
            externalResources: mergeById(
              searchDataset.externalResources ?? [],
              profile.resources,
            ),
          };
        } else if (
          result.entityType === 'researcher' &&
          !searchDataset.researchers.some(
            (researcher) => researcher.id === result.entityId,
          )
        ) {
          const profile = await repository.getResearcherProfile(
            result.entityId,
          );
          if (!profile) {
            throw new Error('The researcher is no longer available.');
          }
          searchDataset = {
            ...searchDataset,
            institutions: mergeById(
              searchDataset.institutions,
              profile.affiliationHistory.map((entry) => entry.institution),
            ),
            researchGroups: mergeById(
              searchDataset.researchGroups,
              profile.affiliationHistory.flatMap((entry) =>
                entry.researchGroup ? [entry.researchGroup] : [],
              ),
            ),
            affiliations: mergeById(
              searchDataset.affiliations,
              profile.affiliationHistory.map((entry) => entry.affiliation),
            ),
            researchers: mergeById(searchDataset.researchers, [
              profile.researcher,
              ...profile.collaborators,
            ]),
            papers: mergeById(searchDataset.papers, profile.papers),
            externalResources: mergeById(
              searchDataset.externalResources ?? [],
              profile.resources,
            ),
            metricObservations: mergeById(
              searchDataset.metricObservations,
              profile.metrics,
            ),
          };
        }
        if (searchDataset !== dataset) {
          datasetRef.current = searchDataset;
          setDataset(searchDataset);
        }
        setSourceError(null);
      } catch (error: unknown) {
        setSourceError(
          `The selected search result could not be loaded.${
            error instanceof Error ? ` ${error.message}` : ''
          }`,
        );
        return;
      }
    }

    if (result.entityType === 'science-domain') {
      selectDomain(result.entityId);
      return;
    }

    if (result.entityType === 'research-field') {
      const domain = searchDataset.scienceDomains.find((candidate) =>
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
      selectCountry(getExplorationCountryId(result.entityId, searchDataset));
      return;
    }

    if (result.entityType === 'institution') {
      const institution = searchDataset.institutions.find(
        (candidate) => candidate.id === result.entityId,
      );
      if (!institution) {
        return;
      }
      const firstGroup = searchDataset.researchGroups.find(
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
          searchDataset,
        ),
        selectedInstitutionId: institution.id,
        selectedResearchGroupId: firstGroup?.id ?? null,
        selectedResearcherId: null,
        isFieldOverviewOpen: false,
      }, false, searchDataset);
      return;
    }

    if (result.entityType === 'research-group') {
      const group = searchDataset.researchGroups.find(
        (candidate) => candidate.id === result.entityId,
      );
      const institution = searchDataset.institutions.find(
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
          searchDataset,
        ),
        selectedInstitutionId: institution.id,
        selectedResearchGroupId: group.id,
        selectedResearcherId: null,
        isFieldOverviewOpen: false,
      }, false, searchDataset);
      return;
    }

    if (result.entityType === 'paper') {
      let paper = searchDataset.papers.find(
        (candidate) => candidate.id === result.entityId,
      );
      let paperAuthorships = searchDataset.authorships.filter(
        (authorship) => authorship.paperId === result.entityId,
      );
      if (repository instanceof APIRepository) {
        try {
          const [loadedPaper, loadedAuthorships] = await Promise.all([
            paper ? Promise.resolve(paper) : repository.getPaper(result.entityId),
            paperAuthorships.length
              ? Promise.resolve(paperAuthorships)
              : repository.getAuthorships(undefined, result.entityId),
          ]);
          if (!loadedPaper) {
            throw new Error('The paper is no longer available.');
          }
          paper = loadedPaper;
          paperAuthorships = loadedAuthorships;
          const authorProfiles = (
            await Promise.all(
              paperAuthorships
                .slice(0, 10)
                .map((authorship) =>
                  repository.getResearcherProfile(authorship.researcherId),
                ),
            )
          ).flatMap((profile) => (profile ? [profile] : []));
          searchDataset = {
            ...searchDataset,
            papers: mergeById(searchDataset.papers, [paper]),
            authorships: mergeById(
              searchDataset.authorships,
              paperAuthorships,
            ),
            institutions: mergeById(
              searchDataset.institutions,
              authorProfiles.flatMap((profile) =>
                profile.affiliationHistory.map((entry) => entry.institution),
              ),
            ),
            researchGroups: mergeById(
              searchDataset.researchGroups,
              authorProfiles.flatMap((profile) =>
                profile.affiliationHistory.flatMap((entry) =>
                  entry.researchGroup ? [entry.researchGroup] : [],
                ),
              ),
            ),
            affiliations: mergeById(
              searchDataset.affiliations,
              authorProfiles.flatMap((profile) =>
                profile.affiliationHistory.map((entry) => entry.affiliation),
              ),
            ),
            researchers: mergeById(
              searchDataset.researchers,
              authorProfiles.flatMap((profile) => [
                profile.researcher,
                ...profile.collaborators,
              ]),
            ),
            externalResources: mergeById(
              searchDataset.externalResources ?? [],
              authorProfiles.flatMap((profile) => profile.resources),
            ),
            metricObservations: mergeById(
              searchDataset.metricObservations,
              authorProfiles.flatMap((profile) => profile.metrics),
            ),
          };
        } catch (error: unknown) {
          setSourceError(
            `The selected paper could not be loaded.${
              error instanceof Error ? ` ${error.message}` : ''
            }`,
          );
          return;
        }
      }

      datasetRef.current = searchDataset;
      setDataset(searchDataset);
      const authorContext = paperAuthorships
        .sort((left, right) => left.authorPosition - right.authorPosition)
        .map((authorship) => {
          const researcher = searchDataset.researchers.find(
            (candidate) => candidate.id === authorship.researcherId,
          );
          const affiliation = searchDataset.affiliations.find(
            (candidate) => candidate.researcherId === researcher?.id,
          );
          const institution = searchDataset.institutions.find(
            (candidate) => candidate.id === affiliation?.institutionId,
          );
          return researcher && affiliation && institution
            ? { researcher, affiliation, institution }
            : null;
        })
        .find((context) => context !== null);
      if (!paper || !authorContext) {
        setSourceNotice(
          'The canonical paper was found, but this dataset has no resolved affiliation path for opening it in the Atlas hierarchy.',
        );
        return;
      }
      setSourceNotice(
        `Opened the first resolved author context for “${paper.title}”.`,
      );
      navigateTo({
        ...navigationState,
        selectedFieldId:
          selectedFieldId && paper.fieldIds.includes(selectedFieldId)
            ? selectedFieldId
            : paper.fieldIds[0] ?? null,
        selectedCountryId: getExplorationCountryId(
          authorContext.institution.countryId,
          searchDataset,
        ),
        selectedInstitutionId: authorContext.institution.id,
        selectedResearchGroupId:
          authorContext.affiliation.researchGroupId ?? null,
        selectedResearcherId: authorContext.researcher.id,
        isFieldOverviewOpen: false,
      }, false, searchDataset);
      return;
    }

    const researcher = searchDataset.researchers.find(
      (candidate) => candidate.id === result.entityId,
    );
    const affiliation = searchDataset.affiliations.find(
      (candidate) => candidate.researcherId === researcher?.id,
    );
    const institution = searchDataset.institutions.find(
      (candidate) => candidate.id === affiliation?.institutionId,
    );
    if (!researcher || !affiliation || !institution) {
      setSourceError(
        'The canonical researcher has no resolvable affiliation context in this dataset.',
      );
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
        searchDataset,
      ),
      selectedInstitutionId: institution.id,
      selectedResearchGroupId: affiliation.researchGroupId ?? null,
      selectedResearcherId: researcher.id,
      isFieldOverviewOpen: false,
    }, false, searchDataset);
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
        datasetKind={dataset.metadata.datasetKind}
        selectedCountryId={selectedCountryId}
        selectedInstitutionId={selectedInstitutionId}
        globalResetToken={globalResetToken}
        onGlobalReset={returnToWorld}
        onCountrySelect={selectCountry}
        onInstitutionSelect={selectInstitution}
      />

      {(isLiveScopeLoading || isLiveProfileLoading) && (
        <div className="live-data-loading" role="status">
          {isLiveProfileLoading
            ? 'Loading scoped entity profile…'
            : isLiveWorldLoading
              ? 'Loading country map observations…'
              : 'Loading institution map nodes…'}
        </div>
      )}

      <header className="atlas-header">
        <div className="brand-mark" aria-hidden="true">
          <span />
        </div>
        <div>
          <p>Tech Echo Collective</p>
          <h1>Physics Atlas</h1>
        </div>
        <span
          className="alpha-badge"
          data-source={dataset.metadata.datasetKind}
        >
          {datasetPresentation.badgeLabel}
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
          datasetKind={dataset.metadata.datasetKind}
          onMetricSelect={selectMetric}
          onApply={applyMetricProfile}
        />
        <AtlasSearch onSearch={searchAtlas} onSelect={selectSearchResult} />
        {datasetPresentation.isSynthetic && (
          <GuidedExploration onNavigate={runGuidedAction} />
        )}
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
          liveApiAvailable={liveApiAvailable}
          isLoading={isDataSourceLoading}
          loadingSourceId={requestedDataSourceId}
          error={sourceError}
          notice={sourceNotice}
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
          datasetKind={dataset.metadata.datasetKind}
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
          datasetKind={dataset.metadata.datasetKind}
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
          datasetKind={dataset.metadata.datasetKind}
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
          datasetKind={dataset.metadata.datasetKind}
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
          {datasetPresentation.disclaimer}
        </p>
      </section>

      <Timeline
        years={timelineYears}
        observedYears={availableYears}
        selectedYear={selectedYear}
        datasetKind={dataset.metadata.datasetKind}
        onChange={selectYear}
      />
    </main>
  );
}
