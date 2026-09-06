import type { AtlasDataset } from '../domain/models';

export interface AtlasNavigationState {
  selectedDomainId: string;
  selectedFieldId: string | null;
  selectedYear: number;
  selectedCountryId: string | null;
  selectedInstitutionId: string | null;
  selectedResearchGroupId: string | null;
  selectedResearcherId: string | null;
  isFieldOverviewOpen: boolean;
}

interface LocationLike {
  pathname: string;
  search: string;
}

export function slugifyAtlasLabel(value: string): string {
  return value
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLocaleLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '');
}

function entitySlug(id: string, prefix: string, label: string): string {
  const idSlug = id.startsWith(prefix) ? id.slice(prefix.length) : id;
  return idSlug || slugifyAtlasLabel(label);
}

function matchesEntitySlug(
  slug: string,
  id: string,
  prefix: string,
  label: string,
): boolean {
  return (
    slug === id ||
    slug === entitySlug(id, prefix, label) ||
    slug === slugifyAtlasLabel(label)
  );
}

export function getExplorationCountryId(
  locationCountryId: string,
  dataset: AtlasDataset,
): string {
  return (
    dataset.geographicViews.find((view) =>
      view.locationCountryIds.includes(locationCountryId),
    )?.countryId ?? locationCountryId
  );
}

export function createDefaultAtlasNavigation(
  dataset: AtlasDataset,
): AtlasNavigationState {
  const domain = dataset.scienceDomains[0];
  const defaultFieldId = dataset.metadata.deliveryMode === 'versioned-dataset' &&
    dataset.metadata.defaultFieldId === dataset.metadata.datasetScope?.rootFieldId &&
    domain?.fieldIds.includes(dataset.metadata.defaultFieldId ?? '')
    ? dataset.metadata.defaultFieldId ?? null
    : null;
  return {
    selectedDomainId: domain?.id ?? 'physics',
    selectedFieldId: defaultFieldId,
    selectedYear: Number(dataset.metadata.period),
    selectedCountryId: null,
    selectedInstitutionId: null,
    selectedResearchGroupId: null,
    selectedResearcherId: null,
    isFieldOverviewOpen: false,
  };
}

