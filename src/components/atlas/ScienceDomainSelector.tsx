import type { ScienceDomain } from '../../domain/models';

interface ScienceDomainSelectorProps {
  domains: ScienceDomain[];
  selectedDomainId: string;
  isDomainView: boolean;
  onSelect: (domainId: string) => void;
}

export function ScienceDomainSelector({
  domains,
  selectedDomainId,
  isDomainView,
  onSelect,
}: ScienceDomainSelectorProps) {
  return (
    <section className="domain-selector" aria-label="Science domain">
      <p className="section-kicker">Science domain</p>
      <div className="domain-list">
        {domains.map((domain) => (
          <button
            className="domain-button"
            data-active={domain.id === selectedDomainId}
            key={domain.id}
            onClick={() => onSelect(domain.id)}
            type="button"
            aria-pressed={domain.id === selectedDomainId}
          >
            <span className="domain-orbit" aria-hidden="true" />
            <span>
              <strong>{domain.label}</strong>
              <small>
                {domain.id === selectedDomainId && isDomainView
                  ? 'Domain heatmap'
                  : 'Science domain'}
              </small>
            </span>
          </button>
        ))}
      </div>
    </section>
  );
}
