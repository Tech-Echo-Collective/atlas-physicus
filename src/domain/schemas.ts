import { z } from 'zod';
import type { DataProvenance, RawEntityAttribute } from './models';

const entityIdSchema = z.string().min(1).regex(/^[a-z0-9-]+$/);
const fieldIdSchema = z.string().min(1).regex(/^[a-z0-9-]+$/);
const metricIdSchema = z.string().min(1).regex(/^[a-z0-9_-]+$/);
const temporalDateSchema = z
  .string()
  .regex(/^\d{4}(?:-(?:0[1-9]|1[0-2])(?:-(?:0[1-9]|[12]\d|3[01]))?)?$/);

/**
 * Static JSON omits unknown optional values, while the FastAPI transport uses
 * explicit JSON nulls. Normalize both representations to the domain model's
 * undefined value without touching meaningful nulls inside raw source evidence.
 */
export function optionalFromNullable<T extends z.ZodType>(schema: T) {
  return z.preprocess(
    (value) => (value === null ? undefined : value),
    schema.optional(),
  );
}

function temporalLowerBound(value: string): string {
  const segments = value.split('-');
  return `${segments[0]}-${segments[1] ?? '01'}-${segments[2] ?? '01'}`;
}

function temporalUpperBound(value: string): string {
  const segments = value.split('-');
  return `${segments[0]}-${segments[1] ?? '12'}-${segments[2] ?? '31'}`;
}

export const syntheticDemoProvenance: DataProvenance = {
  source: 'Physics Atlas synthetic demonstration dataset',
  sourceType: 'synthetic-demo',
  version: 'v3.0.1-alpha',
  status: 'synthetic',
};

export const provenanceSchema = z.object({
  source: z.string().min(1),
  sourceType: z.enum([
    'synthetic-demo',
    'external-api',
    'institutional-source',
    'derived',
  ]),
  version: z.string().min(1),
  status: z.enum(['synthetic', 'unverified', 'verified', 'deprecated']),
  confidence: optionalFromNullable(z.number().min(0).max(1)),
  retrievedAt: optionalFromNullable(z.string().datetime({ offset: true })),
  acquisitionScope: optionalFromNullable(z.string().trim().min(1)),
});

export const externalIdentifierSchema = z.object({
  scheme: z.string().trim().min(1),
  value: z.string().trim().min(1),
});

const canonicalIdentityFieldsShape = {
  canonicalName: optionalFromNullable(z.string().trim().min(1)),
  aliases: z.array(z.string().trim().min(1)).default([]),
  historicalNames: z.array(z.string().trim().min(1)).default([]),
  externalIds: z.array(externalIdentifierSchema).default([]),
  identityConfidence: optionalFromNullable(z.number().min(0).max(1)),
};

const recordProvenanceSchema = z
  .union([provenanceSchema, z.literal('synthetic-demo')])
  .transform((provenance) =>
    provenance === 'synthetic-demo'
      ? { ...syntheticDemoProvenance }
      : provenance,
  )
  .default(syntheticDemoProvenance);

export const scienceDomainSchema = z.object({
  id: entityIdSchema,
  label: z.string().min(1),
  description: z.string().min(1),
  fieldIds: z.array(fieldIdSchema).min(1),
  provenance: recordProvenanceSchema,
});

export const researchFieldSchema = z.object({
  id: fieldIdSchema,
  label: z.string().min(1),
  description: z.string().min(1),
  provenance: recordProvenanceSchema,
});

export const countrySchema = z.object({
  id: entityIdSchema,
  isoAlpha3: z.string().length(3),
  isoNumeric: z.string().length(3).regex(/^\d{3}$/),
  name: z.string().min(1),
  region: z.string().min(1),
  provenance: recordProvenanceSchema,
});

export const geographicViewSchema = z.object({
  id: entityIdSchema,
  countryId: entityIdSchema,
  geometryIsoNumerics: z
    .array(z.string().length(3).regex(/^\d{3}$/))
    .min(1),
  locationCountryIds: z.array(entityIdSchema).min(1),
  provenance: recordProvenanceSchema,
});

