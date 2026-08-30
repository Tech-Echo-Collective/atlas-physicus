import { defaultMetricId, type AtlasDataset, type MetricId } from '../domain/models';
import { getVisualizationReadyMetricDefinitions } from '../metrics/MetricRegistry';
import type { AtlasNavigationState } from '../navigation/AtlasNavigation';

export type AtlasDataSourceId =
  | 'synthetic-framework'
  | 'inspire-hep-pilot'
  | 'live-api';

export interface AtlasDataSourceOption {
  id: AtlasDataSourceId;
  label: string;
  description: string;
  requiresApi?: boolean;
}

export interface AtlasDataSourceObservationAssessment {
  canActivate: boolean;
  hasRenderableObservations: boolean;
  notice: string | null;
}

export interface AtlasNavigationReconciliationOptions {
  allowMissingMetricObservations?: boolean;
}

export const neutralLiveMapNotice =
  'Live scientific metadata is available, but this instance has no reviewed metric observations for the map. The map remains neutral; missing data is not zero.';

export const atlasDataSourceOptions: AtlasDataSourceOption[] = [
  {
    id: 'synthetic-framework',
    label: 'Synthetic framework',
    description: 'Broad UI demonstration data',
  },
  {
    id: 'inspire-hep-pilot',
    label: 'INSPIRE-HEP pilot',
    description: 'Bounded real-data hep-th study',
  },
  {
    id: 'live-api',
    label: 'Live API',
    description: 'Continuously refreshed scientific metadata',
    requiresApi: true,
  },
];

export function resolveAtlasDataSource(
  search: string,
  liveApiAvailable = false,
): AtlasDataSourceId {
  const requestedSource = new URLSearchParams(search).get('source');
  if (requestedSource === 'inspire-hep-pilot') {
    return requestedSource;
  }
  if (requestedSource === 'live-api' && liveApiAvailable) {
    return requestedSource;
  }
  return 'synthetic-framework';
}

export function buildDataSourceAwareAtlasUrl(
  atlasUrl: string,
  sourceId: AtlasDataSourceId,
): string {
  const [pathname, query = ''] = atlasUrl.split('?');
  const parameters = new URLSearchParams(query);
  if (sourceId !== 'synthetic-framework') {
    parameters.set('source', sourceId);
  } else {
    parameters.delete('source');
  }
  const serialized = parameters.toString();
  return serialized ? `${pathname}?${serialized}` : pathname;
}

export function resolveMetricForDataSource(
  dataset: AtlasDataset,
  requestedMetricId: MetricId,
): MetricId {
  const implementedMetricIds = new Set(
    getVisualizationReadyMetricDefinitions(dataset.metricDefinitions).map(
      (definition) => definition.id,
    ),
  );
  if (implementedMetricIds.has(requestedMetricId)) {
    return requestedMetricId;
  }
  if (implementedMetricIds.has(defaultMetricId)) {
    return defaultMetricId;
  }
  return implementedMetricIds.values().next().value ?? defaultMetricId;
}

export function hasRenderableCountryObservations(
  dataset: AtlasDataset,
  metricId: MetricId,
): boolean {
  const definitionIsReady = getVisualizationReadyMetricDefinitions(
    dataset.metricDefinitions,
  ).some((definition) => definition.id === metricId);
  if (!definitionIsReady) {
    return false;
  }
  return dataset.metricObservations.some(
    (observation) =>
      observation.entityType === 'country' &&
      observation.metricId === metricId &&
      Number.isFinite(observation.value),
  );
}

/**
 * Static and pilot sources are visualization datasets and must contain a
 * renderable country layer. A live repository may legitimately expose
 * canonical metadata before a reviewed metric method has produced values; in
 * that case the source remains explorable with an explicitly neutral map.
 */
