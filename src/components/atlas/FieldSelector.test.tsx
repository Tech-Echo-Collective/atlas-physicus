import { renderToStaticMarkup } from 'react-dom/server';
import type { ResearchField } from '../../domain/models';
import { syntheticDemoProvenance } from '../../domain/schemas';
import { FieldSelector } from './FieldSelector';

const fields: ResearchField[] = [
  { id: 'physics', label: 'Physics domain', description: 'Domain test fixture',
    nodeKind: 'domain-root', isExplorable: false, provenance: syntheticDemoProvenance },
  { id: 'nuclear', label: 'Nuclear physics', description: 'Branch test fixture',
    parentFieldId: 'physics', nodeKind: 'branch', isExplorable: false,
    provenance: syntheticDemoProvenance },
  { id: 'nucl-th', label: 'Nuclear theory', description: 'Field test fixture',
    parentFieldId: 'nuclear', nodeKind: 'field', isExplorable: true,
    provenance: syntheticDemoProvenance },
  { id: 'nucl-ex', label: 'Nuclear experiment', description: 'Field test fixture',
    parentFieldId: 'nuclear', nodeKind: 'field', isExplorable: true,
    provenance: syntheticDemoProvenance },
  { id: 'cond-mat', label: 'Condensed matter', description: 'Other branch fixture',
    parentFieldId: 'physics', nodeKind: 'branch', provenance: syntheticDemoProvenance },
  { id: 'hep-th', label: 'Theory', description: 'Legacy flat field fixture',
    provenance: syntheticDemoProvenance },
];

describe('research field selection hierarchy', () => {
  it('omits only domain-root buttons while preserving branches, leaves and legacy fields', () => {
    const original = JSON.stringify(fields);
    const markup = renderToStaticMarkup(
      <FieldSelector fields={fields} selectedFieldId={null} onSelect={() => undefined} />,
    );
    expect(markup).not.toContain('Physics domain');
    expect(markup).not.toContain('>physics</span>');
    for (const field of fields.slice(1)) {
      expect(markup).toContain(`>${field.id}</span>`);
      expect(markup).toContain(field.label);
    }
    expect(markup.match(/<button/g)).toHaveLength(5);
    expect(JSON.stringify(fields)).toBe(original);
  });

  it('retains the declared nuclear branch selection despite isExplorable=false', () => {
    const markup = renderToStaticMarkup(
      <FieldSelector fields={fields} selectedFieldId="nuclear" onSelect={() => undefined} />,
    );
    expect(markup.match(/aria-pressed="true"/g)).toHaveLength(1);
    expect(markup).toMatch(/aria-pressed="true"[^>]*>.*?>nuclear<\/span>/);
  });

  it('does not substitute a field when the separate Physics domain is selected', () => {
    const markup = renderToStaticMarkup(
      <FieldSelector fields={fields} selectedFieldId={null} onSelect={() => undefined} />,
    );
    expect(markup).not.toContain('aria-pressed="true"');
    expect(markup).toContain('>nuclear</span>');
  });
});
