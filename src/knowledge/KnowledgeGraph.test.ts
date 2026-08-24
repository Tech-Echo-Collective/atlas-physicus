import demoData from '../data/demo/atlas.json';
import { atlasDatasetSchema } from '../domain/schemas';
import { KnowledgeGraphService } from './KnowledgeGraph';

const derivedProvenance = {
  source: 'knowledge graph unit fixture',
  sourceType: 'derived' as const,
  version: 'fixture-v1',
  status: 'unverified' as const,
};

describe('KnowledgeGraphService', () => {
  it('derives typed nodes and time-dependent edges from canonical records', () => {
    const source = structuredClone(demoData) as Record<string, unknown>;
    source.externalResources = [
      {
        id: 'resource-maya-homepage',
        entityType: 'researcher',
        entityId: 'researcher-maya-chen',
        resourceType: 'researcher-homepage',
        label: 'Researcher homepage',
        url: 'https://example.org/maya',
        isPrimary: true,
        provenance: derivedProvenance,
      },
    ];
    source.rawEntityRecords = [
      {
        id: 'raw-maya-chen',
        entityType: 'researcher',
        sourceRecordId: 'author-42',
        rawName: 'M. Chen',
        externalIds: [],
        attributes: {},
        ingestedAt: '2026-08-24T10:00:00.000Z',
        provenance: derivedProvenance,
      },
      {
        id: 'raw-unknown-person',
        entityType: 'researcher',
        sourceRecordId: 'author-43',
        rawName: 'Unknown Person',
        externalIds: [],
        attributes: {},
        ingestedAt: '2026-08-24T10:00:00.000Z',
        provenance: derivedProvenance,
      },
    ];
    source.identityResolutions = [
      {
        id: 'resolution-maya-chen',
        rawEntityRecordId: 'raw-maya-chen',
        entityType: 'researcher',
        status: 'matched',
        canonicalEntityId: 'researcher-maya-chen',
        method: 'alias',
        confidence: 0.96,
        evidence: [
          {
            method: 'alias',
            inputValue: 'M. Chen',
            canonicalValue: 'Maya Chen',
            score: 0.96,
          },
        ],
        resolverVersion: 'identity-resolver-v1',
        resolvedAt: '2026-08-24T11:00:00.000Z',
        provenance: derivedProvenance,
      },
      {
        id: 'resolution-unknown-person',
        rawEntityRecordId: 'raw-unknown-person',
        entityType: 'researcher',
        status: 'unresolved',
        confidence: 0,
        evidence: [],
        resolverVersion: 'identity-resolver-v1',
        resolvedAt: '2026-08-24T11:00:00.000Z',
        provenance: derivedProvenance,
      },
    ];

    const dataset = atlasDatasetSchema.parse(source);
    const graph = new KnowledgeGraphService().build(dataset);

    expect(graph.nodes).toContainEqual(
      expect.objectContaining({
        key: 'researcher:researcher-maya-chen',
        nodeType: 'researcher',
      }),
    );
    expect(graph.nodes).toContainEqual(
      expect.objectContaining({
        key: 'external-resource:resource-maya-homepage',
      }),
    );
    expect(graph.edges).toContainEqual(
      expect.objectContaining({
        edgeType: 'entity-has-external-resource',
        sourceKey: 'researcher:researcher-maya-chen',
        targetKey: 'external-resource:resource-maya-homepage',
      }),
    );
    expect(graph.edges).toContainEqual(
      expect.objectContaining({
        edgeType: 'researcher-affiliated-with-institution',
        sourceKey: 'researcher:researcher-maya-chen',
      }),
    );
    expect(graph.identityResolutionBoundary).toEqual({
      matchedRawEntityRecordIds: ['raw-maya-chen'],
      unresolvedRawEntityRecordIds: ['raw-unknown-person'],
      ambiguousRawEntityRecordIds: [],
    });
    expect(
      graph.nodes.some((node) => node.entityId === 'raw-unknown-person'),
    ).toBe(false);
  });

  it('fails loudly rather than creating an edge to a missing canonical node', () => {
    const dataset = atlasDatasetSchema.parse(demoData);
    dataset.fields = dataset.fields.filter((field) => field.id !== 'hep-th');

    expect(() => new KnowledgeGraphService().build(dataset)).toThrow(
      /missing canonical node/,
    );
  });
});