export function assessDataSourceObservations(
  dataset: AtlasDataset,
  metricId: MetricId,
  sourceId: AtlasDataSourceId,
): AtlasDataSourceObservationAssessment {
  const hasRenderableObservations = hasRenderableCountryObservations(
    dataset,
    metricId,
  );
  if (hasRenderableObservations) {
    return {
      canActivate: true,
      hasRenderableObservations: true,
      notice: null,
    };
  }

  return sourceId === 'live-api'
    ? {
        canActivate: true,
        hasRenderableObservations: false,
        notice: neutralLiveMapNotice,
      }
    : {
        canActivate: false,
        hasRenderableObservations: false,
        notice: null,
      };
}

/** Merge scoped live observations without discarding profile history. */
export function mergeMetricObservationsById(
  current: AtlasDataset['metricObservations'],
  incoming: AtlasDataset['metricObservations'],
): AtlasDataset['metricObservations'] {
  const merged = new Map(current.map((observation) => [observation.id, observation]));
  incoming.forEach((observation) => merged.set(observation.id, observation));
  return [...merged.values()].sort((left, right) => left.id.localeCompare(right.id));
}

function closestAvailableYear(requestedYear: number, availableYears: number[]) {
  return [...availableYears].sort(
    (left, right) =>
      Math.abs(left - requestedYear) - Math.abs(right - requestedYear) ||
      right - left,
  )[0];
}

function geographicCountryId(
  locationCountryId: string,
  dataset: AtlasDataset,
): string {
  return (
    dataset.geographicViews.find((view) =>
      view.locationCountryIds.includes(locationCountryId),
    )?.countryId ?? locationCountryId
  );
}

function observationMatchesScope(
  observation: AtlasDataset['metricObservations'][number],
  domainId: string,
  fieldId: string | null,
  metricId: MetricId,
): boolean {
  return (
    observation.metricId === metricId &&
    (fieldId
      ? observation.fieldId === fieldId
      : observation.scienceDomainId === domainId &&
        observation.fieldId === undefined)
  );
}

/**
 * Preserves only navigation that can be represented by the destination
 * dataset. The function never combines records from two sources; it validates
 * the previous selection solely against the newly loaded snapshot.
 */