export const institutionSchema = z
  .object({
    id: entityIdSchema,
    name: z.string().min(1),
    ...canonicalIdentityFieldsShape,
    countryId: entityIdSchema,
    city: z.string().min(1),
    fieldIds: z.array(fieldIdSchema),
    location: optionalFromNullable(
      z.object({
        longitude: z.number().min(-180).max(180),
        latitude: z.number().min(-90).max(90),
      }),
    ),
    provenance: recordProvenanceSchema,
  })
  .transform((institution) => ({
    ...institution,
    canonicalName: institution.canonicalName ?? institution.name,
  }));

export const researcherSchema = z
  .object({
    id: entityIdSchema,
    name: z.string().min(1),
    ...canonicalIdentityFieldsShape,
    fieldIds: z.array(fieldIdSchema),
    provenance: recordProvenanceSchema,
  })
  .transform((researcher) => ({
    ...researcher,
    canonicalName: researcher.canonicalName ?? researcher.name,
  }));

export const researchGroupSchema = z.object({
  id: entityIdSchema,
  name: z.string().min(1),
  institutionId: entityIdSchema,
  description: z.string().min(1),
  fieldIds: z.array(fieldIdSchema),
  provenance: recordProvenanceSchema,
});

export const affiliationSchema = z
  .object({
    id: entityIdSchema,
    researcherId: entityIdSchema,
    institutionId: entityIdSchema,
    researchGroupId: optionalFromNullable(entityIdSchema),
    startDate: optionalFromNullable(temporalDateSchema),
    endDate: optionalFromNullable(temporalDateSchema),
    source: optionalFromNullable(z.string().min(1)),
    confidence: optionalFromNullable(z.number().min(0).max(1)),
    startYear: optionalFromNullable(z.number().int().min(1000).max(9999)),
    endYear: optionalFromNullable(z.number().int().min(1000).max(9999)),
    provenance: recordProvenanceSchema,
  })
  .superRefine((affiliation, context) => {
    const start = affiliation.startDate ?? affiliation.startYear?.toString();
    const end = affiliation.endDate ?? affiliation.endYear?.toString();
    if (
      start &&
      end &&
      temporalUpperBound(end).localeCompare(temporalLowerBound(start)) < 0
    ) {
      context.addIssue({
        code: 'custom',
        path: ['endDate'],
        message: 'Affiliation end date precedes its start date',
      });
    }
  });

export const externalResourceSchema = z
  .object({
    id: entityIdSchema,
    entityType: z.enum([
      'institution',
      'research-group',
      'researcher',
      'paper',
    ]),
    entityId: entityIdSchema,
    resourceType: z.enum([
      'official-institution-website',
      'department-website',
      'research-group-website',
      'institutional-profile',
      'researcher-homepage',
      'ror',
      'wikidata',
      'orcid',
      'inspire',
      'arxiv',
      'doi',
      'publisher-landing-page',
    ]),
    label: z.string().min(1),
    url: z.string().url(),
    externalId: optionalFromNullable(externalIdentifierSchema),
    isPrimary: z.boolean().default(false),
    validFrom: optionalFromNullable(temporalDateSchema),
    validTo: optionalFromNullable(temporalDateSchema),
    lastVerifiedAt: optionalFromNullable(z.string().datetime({ offset: true })),
    provenance: recordProvenanceSchema,
  })
  .superRefine((resource, context) => {
    if (
      resource.validFrom &&
      resource.validTo &&
      temporalUpperBound(resource.validTo).localeCompare(
        temporalLowerBound(resource.validFrom),
      ) < 0
    ) {
      context.addIssue({
        code: 'custom',
        path: ['validTo'],
        message: 'External resource validity ends before it begins',
      });
    }
  });

const rawEntityAttributeSchema: z.ZodType<RawEntityAttribute> = z.lazy(() =>
  z.union([
    z.string(),
    z.number(),
    z.boolean(),
    z.null(),
    z.array(rawEntityAttributeSchema),
    z.record(z.string(), rawEntityAttributeSchema),
  ]),
);

