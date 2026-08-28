import type {
  AtlasDataset,
  AtlasSearchResult,
  Institution,
} from '../domain/models';
import type {
  InstitutionProfileData,
  ResearcherProfileData,
} from '../profiles/ProfileService';

export interface LiveNavigationRepository {
  getInstitution(id: string): Promise<Institution | null>;
  getInstitutionProfile(id: string): Promise<InstitutionProfileData | null>;
  getResearcherProfile(id: string): Promise<ResearcherProfileData | null>;
  searchEntities(query: string, limit?: number): Promise<AtlasSearchResult[]>;
}

interface LiveEntityRoute {
  entityType: 'institution' | 'researcher';
  slug: string;
}

function mergeById<T extends { id: string }>(current: T[], incoming: T[]): T[] {
  const merged = new Map(current.map((item) => [item.id, item]));
  incoming.forEach((item) => merged.set(item.id, item));
  return [...merged.values()];
}

function routeSlug(value: string): string {
  return value
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLocaleLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '');
}

export function parseLiveEntityRoute(pathname: string): LiveEntityRoute | null {
  let segments: string[];
  try {
    segments = pathname
      .split('/')
      .filter(Boolean)
      .map((segment) => decodeURIComponent(segment));
  } catch {
    return null;
  }

  const atlasIndex = segments.findIndex(
    (segment) => segment.toLocaleLowerCase() === 'atlas',
  );
  const entityType = segments[atlasIndex + 1]?.toLocaleLowerCase();
  const slug = segments[atlasIndex + 2]?.toLocaleLowerCase();
  return atlasIndex >= 0 &&
    (entityType === 'institution' || entityType === 'researcher') &&
    Boolean(slug)
    ? { entityType, slug: slug as string }
    : null;
}

/** Country/entity routes render a focused canvas and do not need world rows. */
export function shouldBootstrapLiveWorldMap(pathname: string): boolean {
  let segments: string[];
  try {
    segments = pathname
      .split('/')
      .filter(Boolean)
      .map((segment) => decodeURIComponent(segment).toLocaleLowerCase());
  } catch {
    return true;
  }
  const atlasIndex = segments.indexOf('atlas');
  const view = segments[atlasIndex + 1];
  return !(
    atlasIndex >= 0 &&
    (view === 'country' || view === 'institution' || view === 'researcher')
  );
}

function directEntityIds(route: LiveEntityRoute): string[] {
  const prefix = `${route.entityType}-`;
  return Array.from(
    new Set([
      route.slug,
      route.slug.startsWith(prefix) ? route.slug : `${prefix}${route.slug}`,
    ]),
  );
}

function matchingSearchResult(
  route: LiveEntityRoute,
  results: AtlasSearchResult[],
): AtlasSearchResult | undefined {
  const prefix = `${route.entityType}-`;
  return results.find(
    (result) =>
      result.entityType === route.entityType &&
      (result.entityId.toLocaleLowerCase() === route.slug ||
        result.entityId.toLocaleLowerCase().replace(new RegExp(`^${prefix}`), '') ===
          route.slug ||
        routeSlug(result.label) === route.slug),
  );
}

function mergeInstitutionProfile(
  dataset: AtlasDataset,
  profile: InstitutionProfileData,
): AtlasDataset {
  return {
    ...dataset,
    institutions: mergeById(dataset.institutions, [profile.institution]),
    researchGroups: mergeById(dataset.researchGroups, profile.researchGroups),
    affiliations: mergeById(dataset.affiliations, profile.affiliations),
    researchers: mergeById(dataset.researchers, profile.researchers),
    papers: mergeById(dataset.papers, profile.papers),
    externalResources: mergeById(
      dataset.externalResources ?? [],
      profile.resources,
    ),
    metricObservations: mergeById(
      dataset.metricObservations,
      profile.metrics,
    ),
  };
}

function mergeResearcherProfile(
  dataset: AtlasDataset,
  profile: ResearcherProfileData,
): AtlasDataset {
  return {
    ...dataset,
    institutions: mergeById(
      dataset.institutions,
      profile.affiliationHistory.map((entry) => entry.institution),
    ),
    researchGroups: mergeById(
      dataset.researchGroups,
      profile.affiliationHistory.flatMap((entry) =>
        entry.researchGroup ? [entry.researchGroup] : [],
      ),
    ),
    affiliations: mergeById(
      dataset.affiliations,
      profile.affiliationHistory.map((entry) => entry.affiliation),
    ),
    researchers: mergeById(dataset.researchers, [
      profile.researcher,
      ...profile.collaborators,
    ]),
    papers: mergeById(dataset.papers, profile.papers),
    externalResources: mergeById(
      dataset.externalResources ?? [],
      profile.resources,
    ),
    metricObservations: mergeById(
      dataset.metricObservations,
      profile.metrics,
    ),
  };
}

async function searchEntityId(
  repository: LiveNavigationRepository,
  route: LiveEntityRoute,
): Promise<string | null> {
  const results = await repository.searchEntities(
    route.slug.replace(/-/g, ' '),
    20,
  );
  return matchingSearchResult(route, results)?.entityId ?? null;
}

/**
 * Hydrates only the canonical entity context needed to resolve a shared live
 * institution/researcher URL. Pages project prefixes are accepted because the
 * route parser locates the `atlas` segment rather than assuming it is first.
 */
export async function hydrateLiveNavigationDataset(
  repository: LiveNavigationRepository,
  dataset: AtlasDataset,
  pathname: string,
): Promise<AtlasDataset> {
  const route = parseLiveEntityRoute(pathname);
  if (!route) {
    return dataset;
  }

  const candidateIds = directEntityIds(route);
  if (route.entityType === 'institution') {
    for (const entityId of candidateIds) {
      const profile = await repository.getInstitutionProfile(entityId);
      if (profile) {
        return mergeInstitutionProfile(dataset, profile);
      }
      const institution = await repository.getInstitution(entityId);
      if (institution) {
        return {
          ...dataset,
          institutions: mergeById(dataset.institutions, [institution]),
        };
      }
    }
    const searchedId = await searchEntityId(repository, route);
    if (!searchedId) return dataset;
    const profile = await repository.getInstitutionProfile(searchedId);
    if (profile) return mergeInstitutionProfile(dataset, profile);
    const institution = await repository.getInstitution(searchedId);
    return institution
      ? {
          ...dataset,
          institutions: mergeById(dataset.institutions, [institution]),
        }
      : dataset;
  }

  for (const entityId of candidateIds) {
    const profile = await repository.getResearcherProfile(entityId);
    if (profile) {
      return mergeResearcherProfile(dataset, profile);
    }
  }
  const searchedId = await searchEntityId(repository, route);
  if (!searchedId) return dataset;
  const profile = await repository.getResearcherProfile(searchedId);
  return profile ? mergeResearcherProfile(dataset, profile) : dataset;
}
