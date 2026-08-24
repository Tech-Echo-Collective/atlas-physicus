import type {
  AtlasDataset,
  DataProvenance,
  IdentityResolutionStatus,
} from '../domain/models';

export type KnowledgeNodeType =
  | 'science-domain'
  | 'research-field'
  | 'country'
  | 'institution'
  | 'research-group'
  | 'researcher'
  | 'paper'
  | 'external-resource';

export type KnowledgeEdgeType =
  | 'domain-contains-field'
  | 'institution-located-in-country'
  | 'institution-active-in-field'
  | 'institution-hosts-group'
  | 'group-active-in-field'
  | 'researcher-active-in-field'
  | 'researcher-affiliated-with-institution'
  | 'researcher-member-of-group'
  | 'researcher-authored-paper'
  | 'paper-classified-in-field'
  | 'entity-has-external-resource';

export interface KnowledgeGraphNode {
  key: string;
  entityId: string;
  nodeType: KnowledgeNodeType;
  label: string;
  provenance: DataProvenance;
}

export interface KnowledgeGraphEdge {
  id: string;
  edgeType: KnowledgeEdgeType;
  sourceKey: string;
  targetKey: string;
  validFrom?: string;
  validTo?: string;
  confidence?: number;
  sourceAssertion?: string;
  provenance: DataProvenance;
}

export interface IdentityResolutionBoundary {
  matchedRawEntityRecordIds: string[];
  unresolvedRawEntityRecordIds: string[];
  ambiguousRawEntityRecordIds: string[];
}

export interface ScientificKnowledgeGraph {
  nodes: KnowledgeGraphNode[];
  edges: KnowledgeGraphEdge[];
  identityResolutionBoundary: IdentityResolutionBoundary;
}

function nodeKey(type: KnowledgeNodeType, entityId: string): string {
  return `${type}:${entityId}`;
}

function resolutionIds(
  dataset: AtlasDataset,
  status: IdentityResolutionStatus,
): string[] {
  return (dataset.identityResolutions ?? [])
    .filter((resolution) => resolution.status === status)
    .map((resolution) => resolution.rawEntityRecordId)
    .sort();
}

/**
 * Read-only projection of validated canonical entities and explicit relations.
 * Raw and unresolved records never become canonical graph nodes implicitly.
 */
