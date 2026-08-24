import { getAtlasMapLayerHierarchy } from './MapLayerHierarchy';

describe('map information hierarchy', () => {
  it('shows only the country heatmap in World View', () => {
    expect(getAtlasMapLayerHierarchy(null, null)).toEqual({
      countryHeatmap: 'visible',
      countryCanvas: 'none',
      institutionHeatmap: 'none',
      institutionSelection: 'none',
    });
  });

  it('replaces the country heatmap with the country canvas and institution heatmap', () => {
    expect(getAtlasMapLayerHierarchy('country-us', null)).toEqual({
      countryHeatmap: 'none',
      countryCanvas: 'visible',
      institutionHeatmap: 'visible',
      institutionSelection: 'none',
    });
  });

  it('preserves institution context and highlights the selected institution', () => {
    expect(
      getAtlasMapLayerHierarchy('country-us', 'institution-caltech'),
    ).toEqual({
      countryHeatmap: 'none',
      countryCanvas: 'visible',
      institutionHeatmap: 'visible',
      institutionSelection: 'visible',
    });
  });
});
