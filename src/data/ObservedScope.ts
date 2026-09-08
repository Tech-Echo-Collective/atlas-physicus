import type { AtlasDataset } from '../domain/models';

/** A domain overview may show the named observed subset, never relabel its data. */
export function observationFieldForView(
  dataset: AtlasDataset,
  domainId: string,
  selectedFieldId: string | null,
): string | undefined {
  if (selectedFieldId) return selectedFieldId;
  const scope = dataset.metadata.datasetScope;
  if (dataset.metadata.deliveryMode === 'versioned-dataset' &&
    scope?.version === 'conditional-observed-ontology-branch-release-v1' &&
    domainId === 'physics' &&
    dataset.scienceDomains.find((domain) => domain.id === domainId)?.fieldIds.includes(scope.rootFieldId)) {
    return scope.rootFieldId;
  }
  return undefined;
}