export const rawEntityRecordSchema = z.object({
  id: entityIdSchema,
  entityType: z.enum(['institution', 'researcher', 'paper']),
  sourceRecordId: z.string().min(1),
  sourceSnapshotId: optionalFromNullable(entityIdSchema),
  rawName: z.string().min(1),
  externalIds: z.array(externalIdentifierSchema).default([]),
  attributes: z.record(z.string(), rawEntityAttributeSchema).default({}),
  ingestedAt: z.string().datetime({ offset: true }),
  provenance: recordProvenanceSchema,
});

const identityResolutionMethodSchema = z.enum([
  'external-identifier',
  'canonical-name',
  'alias',
  'historical-name',
  'fuzzy-name',
  'source-record-identifier',
  'manual-review',
  'insufficient-metadata',
]);

const identityEvidenceMethodSchema = z.union([
  identityResolutionMethodSchema,
  z.literal('required-metadata'),
]);

export const identityEvidenceSchema = z.object({
  method: identityEvidenceMethodSchema,
  inputValue: z.string().min(1),
  candidateEntityId: optionalFromNullable(entityIdSchema),
  canonicalValue: optionalFromNullable(z.string().min(1)),
  score: z.number().min(0).max(1),
});

export const identityResolutionSchema = z
  .object({
    id: entityIdSchema,
    rawEntityRecordId: entityIdSchema,
    entityType: z.enum(['institution', 'researcher', 'paper']),
    status: z.enum(['matched', 'unresolved', 'ambiguous']),
    canonicalEntityId: optionalFromNullable(entityIdSchema),
    method: optionalFromNullable(identityResolutionMethodSchema),
    confidence: z.number().min(0).max(1),
    evidence: z.array(identityEvidenceSchema),
    resolverVersion: z.string().min(1),
    resolvedAt: z.string().datetime({ offset: true }),
    provenance: recordProvenanceSchema,
  })
  .superRefine((resolution, context) => {
    if (resolution.status === 'matched' && !resolution.canonicalEntityId) {
      context.addIssue({
        code: 'custom',
        path: ['canonicalEntityId'],
        message: 'Matched identity requires a canonical entity',
      });
    }
    if (resolution.status === 'matched' && !resolution.method) {
      context.addIssue({
        code: 'custom',
        path: ['method'],
        message: 'Matched identity requires a resolution method',
      });
    }
    if (
      resolution.status !== 'matched' &&
      resolution.canonicalEntityId !== undefined
    ) {
      context.addIssue({
        code: 'custom',
        path: ['canonicalEntityId'],
        message: 'Unresolved identities cannot silently reference a canonical entity',
      });
    }
  });

export const sourceSnapshotSchema = z.object({
  id: entityIdSchema,
  source: z.string().min(1),
  sourceVersion: z.string().min(1),
  capturedAt: z.string().datetime({ offset: true }),
  updateMode: z.enum(['full-snapshot', 'incremental']),
  recordCount: z.number().int().min(0),
  previousSnapshotId: optionalFromNullable(entityIdSchema),
  contentChecksum: optionalFromNullable(z.string().min(1)),
  storageReference: optionalFromNullable(z.string().min(1)),
  provenance: recordProvenanceSchema,
});

export const datasetUpdateSchema = z.object({
  id: entityIdSchema,
  appliedAt: z.string().datetime({ offset: true }),
  updateMode: z.enum(['full-snapshot', 'incremental', 'reprocess']),
  sourceSnapshotIds: z.array(entityIdSchema).min(1),
  previousDatasetVersion: optionalFromNullable(z.string().min(1)),
  datasetVersion: z.string().min(1),
  resolverVersion: z.string().min(1),
  metricCalculationVersion: optionalFromNullable(z.string().min(1)),
  changes: z.object({
    created: z.number().int().min(0),
    updated: z.number().int().min(0),
    unchanged: z.number().int().min(0),
    unresolved: z.number().int().min(0),
    failed: z.number().int().min(0).default(0),
  }),
  affectedEntities: z
    .array(
      z.object({
        entityType: z.enum(['institution', 'researcher', 'paper']),
        entityId: entityIdSchema,
      }),
    )
    .default([]),
  provenance: recordProvenanceSchema,
});