export function resolveAtlasLocation(
  location: LocationLike,
  dataset: AtlasDataset,
): AtlasNavigationState {
  const defaultState = createDefaultAtlasNavigation(dataset);
  const segments = location.pathname
    .split('/')
    .filter(Boolean)
    .map((segment) => decodeURIComponent(segment).toLocaleLowerCase());
  const parameters = new URLSearchParams(location.search);
  const availableYears = dataset.metricObservations
    .filter((observation) => observation.entityType === 'country')
    .map((observation) => Number(observation.period))
    .filter(Number.isFinite);
  const minimumYear = Math.min(...availableYears);
  const maximumYear = Math.max(...availableYears);
  const requestedYearParameter = parameters.get('year');
  const requestedYear =
    requestedYearParameter === null || requestedYearParameter.trim() === ''
      ? Number.NaN
      : Number(requestedYearParameter);
  const selectedYear =
    Number.isInteger(requestedYear) &&
    (dataset.metadata.datasetKind === 'live-api' ||
      availableYears.length === 0 ||
      (requestedYear >= minimumYear && requestedYear <= maximumYear))
    ? requestedYear
    : defaultState.selectedYear;
  const requestedDomainId = parameters.get('domain');
  const selectedDomain =
    dataset.scienceDomains.find(
      (domain) => domain.id === requestedDomainId,
    ) ?? dataset.scienceDomains[0];
  const requestedFieldId = parameters.get('field');
  const selectedFieldId =
    requestedFieldId && selectedDomain?.fieldIds.includes(requestedFieldId)
      ? requestedFieldId
      : parameters.has('field') || parameters.has('domain')
        ? null
        : defaultState.selectedFieldId;
  const baseState: AtlasNavigationState = {
    ...defaultState,
    selectedDomainId: selectedDomain?.id ?? defaultState.selectedDomainId,
    selectedFieldId,
    selectedYear,
  };

  if (segments[0] !== 'atlas') {
    return baseState;
  }

  if (
    segments[1] &&
    !['country', 'institution', 'researcher'].includes(segments[1])
  ) {
    const routeDomain = dataset.scienceDomains.find(
      (domain) => domain.id === segments[1],
    );
    if (!routeDomain) {
      return baseState;
    }
    const routeField = segments[2];
    return {
      ...baseState,
      selectedDomainId: routeDomain.id,
      selectedFieldId:
        routeField && routeDomain.fieldIds.includes(routeField)
          ? routeField
          : null,
      isFieldOverviewOpen:
        parameters.get('view') === 'field' && Boolean(routeField),
    };
  }

  const entitySlugValue = segments[2];
  if (!entitySlugValue) {
    return baseState;
  }

  if (segments[1] === 'country') {
    const locationCountry = dataset.countries.find((country) =>
      matchesEntitySlug(
        entitySlugValue,
        country.id,
        'country-',
        country.name,
      ),
    );
    return locationCountry
      ? {
          ...baseState,
          selectedCountryId: getExplorationCountryId(
            locationCountry.id,
            dataset,
          ),
        }
      : baseState;
  }

  const requestedGroupId = parameters.get('group');

  if (segments[1] === 'institution') {
    const institution = dataset.institutions.find((candidate) =>
      matchesEntitySlug(
        entitySlugValue,
        candidate.id,
        'institution-',
        candidate.name,
      ),
    );
    if (!institution) {
      return baseState;
    }
    const groups = dataset.researchGroups.filter(
      (group) => group.institutionId === institution.id,
    );
    const selectedGroup =
      groups.find((group) => group.id === requestedGroupId) ?? groups[0] ?? null;
    return {
      ...baseState,
      selectedFieldId:
        baseState.selectedFieldId &&
        institution.fieldIds.includes(baseState.selectedFieldId)
          ? baseState.selectedFieldId
          : null,
      selectedCountryId: getExplorationCountryId(
        institution.countryId,
        dataset,
      ),
      selectedInstitutionId: institution.id,
      selectedResearchGroupId: selectedGroup?.id ?? null,
    };
  }

  if (segments[1] === 'researcher') {
    const researcher = dataset.researchers.find((candidate) =>
      matchesEntitySlug(
        entitySlugValue,
        candidate.id,
        'researcher-',
        candidate.name,
      ),
    );
    if (!researcher) {
      return baseState;
    }
    const affiliations = dataset.affiliations.filter(
      (affiliation) => affiliation.researcherId === researcher.id,
    );
    const affiliation =
      affiliations.find(
        (candidate) => candidate.researchGroupId === requestedGroupId,
      ) ?? affiliations[0];
    const institution = affiliation
      ? dataset.institutions.find(
          (candidate) => candidate.id === affiliation.institutionId,
        )
      : null;
    if (!affiliation || !institution) {
      return baseState;
    }
    return {
      ...baseState,
      selectedFieldId:
        baseState.selectedFieldId &&
        researcher.fieldIds.includes(baseState.selectedFieldId)
          ? baseState.selectedFieldId
          : null,
      selectedCountryId: getExplorationCountryId(
        institution.countryId,
        dataset,
      ),
      selectedInstitutionId: institution.id,
      selectedResearchGroupId: affiliation.researchGroupId ?? null,
      selectedResearcherId: researcher.id,
    };
  }

  return baseState;
}

export function buildAtlasUrl(
  state: AtlasNavigationState,
  dataset: AtlasDataset,
): string {
  const domain =
    dataset.scienceDomains.find(
      (candidate) => candidate.id === state.selectedDomainId,
    ) ?? dataset.scienceDomains[0];
  const parameters = new URLSearchParams();
  parameters.set('year', String(state.selectedYear));

  let pathname = `/atlas/${domain?.id ?? 'physics'}`;

  if (state.selectedResearcherId) {
    const researcher = dataset.researchers.find(
      (candidate) => candidate.id === state.selectedResearcherId,
    );
    if (researcher) {
      pathname = `/atlas/researcher/${entitySlug(
        researcher.id,
        'researcher-',
        researcher.name,
      )}`;
    }
  } else if (state.selectedInstitutionId) {
    const institution = dataset.institutions.find(
      (candidate) => candidate.id === state.selectedInstitutionId,
    );
    if (institution) {
      pathname = `/atlas/institution/${entitySlug(
        institution.id,
        'institution-',
        institution.name,
      )}`;
    }
  } else if (state.selectedCountryId) {
    const country = dataset.countries.find(
      (candidate) => candidate.id === state.selectedCountryId,
    );
    if (country) {
      pathname = `/atlas/country/${slugifyAtlasLabel(country.name)}`;
    }
  } else if (state.selectedFieldId) {
    pathname += `/${state.selectedFieldId}`;
  }

  const isEntityRoute = Boolean(
    state.selectedCountryId ||
      state.selectedInstitutionId ||
      state.selectedResearcherId,
  );
  if (isEntityRoute) {
    parameters.set('domain', state.selectedDomainId);
    if (state.selectedFieldId) {
      parameters.set('field', state.selectedFieldId);
    }
  }
  if (state.selectedResearchGroupId) {
    parameters.set('group', state.selectedResearchGroupId);
  }
  if (state.isFieldOverviewOpen) {
    parameters.set('view', 'field');
  }

  return `${pathname}?${parameters.toString()}`;
}
