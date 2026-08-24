import { feature } from 'topojson-client';
import type {
  FeatureCollection,
  GeoJsonProperties,
  Geometry,
  MultiPolygon,
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
  metricEntityId?: string;
  isoNumeric: string;
  score?: number;
};

export type ExplorationCanvasProperties = NonNullable<GeoJsonProperties> & {
  explorationCountryId: string;
  sourceIsoNumerics: string[];
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
      const metricEntityId = explorationCountryId ?? country?.id;
      const score = metricEntityId
        ? scoresByCountryId.get(metricEntityId)
        : undefined;

      return {
        ...worldFeature,
        properties: {
          ...(worldFeature.properties ?? {}),
          isoNumeric,
          ...(country ? { countryId: country.id } : {}),
          ...(explorationCountryId ? { explorationCountryId } : {}),
          ...(metricEntityId ? { metricEntityId } : {}),
          ...(score === undefined ? {} : { score }),
        },
      } as FeatureCollection<
        Geometry,
        CountryFeatureProperties
      >['features'][number];
    }),
  };
}

/**
 * Composes every configured polygon for one exploration view into a dedicated
 * render feature. This prevents country mode from depending on filters over
 * the global choropleth while preserving the original source coordinates.
 */
export function buildExplorationCanvasFeatureCollection(
  countries: FeatureCollection<Geometry, CountryFeatureProperties>,
  explorationCountryId: string | null,
): FeatureCollection<MultiPolygon, ExplorationCanvasProperties> {
  if (!explorationCountryId) {
    return { type: 'FeatureCollection', features: [] };
  }

  const sourceFeatures = countries.features.filter(
    (candidate) =>
      candidate.properties.explorationCountryId === explorationCountryId,
  );
  const coordinates: MultiPolygon['coordinates'] = sourceFeatures.flatMap(
    (sourceFeature) => {
      if (sourceFeature.geometry.type === 'Polygon') {
        return [sourceFeature.geometry.coordinates];
      }

      if (sourceFeature.geometry.type === 'MultiPolygon') {
        return sourceFeature.geometry.coordinates;
      }

      return [];
    },
  );

  if (coordinates.length === 0) {
    return { type: 'FeatureCollection', features: [] };
  }

  const scoredFeature = sourceFeatures.find(
    (candidate) => candidate.properties.score !== undefined,
  );

  return {
    type: 'FeatureCollection',
    features: [
      {
        type: 'Feature',
        id: explorationCountryId,
        geometry: { type: 'MultiPolygon', coordinates },
        properties: {
          explorationCountryId,
          sourceIsoNumerics: sourceFeatures.map(
            (candidate) => candidate.properties.isoNumeric,
          ),
          ...(scoredFeature?.properties.score === undefined
            ? {}
            : { score: scoredFeature.properties.score }),
        },
      },
    ],
  };
}
