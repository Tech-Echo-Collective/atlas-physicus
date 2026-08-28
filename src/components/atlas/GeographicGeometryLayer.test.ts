import demoData from '../../data/demo/atlas.json';
import { atlasDatasetSchema } from '../../domain/schemas';
import {
  buildCountryFeatureCollection,
  buildExplorationCanvasFeatureCollection,
  geometryUsesUnwrappedWorldCopy,
  splitGeometryAtAntimeridian,
} from './GeographicGeometryLayer';

const dataset = atlasDatasetSchema.parse(demoData);

function polygonRings(
  geometry: ReturnType<typeof buildCountryFeatureCollection>['features'][number]['geometry'],
) {
  if (geometry.type === 'Polygon') {
    return geometry.coordinates;
  }
  if (geometry.type === 'MultiPolygon') {
    return geometry.coordinates.flat();
  }
  return [];
}

function maximumLongitudeJump(rings: number[][][]): number {
  return Math.max(
    0,
    ...rings.flatMap((ring) =>
      ring.slice(1).map((position, index) =>
        Math.abs(position[0] - (ring[index]?.[0] ?? position[0])),
      ),
    ),
  );
}

describe('geographic geometry layer', () => {
  it('keeps every configured China-view source geometry renderable', () => {
    const collection = buildCountryFeatureCollection(
      dataset.countries,
      dataset.geographicViews,
      [],
    );
    const chinaViewFeatures = collection.features.filter(
      (candidate) =>
        candidate.properties.explorationCountryId === 'country-cn',
    );

    expect(
      chinaViewFeatures.map((candidate) => candidate.properties.isoNumeric),
    ).toEqual(['156', '158']);
    expect(
      chinaViewFeatures.map((candidate) => candidate.geometry.type),
    ).toEqual(['MultiPolygon', 'Polygon']);
    expect(
      chinaViewFeatures.every(
        (candidate) =>
          'coordinates' in candidate.geometry &&
          candidate.geometry.coordinates.length > 0,
      ),
    ).toBe(true);
  });

  it('resolves world heatmap color through view membership without changing native identity', () => {
    const observations = dataset.metricObservations.filter(
      (observation) =>
        observation.entityType === 'country' &&
        observation.scienceDomainId === 'physics' &&
        observation.period === '2026',
    );
    const collection = buildCountryFeatureCollection(
      dataset.countries,
      dataset.geographicViews,
      observations,
    );
    const chinaFeature = collection.features.find(
      (candidate) => candidate.properties.isoNumeric === '156',
    );
    const taiwanFeature = collection.features.find(
      (candidate) => candidate.properties.isoNumeric === '158',
    );

    expect(chinaFeature?.properties).toEqual(
      expect.objectContaining({
        countryId: 'country-cn',
        explorationCountryId: 'country-cn',
        metricEntityId: 'country-cn',
        metricValue: 83,
      }),
    );
    expect(taiwanFeature?.properties).toEqual(
      expect.objectContaining({
        countryId: 'country-tw',
        explorationCountryId: 'country-cn',
        metricEntityId: 'country-cn',
        metricValue: 83,
      }),
    );
  });

  it('composes the complete China exploration canvas into one render feature', () => {
    const observations = dataset.metricObservations.filter(
      (observation) =>
        observation.entityType === 'country' &&
        observation.scienceDomainId === 'physics' &&
        observation.period === '2026',
    );
    const countries = buildCountryFeatureCollection(
      dataset.countries,
      dataset.geographicViews,
      observations,
    );
    const canvas = buildExplorationCanvasFeatureCollection(
      countries,
      'country-cn',
    );
    const canvasFeature = canvas.features[0];
    const coordinates = canvasFeature.geometry.coordinates.flat(3) as number[];
    const coordinatePairs = Array.from(
      { length: coordinates.length / 2 },
      (_, index) => coordinates.slice(index * 2, index * 2 + 2),
    );

    expect(canvas.features).toHaveLength(1);
    expect(canvasFeature.properties).toEqual({
      explorationCountryId: 'country-cn',
      sourceIsoNumerics: ['156', '158'],
      metricValue: 83,
    });
    expect(canvasFeature.geometry.type).toBe('MultiPolygon');
    expect(
      coordinatePairs.some(
        ([longitude, latitude]) =>
          longitude >= 119 &&
          longitude <= 123 &&
          latitude >= 21 &&
          latitude <= 26,
      ),
    ).toBe(true);
  });

  it('cuts Russia antimeridian rings without joining disconnected geometry across the map', () => {
    const russia = {
      ...dataset.countries[0],
      id: 'country-rus',
      isoAlpha3: 'RUS',
      isoNumeric: '643',
      name: 'Russian Federation',
    };
    const russiaView = {
      ...dataset.geographicViews[0],
      id: 'geographic-view-rus',
      countryId: russia.id,
      geometryIsoNumerics: ['643'],
      locationCountryIds: [russia.id],
    };
    const collection = buildCountryFeatureCollection(
      [russia],
      [russiaView],
      [],
    );
    const feature = collection.features.find(
      (candidate) => candidate.properties.isoNumeric === '643',
    );

    expect(feature?.geometry.type).toBe('MultiPolygon');
    expect(maximumLongitudeJump(polygonRings(feature!.geometry))).toBeLessThanOrEqual(
      180,
    );

    const longitudes = polygonRings(feature!.geometry)
      .flat()
      .map((position) => position[0]);
    expect(longitudes.some((longitude) => longitude <= -170)).toBe(true);
    expect(longitudes.some((longitude) => longitude >= 170)).toBe(true);
    expect(
      polygonRings(feature!.geometry).some((ring) =>
        ring.some(
          ([longitude, latitude]) =>
            longitude >= 19 &&
            longitude <= 23 &&
            latitude >= 53 &&
            latitude <= 56,
        ),
      ),
    ).toBe(true);
  });

  it('unwraps an antimeridian country canvas into a compact camera span', () => {
    const russia = {
      ...dataset.countries[0],
      id: 'country-rus',
      isoAlpha3: 'RUS',
      isoNumeric: '643',
      name: 'Russian Federation',
    };
    const russiaView = {
      ...dataset.geographicViews[0],
      id: 'geographic-view-rus',
      countryId: russia.id,
      geometryIsoNumerics: ['643'],
      locationCountryIds: [russia.id],
    };
    const collection = buildCountryFeatureCollection(
      [russia],
      [russiaView],
      [],
    );
    const canvas = buildExplorationCanvasFeatureCollection(
      collection,
      russia.id,
    );
    const longitudes = canvas.features[0].geometry.coordinates
      .flat(3)
      .filter((value, index) => index % 2 === 0) as number[];
    const longitudeSpan = Math.max(...longitudes) - Math.min(...longitudes);

    expect(canvas.features).toHaveLength(1);
    expect(canvas.features[0].geometry.type).toBe('MultiPolygon');
    expect(longitudeSpan).toBeLessThan(180);
    expect(Math.max(...longitudes)).toBeGreaterThan(180);
    expect(
      geometryUsesUnwrappedWorldCopy(canvas.features[0].geometry),
    ).toBe(true);
  });

  it('aligns antimeridian holes with the matching split shell', () => {
    const split = splitGeometryAtAntimeridian({
      type: 'Polygon',
      coordinates: [
        [
          [170, 40],
          [-170, 40],
          [-170, 60],
          [170, 60],
          [170, 40],
        ],
        [
          [-178, 45],
          [-175, 45],
          [-175, 50],
          [-178, 50],
          [-178, 45],
        ],
      ],
    });

    expect(split.type).toBe('MultiPolygon');
    if (split.type !== 'MultiPolygon') {
      return;
    }
    const polygonWithHole = split.coordinates.find(
      (polygon) => polygon.length === 2,
    );
    expect(polygonWithHole).toBeDefined();
    expect(
      polygonWithHole?.[1]?.every(([longitude]) => longitude < 0),
    ).toBe(true);
    expect(
      split.coordinates
        .filter((polygon) => polygon[0]?.some(([longitude]) => longitude > 0))
        .every((polygon) => polygon.length === 1),
    ).toBe(true);
  });
});
