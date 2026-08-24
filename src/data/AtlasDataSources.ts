export type AtlasDataSourceId = 'synthetic-framework' | 'inspire-hep-pilot';

export interface AtlasDataSourceOption {
  id: AtlasDataSourceId;
  label: string;
  description: string;
}

export const atlasDataSourceOptions: AtlasDataSourceOption[] = [
  {
    id: 'synthetic-framework',
    label: 'Synthetic framework',
    description: 'Broad UI demonstration data',
  },
  {
    id: 'inspire-hep-pilot',
    label: 'INSPIRE-HEP pilot',
    description: 'Bounded real-data hep-th study',
  },
];

export function resolveAtlasDataSource(search: string): AtlasDataSourceId {
  return new URLSearchParams(search).get('source') === 'inspire-hep-pilot'
    ? 'inspire-hep-pilot'
    : 'synthetic-framework';
}

export function buildDataSourceAwareAtlasUrl(
  atlasUrl: string,
  sourceId: AtlasDataSourceId,
): string {
  const [pathname, query = ''] = atlasUrl.split('?');
  const parameters = new URLSearchParams(query);
  if (sourceId === 'inspire-hep-pilot') {
    parameters.set('source', sourceId);
  } else {
    parameters.delete('source');
  }
  const serialized = parameters.toString();
  return serialized ? `${pathname}?${serialized}` : pathname;
}
