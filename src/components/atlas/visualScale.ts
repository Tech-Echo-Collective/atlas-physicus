import type maplibregl from 'maplibre-gl';

/**
 * Shared presentation scale for the synthetic research_activity_score.
 * Metric calculation remains outside the visualization layer.
 */
export const researchActivityColor: maplibregl.ExpressionSpecification = [
  'interpolate-hcl',
  ['linear'],
  ['get', 'score'],
  0,
  '#8b3ffc',
  16,
  '#3157e8',
  32,
  '#00b7d6',
  48,
  '#2db96f',
  64,
  '#d8c83f',
  82,
  '#f07a2b',
  100,
  '#df2f3f',
];

export function getResearchActivityCssColor(value: number): string {
  const normalizedValue = Math.min(100, Math.max(0, value));
  const hue = 270 - normalizedValue * 2.7;
  return `hsl(${hue} 76% 55%)`;
}
