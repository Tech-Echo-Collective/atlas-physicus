import type { FeatureCollection, Geometry, Position } from 'geojson';
import type { Country } from '../../domain/models';
import type { CountryFeatureProperties } from './GeographicGeometryLayer';

export interface SmallCountryLocator {
  countryId: string;
  name: string;
  coordinates: [number, number];
  maximumZoom: number;
}

function summarizeRing(ring: Position[]) {
  let twiceArea = 0, longitude = 0, latitude = 0;
  let west = Infinity, east = -Infinity, south = Infinity, north = -Infinity;
  for (let i = 0; i < ring.length - 1; i += 1) {
    const current = ring[i], next = ring[i + 1];
    const cross = current[0] * next[1] - next[0] * current[1];
    twiceArea += cross;
    longitude += (current[0] + next[0]) * cross;
    latitude += (current[1] + next[1]) * cross;
    west = Math.min(west, current[0]); east = Math.max(east, current[0]);
    south = Math.min(south, current[1]); north = Math.max(north, current[1]);
  }
  return { area: Math.abs(twiceArea) / 2,
    coordinates: (Math.abs(twiceArea) > 1e-12 ? [longitude / (3 * twiceArea), latitude / (3 * twiceArea)]
      : [(west + east) / 2, (south + north) / 2]) as [number, number],
    span: Math.max(east - west, north - south) };
}

/** Minimum-size navigation targets; these do not enlarge country borders or encode a metric. */
export function buildSmallCountryLocators(collection: FeatureCollection<Geometry, CountryFeatureProperties>, countries: Country[]): SmallCountryLocator[] {
  const grouped = new Map<string, ReturnType<typeof summarizeRing>[]>();
  for (const item of collection.features) {
    const countryId = item.properties.explorationCountryId;
    if (!countryId) continue;
    const polygons = item.geometry.type === 'Polygon' ? [item.geometry.coordinates]
      : item.geometry.type === 'MultiPolygon' ? item.geometry.coordinates : [];
    const summaries = grouped.get(countryId) ?? [];
    for (const polygon of polygons) if (polygon[0]?.length) summaries.push(summarizeRing(polygon[0]));
    grouped.set(countryId, summaries);
  }
  const names = new Map(countries.map((country) => [country.id, country.name]));
  return [...grouped].flatMap(([countryId, parts]) => {
    const largest = parts.reduce<ReturnType<typeof summarizeRing> | undefined>((best, part) => !best || part.area > best.area ? part : best, undefined);
    // Coordinate area is only a display heuristic, never a physical-area/science measure.
    if (!largest || largest.area <= 0 || parts.reduce((total, part) => total + part.area, 0) > 1 || largest.span > 2) return [];
    const latitudeScale = Math.max(0.1, Math.cos(largest.coordinates[1] * Math.PI / 180));
    const worldPixelSpan = 512 * largest.span / (360 * latitudeScale);
    return [{ countryId, name: names.get(countryId) ?? countryId, coordinates: largest.coordinates,
      maximumZoom: Math.min(12, Math.max(2, Math.log2(32 / Math.max(worldPixelSpan, 0.001)))) }];
  });
}
