import type { AtlasDataset, ResearchField } from '../domain/models';

/** UI membership follows the existing ontology, without relabeling observations. */
export function fieldsWithinSelection(fields: readonly ResearchField[], fieldId: string): Set<string> {
  const included = new Set([fieldId]);
  const pending = [fieldId];
  while (pending.length) {
    const parent = pending.pop();
    for (const field of fields) {
      if (field.parentFieldId === parent && !included.has(field.id)) {
        included.add(field.id); pending.push(field.id);
      }
    }
  }
  return included;
}

export function matchesFieldSelection(fieldIds: readonly string[], selectedId: string | null, fields: readonly ResearchField[]): boolean {
  if (!selectedId) return true;
  const allowed = fieldsWithinSelection(fields, selectedId);
  return fieldIds.some((id) => allowed.has(id));
}

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
