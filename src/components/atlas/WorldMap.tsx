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
import {
  getDatasetPresentation,
  type AtlasDatasetKind,
} from '../../data/DatasetPresentation';
import {
  buildCountryFeatureCollection,
  buildExplorationCanvasFeatureCollection,
  geometryUsesUnwrappedWorldCopy,
} from './GeographicGeometryLayer';
import {
  buildInstitutionFeatureCollection,
  getInstitutionPulseFrame,
  institutionColor,
  institutionHeatmapColor,
  institutionHeatmapWeight,
  institutionPulseColor,
  institutionPulseDurationMs,
  institutionRadius,
} from './InstitutionLayer';
import { GlobalViewControl } from './GlobalViewControl';
import { getAtlasMapLayerHierarchy } from './MapLayerHierarchy';
import { metricValueColor } from './visualScale';

interface WorldMapProps {
  countries: Country[];
  geographicViews: GeographicView[];
  countryObservations: MetricObservation[];
  institutions: Institution[];
  institutionObservations: MetricObservation[];
  metricLabel: string;
  datasetKind: AtlasDatasetKind;
  selectedCountryId: string | null;
  selectedInstitutionId: string | null;
  globalResetToken: number;
  onGlobalReset: () => void;
  onCountrySelect: (countryId: string) => void;
  onInstitutionSelect: (institutionId: string) => void;
}

const worldCamera = {
  center: [9, 24] as [number, number],
  zoom: 0.7,
};

