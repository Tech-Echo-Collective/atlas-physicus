import demoData from '../../data/demo/atlas.json';
import { atlasDatasetSchema } from '../../domain/schemas';
import {
  getInstitutionsForGeographicView,
  resolveExplorationCountryId,
} from './GeographicEntityMapping';

const dataset = atlasDatasetSchema.parse(demoData);

describe('geographic entity mapping', () => {
  it('maps every configured source geometry to its exploration view', () => {
    expect(
      resolveExplorationCountryId(
        '158',
        dataset.countries,
        dataset.geographicViews,
      ),
    ).toBe('country-cn');
    expect(
      resolveExplorationCountryId(
        '156',
        dataset.countries,
        dataset.geographicViews,
      ),
    ).toBe('country-cn');
  });

  it('includes institutions from every location entity in a geographic view', () => {
    const institutions = getInstitutionsForGeographicView(
      dataset.institutions,
      'country-cn',
      dataset.geographicViews,
    );

    expect(institutions.map((institution) => institution.id)).toEqual(
      expect.arrayContaining([
        'institution-eastern',
        'institution-taipei',
      ]),
    );
    expect(institutions.map((institution) => institution.id)).not.toContain(
      'institution-tokyo',
    );
  });

  it('falls back to direct ISO matching when no view is configured', () => {
    expect(resolveExplorationCountryId('158', dataset.countries, [])).toBe(
      'country-tw',
    );
  });
});
