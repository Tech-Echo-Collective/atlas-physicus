import { renderToStaticMarkup } from 'react-dom/server';
import type { MetricDefinition } from '../../domain/models';
import { defaultMetricWeightConfiguration } from '../../metrics/CompositeMetric';
import { MetricWeightingPanel } from './MetricWeightingPanel';

const provenance = {
  source: 'Reviewed metric fixture',
  sourceType: 'derived' as const,
  version: 'metric-test-v1',
  status: 'verified' as const,
};

const definition: MetricDefinition = {
  id: 'research_activity_score',
  name: 'Research Activity',
  category: 'Research Activity',
  description: 'A reviewed activity observation.',
  interpretation: 'Describes observed research activity.',
  unit: 'normalized score',
  version: '1.0.0',
  requiredData: ['publications'],
  implementationStatus: 'live-calculated',
  provenance,
};

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

  it('enables the metric controls only when a validated definition is supplied', () => {
    const markup = renderToStaticMarkup(
      <MetricWeightingPanel
        definitions={[definition]}
        selectedMetricId={definition.id}
        configuration={defaultMetricWeightConfiguration}
        hasConfirmedProfile={false}
        compositeAvailable={false}
        datasetKind="live-api"
        defaultOpen
        onMetricSelect={() => undefined}
        onApply={() => undefined}
      />,
    );

    expect(markup).toContain('Choose a metric');
    expect(markup).toContain('<select');
    expect(markup).toContain('Research Activity');
    expect(markup).not.toContain('Metrics withheld');
  });
});
