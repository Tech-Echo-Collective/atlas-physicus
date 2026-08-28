import demoData from '../data/demo/atlas.json';
import { atlasDatasetSchema } from '../domain/schemas';
import {
  buildAtlasUrl,
  resolveAtlasLocation,
} from './AtlasNavigation';

const dataset = atlasDatasetSchema.parse(demoData);

describe('atlas URL navigation', () => {
  it('restores domain and field state from a shareable URL', () => {
    const state = resolveAtlasLocation(
      { pathname: '/atlas/physics/hep-th', search: '?year=2000' },
      dataset,
    );

    expect(state).toEqual(
      expect.objectContaining({
        selectedDomainId: 'physics',
        selectedFieldId: 'hep-th',
        selectedYear: 2000,
        selectedCountryId: null,
      }),
    );
  });

  it('restores continuous in-range years even without an observation', () => {
    const state = resolveAtlasLocation(
      { pathname: '/atlas/physics/hep-th', search: '?year=1975' },
      dataset,
    );

    expect(state.selectedYear).toBe(1975);
  });

  it('preserves an explicit year when a neutral live map has no country observations', () => {
    const state = resolveAtlasLocation(
      { pathname: '/atlas/physics', search: '?year=2021' },
      { ...dataset, metricObservations: [] },
    );

    expect(state.selectedYear).toBe(2021);
  });

  it('preserves a live requested year outside the bounded bootstrap period', () => {
    const state = resolveAtlasLocation(
      { pathname: '/atlas/physics', search: '?year=2000' },
      {
        ...dataset,
        metadata: { ...dataset.metadata, datasetKind: 'live-api' },
        metricObservations: dataset.metricObservations.filter(
          (observation) =>
            observation.entityType === 'country' &&
            observation.period === '2026',
        ),
      },
    );

    expect(state.selectedYear).toBe(2000);
  });

  it('restores the complete hierarchy for institution and researcher links', () => {
    const institutionState = resolveAtlasLocation(
      {
        pathname: '/atlas/institution/caltech',
        search: '?domain=physics&field=hep-th&year=2026',
      },
      dataset,
    );
    const researcherState = resolveAtlasLocation(
      {
        pathname: '/atlas/researcher/jonah-okafor',
        search: '?domain=physics&field=hep-th&year=2026&group=group-mit-fields',
      },
      dataset,
    );

    expect(institutionState).toEqual(
      expect.objectContaining({
        selectedCountryId: 'country-us',
        selectedInstitutionId: 'institution-caltech',
      }),
    );
    expect(researcherState).toEqual(
      expect.objectContaining({
        selectedCountryId: 'country-us',
        selectedInstitutionId: 'institution-mit',
        selectedResearchGroupId: 'group-mit-fields',
        selectedResearcherId: 'researcher-jonah-okafor',
      }),
    );
  });

  it('resolves location membership without changing geographic identity data', () => {
    const state = resolveAtlasLocation(
      { pathname: '/atlas/country/taiwan', search: '?year=2026' },
      dataset,
    );

    expect(state.selectedCountryId).toBe('country-cn');
    expect(dataset.countries.find((country) => country.id === 'country-tw')).toEqual(
      expect.objectContaining({ name: 'Taiwan' }),
    );
  });

  it('serializes the current hierarchy into a canonical URL', () => {
    const state = resolveAtlasLocation(
      {
        pathname: '/atlas/researcher/jonah-okafor',
        search: '?domain=physics&field=hep-th&year=2026&group=group-mit-fields',
      },
      dataset,
    );

    expect(buildAtlasUrl(state, dataset)).toBe(
      '/atlas/researcher/jonah-okafor?year=2026&domain=physics&field=hep-th&group=group-mit-fields',
    );
  });
});