export class KnowledgeGraphService {
  build(dataset: AtlasDataset): ScientificKnowledgeGraph {
    const nodes: KnowledgeGraphNode[] = [];
    const edges: KnowledgeGraphEdge[] = [];

    const addNode = (
      nodeType: KnowledgeNodeType,
      entityId: string,
      label: string,
      provenance: DataProvenance,
    ) => {
      nodes.push({
        key: nodeKey(nodeType, entityId),
        entityId,
        nodeType,
        label,
        provenance,
      });
    };

    dataset.scienceDomains.forEach((domain) =>
      addNode('science-domain', domain.id, domain.label, domain.provenance),
    );
    dataset.fields.forEach((field) =>
      addNode('research-field', field.id, field.label, field.provenance),
    );
    dataset.countries.forEach((country) =>
      addNode('country', country.id, country.name, country.provenance),
    );
    dataset.institutions.forEach((institution) =>
      addNode(
        'institution',
        institution.id,
        institution.canonicalName ?? institution.name,
        institution.provenance,
      ),
    );
    dataset.researchGroups.forEach((group) =>
      addNode('research-group', group.id, group.name, group.provenance),
    );
    dataset.researchers.forEach((researcher) =>
      addNode(
        'researcher',
        researcher.id,
        researcher.canonicalName ?? researcher.name,
        researcher.provenance,
      ),
    );
    dataset.papers.forEach((paper) =>
      addNode('paper', paper.id, paper.title, paper.provenance),
    );
    (dataset.externalResources ?? []).forEach((resource) =>
      addNode(
        'external-resource',
        resource.id,
        resource.label,
        resource.provenance,
      ),
    );

    const nodeKeys = new Set(nodes.map((node) => node.key));
    const addEdge = (
      edge: Omit<KnowledgeGraphEdge, 'sourceKey' | 'targetKey'> & {
        source: [KnowledgeNodeType, string];
        target: [KnowledgeNodeType, string];
      },
    ) => {
      const sourceKey = nodeKey(...edge.source);
      const targetKey = nodeKey(...edge.target);
      if (!nodeKeys.has(sourceKey) || !nodeKeys.has(targetKey)) {
        throw new Error(
          `Knowledge graph edge ${edge.id} references a missing canonical node`,
        );
      }
      edges.push({
        id: edge.id,
        edgeType: edge.edgeType,
        sourceKey,
        targetKey,
        validFrom: edge.validFrom,
        validTo: edge.validTo,
        confidence: edge.confidence,
        sourceAssertion: edge.sourceAssertion,
        provenance: edge.provenance,
      });
    };

    dataset.scienceDomains.forEach((domain) =>
      domain.fieldIds.forEach((fieldId) =>
        addEdge({
          id: `edge-${domain.id}-contains-${fieldId}`,
          edgeType: 'domain-contains-field',
          source: ['science-domain', domain.id],
          target: ['research-field', fieldId],
          provenance: domain.provenance,
        }),
      ),
    );

    dataset.institutions.forEach((institution) => {
      addEdge({
        id: `edge-${institution.id}-located-in-${institution.countryId}`,
        edgeType: 'institution-located-in-country',
        source: ['institution', institution.id],
        target: ['country', institution.countryId],
        provenance: institution.provenance,
      });
      institution.fieldIds.forEach((fieldId) =>
        addEdge({
          id: `edge-${institution.id}-field-${fieldId}`,
          edgeType: 'institution-active-in-field',
          source: ['institution', institution.id],
          target: ['research-field', fieldId],
          provenance: institution.provenance,
        }),
      );
    });

    dataset.researchGroups.forEach((group) => {
      addEdge({
        id: `edge-${group.id}-hosted-by-${group.institutionId}`,
        edgeType: 'institution-hosts-group',
        source: ['institution', group.institutionId],
        target: ['research-group', group.id],
        provenance: group.provenance,
      });
      group.fieldIds.forEach((fieldId) =>
        addEdge({
          id: `edge-${group.id}-field-${fieldId}`,
          edgeType: 'group-active-in-field',
          source: ['research-group', group.id],
          target: ['research-field', fieldId],
          provenance: group.provenance,
        }),
      );
    });

    dataset.researchers.forEach((researcher) =>
      researcher.fieldIds.forEach((fieldId) =>
        addEdge({
          id: `edge-${researcher.id}-field-${fieldId}`,
          edgeType: 'researcher-active-in-field',
          source: ['researcher', researcher.id],
          target: ['research-field', fieldId],
          provenance: researcher.provenance,
        }),
      ),
    );

    dataset.affiliations.forEach((affiliation) => {
      addEdge({
        id: `edge-${affiliation.id}-institution`,
        edgeType: 'researcher-affiliated-with-institution',
        source: ['researcher', affiliation.researcherId],
        target: ['institution', affiliation.institutionId],
        validFrom: affiliation.startDate ?? affiliation.startYear?.toString(),
        validTo: affiliation.endDate ?? affiliation.endYear?.toString(),
        confidence: affiliation.confidence ?? affiliation.provenance.confidence,
        sourceAssertion: affiliation.source ?? affiliation.provenance.source,
        provenance: affiliation.provenance,
      });
      if (affiliation.researchGroupId) {
        addEdge({
          id: `edge-${affiliation.id}-group`,
          edgeType: 'researcher-member-of-group',
          source: ['researcher', affiliation.researcherId],
          target: ['research-group', affiliation.researchGroupId],
          validFrom: affiliation.startDate ?? affiliation.startYear?.toString(),
          validTo: affiliation.endDate ?? affiliation.endYear?.toString(),
          confidence: affiliation.confidence ?? affiliation.provenance.confidence,
          sourceAssertion: affiliation.source ?? affiliation.provenance.source,
          provenance: affiliation.provenance,
        });
      }
    });

    dataset.authorships.forEach((authorship) =>
      addEdge({
        id: `edge-${authorship.id}`,
        edgeType: 'researcher-authored-paper',
        source: ['researcher', authorship.researcherId],
        target: ['paper', authorship.paperId],
        confidence: authorship.provenance.confidence,
        sourceAssertion: authorship.provenance.source,
        provenance: authorship.provenance,
      }),
    );

    dataset.papers.forEach((paper) =>
      paper.fieldIds.forEach((fieldId) =>
        addEdge({
          id: `edge-${paper.id}-field-${fieldId}`,
          edgeType: 'paper-classified-in-field',
          source: ['paper', paper.id],
          target: ['research-field', fieldId],
          provenance: paper.provenance,
        }),
      ),
    );

    (dataset.externalResources ?? []).forEach((resource) =>
      addEdge({
        id: `edge-${resource.id}-owner`,
        edgeType: 'entity-has-external-resource',
        source: [resource.entityType, resource.entityId],
        target: ['external-resource', resource.id],
        validFrom: resource.validFrom,
        validTo: resource.validTo,
        provenance: resource.provenance,
      }),
    );

    return {
      nodes,
      edges,
      identityResolutionBoundary: {
        matchedRawEntityRecordIds: resolutionIds(dataset, 'matched'),
        unresolvedRawEntityRecordIds: resolutionIds(dataset, 'unresolved'),
        ambiguousRawEntityRecordIds: resolutionIds(dataset, 'ambiguous'),
      },
    };
  }
}
