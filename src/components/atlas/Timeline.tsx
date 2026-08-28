import type { CSSProperties } from 'react';
import {
  getDatasetPresentation,
  type AtlasDatasetKind,
} from '../../data/DatasetPresentation';
import {
  buildTimelineMajorTicks,
  getTimelineYearPosition,
} from './TimelineScale';

interface TimelineProps {
  years: number[];
  observedYears?: number[];
  selectedYear: number;
  datasetKind: AtlasDatasetKind;
  onChange: (year: number) => void;
}

type TimelineStyle = CSSProperties & {
  '--timeline-progress': string;
};

type TimelineTickStyle = CSSProperties & {
  '--timeline-tick-position': string;
};

export function Timeline({
  years,
  observedYears = years,
  selectedYear,
  datasetKind,
  onChange,
}: TimelineProps) {
  const presentation = getDatasetPresentation(datasetKind);
  const sortedYears = Array.from(new Set([...years, selectedYear])).sort(
    (left, right) => left - right,
  );
  const minimumYear = sortedYears[0] ?? selectedYear;
  const maximumYear = sortedYears.at(-1) ?? selectedYear;
  const progress = getTimelineYearPosition(
    selectedYear,
    minimumYear,
    maximumYear,
  );
  const majorTicks = buildTimelineMajorTicks(minimumYear, maximumYear);
  const sortedObservedYears = Array.from(new Set(observedYears))
    .filter((year) => year >= minimumYear && year <= maximumYear)
    .sort((left, right) => left - right);
  const observedYearSet = new Set(sortedObservedYears);
  const hasSelectedObservation = observedYearSet.has(selectedYear);
  const observationStatus = hasSelectedObservation
    ? 'recorded observation; no temporal interpolation'
    : 'no recorded observation; missing is not zero';
  const dataLabel = presentation.dataLabel;

  return (
    <section
      className="timeline"
      aria-label="Historical metric timeline"
      style={{ '--timeline-progress': `${progress}%` } as TimelineStyle}
    >
      <div className="timeline-heading">
        <p className="section-kicker">Temporal layer</p>
        <span>{dataLabel}</span>
      </div>

      <div className="timeline-control">
        <div
          className="timeline-selected-year"
          data-observed={hasSelectedObservation}
          aria-hidden="true"
        >
          <output>{selectedYear}</output>
          <i />
        </div>
        <input
          type="range"
          min={minimumYear}
          max={maximumYear}
          step={1}
          value={selectedYear}
          disabled={minimumYear === maximumYear}
          onChange={(event) => {
            onChange(Number(event.target.value));
          }}
          aria-label="Selected year"
          aria-valuetext={`${selectedYear}; ${observationStatus}`}
          aria-describedby="timeline-missing-data-note"
        />
        <div className="timeline-track" aria-hidden="true">
          <span />
        </div>
        <div className="timeline-observation-points" aria-hidden="true">
          {sortedObservedYears.map((year) => (
            <i
              key={year}
              style={
                {
                  '--timeline-tick-position': `${getTimelineYearPosition(
                    year,
                    minimumYear,
                    maximumYear,
                  )}%`,
                } as TimelineTickStyle
              }
            />
          ))}
        </div>
        <div className="timeline-major-ticks">
          {majorTicks.map((year, index) => (
            <button
              key={year}
              type="button"
              data-edge={index === 0 || index === majorTicks.length - 1}
              style={
                {
                  '--timeline-tick-position': `${getTimelineYearPosition(
                    year,
                    minimumYear,
                    maximumYear,
                  )}%`,
                } as TimelineTickStyle
              }
              onClick={() => onChange(year)}
              aria-label={
                observedYearSet.has(year)
                  ? `Show recorded ${year} ${presentation.recordLabel} data`
                  : `Select ${year}; no recorded observation`
              }
            >
              <span>{year}</span>
            </button>
          ))}
        </div>
      </div>
      <p
        className="timeline-missing-note"
        id="timeline-missing-data-note"
        role="status"
        aria-live="polite"
      >
        {hasSelectedObservation
          ? 'Recorded observation · no temporal interpolation'
          : 'No recorded observation · missing is not zero'}
      </p>
    </section>
  );
}
