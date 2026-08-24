import type {
  Affiliation,
  Authorship,
  HistoricalEvent,
  Institution,
  Paper,
  Researcher,
  ResearchField,
  ResearchGroup,
} from '../../domain/models';

interface ResearcherProfileProps {
  researcher: Researcher;
  affiliation: Affiliation | null;
  institution: Institution;
  group: ResearchGroup | null;
  fields: ResearchField[];
  papers: Paper[];
  authorships: Authorship[];
  historicalEvents: HistoricalEvent[];
  onBackToInstitution: () => void;
}

const linkLabels = {
  institutionalHomepage: 'Institutional homepage',
  personalWebsite: 'Personal website',
  arxiv: 'arXiv profile',
  github: 'GitHub',
} as const;

export function ResearcherProfile({
  researcher,
  affiliation,
  institution,
  group,
  fields,
  papers,
  authorships,
  historicalEvents,
  onBackToInstitution,
}: ResearcherProfileProps) {
  const researcherPaperIds = new Set(
    authorships
      .filter((authorship) => authorship.researcherId === researcher.id)
      .map((authorship) => authorship.paperId),
  );
  const researcherPapers = papers
    .filter((paper) => researcherPaperIds.has(paper.id))
    .sort((left, right) => right.year - left.year);
  const relatedEvents = historicalEvents
    .filter((event) => event.relatedResearcherIds.includes(researcher.id))
    .sort((left, right) => left.year - right.year);
  const fieldsById = new Map(fields.map((field) => [field.id, field]));
  const externalLinks = Object.entries(researcher.externalLinks ?? {}) as Array<
    [keyof typeof linkLabels, string]
  >;

  return (
    <aside className="entity-view researcher-profile" aria-live="polite">
      <header className="entity-view-header researcher-profile-header">
        <button
          className="entity-back"
          type="button"
          onClick={onBackToInstitution}
        >
          ← Back to Institution
        </button>
        <p className="section-kicker">Researcher profile · synthetic demo</p>
        <div className="researcher-identity">
          <span className="researcher-avatar researcher-avatar--large" aria-hidden="true">
            {researcher.name
              .split(' ')
              .map((part) => part[0])
              .join('')}
          </span>
          <div>
            <h2>{researcher.name}</h2>
            <p>{institution.name}</p>
          </div>
        </div>
      </header>

      <div className="entity-view-scroll">
        <section className="entity-section profile-affiliation">
          <p className="section-kicker">Affiliation</p>
          <h3>{group?.name ?? institution.name}</h3>
          <p>{institution.name}</p>
          {affiliation?.startYear && (
            <small>Demo affiliation from {affiliation.startYear}</small>
          )}
        </section>

        <section className="entity-section">
          <div className="entity-section-heading">
            <div>
              <p className="section-kicker">Research fields</p>
              <h3>Connected areas</h3>
            </div>
          </div>
          <div className="entity-field-tags">
            {researcher.fieldIds.map((fieldId) => (
              <span key={fieldId}>
                {fieldsById.get(fieldId)?.label ?? fieldId}
              </span>
            ))}
          </div>
        </section>

        {externalLinks.length > 0 && (
          <section className="entity-section">
            <div className="entity-section-heading">
              <div>
                <p className="section-kicker">External links</p>
                <h3>Available references</h3>
              </div>
              <span>Demo metadata</span>
            </div>
            <div className="external-link-list">
              {externalLinks.map(([key, href]) => (
                <a key={key} href={href} target="_blank" rel="noreferrer">
                  <span>{linkLabels[key]}</span>
                  <i aria-hidden="true">↗</i>
                </a>
              ))}
            </div>
          </section>
        )}

        <section className="entity-section">
          <div className="entity-section-heading">
            <div>
              <p className="section-kicker">Paper connections</p>
              <h3>Representative demo records</h3>
            </div>
            <span>Not a performance list</span>
          </div>
          {researcherPapers.length > 0 ? (
            <ol className="paper-list">
              {researcherPapers.map((paper) => (
                <li key={paper.id}>
                  <div>
                    <time>{paper.year}</time>
                    <span>synthetic</span>
                  </div>
                  <strong>{paper.title}</strong>
                  <p>{paper.summary}</p>
                </li>
              ))}
            </ol>
          ) : (
            <p className="muted-copy">No representative demo papers are connected.</p>
          )}
        </section>

        {relatedEvents.length > 0 && (
          <section className="entity-section">
            <div className="entity-section-heading">
              <div>
                <p className="section-kicker">Historical connections</p>
                <h3>Related demo events</h3>
              </div>
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

        <p className="entity-disclaimer">
          This synthetic profile describes ecosystem relationships only. It is
          not a ranking, recommendation, evaluation, or admission prediction.
        </p>
      </div>
    </aside>
  );
}
