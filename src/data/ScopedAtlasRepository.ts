import type { AtlasDataset, AtlasRepository } from '../domain/models';
import type { LiveNavigationRepository } from './LiveNavigationHydration';

export interface AtlasEntityScope {
  entityType: 'institution' | 'researcher' | 'research-group' | 'paper' | 'research-field';
  id: string;
}

export type AtlasEntityContext = Pick<AtlasDataset,
  'affiliations' | 'authorships' | 'externalResources'> &
  Partial<Pick<AtlasDataset, 'papers' | 'researchers'>>;

/** Complete for one selected context, never a claim that unloaded facts are absent. */
export interface ScopedAtlasRepository extends AtlasRepository, LiveNavigationRepository {
  loadEntityContext(scope: AtlasEntityScope, signal?: AbortSignal): Promise<AtlasEntityContext>;
  readonly paperAuthorCounts: Readonly<Record<string, number>>;
}

export function hasScopedEntityHydration(repository: AtlasRepository | null): repository is ScopedAtlasRepository {
  return repository !== null && 'loadEntityContext' in repository && typeof repository.loadEntityContext === 'function';
}

/** Replace, do not accumulate a client-side corpus when navigating profiles. */
export function replaceEntityContext(dataset: AtlasDataset, context: AtlasEntityContext): AtlasDataset {
  return { ...dataset, affiliations: context.affiliations, authorships: context.authorships,
    externalResources: context.externalResources ?? [],
    ...(context.papers ? { papers: context.papers } : {}),
    ...(context.researchers ? { researchers: context.researchers } : {}) };
}
