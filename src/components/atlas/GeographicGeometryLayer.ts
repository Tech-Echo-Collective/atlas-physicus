import { feature } from 'topojson-client';
import type {
  FeatureCollection,
  GeoJsonProperties,
  Geometry,
  MultiPolygon,
  Polygon,
  Position,
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
  metricValue?: number;
};

export type ExplorationCanvasProperties = NonNullable<GeoJsonProperties> & {
  explorationCountryId: string;
  sourceIsoNumerics: string[];
  metricValue?: number;
};

const antimeridianLongitude = 180;
const coordinateEpsilon = 1e-9;

function positionsEqual(left: Position, right: Position): boolean {
  return (
    Math.abs(left[0] - right[0]) < coordinateEpsilon &&
    Math.abs(left[1] - right[1]) < coordinateEpsilon
  );
}

function hasAntimeridianJump(ring: Position[]): boolean {
  return ring.some(
    (position, index) =>
      index > 0 &&
      Math.abs(position[0] - (ring[index - 1]?.[0] ?? position[0])) >
        antimeridianLongitude,
  );
}

function unwrapRing(ring: Position[]): Position[] {
  if (ring.length === 0) {
    return [];
  }

  const unwrapped: Position[] = [[...ring[0]]];
  for (const position of ring.slice(1)) {
    const previousLongitude = unwrapped.at(-1)?.[0] ?? position[0];
    let longitude = position[0];

    while (longitude - previousLongitude > antimeridianLongitude) {
      longitude -= 360;
    }
    while (longitude - previousLongitude < -antimeridianLongitude) {
      longitude += 360;
    }

    unwrapped.push([longitude, position[1], ...position.slice(2)]);
  }

  return unwrapped;
}

function longitudeIntersection(
  start: Position,
  end: Position,
  boundary: number,
): Position {
  const longitudeSpan = end[0] - start[0];
  const ratio =
    Math.abs(longitudeSpan) < coordinateEpsilon
      ? 0
      : (boundary - start[0]) / longitudeSpan;
  return [boundary, start[1] + (end[1] - start[1]) * ratio];
}

function clipOpenRing(
  positions: Position[],
  boundary: number,
  keepGreater: boolean,
): Position[] {
  if (positions.length === 0) {
    return [];
  }

  const result: Position[] = [];
  const isInside = (position: Position) =>
    keepGreater
      ? position[0] >= boundary - coordinateEpsilon
      : position[0] <= boundary + coordinateEpsilon;

  let previous = positions.at(-1) as Position;
  let previousInside = isInside(previous);
  for (const current of positions) {
    const currentInside = isInside(current);
    if (currentInside !== previousInside) {
      result.push(longitudeIntersection(previous, current, boundary));
    }
    if (currentInside) {
      result.push(current);
    }
    previous = current;
    previousInside = currentInside;
  }

  return result.filter(
    (position, index) =>
      index === 0 || !positionsEqual(position, result[index - 1] as Position),
  );
}

function signedRingArea(ring: Position[]): number {
  let area = 0;
  for (let index = 0; index < ring.length - 1; index += 1) {
    const current = ring[index];
    const next = ring[index + 1];
    if (current && next) {
      area += current[0] * next[1] - next[0] * current[1];
    }
  }
  return area / 2;
}

function clipRingToWorld(ring: Position[]): Position[] | null {
  const openRing =
    ring.length > 1 && positionsEqual(ring[0] as Position, ring.at(-1) as Position)
      ? ring.slice(0, -1)
      : [...ring];
  const clipped = clipOpenRing(
    clipOpenRing(openRing, -antimeridianLongitude, true),
    antimeridianLongitude,
    false,
  );

  if (clipped.length < 3) {
    return null;
  }

  const closed = [...clipped, [...clipped[0]]];
  return Math.abs(signedRingArea(closed)) > coordinateEpsilon ? closed : null;
}

function shiftRing(ring: Position[], longitudeOffset: number): Position[] {
  return ring.map((position) => [
    position[0] + longitudeOffset,
    position[1],
    ...position.slice(2),
  ]);
}

function ringLongitudeCenter(ring: Position[]): number {
  const longitudes = ring.map((position) => position[0]);
  return (Math.min(...longitudes) + Math.max(...longitudes)) / 2;
}

function alignRingToLongitude(ring: Position[], referenceLongitude: number) {
  const longitudeOffset =
    Math.round((referenceLongitude - ringLongitudeCenter(ring)) / 360) * 360;
  return shiftRing(ring, longitudeOffset);
}

