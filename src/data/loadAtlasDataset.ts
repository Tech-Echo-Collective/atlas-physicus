import type { AtlasDataset, AtlasRepository } from '../domain/models';

/**
 * Builds the alpha client snapshot through repository queries rather than by
 * coupling the interface to the static JSON loader. A future API adapter can
 * implement the same methods while the current normalized UI remains intact.
 */
export async function loadAtlasDataset(
  repository: AtlasRepository,
): Promise<AtlasDataset> {
  if (repository.loadDataset) {
    return repository.loadDataset();
  }

  const [
    metadata,
    scienceDomains,
    fields,
    countries,
    geographicViews,
    institutions,
    researchers,
    researchGroups,
    affiliations,
    papers,
    authorships,
    historicalEvents,
    metricDefinitions,
    metricObservations,
  ] = await Promise.all([
    repository.getMetadata(),
    repository.getScienceDomains(),
    repository.getResearchFields(),
    repository.getCountries(),
    repository.getGeographicViews(),
    repository.getInstitutions(),
    repository.getResearchers(),
    repository.getResearchGroups(),
    repository.getAffiliations(),
    repository.getPapers(),
    repository.getAuthorships(),
    repository.getHistoricalEvents(),
    repository.getMetricDefinitions(),
    repository.getMetricObservations(),
  ]);

  return {
    metadata,
    scienceDomains,
    fields,
    countries,
    geographicViews,
    institutions,
    researchers,
    researchGroups,
    affiliations,
    papers,
    authorships,
    historicalEvents,
    metricDefinitions,
    metricObservations,
  };
}
