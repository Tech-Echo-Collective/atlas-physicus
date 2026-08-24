import type { ResearchField } from '../../domain/models';

interface FieldSelectorProps {
  fields: ResearchField[];
  selectedFieldId: string;
  onSelect: (fieldId: string) => void;
}

export function FieldSelector({
  fields,
  selectedFieldId,
  onSelect,
}: FieldSelectorProps) {
  return (
    <nav className="field-selector" aria-label="Research fields">
      <p className="section-kicker">Research field</p>
      <div className="field-list">
        {fields.map((field) => {
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
