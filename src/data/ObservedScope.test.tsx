import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import demoData from './demo/atlas.json';
import { atlasDatasetSchema } from '../domain/schemas';
import { fieldsWithinSelection, matchesFieldSelection } from './ObservedScope';
import { FieldOverview } from '../components/atlas/FieldOverview';
import { resolveAtlasLocation } from '../navigation/AtlasNavigation';

function fixture() {
  const dataset = structuredClone(atlasDatasetSchema.parse(demoData));
  const branch = { ...dataset.fields[0], id: 'test-parent-branch', label: 'Test branch', nodeKind: 'branch' as const };
  dataset.fields[0].parentFieldId = branch.id;
  dataset.fields.push(branch);
  dataset.scienceDomains[0].fieldIds.push(branch.id);
  return { dataset, branch };
}

describe('branch-aware catalog display, without observation relabeling', () => {
  it('uses generic descendant membership and terminates even on a malformed cycle', () => {
    const { dataset, branch } = fixture();
    expect(fieldsWithinSelection(dataset.fields, branch.id)).toEqual(new Set([branch.id, dataset.fields[0].id]));
    expect(matchesFieldSelection([dataset.fields[0].id], branch.id, dataset.fields)).toBe(true);
    expect(matchesFieldSelection([dataset.fields[1].id], branch.id, dataset.fields)).toBe(false);
    branch.parentFieldId = dataset.fields[0].id;
    expect(fieldsWithinSelection(dataset.fields, branch.id).size).toBe(2);
  });

  it('retains a branch selection when opening an institution whose recorded fields are leaves', () => {
    const { dataset, branch } = fixture();
    const institution = dataset.institutions.find((row) => row.fieldIds.includes(dataset.fields[0].id))!;
    const resolved = resolveAtlasLocation({ pathname: `/atlas/institution/${institution.id}`, search: `?domain=physics&field=${branch.id}&year=2026` }, dataset);
    expect(resolved.selectedFieldId).toBe(branch.id);
    expect(resolved.selectedInstitutionId).toBe(institution.id);
  });

  it('renders the branch community and never calls zero known links zero source authors', () => {
    const { dataset, branch } = fixture();
    const paper = dataset.papers.find((row) => row.fieldIds.includes(dataset.fields[0].id))!;
    const html = renderToStaticMarkup(<FieldOverview field={branch} fields={dataset.fields}
      institutions={dataset.institutions} researchers={dataset.researchers} affiliations={dataset.affiliations}
      papers={dataset.papers} authorships={[]} historicalEvents={dataset.historicalEvents}
      paperAuthorCounts={{ [paper.id]: 0 }} datasetKind="live-api" onClose={() => {}} />);
    expect(html).toContain(paper.title);
    expect(html).toContain('0 linked researchers');
    expect(html).not.toContain('0 authors');
    expect(html).toContain('Linked researcher count unavailable');
  });
});
