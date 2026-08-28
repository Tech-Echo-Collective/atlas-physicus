import { vi } from 'vitest';
import demoData from './demo/atlas.json';
import { defaultMetricId, type AtlasDataset } from '../domain/models';
import { atlasDatasetSchema } from '../domain/schemas';
import {
  reconcileNavigationForDataSource,
} from './AtlasDataSources';
import {
  hydrateLiveNavigationDataset,
  parseLiveEntityRoute,
  shouldBootstrapLiveWorldMap,
  type LiveNavigationRepository,
} from './LiveNavigationHydration';
import { resolveAtlasLocation } from '../navigation/AtlasNavigation';
import { ProfileService } from '../profiles/ProfileService';

const dataset = atlasDatasetSchema.parse(demoData);
const profileService = new ProfileService(dataset);
const mapOnlyDataset: AtlasDataset = {
  ...dataset,
  institutions: [],
  researchers: [],
  researchGroups: [],
  affiliations: [],
  papers: [],
  authorships: [],
  externalResources: [],
  metricObservations: [],
};

function repositoryFixture(): LiveNavigationRepository {
  return {
    getInstitution: vi.fn(async (id: string) =>
      dataset.institutions.find((institution) => institution.id === id) ?? null,
    ),
    getInstitutionProfile: vi.fn(async (id: string) =>
      profileService.getInstitutionProfile(id),
    ),
    getResearcherProfile: vi.fn(async (id: string) =>
      profileService.getResearcherProfile(id),
    ),
    searchEntities: vi.fn(async () => []),
  };
}

describe('live shared-route hydration', () => {
  it('recognizes entity routes below a GitHub Pages project prefix', () => {
    expect(
      parseLiveEntityRoute(
        '/Physics-Atlas-Web/atlas/institution/mit',
      ),
    ).toEqual({ entityType: 'institution', slug: 'mit' });
  });

  it('loads world rows only for world/field routes', () => {
    expect(shouldBootstrapLiveWorldMap('/atlas/physics/hep-th')).toBe(true);
    expect(
      shouldBootstrapLiveWorldMap(
        '/Physics-Atlas-Web/atlas/country/united-states',
      ),
    ).toBe(false);
    expect(
      shouldBootstrapLiveWorldMap('/atlas/institution/mit'),
    ).toBe(false);
    expect(
      shouldBootstrapLiveWorldMap('/atlas/researcher/jonah-okafor'),
    ).toBe(false);
  });

  it('hydrates an institution before resolving a direct live route', async () => {
    const hydrated = await hydrateLiveNavigationDataset(
      repositoryFixture(),
      mapOnlyDataset,
      '/atlas/institution/mit',
    );
    const route = resolveAtlasLocation(
      {
        pathname: '/atlas/institution/mit',
        search: '?source=live-api&domain=physics&year=2026',
      },
      hydrated,
    );
    const reconciled = reconcileNavigationForDataSource(
      route,
      hydrated,
      defaultMetricId,
      { allowMissingMetricObservations: true },
    );

    expect(reconciled.selectedCountryId).toBe('country-us');
    expect(reconciled.selectedInstitutionId).toBe('institution-mit');
    expect(hydrated.researchGroups).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ institutionId: 'institution-mit' }),
      ]),
    );
  });

  it('hydrates affiliation context before resolving a direct researcher route', async () => {
    const hydrated = await hydrateLiveNavigationDataset(
      repositoryFixture(),
      mapOnlyDataset,
      '/Physics-Atlas-Web/atlas/researcher/jonah-okafor',
    );
    const route = resolveAtlasLocation(
      {
        pathname: '/atlas/researcher/jonah-okafor',
        search:
          '?source=live-api&domain=physics&field=hep-th&year=2021&group=group-mit-fields',
      },
      hydrated,
    );
    const reconciled = reconcileNavigationForDataSource(
      route,
      hydrated,
      defaultMetricId,
      { allowMissingMetricObservations: true },
    );

    expect(reconciled).toEqual(
      expect.objectContaining({
        selectedFieldId: 'hep-th',
        selectedYear: 2021,
        selectedCountryId: 'country-us',
        selectedInstitutionId: 'institution-mit',
        selectedResearchGroupId: 'group-mit-fields',
        selectedResearcherId: 'researcher-jonah-okafor',
      }),
    );
    expect(hydrated.affiliations).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          researcherId: 'researcher-jonah-okafor',
          institutionId: 'institution-mit',
        }),
      ]),
    );
  });
});
