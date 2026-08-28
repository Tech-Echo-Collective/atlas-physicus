import { renderToStaticMarkup } from 'react-dom/server';
import { Timeline } from './Timeline';
import {
  buildTimelineMajorTicks,
  getTimelineYearPosition,
} from './TimelineScale';

describe('continuous timeline', () => {
  it('uses sparse major labels across a long historical range', () => {
    const ticks = buildTimelineMajorTicks(1900, 2026);

    expect(ticks[0]).toBe(1900);
    expect(ticks.at(-1)).toBe(2026);
    expect(ticks.length).toBeLessThanOrEqual(5);
    expect(ticks).not.toContain(2025);
  });

  it('positions years by elapsed time rather than observation index', () => {
    expect(getTimelineYearPosition(1963, 1900, 2026)).toBe(50);
    expect(getTimelineYearPosition(1800, 1900, 2026)).toBe(0);
    expect(getTimelineYearPosition(2100, 1900, 2026)).toBe(100);
  });

  it('never exceeds the requested sparse-label budget for offset ranges', () => {
    expect(buildTimelineMajorTicks(1901, 2301, 5)).toHaveLength(4);
    expect(buildTimelineMajorTicks(1901, 2301, 3).length).toBeLessThanOrEqual(3);
  });

  it('keeps an unobserved selected year explicit instead of rendering a zero', () => {
    const markup = renderToStaticMarkup(
      <Timeline
        years={[1900, 1950, 2000, 2026]}
        observedYears={[1900, 1950, 2000, 2026]}
        selectedYear={1975}
        datasetKind="synthetic-demo"
        onChange={() => undefined}
      />,
    );

    expect(markup).toContain('<output>1975</output>');
    expect(markup).toContain('No recorded observation · missing is not zero');
    expect(markup).toContain(
      'aria-valuetext="1975; no recorded observation; missing is not zero"',
    );
    expect(markup).toContain('min="1900"');
    expect(markup).toContain('max="2026"');
    expect(markup.match(/<button/g)?.length ?? 0).toBeLessThanOrEqual(5);
  });

  it('renders discrete observation markers independently from range endpoints', () => {
    const markup = renderToStaticMarkup(
      <Timeline
        years={[1900, 2026]}
        observedYears={[1900, 1950, 2000, 2026]}
        selectedYear={1975}
        datasetKind="synthetic-demo"
        onChange={() => undefined}
      />,
    );
    const observationPoints = markup.match(
      /<div class="timeline-observation-points"[^>]*>(.*?)<\/div>/,
    )?.[1];

    expect(observationPoints?.match(/<i/g)).toHaveLength(4);
    expect(markup).toContain('No recorded observation · missing is not zero');
  });

  it('keeps a live missing selection visible outside the bounded observed years', () => {
    const markup = renderToStaticMarkup(
      <Timeline
        years={[2026]}
        observedYears={[2026]}
        selectedYear={2000}
        datasetKind="live-api"
        onChange={() => undefined}
      />,
    );

    expect(markup).toContain('<output>2000</output>');
    expect(markup).toContain('min="2000"');
    expect(markup).toContain('max="2026"');
    expect(markup).toContain('No recorded observation · missing is not zero');
  });
});
