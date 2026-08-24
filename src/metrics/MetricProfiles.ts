import type { MetricWeightConfiguration } from '../domain/models';

export interface MetricProfile extends MetricWeightConfiguration {
  purpose: string;
}

export const metricProfiles: MetricProfile[] = [
  {
    id: 'balanced-scientific-ecosystem',
    name: 'Balanced Scientific Ecosystem',
    purpose: 'General exploration of scientific ecosystems.',
    weights: {
      research_activity_score: 25,
      research_impact: 25,
      collaboration: 20,
      research_diversity: 15,
      momentum: 15,
    },
  },
  {
    id: 'research-excellence',
    name: 'Research Excellence',
    purpose: 'Explore research output and influence.',
    weights: {
      research_activity_score: 20,
      research_impact: 45,
      collaboration: 15,
      research_diversity: 10,
      momentum: 10,
    },
  },
  {
    id: 'frontier-growth',
    name: 'Frontier Growth',
    purpose: 'Explore emerging and developing research ecosystems.',
    weights: {
      research_activity_score: 20,
      research_impact: 20,
      collaboration: 20,
      research_diversity: 20,
      momentum: 20,
    },
  },
  {
    id: 'global-network',
    name: 'Global Network',
    purpose: 'Explore international scientific connectivity.',
    weights: {
      research_activity_score: 15,
      research_impact: 20,
      collaboration: 45,
      research_diversity: 10,
      momentum: 10,
    },
  },
];

export const defaultMetricWeightConfiguration: MetricWeightConfiguration = {
  id: metricProfiles[0].id,
  name: metricProfiles[0].name,
  weights: { ...metricProfiles[0].weights },
};
