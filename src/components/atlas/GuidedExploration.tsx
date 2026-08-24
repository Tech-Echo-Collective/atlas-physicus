import { useState } from 'react';

export type GuidedAction =
  | 'physics'
  | 'hep-th'
  | 'year'
  | 'country'
  | 'institution'
  | 'researcher'
  | 'history';

interface GuidedExplorationProps {
  onNavigate: (action: GuidedAction) => void;
}

const steps: Array<{
  action: GuidedAction;
  eyebrow: string;
  title: string;
  description: string;
  buttonLabel: string;
}> = [
  {
    action: 'physics',
    eyebrow: 'Science domain',
    title: 'Begin with Physics',
    description: 'The domain heatmap shows the global synthetic activity layer.',
    buttonLabel: 'Show Physics',
  },
  {
    action: 'hep-th',
    eyebrow: 'Research field',
    title: 'Narrow to hep-th',
    description: 'Field selection replaces the domain observations without ranking them.',
    buttonLabel: 'Select hep-th',
  },
  {
    action: 'year',
    eyebrow: 'Temporal layer',
    title: 'Choose a year',
    description: 'Each year is an explicit demo observation, not a predicted value.',
    buttonLabel: 'Use 2026',
  },
  {
    action: 'country',
    eyebrow: 'Geographic view',
    title: 'Enter the United States',
    description: 'Country mode reveals institution nodes inside the geographic canvas.',
    buttonLabel: 'Open country',
  },
  {
    action: 'institution',
    eyebrow: 'Institution view',
    title: 'Explore MIT',
    description: 'The institution view connects groups, people, papers, and time.',
    buttonLabel: 'Open institution',
  },
  {
    action: 'researcher',
    eyebrow: 'Researcher view',
    title: 'Follow an affiliation',
    description: 'Open Jonah Okafor, a fully synthetic researcher record.',
    buttonLabel: 'Open researcher',
  },
  {
    action: 'history',
    eyebrow: 'Historical connection',
    title: 'Read the connected event',
    description: 'The profile links to a synthetic field-history event below its papers.',
    buttonLabel: 'Complete tour',
  },
];

export function GuidedExploration({ onNavigate }: GuidedExplorationProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [stepIndex, setStepIndex] = useState(0);
  const step = steps[stepIndex];

  const runStep = () => {
    onNavigate(step.action);
    if (stepIndex === steps.length - 1) {
      setIsOpen(false);
      setStepIndex(0);
      return;
    }
    setStepIndex((current) => current + 1);
  };

  return (
    <div className="guided-exploration" data-open={isOpen}>
      <button
        className="atlas-utility-button"
        type="button"
        onClick={() => setIsOpen((current) => !current)}
        aria-label="Open guided atlas exploration"
        aria-expanded={isOpen}
        title="Guided exploration"
      >
        <span aria-hidden="true">?</span>
      </button>
      {isOpen && (
        <section className="guided-exploration-panel" aria-live="polite">
          <div className="guided-progress" aria-label={`Step ${stepIndex + 1} of ${steps.length}`}>
            {steps.map((candidate, index) => (
              <i key={candidate.action} data-active={index <= stepIndex} />
            ))}
          </div>
          <p className="section-kicker">{step.eyebrow}</p>
          <h2>{step.title}</h2>
          <p>{step.description}</p>
          <div>
            <button type="button" onClick={() => setIsOpen(false)}>
              Exit
            </button>
            <button type="button" onClick={runStep}>
              {step.buttonLabel} <span aria-hidden="true">→</span>
            </button>
          </div>
        </section>
      )}
    </div>
  );
}
