import { useEffect, useMemo, useRef, useState } from 'react';
import maplibregl, {
  type GeoJSONSource,
  type Map as MapLibreMap,
} from 'maplibre-gl';
import type { Feature, Geometry } from 'geojson';
import type {
  Country,
  GeographicView,
  Institution,
  MetricObservation,
} from '../../domain/models';
import { buildCountryFeatureCollection } from './GeographicGeometryLayer';
import {
  buildInstitutionFeatureCollection,
  institutionColor,
  institutionRadius,
} from './InstitutionLayer';
import { researchActivityColor } from './visualScale';

interface WorldMapProps {
  countries: Country[];
  geographicViews: GeographicView[];
  countryObservations: MetricObservation[];
  institutions: Institution[];
  institutionObservations: MetricObservation[];
  selectedCountryId: string | null;
  selectedInstitutionId: string | null;
  globalResetToken: number;
  onCountrySelect: (countryId: string) => void;
  onInstitutionSelect: (institutionId: string) => void;
}

const worldCamera = {
  center: [9, 24] as [number, number],
  zoom: 0.7,
};

const countryFillColor: maplibregl.ExpressionSpecification = [
  'case',
  ['has', 'score'],
  researchActivityColor,
  '#0e1c2a',
];

function getFeatureBounds(features: Feature<Geometry>[]) {
  const bounds = new maplibregl.LngLatBounds();

  const visitCoordinates = (coordinates: unknown): void => {
    if (
      Array.isArray(coordinates) &&
      coordinates.length >= 2 &&
      typeof coordinates[0] === 'number' &&
      typeof coordinates[1] === 'number'
    ) {
      bounds.extend([coordinates[0], coordinates[1]]);
      return;
    }

    if (Array.isArray(coordinates)) {
      coordinates.forEach(visitCoordinates);
    }
  };

  features.forEach((feature) => {
    if ('coordinates' in feature.geometry) {
      visitCoordinates(feature.geometry.coordinates);
    }
  });

  return bounds;
}