export const paperSchema = z.object({
  id: entityIdSchema,
  title: z.string().min(1),
  summary: z.string(),
  year: z.number().int().min(1000).max(9999),
  fieldIds: z.array(fieldIdSchema),
  doi: optionalFromNullable(z.string().regex(/^10\.\d{4,9}\/\S+$/)),
  arxivId: optionalFromNullable(
    z
      .string()
      .regex(/^(?:arXiv:)?(?:\d{4}\.\d{4,5}|[a-z-]+\/\d{7})$/i),
  ),
  externalIdentifiers: optionalFromNullable(z.array(externalIdentifierSchema)),
  provenance: recordProvenanceSchema,
});

export const authorshipSchema = z.object({
  id: entityIdSchema,
  paperId: entityIdSchema,
  researcherId: entityIdSchema,
  authorPosition: z.number().int().positive(),
  provenance: recordProvenanceSchema,
});

export const historicalEventSchema = z.object({
  id: entityIdSchema,
  title: z.string().min(1),
  summary: z.string().min(1),
  year: z.number().int().min(1000).max(9999),
  fieldId: fieldIdSchema,
  relatedResearcherIds: z.array(entityIdSchema),
  relatedInstitutionIds: z.array(entityIdSchema),
  provenance: recordProvenanceSchema,
});

export const metricDefinitionSchema = z.object({
  id: metricIdSchema,
  name: z.string().min(1),
  category: z.string().min(1),
  description: z.string().min(1),
  interpretation: z.string().min(1),
  unit: z.string().min(1),
  version: z.string().min(1),
  requiredData: z.array(z.string().min(1)).min(1),
  implementationStatus: z.enum([
    'synthetic-demo',
    'pilot-calculated',
    'live-calculated',
    'taxonomy-only',
  ]),
  provenance: recordProvenanceSchema,
});

export const metricObservationSchema = z.object({
  id: entityIdSchema,
  entityType: z.enum([
    'science-domain',
    'field',
    'country',
    'institution',
    'research-group',
    'researcher',
  ]),
  entityId: entityIdSchema,
  scienceDomainId: optionalFromNullable(entityIdSchema),
  fieldId: optionalFromNullable(fieldIdSchema),
  metricId: metricIdSchema,
  period: z.string().regex(/^\d{4}$/),
  value: z.number().min(0).max(100),
  source: z.string().min(1).default('synthetic-demo'),
  algorithmVersion: z.string().min(1).default('metric-engine-v1'),
  calculationVersion: z.string().min(1).default('v3.0.1-alpha'),
  calculatedAt: optionalFromNullable(z.string().datetime({ offset: true })),
  provenance: recordProvenanceSchema,
});

export const metricWeightConfigurationSchema = z
  .object({
    id: entityIdSchema,
    name: z.string().min(1),
    weights: z.record(metricIdSchema, z.number().min(0).max(100)),
  })
  .superRefine((configuration, context) => {
    const weights = Object.values(configuration.weights);
    if (weights.length === 0) {
      context.addIssue({
        code: 'custom',
        path: ['weights'],
        message: 'At least one metric weight is required',
      });
      return;
    }

    const total = weights.reduce((sum, weight) => sum + weight, 0);
    if (Math.abs(total - 100) > 0.0001) {
      context.addIssue({
        code: 'custom',
        path: ['weights'],
        message: 'Metric weights must total 100%',
      });
    }
  });

export const datasetMetadataSchema = z.object({
  schemaVersion: z.string().min(1),
  datasetKind: z.enum([
    'synthetic-demo',
    'inspire-hep-pilot',
    'live-api',
  ]),
  period: z.string().regex(/^\d{4}$/),
  generatedAt: z.string().datetime({ offset: true }),
  latestUpdateAt: optionalFromNullable(z.string().datetime({ offset: true })),
  sourceSnapshotIds: z.array(entityIdSchema).default([]),
  updateSequence: z.number().int().min(0).default(0),
  disclaimer: z.string().min(1),
  provenance: recordProvenanceSchema,
});

