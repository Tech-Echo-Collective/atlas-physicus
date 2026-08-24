import type {
  Affiliation,
  AtlasDataset,
  Authorship,
  ExternalResource,
  Institution,
  MetricObservation,
  Paper,
  Researcher,
  ResearchField,
  ResearchGroup,
} from '../domain/models';

export interface AffiliationHistoryEntry {
  affiliation: Affiliation;
  institution: Institution;
  researchGroup: ResearchGroup | null;
}

export interface InstitutionProfileData {
  institution: Institution;
  resources: ExternalResource[];
  researchGroups: ResearchGroup[];
  affiliations: Affiliation[];
  researchers: Researcher[];
  papers: Paper[];
  metrics: MetricObservation[];
}

export interface ResearcherProfileData {
  researcher: Researcher;
  resources: ExternalResource[];
  fields: ResearchField[];
  affiliationHistory: AffiliationHistoryEntry[];
  papers: Paper[];
  collaborators: Researcher[];
  metrics: MetricObservation[];
}

export interface ResearchGroupProfileData {
  researchGroup: ResearchGroup;
  institution: Institution;
  resources: ExternalResource[];
  fields: ResearchField[];
  affiliations: Affiliation[];
  members: Researcher[];
  papers: Paper[];
}

function yearFromDate(value?: string): number | null {
  if (!value) {
    return null;
  }
  const year = Number(value.slice(0, 4));
  return Number.isInteger(year) ? year : null;
}

function affiliationIncludesYear(
  affiliation: Affiliation,
  year: number,
): boolean {
  const startYear = yearFromDate(affiliation.startDate) ?? affiliation.startYear;
  const endYear = yearFromDate(affiliation.endDate) ?? affiliation.endYear;
  return (
    (startYear === undefined || startYear === null || startYear <= year) &&
    (endYear === undefined || endYear === null || endYear >= year)
  );
}

function uniqueById<T extends { id: string }>(values: T[]): T[] {
  return [...new Map(values.map((value) => [value.id, value])).values()];
}

/**
 * Read-only enrichment layer over canonical graph records. It does not copy
 * profile data into entities, so a future API or database can assemble the same
 * views without changing profile components.
 */
export class ProfileService {
  private readonly institutionsById: Map<string, Institution>;
  private readonly researchersById: Map<string, Researcher>;
  private readonly groupsById: Map<string, ResearchGroup>;
  private readonly papersById: Map<string, Paper>;

  constructor(private readonly dataset: AtlasDataset) {
    this.institutionsById = new Map(
      dataset.institutions.map((institution) => [institution.id, institution]),
    );
    this.researchersById = new Map(
      dataset.researchers.map((researcher) => [researcher.id, researcher]),
    );
    this.groupsById = new Map(
      dataset.researchGroups.map((group) => [group.id, group]),
    );
    this.papersById = new Map(dataset.papers.map((paper) => [paper.id, paper]));
  }

  private resourcesFor(
    entityType: ExternalResource['entityType'],
    entityId: string,
  ): ExternalResource[] {
    return (this.dataset.externalResources ?? []).filter(
      (resource) =>
        resource.entityType === entityType && resource.entityId === entityId,
    );
  }

  private papersForResearchers(
    researcherIds: Set<string>,
    affiliations?: Affiliation[],
  ): Paper[] {
    const authorshipsByPaper = new Map<string, Authorship[]>();
    this.dataset.authorships.forEach((authorship) => {
      const list = authorshipsByPaper.get(authorship.paperId) ?? [];
      list.push(authorship);
      authorshipsByPaper.set(authorship.paperId, list);
    });

    return this.dataset.papers.filter((paper) => {
      const relevantAuthorships = (authorshipsByPaper.get(paper.id) ?? []).filter(
        (authorship) => researcherIds.has(authorship.researcherId),
      );
      const hasResearcher = relevantAuthorships.length > 0;
      if (!hasResearcher || !affiliations) {
        return hasResearcher;
      }
      return relevantAuthorships.some((authorship) =>
        affiliations.some(
          (affiliation) =>
            affiliation.researcherId === authorship.researcherId &&
            affiliationIncludesYear(affiliation, paper.year),
        ),
      );
    });
  }