function splitPolygonAtAntimeridian(
  polygon: Polygon['coordinates'],
): MultiPolygon['coordinates'] {
  if (!polygon.some(hasAntimeridianJump)) {
    return [polygon];
  }

  const outer = unwrapRing(polygon[0] ?? []);
  const outerLongitudeCenter = ringLongitudeCenter(outer);
  // Interior rings must use the same continuous world copy as their shell.
  // Unwrapping each ring independently can otherwise attach a -178° hole to
  // the +170° half of a polygon after the antimeridian cut.
  const unwrapped = [
    outer,
    ...polygon
      .slice(1)
      .map(unwrapRing)
      .map((hole) => alignRingToLongitude(hole, outerLongitudeCenter)),
  ];
  const longitudes = outer.map((position) => position[0]);
  const minimumLongitude = Math.min(...longitudes);
  const maximumLongitude = Math.max(...longitudes);
  const minimumShift = Math.ceil(
    (-antimeridianLongitude - maximumLongitude) / 360,
  );
  const maximumShift = Math.floor(
    (antimeridianLongitude - minimumLongitude) / 360,
  );
  const pieces: MultiPolygon['coordinates'] = [];

  for (let shiftIndex = minimumShift; shiftIndex <= maximumShift; shiftIndex += 1) {
    const longitudeOffset = shiftIndex * 360;
    const clippedOuter = clipRingToWorld(
      shiftRing(outer, longitudeOffset),
    );
    if (!clippedOuter) {
      continue;
    }

    const clippedHoles = unwrapped.slice(1).flatMap((hole) => {
      const clipped = clipRingToWorld(shiftRing(hole, longitudeOffset));
      return clipped ? [clipped] : [];
    });
    pieces.push([clippedOuter, ...clippedHoles]);
  }

  return pieces;
}

/**
 * Cuts polygon rings at +/-180 degrees instead of allowing renderers to draw
 * a straight segment through the map interior. The algorithm is applied to
 * every polygon and therefore also covers islands, exclaves, and other
 * antimeridian-spanning geographic sources without country-specific patches.
 */
export function splitGeometryAtAntimeridian(geometry: Geometry): Geometry {
  if (geometry.type === 'Polygon') {
    const pieces = splitPolygonAtAntimeridian(geometry.coordinates);
    return pieces.length === 1
      ? { type: 'Polygon', coordinates: pieces[0] as Polygon['coordinates'] }
      : { type: 'MultiPolygon', coordinates: pieces };
  }

  if (geometry.type === 'MultiPolygon') {
    return {
      type: 'MultiPolygon',
      coordinates: geometry.coordinates.flatMap(splitPolygonAtAntimeridian),
    };
  }

  return geometry;
}

function polygonLongitudeCenter(polygon: Polygon['coordinates']): number {
  return ringLongitudeCenter(polygon[0] ?? []);
}

function polygonArea(polygon: Polygon['coordinates']): number {
  return Math.abs(signedRingArea(polygon[0] ?? []));
}

/**
 * Places disconnected polygon components into the nearest continuous world
 * copy for a compact country camera. Coordinates may intentionally exceed
 * +/-180; MapLibre supports these unwrapped coordinates in a country-only
 * canvas and avoids treating nearby Bering components as world-width apart.
 */
export function compactMultiPolygonCoordinates(
  coordinates: MultiPolygon['coordinates'],
): MultiPolygon['coordinates'] {
  if (coordinates.length === 0) {
    return [];
  }

  const anchorPolygon = [...coordinates].sort(
    (left, right) => polygonArea(right) - polygonArea(left),
  )[0] as Polygon['coordinates'];
  const anchorLongitude = polygonLongitudeCenter(anchorPolygon);

  return coordinates.map((polygon) => {
    const longitudeOffset =
      Math.round(
        (anchorLongitude - polygonLongitudeCenter(polygon)) / 360,
      ) * 360;
    return polygon.map((ring) => shiftRing(ring, longitudeOffset));
  });
}

export function geometryUsesUnwrappedWorldCopy(geometry: Geometry): boolean {
  let usesUnwrappedLongitude = false;
  const visit = (coordinates: unknown): void => {
    if (usesUnwrappedLongitude || !Array.isArray(coordinates)) {
      return;
    }
    if (
      coordinates.length >= 2 &&
      typeof coordinates[0] === 'number' &&
      typeof coordinates[1] === 'number'
    ) {
      usesUnwrappedLongitude = coordinates[0] < -180 || coordinates[0] > 180;
      return;
    }
    coordinates.forEach(visit);
  };

  if ('coordinates' in geometry) {
    visit(geometry.coordinates);
  }
  return usesUnwrappedLongitude;
}

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
  const valuesByCountryId = new Map(
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
      const metricValue = metricEntityId
        ? valuesByCountryId.get(metricEntityId)
        : undefined;

      return {
        ...worldFeature,
        geometry: splitGeometryAtAntimeridian(worldFeature.geometry),
        properties: {
          ...(worldFeature.properties ?? {}),
          isoNumeric,
          ...(country ? { countryId: country.id } : {}),
          ...(explorationCountryId ? { explorationCountryId } : {}),
          ...(metricEntityId ? { metricEntityId } : {}),
          ...(metricValue === undefined ? {} : { metricValue }),
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
  const sourceCoordinates: MultiPolygon['coordinates'] = sourceFeatures.flatMap(
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
  const coordinates = compactMultiPolygonCoordinates(sourceCoordinates);

  if (coordinates.length === 0) {
    return { type: 'FeatureCollection', features: [] };
  }

  const valuedFeature = sourceFeatures.find(
    (candidate) => candidate.properties.metricValue !== undefined,
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
          ...(valuedFeature?.properties.metricValue === undefined
            ? {}
            : { metricValue: valuedFeature.properties.metricValue }),
        },
      },
    ],
  };
}
