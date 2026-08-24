import type { CSSProperties } from 'react';

interface TimelineProps {
  years: number[];
  selectedYear: number;
  onChange: (year: number) => void;
}

type TimelineStyle = CSSProperties & {
  '--timeline-progress': string;
};

export function Timeline({ years, selectedYear, onChange }: TimelineProps) {
  const selectedIndex = Math.max(0, years.indexOf(selectedYear));
  const progress =
    years.length <= 1 ? 100 : (selectedIndex / (years.length - 1)) * 100;

  return (
    <section
      className="timeline"
      aria-label="Historical research activity timeline"
      style={{ '--timeline-progress': `${progress}%` } as TimelineStyle}
    >
      <div className="timeline-heading">
        <div>
          <p className="section-kicker">Temporal layer</p>
          <strong>{selectedYear}</strong>
        </div>
        <span>Demo historical data</span>
      </div>

      <div className="timeline-control">
        <input
          type="range"
          min={0}
          max={Math.max(0, years.length - 1)}
          step={1}
          value={selectedIndex}
          onChange={(event) => {
            const year = years[Number(event.target.value)];
            if (year !== undefined) {
              onChange(year);
            }
          }}
          aria-label="Selected year"
          aria-valuetext={String(selectedYear)}
        />
        <div className="timeline-track" aria-hidden="true">
          <span />
        </div>
        <div className="timeline-ticks">
          {years.map((year) => (
            <button
              key={year}
              type="button"
              data-active={year === selectedYear}
              onClick={() => onChange(year)}
              aria-label={`Show ${year} demo data`}
            >
              <i aria-hidden="true" />
              <span>{year}</span>
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}