  getInstitutionProfile(id: string): InstitutionProfileData | null {
    const institution = this.institutionsById.get(id);
    if (!institution) {
      return null;
    }
    const affiliations = this.dataset.affiliations.filter(
      (affiliation) => affiliation.institutionId === id,
    );
    const researcherIds = new Set(
      affiliations.map((affiliation) => affiliation.researcherId),
    );
    return {
      institution,
      resources: this.resourcesFor('institution', id),
      researchGroups: this.dataset.researchGroups.filter(
        (group) => group.institutionId === id,
      ),
      affiliations,
      researchers: this.dataset.researchers.filter((researcher) =>
        researcherIds.has(researcher.id),
      ),
      papers: this.papersForResearchers(researcherIds, affiliations),
      metrics: this.dataset.metricObservations.filter(
        (observation) =>
          observation.entityType === 'institution' && observation.entityId === id,
      ),
    };
  }

  getResearcherProfile(id: string): ResearcherProfileData | null {
    const researcher = this.researchersById.get(id);
    if (!researcher) {
      return null;
    }
    const affiliations = this.dataset.affiliations.filter(
      (affiliation) => affiliation.researcherId === id,
    );
    const paperIds = new Set(
      this.dataset.authorships
        .filter((authorship) => authorship.researcherId === id)
        .map((authorship) => authorship.paperId),
    );
    const collaboratorIds = new Set(
      this.dataset.authorships
        .filter(
          (authorship) =>
            paperIds.has(authorship.paperId) && authorship.researcherId !== id,
        )
        .map((authorship) => authorship.researcherId),
    );
    return {
      researcher,
      resources: this.resourcesFor('researcher', id),
      fields: this.dataset.fields.filter((field) =>
        researcher.fieldIds.includes(field.id),
      ),
      affiliationHistory: affiliations
        .map((affiliation) => ({
          affiliation,
          institution: this.institutionsById.get(affiliation.institutionId),
          researchGroup: affiliation.researchGroupId
            ? (this.groupsById.get(affiliation.researchGroupId) ?? null)
            : null,
        }))
        .filter(
          (entry): entry is AffiliationHistoryEntry =>
            entry.institution !== undefined,
        )
        .sort((left, right) =>
          (right.affiliation.startDate ?? String(right.affiliation.startYear ?? ''))
            .localeCompare(
              left.affiliation.startDate ??
                String(left.affiliation.startYear ?? ''),
            ),
        ),
      papers: [...paperIds]
        .map((paperId) => this.papersById.get(paperId))
        .filter((paper): paper is Paper => paper !== undefined)
        .sort((left, right) => right.year - left.year),
      collaborators: this.dataset.researchers.filter((candidate) =>
        collaboratorIds.has(candidate.id),
      ),
      metrics: this.dataset.metricObservations.filter(
        (observation) =>
          observation.entityType === 'researcher' && observation.entityId === id,
      ),
    };
  }

  getResearchGroupProfile(id: string): ResearchGroupProfileData | null {
    const researchGroup = this.groupsById.get(id);
    const institution = researchGroup
      ? this.institutionsById.get(researchGroup.institutionId)
      : undefined;
    if (!researchGroup || !institution) {
      return null;
    }
    const affiliations = this.dataset.affiliations.filter(
      (affiliation) => affiliation.researchGroupId === id,
    );
    const memberIds = new Set(
      affiliations.map((affiliation) => affiliation.researcherId),
    );
    return {
      researchGroup,
      institution,
      resources: this.resourcesFor('research-group', id),
      fields: this.dataset.fields.filter((field) =>
        researchGroup.fieldIds.includes(field.id),
      ),
      affiliations,
      members: this.dataset.researchers.filter((researcher) =>
        memberIds.has(researcher.id),
      ),
      papers: uniqueById(this.papersForResearchers(memberIds, affiliations)),
    };
  }
}
