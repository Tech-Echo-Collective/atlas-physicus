import type { ResearchField } from '../../domain/models';

interface FieldSelectorProps {
  fields: ResearchField[];
  selectedFieldId: string | null;
  onSelect: (fieldId: string) => void;
}

export function FieldSelector({
  fields,
  selectedFieldId,
  onSelect,
}: FieldSelectorProps) {
  // Domain roots already have their own selector; branches remain explorable.
  const selectableFields = fields.filter((field) => field.nodeKind !== 'domain-root');
  return (
    <nav className="field-selector" aria-label="Research fields">
      <p className="section-kicker">Research field</p>
      <div className="field-list">
        {selectableFields.map((field) => {
          const isSelected = field.id === selectedFieldId;

          return (
            <button
              className="field-button"
              data-active={isSelected}
              key={field.id}
              onClick={() => onSelect(field.id)}
              type="button"
              aria-pressed={isSelected}
              title={field.description}
            >
              <span className="field-code">{field.id}</span>
              <span className="field-label">{field.label}</span>
            </button>
          );
        })}
      </div>
    </nav>
  );
}
