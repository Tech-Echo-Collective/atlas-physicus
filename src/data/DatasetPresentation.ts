import type { DatasetMetadata } from '../domain/models';

export type AtlasDatasetKind = DatasetMetadata['datasetKind'];

export interface DatasetPresentation {
  badgeLabel: string;
  dataLabel: string;
  dataLabelLower: string;
  observationLabel: string;
  sourceLabel: string;
  valuesLabel: string;
  recordLabel: string;
  sampleLabel: string;
  mapAriaLabel: string;
  disclaimer: string;
  isSynthetic: boolean;
  isPilot: boolean;
  isLiveApi: boolean;
}

const presentations: Record<AtlasDatasetKind, DatasetPresentation> = {
  'synthetic-demo': {
    badgeLabel: 'Metric Engine alpha',
    dataLabel: 'Synthetic demo',
    dataLabelLower: 'synthetic demo',
    observationLabel: 'Synthetic demonstration observation',
    sourceLabel: 'synthetic',
    valuesLabel: 'Synthetic values',
    recordLabel: 'demo',
    sampleLabel: 'Synthetic sample',
    mapAriaLabel: 'Temporal geographic atlas of synthetic physics metric values',
    disclaimer: 'Demo visualization only. Not a scientific ranking.',
    isSynthetic: true,
    isPilot: false,
    isLiveApi: false,
  },
  'inspire-hep-pilot': {
    badgeLabel: 'INSPIRE-HEP pilot',
    dataLabel: 'INSPIRE-HEP pilot',
    dataLabelLower: 'INSPIRE-HEP pilot',
    observationLabel: 'INSPIRE-HEP pilot observation',
    sourceLabel: 'INSPIRE-HEP',
    valuesLabel: 'Pilot values',
    recordLabel: 'pilot',
    sampleLabel: 'Pilot sample',
    mapAriaLabel: 'Temporal geographic atlas of INSPIRE-HEP pilot metric values',
    disclaimer: 'Bounded INSPIRE-HEP pilot. Not a scientific ranking.',
    isSynthetic: false,
    isPilot: true,
    isLiveApi: false,
  },
  'live-api': {
    badgeLabel: 'Live API alpha',
    dataLabel: 'API-backed metadata',
    dataLabelLower: 'API-backed metadata',
    observationLabel: 'API-backed scientific metadata observation',
    sourceLabel: 'provider metadata',
    valuesLabel: 'API values',
    recordLabel: 'source-backed',
    sampleLabel: 'API dataset',
    mapAriaLabel: 'Temporal geographic atlas of API-backed physics metric values',
    disclaimer:
      'API-backed scientific metadata with source-dependent coverage. Not a scientific ranking.',
    isSynthetic: false,
    isPilot: false,
    isLiveApi: true,
  },
};

export function getDatasetPresentation(
  datasetKind: AtlasDatasetKind,
): DatasetPresentation {
  return presentations[datasetKind];
}