export const atlasDatasetSchema = z
  .object({
    metadata: datasetMetadataSchema,
    scienceDomains: z.array(scienceDomainSchema).default([]),
    fields: z.array(researchFieldSchema).min(1),
    countries: z.array(countrySchema).min(1),
    geographicViews: z.array(geographicViewSchema).default([]),
    institutions: z.array(institutionSchema),
    researchers: z.array(researcherSchema),
    researchGroups: z.array(researchGroupSchema).default([]),
    affiliations: z.array(affiliationSchema).default([]),
    papers: z.array(paperSchema).default([]),
    authorships: z.array(authorshipSchema).default([]),
    externalResources: z.array(externalResourceSchema).default([]),
    rawEntityRecords: z.array(rawEntityRecordSchema).default([]),
    identityResolutions: z.array(identityResolutionSchema).default([]),
    sourceSnapshots: z.array(sourceSnapshotSchema).default([]),
    datasetUpdates: z.array(datasetUpdateSchema).default([]),
    historicalEvents: z.array(historicalEventSchema).default([]),
    metricDefinitions: z.array(metricDefinitionSchema).min(1),
    metricObservations: z.array(metricObservationSchema),
  })
  .superRefine((dataset, context) => {
    const fieldIds = new Set(dataset.fields.map((field) => field.id));
    const scienceDomainIds = new Set(
      dataset.scienceDomains.map((domain) => domain.id),
    );
    const countryIds = new Set(dataset.countries.map((country) => country.id));
    const institutionIds = new Set(
      dataset.institutions.map((institution) => institution.id),
    );
    const researcherIds = new Set(
      dataset.researchers.map((researcher) => researcher.id),
    );
    const researchGroupsById = new Map(
      dataset.researchGroups.map((group) => [group.id, group]),
    );
    const paperIds = new Set(dataset.papers.map((paper) => paper.id));
    const sourceSnapshotIds = new Set(
      dataset.sourceSnapshots.map((snapshot) => snapshot.id),
    );
    const rawEntityRecordsById = new Map(
      dataset.rawEntityRecords.map((record) => [record.id, record]),
    );
    const metricDefinitionIds = new Set(
      dataset.metricDefinitions.map((definition) => definition.id),
    );
    const geographicViewCountryIds = new Set<string>();
    const mappedGeometryIsoNumerics = new Set<string>();

    const reportDuplicateIds = (
      records: Array<{ id: string }>,
      path: string,
    ) => {
      const ids = new Set<string>();
      records.forEach((record, index) => {
        if (ids.has(record.id)) {
          context.addIssue({
            code: 'custom',
            path: [path, index, 'id'],
            message: `Duplicate ${path} identifier: ${record.id}`,
          });
        }
        ids.add(record.id);
      });
    };

    reportDuplicateIds(dataset.externalResources, 'externalResources');
    reportDuplicateIds(dataset.rawEntityRecords, 'rawEntityRecords');
    reportDuplicateIds(dataset.identityResolutions, 'identityResolutions');
    reportDuplicateIds(dataset.sourceSnapshots, 'sourceSnapshots');
    reportDuplicateIds(dataset.datasetUpdates, 'datasetUpdates');

    dataset.scienceDomains.forEach((domain, index) => {
      domain.fieldIds.forEach((fieldId) => {
        if (!fieldIds.has(fieldId)) {
          context.addIssue({
            code: 'custom',
            path: ['scienceDomains', index, 'fieldIds'],
            message: `Unknown field: ${fieldId}`,
          });
        }
      });
    });

    dataset.geographicViews.forEach((view, index) => {
      if (geographicViewCountryIds.has(view.countryId)) {
        context.addIssue({
          code: 'custom',
          path: ['geographicViews', index, 'countryId'],
          message: `Duplicate geographic view for country: ${view.countryId}`,
        });
      }
      geographicViewCountryIds.add(view.countryId);

      if (!countryIds.has(view.countryId)) {
        context.addIssue({
          code: 'custom',
          path: ['geographicViews', index, 'countryId'],
          message: `Unknown country: ${view.countryId}`,
        });
      }
      view.geometryIsoNumerics.forEach((isoNumeric) => {
        if (mappedGeometryIsoNumerics.has(isoNumeric)) {
          context.addIssue({
            code: 'custom',
            path: ['geographicViews', index, 'geometryIsoNumerics'],
            message: `Geometry is assigned to multiple views: ${isoNumeric}`,
          });
        }
        mappedGeometryIsoNumerics.add(isoNumeric);
      });
      view.locationCountryIds.forEach((countryId) => {
        if (!countryIds.has(countryId)) {
          context.addIssue({
            code: 'custom',
            path: ['geographicViews', index, 'locationCountryIds'],
            message: `Unknown location country: ${countryId}`,
          });
        }
      });
    });

    dataset.institutions.forEach((institution, index) => {
      if (!countryIds.has(institution.countryId)) {
        context.addIssue({
          code: 'custom',
          path: ['institutions', index, 'countryId'],
          message: `Unknown country: ${institution.countryId}`,
        });
      }
      institution.fieldIds.forEach((fieldId) => {
        if (!fieldIds.has(fieldId)) {
          context.addIssue({
            code: 'custom',
            path: ['institutions', index, 'fieldIds'],
            message: `Unknown field: ${fieldId}`,
          });
        }
      });
    });

    dataset.researchers.forEach((researcher, index) => {
      researcher.fieldIds.forEach((fieldId) => {
        if (!fieldIds.has(fieldId)) {
          context.addIssue({
            code: 'custom',
            path: ['researchers', index, 'fieldIds'],
            message: `Unknown field: ${fieldId}`,
          });
        }
      });
    });

    dataset.researchGroups.forEach((group, index) => {
      if (!institutionIds.has(group.institutionId)) {
        context.addIssue({
          code: 'custom',
          path: ['researchGroups', index, 'institutionId'],
          message: `Unknown institution: ${group.institutionId}`,
        });
      }
      group.fieldIds.forEach((fieldId) => {
        if (!fieldIds.has(fieldId)) {
          context.addIssue({
            code: 'custom',
            path: ['researchGroups', index, 'fieldIds'],
            message: `Unknown field: ${fieldId}`,
          });
        }
      });
    });

    dataset.affiliations.forEach((affiliation, index) => {
      if (!researcherIds.has(affiliation.researcherId)) {
        context.addIssue({
          code: 'custom',
          path: ['affiliations', index, 'researcherId'],
          message: `Unknown researcher: ${affiliation.researcherId}`,
        });
      }
      if (!institutionIds.has(affiliation.institutionId)) {
        context.addIssue({
          code: 'custom',
          path: ['affiliations', index, 'institutionId'],
          message: `Unknown institution: ${affiliation.institutionId}`,
        });
      }
      if (affiliation.researchGroupId) {
        const group = researchGroupsById.get(affiliation.researchGroupId);
        if (!group) {
          context.addIssue({
            code: 'custom',
            path: ['affiliations', index, 'researchGroupId'],
            message: `Unknown research group: ${affiliation.researchGroupId}`,
          });
        } else if (group.institutionId !== affiliation.institutionId) {
          context.addIssue({
            code: 'custom',
            path: ['affiliations', index, 'researchGroupId'],
            message: 'Research group and affiliation institutions differ',
          });
        }
      }
      if (
        affiliation.startYear !== undefined &&
        affiliation.endYear !== undefined &&
        affiliation.endYear < affiliation.startYear
      ) {
        context.addIssue({
          code: 'custom',
          path: ['affiliations', index, 'endYear'],
          message: 'Affiliation end year precedes its start year',
        });
      }
    });

    dataset.externalResources.forEach((resource, index) => {
      const entityExists =
        (resource.entityType === 'institution' &&
          institutionIds.has(resource.entityId)) ||
        (resource.entityType === 'research-group' &&
          researchGroupsById.has(resource.entityId)) ||
        (resource.entityType === 'researcher' &&
          researcherIds.has(resource.entityId)) ||
        (resource.entityType === 'paper' && paperIds.has(resource.entityId));
      if (!entityExists) {
        context.addIssue({
          code: 'custom',
          path: ['externalResources', index, 'entityId'],
          message: `Unknown external resource owner: ${resource.entityId}`,
        });
      }
    });

    dataset.rawEntityRecords.forEach((record, index) => {
      if (
        record.sourceSnapshotId &&
        !sourceSnapshotIds.has(record.sourceSnapshotId)
      ) {
        context.addIssue({
          code: 'custom',
          path: ['rawEntityRecords', index, 'sourceSnapshotId'],
          message: `Unknown source snapshot: ${record.sourceSnapshotId}`,
        });
      }
    });

    dataset.identityResolutions.forEach((resolution, index) => {
      const rawRecord = rawEntityRecordsById.get(resolution.rawEntityRecordId);
      if (!rawRecord) {
        context.addIssue({
          code: 'custom',
          path: ['identityResolutions', index, 'rawEntityRecordId'],
          message: `Unknown raw entity record: ${resolution.rawEntityRecordId}`,
        });
        return;
      }
      if (rawRecord.entityType !== resolution.entityType) {
        context.addIssue({
          code: 'custom',
          path: ['identityResolutions', index, 'entityType'],
          message: 'Raw record and identity resolution entity types differ',
        });
      }
      resolution.evidence.forEach((evidence) => {
        if (!evidence.candidateEntityId) {
          return;
        }
        const candidateExists =
          resolution.entityType === 'institution'
            ? institutionIds.has(evidence.candidateEntityId)
            : researcherIds.has(evidence.candidateEntityId);
        if (!candidateExists) {
          context.addIssue({
            code: 'custom',
            path: ['identityResolutions', index, 'evidence'],
            message: `Unknown identity candidate: ${evidence.candidateEntityId}`,
          });
        }
      });
      if (resolution.status !== 'matched' || !resolution.canonicalEntityId) {
        return;
      }
      const canonicalExists =
        resolution.entityType === 'institution'
          ? institutionIds.has(resolution.canonicalEntityId)
          : researcherIds.has(resolution.canonicalEntityId);
      if (!canonicalExists) {
        context.addIssue({
          code: 'custom',
          path: ['identityResolutions', index, 'canonicalEntityId'],
          message: `Unknown canonical entity: ${resolution.canonicalEntityId}`,
        });
      }
    });

    dataset.sourceSnapshots.forEach((snapshot, index) => {
      if (
        snapshot.previousSnapshotId &&
        !sourceSnapshotIds.has(snapshot.previousSnapshotId)
      ) {
        context.addIssue({
          code: 'custom',
          path: ['sourceSnapshots', index, 'previousSnapshotId'],
          message: `Unknown previous source snapshot: ${snapshot.previousSnapshotId}`,
        });
      }
    });

    dataset.metadata.sourceSnapshotIds.forEach((snapshotId) => {
      if (!sourceSnapshotIds.has(snapshotId)) {
        context.addIssue({
          code: 'custom',
          path: ['metadata', 'sourceSnapshotIds'],
          message: `Unknown metadata source snapshot: ${snapshotId}`,
        });
      }
    });

    dataset.datasetUpdates.forEach((update, index) => {
      update.sourceSnapshotIds.forEach((snapshotId) => {
        if (!sourceSnapshotIds.has(snapshotId)) {
          context.addIssue({
            code: 'custom',
            path: ['datasetUpdates', index, 'sourceSnapshotIds'],
            message: `Unknown update source snapshot: ${snapshotId}`,
          });
        }
      });
    });

    dataset.papers.forEach((paper, index) => {
      paper.fieldIds.forEach((fieldId) => {
        if (!fieldIds.has(fieldId)) {
          context.addIssue({
            code: 'custom',
            path: ['papers', index, 'fieldIds'],
            message: `Unknown field: ${fieldId}`,
          });
        }
      });
    });

    dataset.authorships.forEach((authorship, index) => {
      if (!paperIds.has(authorship.paperId)) {
        context.addIssue({
          code: 'custom',
          path: ['authorships', index, 'paperId'],
          message: `Unknown paper: ${authorship.paperId}`,
        });
      }
      if (!researcherIds.has(authorship.researcherId)) {
        context.addIssue({
          code: 'custom',
          path: ['authorships', index, 'researcherId'],
          message: `Unknown researcher: ${authorship.researcherId}`,
        });
      }
    });

    dataset.historicalEvents.forEach((event, index) => {
      if (!fieldIds.has(event.fieldId)) {
        context.addIssue({
          code: 'custom',
          path: ['historicalEvents', index, 'fieldId'],
          message: `Unknown field: ${event.fieldId}`,
        });
      }
      event.relatedResearcherIds.forEach((researcherId) => {
        if (!researcherIds.has(researcherId)) {
          context.addIssue({
            code: 'custom',
            path: ['historicalEvents', index, 'relatedResearcherIds'],
            message: `Unknown researcher: ${researcherId}`,
          });
        }
      });
      event.relatedInstitutionIds.forEach((institutionId) => {
        if (!institutionIds.has(institutionId)) {
          context.addIssue({
            code: 'custom',
            path: ['historicalEvents', index, 'relatedInstitutionIds'],
            message: `Unknown institution: ${institutionId}`,
          });
        }
      });
    });

    dataset.metricObservations.forEach((observation, index) => {
      if (!metricDefinitionIds.has(observation.metricId)) {
        context.addIssue({
          code: 'custom',
          path: ['metricObservations', index, 'metricId'],
          message: `Unknown metric definition: ${observation.metricId}`,
        });
      }
      if (!observation.fieldId && !observation.scienceDomainId) {
        context.addIssue({
          code: 'custom',
          path: ['metricObservations', index],
          message: 'Metric observation requires a field or science domain',
        });
      }
      if (observation.fieldId && !fieldIds.has(observation.fieldId)) {
        context.addIssue({
          code: 'custom',
          path: ['metricObservations', index, 'fieldId'],
          message: `Unknown field: ${observation.fieldId}`,
        });
      }
      if (
        observation.scienceDomainId &&
        !scienceDomainIds.has(observation.scienceDomainId)
      ) {
        context.addIssue({
          code: 'custom',
          path: ['metricObservations', index, 'scienceDomainId'],
          message: `Unknown science domain: ${observation.scienceDomainId}`,
        });
      }
      if (
        observation.entityType === 'country' &&
        !countryIds.has(observation.entityId)
      ) {
        context.addIssue({
          code: 'custom',
          path: ['metricObservations', index, 'entityId'],
          message: `Unknown country: ${observation.entityId}`,
        });
      }
      if (
        observation.entityType === 'institution' &&
        !institutionIds.has(observation.entityId)
      ) {
        context.addIssue({
          code: 'custom',
          path: ['metricObservations', index, 'entityId'],
          message: `Unknown institution: ${observation.entityId}`,
        });
      }
      if (
        observation.entityType === 'science-domain' &&
        !scienceDomainIds.has(observation.entityId)
      ) {
        context.addIssue({
          code: 'custom',
          path: ['metricObservations', index, 'entityId'],
          message: `Unknown science domain: ${observation.entityId}`,
        });
      }
      if (
        observation.entityType === 'field' &&
        !fieldIds.has(observation.entityId)
      ) {
        context.addIssue({
          code: 'custom',
          path: ['metricObservations', index, 'entityId'],
          message: `Unknown field: ${observation.entityId}`,
        });
      }
      if (
        observation.entityType === 'research-group' &&
        !researchGroupsById.has(observation.entityId)
      ) {
        context.addIssue({
          code: 'custom',
          path: ['metricObservations', index, 'entityId'],
          message: `Unknown research group: ${observation.entityId}`,
        });
      }
      if (
        observation.entityType === 'researcher' &&
        !researcherIds.has(observation.entityId)
      ) {
        context.addIssue({
          code: 'custom',
          path: ['metricObservations', index, 'entityId'],
          message: `Unknown researcher: ${observation.entityId}`,
        });
      }
    });
  });