const countryFillColor: maplibregl.ExpressionSpecification = [
  'case',
  ['has', 'metricValue'],
  metricValueColor,
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
  metricLabel,
  datasetKind,
  selectedCountryId,
  selectedInstitutionId,
  globalResetToken,
  onGlobalReset,
  onCountrySelect,
  onInstitutionSelect,
}: WorldMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const pulseAnimationFrameRef = useRef<number | null>(null);
  const institutionLayersVisibleRef = useRef(false);
  const hoverPopupRef = useRef<maplibregl.Popup | null>(null);
  const [mapReady, setMapReady] = useState(false);
  const onCountrySelectRef = useRef(onCountrySelect);
  const onInstitutionSelectRef = useRef(onInstitutionSelect);
  const metricLabelRef = useRef(metricLabel);
  const datasetPresentation = getDatasetPresentation(datasetKind);
  const observationLabelRef = useRef(datasetPresentation.observationLabel);
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
  const explorationCanvasGeoJson = useMemo(
    () =>
      buildExplorationCanvasFeatureCollection(
        countryGeoJson,
        selectedCountryId,
      ),
    [countryGeoJson, selectedCountryId],
  );
  const explorationCanvasUsesWorldCopy = useMemo(
    () =>
      explorationCanvasGeoJson.features.some((feature) =>
        geometryUsesUnwrappedWorldCopy(feature.geometry),
      ),
    [explorationCanvasGeoJson],
  );
  const countryGeoJsonRef = useRef(countryGeoJson);
  const explorationCanvasGeoJsonRef = useRef(explorationCanvasGeoJson);
  const institutionGeoJsonRef = useRef(institutionGeoJson);

  useEffect(() => {
    countryGeoJsonRef.current = countryGeoJson;
  }, [countryGeoJson]);

  useEffect(() => {
    explorationCanvasGeoJsonRef.current = explorationCanvasGeoJson;
  }, [explorationCanvasGeoJson]);

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
    metricLabelRef.current = metricLabel;
  }, [metricLabel]);

  useEffect(() => {
    observationLabelRef.current = datasetPresentation.observationLabel;
  }, [datasetPresentation.observationLabel]);

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
    const hoverPopup = new maplibregl.Popup({
      closeButton: false,
      closeOnClick: false,
      offset: 18,
      className: 'institution-map-popup',
    });
    hoverPopupRef.current = hoverPopup;

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
            ['has', 'metricValue'],
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
            ['has', 'metricValue'],
            metricValueColor,
            '#203849',
          ],
          'line-width': [
            'case',
            ['has', 'metricValue'],
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
            ['has', 'metricValue'],
            metricValueColor,
            '#294154',
          ],
          'line-width': [
            'case',
            ['has', 'metricValue'],
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

      map.addSource('exploration-canvas', {
        type: 'geojson',
        data: explorationCanvasGeoJsonRef.current,
      });
      map.addLayer({
        id: 'exploration-canvas-fill',
        type: 'fill',
        source: 'exploration-canvas',
        layout: { visibility: 'none' },
        paint: {
          'fill-color': '#0b1b28',
          'fill-opacity': 0.72,
        },
      });
      map.addLayer({
        id: 'exploration-canvas-glow',
        type: 'line',
        source: 'exploration-canvas',
        layout: { visibility: 'none' },
        paint: {
          'line-color': '#4c7b84',
          'line-width': 5,
          'line-blur': 3,
          'line-opacity': 0.3,
        },
      });
      map.addLayer({
        id: 'exploration-canvas-outline',
        type: 'line',
        source: 'exploration-canvas',
        layout: { visibility: 'none' },
        paint: {
          'line-color': '#8eb9c2',
          'line-width': 2.2,
          'line-opacity': 1,
        },
      });

      map.addSource('institutions', {
        type: 'geojson',
        data: institutionGeoJsonRef.current,
      });
      map.addLayer({
        id: 'institution-heatmap',
        type: 'heatmap',
        source: 'institutions',
        layout: { visibility: 'none' },
        paint: {
          'heatmap-weight': institutionHeatmapWeight,
          'heatmap-intensity': [
            'interpolate',
            ['linear'],
            ['zoom'],
            1,
            0.85,
            6,
            1.25,
          ],
          'heatmap-radius': [
            'interpolate',
            ['linear'],
            ['zoom'],
            1,
            28,
            4,
            46,
            7,
            64,
          ],
          'heatmap-color': institutionHeatmapColor,
          'heatmap-opacity': 0.72,
        },
      });
      const initialPulseFrame = getInstitutionPulseFrame(
        institutionPulseDurationMs * 0.35,
      );
      map.addLayer({
        id: 'institution-pulse-outer',
        type: 'circle',
        source: 'institutions',
        layout: { visibility: 'none' },
        paint: {
          'circle-radius': [
            '+',
            institutionRadius,
            initialPulseFrame.outerRadiusOffset,
          ],
          'circle-color': 'rgba(0, 0, 0, 0)',
          'circle-stroke-color': institutionPulseColor,
          'circle-stroke-width': 1,
          'circle-stroke-opacity': initialPulseFrame.opacity * 0.72,
        },
      });
      map.addLayer({
        id: 'institution-pulse-inner',
        type: 'circle',
        source: 'institutions',
        layout: { visibility: 'none' },
        paint: {
          'circle-radius': [
            '+',
            institutionRadius,
            initialPulseFrame.innerRadiusOffset,
          ],
          'circle-color': 'rgba(0, 0, 0, 0)',
          'circle-stroke-color': institutionPulseColor,
          'circle-stroke-width': 1.2,
          'circle-stroke-opacity': initialPulseFrame.opacity,
        },
      });
      map.addLayer({
        id: 'institution-halo',
        type: 'circle',
        source: 'institutions',
        layout: { visibility: 'none' },
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
        layout: { visibility: 'none' },
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
        layout: { visibility: 'none' },
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

      const prefersReducedMotion = window.matchMedia(
        '(prefers-reduced-motion: reduce)',
      ).matches;
      if (!prefersReducedMotion) {
        let lastPulseUpdateMs = 0;
        const animateInstitutionPulses = (elapsedMs: number) => {
          if (
            institutionLayersVisibleRef.current &&
            elapsedMs - lastPulseUpdateMs >= 32 &&
            map.getLayer('institution-pulse-inner') &&
            map.getLayer('institution-pulse-outer')
          ) {
            lastPulseUpdateMs = elapsedMs;
            const pulseFrame = getInstitutionPulseFrame(elapsedMs);
            map.setPaintProperty('institution-pulse-inner', 'circle-radius', [
              '+',
              institutionRadius,
              pulseFrame.innerRadiusOffset,
            ]);
            map.setPaintProperty(
              'institution-pulse-inner',
              'circle-stroke-opacity',
              pulseFrame.opacity,
            );
            map.setPaintProperty('institution-pulse-outer', 'circle-radius', [
              '+',
              institutionRadius,
              pulseFrame.outerRadiusOffset,
            ]);
            map.setPaintProperty(
              'institution-pulse-outer',
              'circle-stroke-opacity',
              pulseFrame.opacity * 0.72,
            );
          }

          pulseAnimationFrameRef.current = window.requestAnimationFrame(
            animateInstitutionPulses,
          );
        };

        pulseAnimationFrameRef.current = window.requestAnimationFrame(
          animateInstitutionPulses,
        );
      }
      setMapReady(true);
    });

    map.on('click', 'institution-points', (event) => {
      event.originalEvent.stopPropagation();
      const institutionId = event.features?.[0]?.properties?.institutionId;
      if (typeof institutionId === 'string') {
        onInstitutionSelectRef.current(institutionId);
      }
    });
    map.on('mousemove', 'institution-points', (event) => {
      map.getCanvas().style.cursor = 'pointer';
      const properties = event.features?.[0]?.properties;
      if (!properties) {
        return;
      }

      const institutionId = String(properties.institutionId ?? '');
      const activeInstitutionId = hoverPopup
        .getElement()
        ?.dataset.institutionId;
      if (institutionId !== activeInstitutionId) {
        const content = document.createElement('div');
        content.className = 'institution-popup-content';

        const name = document.createElement('strong');
        name.textContent = String(properties.name ?? 'Institution');
        const location = document.createElement('span');
        location.textContent = String(
          properties.city ?? 'Location unavailable',
        );
        const value = document.createElement('span');
        value.textContent = `${metricLabelRef.current} · ${String(properties.metricValue ?? '—')}`;
        const status = document.createElement('small');
        status.textContent = observationLabelRef.current;

        content.append(name, location, value, status);
        hoverPopup.setDOMContent(content);
      }

      hoverPopup.setLngLat(event.lngLat);
      if (!hoverPopup.isOpen()) {
        hoverPopup.addTo(map);
      }
      hoverPopup.getElement().dataset.institutionId = institutionId;
    });
    map.on('mouseleave', 'institution-points', () => {
      map.getCanvas().style.cursor = '';
      hoverPopup.remove();
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
      if (pulseAnimationFrameRef.current !== null) {
        window.cancelAnimationFrame(pulseAnimationFrameRef.current);
        pulseAnimationFrameRef.current = null;
      }
      hoverPopup.remove();
      hoverPopupRef.current = null;
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) {
      return;
    }

    (map.getSource('countries') as GeoJSONSource | undefined)?.setData(
      countryGeoJson,
    );
  }, [countryGeoJson, mapReady]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) {
      return;
    }

    (
      map.getSource('exploration-canvas') as GeoJSONSource | undefined
    )?.setData(explorationCanvasGeoJson);
  }, [explorationCanvasGeoJson, mapReady]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) {
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

    const layerHierarchy = getAtlasMapLayerHierarchy(
      selectedCountryId,
      selectedInstitutionId,
    );
    institutionLayersVisibleRef.current =
      layerHierarchy.institutionHeatmap === 'visible';
    // Antimeridian country canvases intentionally use the nearest unwrapped
    // world copy. Enable copies only for that focused view so MapLibre renders
    // +180° components without duplicating the minimum global map.
    map.setRenderWorldCopies(explorationCanvasUsesWorldCopy);
    if (!institutionLayersVisibleRef.current) {
      hoverPopupRef.current?.remove();
    }

    map.setLayoutProperty(
      'countries-fill',
      'visibility',
      layerHierarchy.countryHeatmap,
    );
    map.setLayoutProperty(
      'countries-glow',
      'visibility',
      layerHierarchy.countryHeatmap,
    );
    map.setLayoutProperty(
      'countries-outline',
      'visibility',
      layerHierarchy.countryHeatmap,
    );
    map.setLayoutProperty(
      'country-selection',
      'visibility',
      layerHierarchy.countryHeatmap,
    );
    map.setLayoutProperty(
      'exploration-canvas-fill',
      'visibility',
      layerHierarchy.countryCanvas,
    );
    map.setLayoutProperty(
      'exploration-canvas-glow',
      'visibility',
      layerHierarchy.countryCanvas,
    );
    map.setLayoutProperty(
      'exploration-canvas-outline',
      'visibility',
      layerHierarchy.countryCanvas,
    );
    map.setLayoutProperty(
      'institution-heatmap',
      'visibility',
      layerHierarchy.institutionHeatmap,
    );
    map.setLayoutProperty(
      'institution-pulse-outer',
      'visibility',
      layerHierarchy.institutionHeatmap,
    );
    map.setLayoutProperty(
      'institution-pulse-inner',
      'visibility',
      layerHierarchy.institutionHeatmap,
    );
    map.setLayoutProperty(
      'institution-halo',
      'visibility',
      layerHierarchy.institutionHeatmap,
    );
    map.setLayoutProperty(
      'institution-points',
      'visibility',
      layerHierarchy.institutionHeatmap,
    );
    map.setLayoutProperty(
      'institution-selection',
      'visibility',
      layerHierarchy.institutionSelection,
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

    const selectedFeatures = explorationCanvasGeoJson.features;
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
    explorationCanvasGeoJson,
    explorationCanvasUsesWorldCopy,
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

  const zoomMap = (direction: 1 | -1) => {
    const map = mapRef.current;
    if (!map) {
      return;
    }
    map.zoomTo(map.getZoom() + direction, { duration: 280 });
  };

  return (
    <>
      <div
        className="world-map"
        ref={containerRef}
        role="application"
        aria-label={datasetPresentation.mapAriaLabel}
      />
      <nav className="map-navigation-controls" aria-label="Map navigation">
        <GlobalViewControl
          isGlobalView={!selectedCountryId && !selectedInstitutionId}
          onReturn={onGlobalReset}
        />
        <span className="map-control-divider" aria-hidden="true" />
        <button
          type="button"
          onClick={() => zoomMap(1)}
          aria-label="Zoom in"
          title="Zoom in"
        >
          <span aria-hidden="true">+</span>
        </button>
        <button
          type="button"
          onClick={() => zoomMap(-1)}
          aria-label="Zoom out"
          title="Zoom out"
        >
          <span aria-hidden="true">−</span>
        </button>
      </nav>
    </>
  );
}
