import type {
  Affiliation,
  Authorship,
  HistoricalEvent,
  Institution,
  Paper,
  Researcher,
  ResearchField,
} from '../../domain/models';

interface FieldOverviewProps {
  field: ResearchField;
  institutions: Institution[];
  researchers: Researcher[];
  affiliations: Affiliation[];
  papers: Paper[];
  authorships: Authorship[];
  historicalEvents: HistoricalEvent[];
  onClose: () => void;
}

export function FieldOverview({
  field,
  institutions,
  researchers,
  affiliations,
  papers,
  authorships,
  historicalEvents,
  onClose,
}: FieldOverviewProps) {
  const fieldInstitutions = institutions
    .filter((institution) => institution.fieldIds.includes(field.id))
    .slice(0, 6);
  const fieldResearchers = researchers
    .filter((researcher) => researcher.fieldIds.includes(field.id))
    .slice(0, 8);
  const fieldPapers = papers
    .filter((paper) => paper.fieldIds.includes(field.id))
    .sort((left, right) => right.year - left.year);
  const fieldEvents = historicalEvents
    .filter((event) => event.fieldId === field.id)
    .sort((left, right) => left.year - right.year);
  const affiliationsByResearcherId = new Map(
    affiliations.map((affiliation) => [affiliation.researcherId, affiliation]),
  );
  const institutionsById = new Map(
    institutions.map((institution) => [institution.id, institution]),
  );
  const authorCountByPaperId = new Map<string, number>();
  authorships.forEach((authorship) => {
    authorCountByPaperId.set(
      authorship.paperId,
      (authorCountByPaperId.get(authorship.paperId) ?? 0) + 1,
    );
  });

  return (
    <aside className="field-overview" aria-live="polite">
      <header className="field-overview-header">
        <button className="entity-back" type="button" onClick={onClose}>
          ← Back to Atlas
        </button>
        <p className="section-kicker">Research field overview · demo</p>
        <span className="field-overview-code">{field.id}</span>
        <h2>{field.label}</h2>
        <p>{field.description}</p>
      </header>

      <div className="field-overview-grid">
        <section className="entity-section field-history">
          <div className="entity-section-heading">
            <div>
              <p className="section-kicker">Historical milestones</p>
              <h3>Demo chronology</h3>
            </div>
            <span>Not comprehensive</span>
          </div>
          {fieldEvents.length > 0 ? (
            <ol className="event-list">
              {fieldEvents.map((event) => (
                <li key={event.id}>
                  <time>{event.year}</time>
                  <div>
                    <strong>{event.title}</strong>
                    <p>{event.summary}</p>
                  </div>
                </li>
              ))}
            </ol>
          ) : (
            <p className="muted-copy">No synthetic milestones are connected.</p>
          )}
        </section>

        <section className="entity-section">
          <div className="entity-section-heading">
            <div>
              <p className="section-kicker">Institutions</p>
              <h3>Major nodes in this demo</h3>
            </div>
            <span>Unranked sample</span>
          </div>
          <ul className="field-entity-list">
            {fieldInstitutions.map((institution) => (
              <li key={institution.id}>
                <strong>{institution.name}</strong>
                <span>{institution.city}</span>
              </li>
            ))}
          </ul>
        </section>

        <section className="entity-section">
          <div className="entity-section-heading">
            <div>
              <p className="section-kicker">Researchers</p>
              <h3>Associated demo community</h3>
            </div>
            <span>Not ranked</span>
          </div>
          <ul className="field-entity-list">
            {fieldResearchers.map((researcher) => {
              const affiliation = affiliationsByResearcherId.get(researcher.id);
              return (
                <li key={researcher.id}>
                  <strong>{researcher.name}</strong>
                  <span>
                    {affiliation
                      ? institutionsById.get(affiliation.institutionId)?.name
                      : 'Affiliation unavailable'}
                  </span>
                </li>
              );
            })}
          </ul>
        </section>

        <section className="entity-section">
          <div className="entity-section-heading">
            <div>
              <p className="section-kicker">Representative papers</p>
              <h3>Preparation records</h3>
            </div>
            <span>Synthetic sample</span>
          </div>
          <ol className="paper-list">
            {fieldPapers.map((paper) => (
              <li key={paper.id}>
                <div>
                  <time>{paper.year}</time>
                  <span>{authorCountByPaperId.get(paper.id) ?? 0} authors</span>
                </div>
                <strong>{paper.title}</strong>
                <p>{paper.summary}</p>
              </li>
            ))}
          </ol>
        </section>
      </div>

      <p className="entity-disclaimer field-overview-disclaimer">
        This overview uses incomplete synthetic content to prepare the field
        exploration model. It does not claim historical or community completeness.
      </p>
    </aside>
  );
}
