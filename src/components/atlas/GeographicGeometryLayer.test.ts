import demoData from '../../data/demo/atlas.json';
import { atlasDatasetSchema } from '../../domain/schemas';
import { buildCountryFeatureCollection } from './GeographicGeometryLayer';

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

  it('preserves native heatmap scoring independently from view membership', () => {
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
        score: 83,
      }),
    );
    expect(taiwanFeature?.properties).toEqual(
      expect.objectContaining({
        countryId: 'country-tw',
        explorationCountryId: 'country-cn',
      }),
    );
    expect(taiwanFeature?.properties.score).toBeUndefined();
  });
});
