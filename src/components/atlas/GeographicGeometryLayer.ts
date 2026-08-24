import { feature } from 'topojson-client';
import type {
  FeatureCollection,
  GeoJsonProperties,
  Geometry,
} from 'geojson';
import type { GeometryCollection, Topology } from 'topojson-specification';
import worldCountries from 'world-atlas/countries-110m.json';
import type {
  Country,
  GeographicView,
  MetricObservation,
} from '../../domain/models';
import { resolveExplorationCountryId } from './GeographicEntityMapping';

export type CountryFeatureProperties = NonNullable<GeoJsonProperties> & {
  countryId?: string;
  explorationCountryId?: string;
  isoNumeric: string;
  score?: number;
};

/**
 * Joins the packaged world geometry to native location entities and configured
 * exploration views. Geometry membership remains independent from metrics and
 * scientific attribution.
 */
export function buildCountryFeatureCollection(
  countries: Country[],
  geographicViews: GeographicView[],
  observations: MetricObservation[],
): FeatureCollection<Geometry, CountryFeatureProperties> {
  const topology = worldCountries as unknown as Topology;
  const object = topology.objects.countries as GeometryCollection;
  const collection = feature(topology, object) as unknown as FeatureCollection<
    Geometry,
    GeoJsonProperties
  >;
  const countriesByIso = new Map(
    countries.map((country) => [country.isoNumeric, country]),
  );
  const scoresByCountryId = new Map(
    observations.map((observation) => [
      observation.entityId,
      observation.value,
    ]),
  );

  return {
    type: 'FeatureCollection',
    features: collection.features.map((worldFeature) => {
      const isoNumeric = String(worldFeature.id ?? '').padStart(3, '0');
      const country = countriesByIso.get(isoNumeric);
      const explorationCountryId = resolveExplorationCountryId(
        isoNumeric,
        countries,
        geographicViews,
      );
      const score = country ? scoresByCountryId.get(country.id) : undefined;

      return {
        ...worldFeature,
        properties: {
          ...(worldFeature.properties ?? {}),
          isoNumeric,
          ...(country ? { countryId: country.id } : {}),
          ...(explorationCountryId ? { explorationCountryId } : {}),
          ...(score === undefined ? {} : { score }),
        },
      } as FeatureCollection<
        Geometry,
        CountryFeatureProperties
      >['features'][number];
    }),
  };
}
