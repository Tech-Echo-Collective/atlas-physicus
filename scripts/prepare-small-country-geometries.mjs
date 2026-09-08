// Retain the installed Natural Earth geometry; never draw replacement borders.
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { createRequire } from 'node:module';
import { URL } from 'node:url';
import { log } from 'node:console';
import { feature } from 'topojson-client';

const require = createRequire(import.meta.url);
function countries(resolution) {
  const topology = JSON.parse(readFileSync(require.resolve(`world-atlas/countries-${resolution}.json`), 'utf8'));
  return feature(topology, topology.objects.countries).features;
}
const medium = new Map(countries('50m').filter((item) => item.id).map((item) => [item.id, item]));
const supplements = countries('10m').filter((item) => {
  if (!item.id) return false;
  const polygons = item.geometry.type === 'Polygon' ? [item.geometry.coordinates] : item.geometry.coordinates;
  // Quantization collapses a few tiny 10m polygons; preserve the valid 50m shape.
  const hasArea = polygons.some(([ring]) => Math.abs(ring.slice(1).reduce((area, point, i) =>
    area + ring[i][0] * point[1] - point[0] * ring[i][1], 0)) > 1e-12);
  if (!hasArea) return false;
  if (!medium.has(item.id)) return true;
  let west = Infinity, east = -Infinity, south = Infinity, north = -Infinity;
  const visit = (coordinates) => {
    if (typeof coordinates[0] === 'number') {
      west = Math.min(west, coordinates[0]); east = Math.max(east, coordinates[0]);
      south = Math.min(south, coordinates[1]); north = Math.max(north, coordinates[1]);
    } else coordinates.forEach(visit);
  };
  visit(item.geometry.coordinates);
  return east - west < 1 && north - south < 1;
});
const directory = new URL('../src/data/geography/', import.meta.url);
mkdirSync(directory, { recursive: true });
writeFileSync(new URL('small-countries-10m.json', directory), JSON.stringify({
  type: 'FeatureCollection',
  source: 'world-atlas 2.0.2 / Natural Earth 4.1.0, countries-10m.json; nondegenerate ISO features missing at 50m or spanning less than one degree on both axes',
  features: supplements,
}) + '\n');
log(`Preserved ${supplements.length} detailed small-country/source-missing geometries.`);
