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
    dataLabel: 'Source-backed scientific metadata',
    dataLabelLower: 'source-backed scientific metadata',
    observationLabel: 'Source-backed scientific observation',
    sourceLabel: 'provider metadata',
    valuesLabel: 'Atlas values',
    recordLabel: 'source-backed',
    sampleLabel: 'Atlas dataset',
    mapAriaLabel: 'Temporal geographic atlas of source-backed physics metric values',
    disclaimer:
      'Scientific metadata with source-dependent coverage. Not a scientific ranking.',
    isSynthetic: false,
    isPilot: false,
    isLiveApi: true,
  },
};

export function getDatasetPresentation(
  datasetKind: AtlasDatasetKind,
  deliveryMode?: DatasetMetadata['deliveryMode'],
): DatasetPresentation {
  if (datasetKind === 'live-api' && deliveryMode === 'versioned-dataset') {
    return {
      ...presentations['live-api'],
      badgeLabel: 'Certified Atlas dataset',
      dataLabel: 'Certified scientific dataset',
      dataLabelLower: 'certified scientific dataset',
      observationLabel: 'Certified Atlas observation',
      valuesLabel: 'Certified Atlas values',
      sampleLabel: 'Versioned dataset',
      mapAriaLabel: 'Temporal geographic atlas of certified physics metric values',
      disclaimer: 'Versioned scientific evidence with limited coverage. Not a scientific ranking.',
      isLiveApi: false,
    };
  }
  return presentations[datasetKind];
}
