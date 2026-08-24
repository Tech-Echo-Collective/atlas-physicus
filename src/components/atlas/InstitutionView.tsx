import type {
  Affiliation,
  Authorship,
  Country,
  HistoricalEvent,
  Institution,
  MetricObservation,
  Paper,
  Researcher,
  ResearchField,
  ResearchGroup,
} from '../../domain/models';
import { InstitutionActivityHistory } from './InstitutionActivityHistory';

interface InstitutionViewProps {
  institution: Institution;
  explorationCountry: Country;
  locationCountry: Country;
  fields: ResearchField[];
  activeFieldId: string | null;
  groups: ResearchGroup[];
  affiliations: Affiliation[];
  researchers: Researcher[];
  papers: Paper[];
  authorships: Authorship[];
  historicalEvents: HistoricalEvent[];
  activityObservations: MetricObservation[];
  selectedGroupId: string | null;
  onGroupSelect: (groupId: string) => void;
  onResearcherSelect: (researcherId: string) => void;
  onBackToCountry: () => void;
}

export function InstitutionView({
  institution,
  explorationCountry,
  locationCountry,
  fields,
  activeFieldId,
  groups,
  affiliations,
  researchers,
  papers,
  authorships,
  historicalEvents,
  activityObservations,
  selectedGroupId,
  onGroupSelect,
  onResearcherSelect,
  onBackToCountry,
}: InstitutionViewProps) {
  const activeGroup =
    groups.find((group) => group.id === selectedGroupId) ?? groups[0] ?? null;
  const activeAffiliations = affiliations.filter(
    (affiliation) =>
      affiliation.institutionId === institution.id &&
      (!activeGroup || affiliation.researchGroupId === activeGroup.id),
  );
  const activeResearcherIds = new Set(
    activeAffiliations.map((affiliation) => affiliation.researcherId),
  );
  const activeResearchers = researchers.filter(
    (researcher) =>
      activeResearcherIds.has(researcher.id) &&
      (!activeFieldId || researcher.fieldIds.includes(activeFieldId)),
  );
  const institutionResearcherIds = new Set(
    affiliations
      .filter((affiliation) => affiliation.institutionId === institution.id)
      .map((affiliation) => affiliation.researcherId),
  );
  const paperIds = new Set(
    authorships
      .filter((authorship) =>
        institutionResearcherIds.has(authorship.researcherId),
      )
      .map((authorship) => authorship.paperId),
  );
  const representativePapers = papers
    .filter(
      (paper) =>
        paperIds.has(paper.id) &&
        (!activeFieldId || paper.fieldIds.includes(activeFieldId)),
    )
    .sort((left, right) => right.year - left.year)
    .slice(0, 4);
  const relatedEvents = historicalEvents
    .filter(
      (event) =>
        (!activeFieldId || event.fieldId === activeFieldId) &&
        event.relatedInstitutionIds.includes(institution.id),
    )
    .sort((left, right) => left.year - right.year);
  const fieldsById = new Map(fields.map((field) => [field.id, field]));
  const authorsByPaperId = new Map<string, string[]>();

  representativePapers.forEach((paper) => {
    const authorNames = authorships
      .filter((authorship) => authorship.paperId === paper.id)
      .sort((left, right) => left.authorPosition - right.authorPosition)
      .map(
        (authorship) =>
          researchers.find(
            (researcher) => researcher.id === authorship.researcherId,
          )?.name,
      )
      .filter((name): name is string => Boolean(name));
    authorsByPaperId.set(paper.id, authorNames);
  });

  return (
    <aside className="entity-view institution-view" aria-live="polite">
      <header className="entity-view-header">
        <button className="entity-back" type="button" onClick={onBackToCountry}>
          ← Back to {explorationCountry.name}
        </button>
        <p className="section-kicker">Institution ecosystem · demo</p>
        <h2>{institution.name}</h2>
        <p>
          {institution.city}, {locationCountry.name}
        </p>
        <div className="entity-field-tags" aria-label="Associated research fields">
          {institution.fieldIds.map((fieldId) => (
            <span key={fieldId} data-active={fieldId === activeFieldId}>
              {fieldsById.get(fieldId)?.id ?? fieldId}
            </span>
          ))}
        </div>
      </header>

      <div className="entity-view-scroll">
        <InstitutionActivityHistory observations={activityObservations} />

        <section className="entity-section">
          <div className="entity-section-heading">
            <div>
              <p className="section-kicker">Research groups</p>
              <h3>Community structure</h3>
            </div>
            <span>{groups.length} demo groups</span>
          </div>
          {groups.length > 0 ? (
            <div className="group-selector">
              {groups.map((group) => (
                <button
                  key={group.id}
                  type="button"
                  data-active={group.id === activeGroup?.id}
                  onClick={() => onGroupSelect(group.id)}
                >
                  <strong>{group.name}</strong>
                  <small>{group.description}</small>
                </button>
              ))}
            </div>
          ) : (
            <p className="muted-copy">No demo research groups are connected.</p>
          )}
        </section>

        <section className="entity-section">
          <div className="entity-section-heading">
            <div>
              <p className="section-kicker">Affiliated researchers</p>
              <h3>{activeGroup?.name ?? 'Institution researchers'}</h3>
            </div>
            <span>Not ranked</span>
          </div>
          {activeResearchers.length > 0 ? (
            <div className="researcher-list">
              {activeResearchers.map((researcher) => (
                <button
                  key={researcher.id}
                  type="button"
                  onClick={() => onResearcherSelect(researcher.id)}
                >
                  <span className="researcher-avatar" aria-hidden="true">
                    {researcher.name
                      .split(' ')
                      .map((part) => part[0])
                      .join('')}
                  </span>
                  <span>
                    <strong>{researcher.name}</strong>
                    <small>{researcher.fieldIds.join(' · ')}</small>
                  </span>
                  <i aria-hidden="true">→</i>
                </button>
              ))}
            </div>
          ) : (
            <p className="muted-copy">
              No affiliated demo researcher is connected to this group and scope.
            </p>
          )}
        </section>

        {relatedEvents.length > 0 && (
          <section className="entity-section">
            <div className="entity-section-heading">
              <div>
                <p className="section-kicker">Historical connections</p>
                <h3>Timeline links</h3>
              </div>
              <span>Preparation layer</span>
            </div>
            <ol className="event-list">
              {relatedEvents.map((event) => (
                <li key={event.id}>
                  <time>{event.year}</time>
                  <div>
                    <strong>{event.title}</strong>
                    <p>{event.summary}</p>
                  </div>
                </li>
              ))}
            </ol>
          </section>
        )}

        <section className="entity-section">
          <div className="entity-section-heading">
            <div>
              <p className="section-kicker">Representative papers</p>
              <h3>Demo publication connections</h3>
            </div>
            <span>Incomplete sample</span>
          </div>
          {representativePapers.length > 0 ? (
            <ol className="paper-list">
              {representativePapers.map((paper) => (
                <li key={paper.id}>
                  <div>
                    <time>{paper.year}</time>
                    <span>synthetic</span>
                  </div>
                  <strong>{paper.title}</strong>
                  <p>{authorsByPaperId.get(paper.id)?.join(', ')}</p>
                </li>
              ))}
            </ol>
          ) : (
            <p className="muted-copy">No representative demo papers for this scope.</p>
          )}
        </section>

        <p className="entity-disclaimer">
          All people, groups, papers, events, and activity values shown here are
          synthetic interface data. Ordering does not express scientific value.
        </p>
      </div>
    </aside>
  );
}