export function WorldMap({
  countries,
  geographicViews,
  countryObservations,
  institutions,
  institutionObservations,
  selectedCountryId,
  selectedInstitutionId,
  globalResetToken,
  onCountrySelect,
  onInstitutionSelect,
}: WorldMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const [mapReady, setMapReady] = useState(false);
  const onCountrySelectRef = useRef(onCountrySelect);
  const onInstitutionSelectRef = useRef(onInstitutionSelect);
  const countryGeoJson = useMemo(
    () =>
      buildCountryFeatureCollection(
        countries,
        geographicViews,
        countryObservations,
      ),
    [countries, countryObservations, geographicViews],
  );
  const institutionGeoJson = useMemo(
    () =>
      buildInstitutionFeatureCollection(
        institutions,
        institutionObservations,
      ),
    [institutions, institutionObservations],
  );
  const countryGeoJsonRef = useRef(countryGeoJson);
  const institutionGeoJsonRef = useRef(institutionGeoJson);

  useEffect(() => {
    countryGeoJsonRef.current = countryGeoJson;
  }, [countryGeoJson]);

  useEffect(() => {
    institutionGeoJsonRef.current = institutionGeoJson;
  }, [institutionGeoJson]);

  useEffect(() => {
    onCountrySelectRef.current = onCountrySelect;
  }, [onCountrySelect]);

  useEffect(() => {
    onInstitutionSelectRef.current = onInstitutionSelect;
  }, [onInstitutionSelect]);

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
            paint: { 'background-color': '#050d17' },
          },
        ],
      },
      center: worldCamera.center,
      zoom: worldCamera.zoom,
      minZoom: 0.7,
      maxZoom: 8,
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
        data: countryGeoJsonRef.current,
        promoteId: 'isoNumeric',
      });
      map.addLayer({
        id: 'countries-fill',
        type: 'fill',
        source: 'countries',
        paint: {
          'fill-color': countryFillColor,
          'fill-opacity': [
            'case',
            ['has', 'score'],
            0.94,
            0.52,
          ],
        },
      });
      map.addLayer({
        id: 'countries-glow',
        type: 'line',
        source: 'countries',
        paint: {
          'line-color': [
            'case',
            ['has', 'score'],
            researchActivityColor,
            '#203849',
          ],
          'line-width': [
            'case',
            ['has', 'score'],
            2.2,
            0.7,
          ],
          'line-blur': 2.4,
          'line-opacity': 0.3,
        },
      });
      map.addLayer({
        id: 'countries-outline',
        type: 'line',
        source: 'countries',
        paint: {
          'line-color': [
            'case',
            ['has', 'score'],
            researchActivityColor,
            '#294154',
          ],
          'line-width': [
            'case',
            ['has', 'score'],
            0.85,
            0.45,
          ],
          'line-opacity': 0.84,
        },
      });
      map.addLayer({
        id: 'country-selection',
        type: 'line',
        source: 'countries',
        filter: ['==', ['get', 'explorationCountryId'], ''],
        paint: {
          'line-color': '#ffb067',
          'line-width': 4,
          'line-blur': 0.6,
          'line-opacity': 1,
        },
      });

      map.addSource('institutions', {
        type: 'geojson',
        data: institutionGeoJsonRef.current,
      });
      map.addLayer({
        id: 'institution-halo',
        type: 'circle',
        source: 'institutions',
        paint: {
          'circle-radius': [
            '+',
            institutionRadius,
            8,
          ],
          'circle-color': institutionColor,
          'circle-opacity': 0.18,
          'circle-blur': 0.75,
        },
      });
      map.addLayer({
        id: 'institution-points',
        type: 'circle',
        source: 'institutions',
        paint: {
          'circle-radius': institutionRadius,
          'circle-color': institutionColor,
          'circle-stroke-color': '#fff0df',
          'circle-stroke-width': 1.25,
          'circle-opacity': 0.96,
        },
      });
      map.addLayer({
        id: 'institution-selection',
        type: 'circle',
        source: 'institutions',
        filter: ['==', ['get', 'institutionId'], ''],
        paint: {
          'circle-radius': [
            '+',
            institutionRadius,
            5,
          ],
          'circle-color': 'rgba(0, 0, 0, 0)',
          'circle-stroke-color': '#ffffff',
          'circle-stroke-width': 2.5,
          'circle-blur': 0.2,
        },
      });
      setMapReady(true);
    });

    map.on('click', 'institution-points', (event) => {
      event.originalEvent.stopPropagation();
      const institutionId = event.features?.[0]?.properties?.institutionId;
      if (typeof institutionId === 'string') {
        onInstitutionSelectRef.current(institutionId);
      }
    });
    map.on('mouseenter', 'institution-points', () => {
      map.getCanvas().style.cursor = 'pointer';
    });
    map.on('mouseleave', 'institution-points', () => {
      map.getCanvas().style.cursor = '';
    });

    map.on('click', 'countries-fill', (event) => {
      const institutionFeatures = map.queryRenderedFeatures(event.point, {
        layers: ['institution-points'],
      });
      if (institutionFeatures.length > 0) {
        return;
      }

      const countryId =
        event.features?.[0]?.properties?.explorationCountryId;
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

    (map.getSource('countries') as GeoJSONSource | undefined)?.setData(
      countryGeoJson,
    );
  }, [countryGeoJson, mapReady]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map?.isStyleLoaded()) {
      return;
    }

    (map.getSource('institutions') as GeoJSONSource | undefined)?.setData(
      institutionGeoJson,
    );
  }, [institutionGeoJson, mapReady]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map?.getLayer('country-selection')) {
      return;
    }

    map.setFilter('country-selection', [
      '==',
      ['get', 'explorationCountryId'],
      selectedCountryId ?? '',
    ]);

    const countryFocusFilter: maplibregl.FilterSpecification | null =
      selectedCountryId
        ? ['==', ['get', 'explorationCountryId'], selectedCountryId]
        : null;
    map.setFilter('countries-fill', countryFocusFilter);
    map.setFilter('countries-glow', countryFocusFilter);
    map.setFilter('countries-outline', countryFocusFilter);
    map.setPaintProperty(
      'countries-fill',
      'fill-opacity',
      selectedCountryId
        ? 0.08
        : ['case', ['has', 'score'], 0.94, 0.52],
    );
    map.setPaintProperty(
      'countries-glow',
      'line-opacity',
      selectedCountryId ? 0.78 : 0.3,
    );
    map.setPaintProperty(
      'countries-glow',
      'line-width',
      selectedCountryId ? 5 : ['case', ['has', 'score'], 2.2, 0.7],
    );
    map.setPaintProperty(
      'countries-outline',
      'line-width',
      selectedCountryId ? 1.8 : ['case', ['has', 'score'], 0.85, 0.45],
    );

    if (!selectedCountryId) {
      map.easeTo({
        center: worldCamera.center,
        zoom: worldCamera.zoom,
        duration: 850,
      });
      return;
    }

    if (selectedInstitutionId) {
      return;
    }

    const selectedFeatures = countryGeoJson.features.filter(
      (candidate) =>
        candidate.properties.explorationCountryId === selectedCountryId,
    );
    if (selectedFeatures.length === 0) {
      return;
    }

    const bounds = getFeatureBounds(selectedFeatures);
    if (!bounds.isEmpty()) {
      const isNarrow = window.innerWidth < 900;
      map.fitBounds(bounds, {
        padding: isNarrow
          ? { top: 150, right: 44, bottom: 220, left: 44 }
          : { top: 120, right: 390, bottom: 180, left: 105 },
        maxZoom: 5.2,
        duration: 950,
      });
    }
  }, [
    countryGeoJson,
    globalResetToken,
    mapReady,
    selectedCountryId,
    selectedInstitutionId,
  ]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map?.getLayer('institution-selection')) {
      return;
    }

    map.setFilter('institution-selection', [
      '==',
      ['get', 'institutionId'],
      selectedInstitutionId ?? '',
    ]);

    if (!selectedInstitutionId) {
      return;
    }

    const institution = institutions.find(
      (candidate) => candidate.id === selectedInstitutionId,
    );
    if (institution?.location) {
      map.easeTo({
        center: [
          institution.location.longitude,
          institution.location.latitude,
        ],
        zoom: Math.max(map.getZoom(), 4.6),
        duration: 700,
      });
    }
  }, [institutions, mapReady, selectedInstitutionId]);

  return (
    <div
      className="world-map"
      ref={containerRef}
      role="application"
      aria-label="Temporal geographic atlas of synthetic physics research activity"
    />
  );
}
