import demoData from '../../data/demo/atlas.json';
import { atlasDatasetSchema } from '../../domain/schemas';
import {
  buildCountryFeatureCollection,
  buildExplorationCanvasFeatureCollection,
} from './GeographicGeometryLayer';

const dataset = atlasDatasetSchema.parse(demoData);

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
});
