function niceTickStep(rawStep: number): number {
  if (rawStep <= 1) {
    return 1;
  }

  const magnitude = 10 ** Math.floor(Math.log10(rawStep));
  const normalized = rawStep / magnitude;
  const multiplier =
    normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10;
  return multiplier * magnitude;
}

function ticksForStep(
  minimumYear: number,
  maximumYear: number,
  step: number,
): number[] {
  const ticks = [minimumYear];
  for (
    let year = Math.ceil(minimumYear / step) * step;
    year < maximumYear;
    year += step
  ) {
    if (year > minimumYear) {
      ticks.push(year);
    }
  }
  ticks.push(maximumYear);
  return Array.from(new Set(ticks));
}

export function buildTimelineMajorTicks(
  minimumYear: number,
  maximumYear: number,
  maximumLabels = 5,
): number[] {
  if (maximumYear <= minimumYear) {
    return [minimumYear];
  }

  const labelCount = Math.max(2, Math.floor(maximumLabels));
  let step = niceTickStep((maximumYear - minimumYear) / (labelCount - 1));
  let ticks = ticksForStep(minimumYear, maximumYear, step);
  while (ticks.length > labelCount) {
    step = niceTickStep(step * 1.01);
    ticks = ticksForStep(minimumYear, maximumYear, step);
  }
  return ticks;
}

export function getTimelineYearPosition(
  year: number,
  minimumYear: number,
  maximumYear: number,
): number {
  if (maximumYear <= minimumYear) {
    return 50;
  }
  return (
    ((Math.min(maximumYear, Math.max(minimumYear, year)) - minimumYear) /
      (maximumYear - minimumYear)) *
    100
  );
}
