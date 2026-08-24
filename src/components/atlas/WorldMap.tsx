import { useEffect, useMemo, useRef } from 'react';
import maplibregl, { type GeoJSONSource, type Map as MapLibreMap } from 'maplibre-gl';
import { feature } from 'topojson-client';
import type { FeatureCollection, GeoJsonProperties, Geometry } from 'geojson';
import type { GeometryCollection, Topology } from 'topojson-specification';
import worldCountries from 'world-atlas/countries-110m.json';
import type { Country, MetricObservation } from '../../domain/models';

interface WorldMapProps {
  countries: Country[];
  observations: MetricObservation[];
  selectedCountryId: string | null;
  onCountrySelect: (countryId: string) => void;
}

type CountryFeatureProperties = NonNullable<GeoJsonProperties> & {
  countryId?: string;
  isoNumeric: string;
  score?: number;
};

const countryFillColor: maplibregl.ExpressionSpecification = [
  'case',
  ['has', 'score'],
  [
    'interpolate',
    ['linear'],
    ['get', 'score'],
    0,
    '#17324a',
    25,
    '#13546b',
    50,
    '#1e8090',
    75,
    '#63b6a1',
    100,
    '#f2d58a',
  ],
  '#122131',
];

function buildGeoJson(
  countries: Country[],
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
      const score = country ? scoresByCountryId.get(country.id) : undefined;

      return {
        ...worldFeature,
        properties: {
          ...(worldFeature.properties ?? {}),
          isoNumeric,
          ...(country ? { countryId: country.id } : {}),
          ...(score === undefined ? {} : { score }),
        },
      } as FeatureCollection<Geometry, CountryFeatureProperties>['features'][number];
    }),
  };
}

export function WorldMap({
  countries,
  observations,
  selectedCountryId,
  onCountrySelect,
}: WorldMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const onCountrySelectRef = useRef(onCountrySelect);
  const geoJson = useMemo(
    () => buildGeoJson(countries, observations),
    [countries, observations],
  );
  const initialGeoJsonRef = useRef(geoJson);

  useEffect(() => {
    onCountrySelectRef.current = onCountrySelect;
  }, [onCountrySelect]);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) {
      return;
    }

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: {
        version: 8,
        sources: {},
        layers: [
          {
            id: 'background',
            type: 'background',
            paint: { 'background-color': '#07111d' },
          },
        ],
      },
      center: [9, 24],
      zoom: 1.25,
      minZoom: 0.7,
      maxZoom: 6,
      attributionControl: false,
      renderWorldCopies: false,
    });

    map.addControl(
      new maplibregl.NavigationControl({ showCompass: false }),
      'bottom-left',
    );

    map.on('load', () => {
      map.addSource('countries', {
        type: 'geojson',
        data: initialGeoJsonRef.current,
        promoteId: 'isoNumeric',
      });
      map.addLayer({
        id: 'countries-fill',
        type: 'fill',
        source: 'countries',
        paint: {
          'fill-color': countryFillColor,
          'fill-opacity': 0.96,
        },
      });
      map.addLayer({
        id: 'countries-outline',
        type: 'line',
        source: 'countries',
        paint: {
          'line-color': '#345066',
          'line-width': 0.65,
          'line-opacity': 0.9,
        },
      });
      map.addLayer({
        id: 'country-selection',
        type: 'line',
        source: 'countries',
        filter: ['==', ['get', 'countryId'], ''],
        paint: {
          'line-color': '#fff0bf',
          'line-width': 2.5,
          'line-opacity': 1,
        },
      });
    });

    map.on('click', 'countries-fill', (event) => {
      const countryId = event.features?.[0]?.properties?.countryId;
      if (typeof countryId === 'string') {
        onCountrySelectRef.current(countryId);
      }
    });
    map.on('mouseenter', 'countries-fill', () => {
      map.getCanvas().style.cursor = 'pointer';
    });
    map.on('mouseleave', 'countries-fill', () => {
      map.getCanvas().style.cursor = '';
    });

    mapRef.current = map;

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map?.isStyleLoaded()) {
      return;
    }

    (map.getSource('countries') as GeoJSONSource | undefined)?.setData(geoJson);
  }, [geoJson]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map?.getLayer('country-selection')) {
      return;
    }

    map.setFilter('country-selection', [
      '==',
      ['get', 'countryId'],
      selectedCountryId ?? '',
    ]);
  }, [selectedCountryId]);

  return (
    <div
      className="world-map"
      ref={containerRef}
      role="application"
      aria-label="Interactive world map of synthetic physics research activity"
    />
  );
}
