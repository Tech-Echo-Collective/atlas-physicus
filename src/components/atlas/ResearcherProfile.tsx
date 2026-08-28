import type {
  Affiliation,
  Authorship,
  ExternalResource,
  HistoricalEvent,
  IdentityResolution,
  Institution,
  Paper,
  Researcher,
  ResearchField,
  ResearchGroup,
} from '../../domain/models';
import {
  getDatasetPresentation,
  type AtlasDatasetKind,
} from '../../data/DatasetPresentation';

interface ResearcherProfileProps {
  researcher: Researcher;
  affiliationHistory: Affiliation[];
  institution: Institution;
  institutions: Institution[];
  group: ResearchGroup | null;
  fields: ResearchField[];
  papers: Paper[];
  authorships: Authorship[];
  historicalEvents: HistoricalEvent[];
  externalResources: ExternalResource[];
  identityResolutions: IdentityResolution[];
  collaborators: Researcher[];
  datasetKind: AtlasDatasetKind;
  onBackToInstitution: () => void;
}

export function ResearcherProfile({
  researcher,
  affiliationHistory,
  institution,
  institutions,
  group,
  fields,
  papers,
  authorships,
  historicalEvents,
  externalResources,
  identityResolutions,
  collaborators,
  datasetKind,
  onBackToInstitution,
}: ResearcherProfileProps) {
  const presentation = getDatasetPresentation(datasetKind);
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
  const institutionsById = new Map(
    institutions.map((candidate) => [candidate.id, candidate]),
  );
  const canonicalName = researcher.canonicalName ?? researcher.name;

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
        <p className="section-kicker">
          Researcher profile · {presentation.dataLabel}
        </p>
        <div className="researcher-identity">
          <span className="researcher-avatar researcher-avatar--large" aria-hidden="true">
            {canonicalName
              .split(' ')
              .map((part) => part[0])
              .join('')}
          </span>
          <div>
            <h2>{canonicalName}</h2>
            <p>{institution.name}</p>
          </div>
        </div>
      </header>

      <div className="entity-view-scroll">
        <section className="entity-section canonical-identity-card">
          <div className="entity-section-heading">
            <div>
              <p className="section-kicker">Canonical identity</p>
              <h3>{canonicalName}</h3>
            </div>
            <span>
              {researcher.identityConfidence !== undefined
                ? `${Math.round(researcher.identityConfidence * 100)}% identity confidence`
                : 'Identity confidence unavailable'}
            </span>
          </div>
          {(researcher.aliases?.length ?? 0) > 0 && (
            <p className="identity-aliases">
              <strong>Name variants</strong> {researcher.aliases?.join(' · ')}
            </p>
          )}
          {(researcher.externalIds?.length ?? 0) > 0 && (
            <div className="identity-identifiers" aria-label="Researcher identifiers">
              {researcher.externalIds?.map((identifier) => (
                <span key={`${identifier.scheme}-${identifier.value}`}>
                  {identifier.scheme}: {identifier.value}
                </span>
              ))}
            </div>
          )}
          <small className="identity-resolution-note">
            {identityResolutions.length} source record
            {identityResolutions.length === 1 ? '' : 's'} resolved to this
            researcher. Identity confidence describes matching evidence, not
            scientific quality.
          </small>
        </section>

        <section className="entity-section profile-affiliation">
          <p className="section-kicker">Affiliation history</p>
          <h3>{group?.name ?? institution.name}</h3>
          {affiliationHistory.length > 0 ? (
            <ol className="affiliation-history-list">
              {affiliationHistory.map((historyEntry) => (
                <li key={historyEntry.id}>
                  <strong>
                    {institutionsById.get(historyEntry.institutionId)?.name ??
                      historyEntry.institutionId}
                  </strong>
                  <span>
                    {historyEntry.startDate ?? historyEntry.startYear ?? 'Start unknown'}
                    {' → '}
                    {historyEntry.endDate ?? historyEntry.endYear ?? 'present / unknown'}
                  </span>
                  <small>
                    {Math.round(
                      (historyEntry.confidence ??
                        historyEntry.provenance.confidence ??
                        0) * 100,
                    )}% relationship confidence · {historyEntry.source ?? historyEntry.provenance.source}
                  </small>
                </li>
              ))}
            </ol>
          ) : (
            <p className="muted-copy">No resolved affiliation history.</p>
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

        {externalResources.length > 0 && (
          <section className="entity-section">
            <div className="entity-section-heading">
              <div>
                <p className="section-kicker">External links</p>
                <h3>Available references</h3>
              </div>
              <span>{presentation.dataLabel}</span>
            </div>
            <div className="external-link-list">
              {externalResources.map((resource) => (
                <a
                  key={resource.id}
                  href={resource.url}
                  target="_blank"
                  rel="noreferrer"
                >
                  <span>{resource.label}</span>
                  <i aria-hidden="true">↗</i>
                </a>
              ))}
            </div>
          </section>
        )}

        <section className="entity-section">
          <div className="entity-section-heading">
            <div>
              <p className="section-kicker">Collaboration graph</p>
              <h3>Connected co-authors</h3>
            </div>
            <span>Relationship view · not ranked</span>
          </div>
          {collaborators.length > 0 ? (
            <ul className="field-entity-list">
              {collaborators.slice(0, 12).map((collaborator) => (
                <li key={collaborator.id}>
                  <strong>{collaborator.canonicalName ?? collaborator.name}</strong>
                  <span>{collaborator.fieldIds.join(' · ')}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted-copy">
              No collaborator relationship is present in this dataset.
            </p>
          )}
        </section>

        <section className="entity-section">
          <div className="entity-section-heading">
            <div>
              <p className="section-kicker">Paper connections</p>
              <h3>
                Representative {presentation.recordLabel} records
              </h3>
            </div>
            <span>Not a performance list</span>
          </div>
          {researcherPapers.length > 0 ? (
            <ol className="paper-list">
              {researcherPapers.map((paper) => (
                <li key={paper.id}>
                  <div>
                    <time>{paper.year}</time>
                    <span>{presentation.sourceLabel}</span>
                  </div>
                  <strong>{paper.title}</strong>
                  <p>{paper.summary || 'Summary unavailable in this source.'}</p>
                </li>
              ))}
            </ol>
          ) : (
            <p className="muted-copy">
              No representative {presentation.recordLabel} papers are
              connected.
            </p>
          )}
        </section>

        {relatedEvents.length > 0 && (
          <section className="entity-section">
            <div className="entity-section-heading">
              <div>
                <p className="section-kicker">Historical connections</p>
                <h3>Related {presentation.recordLabel} events</h3>
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
          {presentation.isSynthetic
            ? 'This synthetic profile describes ecosystem relationships only. It is not a ranking, recommendation, evaluation, or admission prediction.'
            : `${presentation.disclaimer} It is not a recommendation, evaluation, or admission prediction.`}
        </p>
      </div>
    </aside>
  );
}
