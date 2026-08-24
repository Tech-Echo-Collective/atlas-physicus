import type maplibregl from 'maplibre-gl';

/**
 * Shared presentation scale for normalized MetricObservation values.
 * Metric calculation remains outside the visualization layer.
 */
export const metricValueColor: maplibregl.ExpressionSpecification = [
  'interpolate-hcl',
  ['linear'],
  ['get', 'metricValue'],
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

export function getMetricValueCssColor(value: number): string {
  const normalizedValue = Math.min(100, Math.max(0, value));
  const hue = 270 - normalizedValue * 2.7;
  return `hsl(${hue} 76% 55%)`;
}
