import { renderToStaticMarkup } from 'react-dom/server';
import {
  metricSystemV1Ids,
  type MetricDefinition,
} from '../../domain/models';
import { defaultMetricWeightConfiguration } from '../../metrics/CompositeMetric';
import { MetricWeightingPanel } from './MetricWeightingPanel';

const provenance = {
  source: 'Reviewed metric fixture',
  sourceType: 'derived' as const,
  version: 'metric-test-v1',
  status: 'verified' as const,
};

const metricNames: Record<(typeof metricSystemV1Ids)[number], string> = {
  research_activity_score: 'Research Activity',
  research_impact: 'Research Impact',
  collaboration: 'Collaboration',
  research_diversity: 'Research Diversity',
  momentum: 'Momentum',
};

const definitions: MetricDefinition[] = metricSystemV1Ids.map((id) => ({
  id,
  name: metricNames[id],
  category: metricNames[id],
  description: `A reviewed ${metricNames[id]} observation.`,
  interpretation: `Describes observed ${metricNames[id]}.`,
  unit: 'normalized score',
  version: `${id}-v1`,
  requiredData: ['publications'],
  implementationStatus: 'live-calculated',
  provenance,
}));

describe('metric weighting availability', () => {
  it('withholds the metric controls when no validated layers are supplied', () => {
    const markup = renderToStaticMarkup(
      <MetricWeightingPanel
        definitions={[]}
        selectedMetricId="research_activity_score"
        configuration={defaultMetricWeightConfiguration}
        hasConfirmedProfile={false}
        compositeAvailable={false}
        datasetKind="live-api"
        defaultOpen
        onMetricSelect={() => undefined}
        onApply={() => undefined}
      />,
    );

    expect(markup).toContain('Metrics withheld');
    expect(markup).toContain('missing data is not zero');
    expect(markup).toContain('values from another dataset are never substituted');
    expect(markup).not.toContain('<select');
  });

  it('withholds a partial set even when its supplied definition is individually validated', () => {
    const markup = renderToStaticMarkup(
      <MetricWeightingPanel
        definitions={definitions.slice(0, 1)}
        selectedMetricId={definitions[0].id}
        configuration={defaultMetricWeightConfiguration}
        hasConfirmedProfile={false}
        compositeAvailable={false}
        datasetKind="live-api"
        defaultOpen
        onMetricSelect={() => undefined}
        onApply={() => undefined}
      />,
    );

    expect(markup).toContain('Metrics withheld');
    expect(markup).not.toContain('<select');
  });

  it('exposes all five layers and five 0.5% controls only for a complete system', () => {
    const markup = renderToStaticMarkup(
      <MetricWeightingPanel
        definitions={definitions}
        selectedMetricId={definitions[0].id}
        configuration={defaultMetricWeightConfiguration}
        hasConfirmedProfile={false}
        compositeAvailable
        datasetKind="live-api"
        defaultOpen
        onMetricSelect={() => undefined}
        onApply={() => undefined}
      />,
    );

    expect(markup).toContain('Define a perspective');
    metricSystemV1Ids.forEach((id) => {
      expect(markup).toContain(`value="${defaultMetricWeightConfiguration.weights[id]}"`);
    });
    expect(markup.match(/step="0\.5"/g)).toHaveLength(5);
    expect(markup).toContain('Ready to confirm. Draft total is exactly 100%.');
    expect(markup).not.toContain('Metrics withheld');
  });
});
