import type {
  AtlasUpdateStatus,
  AtlasRepository,
  DatasetUpdate,
  ExternalResource,
  IdentityEntityType,
  IdentityResolution,
  IdentityResolutionSummary,
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
  /** Live adapters may expose operational summaries; static sources stay offline. */
  getUpdateStatus?(): Promise<AtlasUpdateStatus>;
  getIdentityResolutionSummary?(): Promise<IdentityResolutionSummary>;
}

/**
 * Network boundary implemented by APIRepository. It deliberately transports
 * versioned resources rather than exposing database details to the frontend.
 */
export interface AtlasApiTransport {
  getDatasetVersion(): Promise<string>;
  fetchRepositorySnapshot(): Promise<unknown>;
  searchCanonicalEntities(query: string, limit?: number): Promise<unknown>;
  getUpdateStatus(): Promise<AtlasUpdateStatus>;
  getIdentityResolutionSummary(): Promise<IdentityResolutionSummary>;
}

/**
 * Persistence-facing read boundary. The static repository implements it in
 * memory, while the FastAPI/PostgreSQL service implements the live equivalent
 * without exposing SQL details to UI code.
 */
export interface CanonicalEntityPersistence {
  readRepositorySnapshot(version?: string): Promise<unknown>;
  readSourceSnapshot(snapshotId: string): Promise<unknown>;
}
