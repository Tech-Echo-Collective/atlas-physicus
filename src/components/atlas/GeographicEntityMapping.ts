import type {
  Country,
  GeographicView,
  Institution,
} from '../../domain/models';

/**
 * Geographic view membership is a rendering concern. It does not change the
 * location metadata or research attribution attached to an entity.
 */
export function resolveExplorationCountryId(
  isoNumeric: string,
  countries: Country[],
  geographicViews: GeographicView[],
): string | undefined {
  const configuredView = geographicViews.find((view) =>
    view.geometryIsoNumerics.includes(isoNumeric),
  );

  if (configuredView) {
    return configuredView.countryId;
  }

  return countries.find((country) => country.isoNumeric === isoNumeric)?.id;
}

export function getLocationCountryIdsForView(
  countryId: string,
  geographicViews: GeographicView[],
): ReadonlySet<string> {
  const configuredView = geographicViews.find(
    (view) => view.countryId === countryId,
  );

  return new Set(configuredView?.locationCountryIds ?? [countryId]);
}

export function getInstitutionsForGeographicView(
  institutions: Institution[],
  countryId: string,
  geographicViews: GeographicView[],
): Institution[] {
  const locationCountryIds = getLocationCountryIdsForView(
    countryId,
    geographicViews,
  );

  return institutions.filter((institution) =>
    locationCountryIds.has(institution.countryId),
  );
}