export function reconcileNavigationForDataSource(
  previous: AtlasNavigationState,
  dataset: AtlasDataset,
  metricId: MetricId,
  options: AtlasNavigationReconciliationOptions = {},
): AtlasNavigationState {
  const domain =
    dataset.scienceDomains.find(
      (candidate) => candidate.id === previous.selectedDomainId,
    ) ?? dataset.scienceDomains[0];
  const domainId = domain?.id ?? 'physics';
  const compatibleFieldIds = new Set(domain?.fieldIds ?? []);
  let fieldId =
    previous.selectedFieldId &&
    compatibleFieldIds.has(previous.selectedFieldId) &&
    dataset.fields.some((field) => field.id === previous.selectedFieldId)
      ? previous.selectedFieldId
      : null;

  const scopedObservations = (candidateFieldId: string | null) =>
    dataset.metricObservations.filter((observation) =>
      observationMatchesScope(
        observation,
        domainId,
        candidateFieldId,
        metricId,
      ),
    );
  const scopedCountryObservations = (candidateFieldId: string | null) =>
    scopedObservations(candidateFieldId).filter(
      (observation) => observation.entityType === 'country',
    );

  if (
    !options.allowMissingMetricObservations &&
    fieldId &&
    scopedCountryObservations(fieldId).length === 0
  ) {
    fieldId = null;
  }
  if (
    !options.allowMissingMetricObservations &&
    !fieldId &&
    scopedCountryObservations(null).length === 0
  ) {
    fieldId =
      domain?.fieldIds.find(
        (candidateFieldId) =>
          scopedCountryObservations(candidateFieldId).length > 0,
      ) ?? null;
  }

  const observations = scopedObservations(fieldId);
  const availableYears = Array.from(
    new Set(
      observations
        .filter((observation) => observation.entityType === 'country')
        .map((observation) => Number(observation.period))
        .filter(Number.isFinite),
    ),
  ).sort((left, right) => left - right);
  const minimumYear = availableYears[0];
  const maximumYear = availableYears.at(-1);
  const requestedYearIsInRange =
    Number.isInteger(previous.selectedYear) &&
    minimumYear !== undefined &&
    maximumYear !== undefined &&
    previous.selectedYear >= minimumYear &&
    previous.selectedYear <= maximumYear;
  const selectedYear =
    options.allowMissingMetricObservations &&
    Number.isInteger(previous.selectedYear)
      ? previous.selectedYear
      : requestedYearIsInRange
        ? previous.selectedYear
        : (closestAvailableYear(previous.selectedYear, availableYears) ??
          Number(dataset.metadata.period));
  const period = String(selectedYear);

  const requestedCountryId = previous.selectedCountryId
    ? geographicCountryId(previous.selectedCountryId, dataset)
    : null;
  const countryExists = Boolean(
    requestedCountryId &&
      (dataset.countries.some((country) => country.id === requestedCountryId) ||
        dataset.geographicViews.some(
          (view) => view.countryId === requestedCountryId,
        )),
  );
  const countryHasObservation = observations.some(
    (observation) =>
      observation.entityType === 'country' &&
      observation.entityId === requestedCountryId &&
      observation.period === period,
  );
  const selectedCountryId =
    countryExists &&
    (countryHasObservation || options.allowMissingMetricObservations)
      ? requestedCountryId
      : null;

  const institution = selectedCountryId
    ? dataset.institutions.find(
        (candidate) => candidate.id === previous.selectedInstitutionId,
      )
    : undefined;
  const institutionMatchesCountry = Boolean(
    institution &&
      geographicCountryId(institution.countryId, dataset) === selectedCountryId,
  );
  const institutionHasObservation = observations.some(
    (observation) =>
      observation.entityType === 'institution' &&
      observation.entityId === institution?.id &&
      observation.period === period,
  );
  const selectedInstitutionId =
    institutionMatchesCountry &&
    (institutionHasObservation || options.allowMissingMetricObservations)
      ? (institution?.id ?? null)
      : null;

  const selectedGroup = selectedInstitutionId
    ? dataset.researchGroups.find(
        (group) =>
          group.id === previous.selectedResearchGroupId &&
          group.institutionId === selectedInstitutionId,
      )
    : undefined;
  const selectedResearchGroupId = selectedGroup?.id ?? null;
  const selectedResearcher = selectedInstitutionId
    ? dataset.researchers.find(
        (researcher) => researcher.id === previous.selectedResearcherId,
      )
    : undefined;
  const researcherHasAffiliation = Boolean(
    selectedResearcher &&
      dataset.affiliations.some(
        (affiliation) =>
          affiliation.researcherId === selectedResearcher.id &&
          affiliation.institutionId === selectedInstitutionId &&
          (!selectedResearchGroupId ||
            affiliation.researchGroupId === selectedResearchGroupId),
      ),
  );

  if (previous.isFieldOverviewOpen && fieldId) {
    return {
      selectedDomainId: domainId,
      selectedFieldId: fieldId,
      selectedYear,
      selectedCountryId: null,
      selectedInstitutionId: null,
      selectedResearchGroupId: null,
      selectedResearcherId: null,
      isFieldOverviewOpen: true,
    };
  }

  return {
    selectedDomainId: domainId,
    selectedFieldId: fieldId,
    selectedYear,
    selectedCountryId,
    selectedInstitutionId,
    selectedResearchGroupId,
    selectedResearcherId: researcherHasAffiliation
      ? (selectedResearcher?.id ?? null)
      : null,
    isFieldOverviewOpen: false,
  };
}

/** Monotonic request ownership prevents a slower source load winning a race. */
export class AtlasDataSourceRequestGate {
  private latestRequestId = 0;

  begin(): number {
    this.latestRequestId += 1;
    return this.latestRequestId;
  }

  isCurrent(requestId: number): boolean {
    return requestId === this.latestRequestId;
  }

  invalidate(): void {
    this.latestRequestId += 1;
  }
}

export function getInitialSourceFallback(
  hasUsableDataset: boolean,
  failedSourceId: AtlasDataSourceId,
): AtlasDataSourceId | null {
  return !hasUsableDataset && failedSourceId !== 'synthetic-framework'
    ? 'synthetic-framework'
    : null;
}
