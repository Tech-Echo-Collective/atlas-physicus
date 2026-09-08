import historicalFixture from '../demo/atlas.json';
import { geographicViewSchema } from '../../domain/schemas';
import reference from './geographic-views.json';

describe('non-observational geographic display policy', () => {
  it('preserves the existing exact canvas membership without copying demo evidence', () => {
    const expected = historicalFixture.geographicViews.map(
      ({ id, countryId, geometryIsoNumerics, locationCountryIds }) =>
        ({ id, countryId, geometryIsoNumerics, locationCountryIds }),
    );
    expect(reference.views).toEqual(expected);
    for (const view of reference.views) {
      expect('provenance' in view).toBe(false);
      expect(geographicViewSchema.parse({
        ...view,
        provenance: { source: reference.source, sourceType: 'derived',
          version: reference.version, status: 'verified' },
      }).geometryIsoNumerics).toEqual(view.geometryIsoNumerics);
    }
  });
});
