import type {
  AtlasRepository,
  DatasetUpdate,
  ExternalResource,
  IdentityEntityType,
  IdentityResolution,
  IdentityResolutionStatus,
  RawEntityRecord,
  SourceSnapshot,
} from '../domain/models';
import type { ScientificKnowledgeGraph } from '../knowledge/KnowledgeGraph';
import type {
  InstitutionProfileData,
  ResearcherProfileData,
  ResearchGroupProfileData,
} from '../profiles/ProfileService';

/**
 * Read-side contract used by the Atlas application. A future FastAPI adapter
 * can implement this contract without changing profile or visualization code.
 */
export interface ScientificAtlasRepository extends AtlasRepository {
  getRawEntityRecords(entityType?: IdentityEntityType): Promise<RawEntityRecord[]>;
  getIdentityResolutions(
    status?: IdentityResolutionStatus,
  ): Promise<IdentityResolution[]>;
  getExternalResources(
    entityType?: ExternalResource['entityType'],
    entityId?: string,
  ): Promise<ExternalResource[]>;
  getSourceSnapshots(): Promise<SourceSnapshot[]>;
  getDatasetUpdates(): Promise<DatasetUpdate[]>;
  getKnowledgeGraph(): Promise<ScientificKnowledgeGraph>;
  getInstitutionProfile(id: string): Promise<InstitutionProfileData | null>;
  getResearcherProfile(id: string): Promise<ResearcherProfileData | null>;
  getResearchGroupProfile(id: string): Promise<ResearchGroupProfileData | null>;
}

/**
 * Network boundary for a future API client. It deliberately transports
 * versioned resources rather than exposing database details to the frontend.
 */
export interface AtlasApiTransport {
  getDatasetVersion(): Promise<string>;
  fetchRepositorySnapshot(): Promise<unknown>;
  searchCanonicalEntities(query: string, limit?: number): Promise<unknown>;
}

/**
 * Persistence boundary for a future PostgreSQL adapter. This alpha provides
 * only an in-memory implementation through StaticAtlasRepository.
 */
export interface CanonicalEntityPersistence {
  readRepositorySnapshot(version?: string): Promise<unknown>;
  readSourceSnapshot(snapshotId: string): Promise<unknown>;
}
