import { z } from 'zod';
import { prototypeMetricId } from './models';

const entityIdSchema = z.string().min(1).regex(/^[a-z0-9-]+$/);
const fieldIdSchema = z.string().min(1).regex(/^[a-z0-9-]+$/);

export const scienceDomainSchema = z.object({
  id: entityIdSchema,
  label: z.string().min(1),
  description: z.string().min(1),
  fieldIds: z.array(fieldIdSchema).min(1),
});

export const researchFieldSchema = z.object({
  id: fieldIdSchema,
  label: z.string().min(1),
  description: z.string().min(1),
});

export const countrySchema = z.object({
  id: entityIdSchema,
  isoAlpha3: z.string().length(3),
  isoNumeric: z.string().length(3).regex(/^\d{3}$/),
  name: z.string().min(1),
  region: z.string().min(1),
});

export const geographicViewSchema = z.object({
  id: entityIdSchema,
  countryId: entityIdSchema,
  geometryIsoNumerics: z
    .array(z.string().length(3).regex(/^\d{3}$/))
    .min(1),
  locationCountryIds: z.array(entityIdSchema).min(1),
  provenance: z.literal('synthetic-demo'),
});

export const institutionSchema = z.object({
  id: entityIdSchema,
  name: z.string().min(1),
  countryId: entityIdSchema,
  city: z.string().min(1),
  fieldIds: z.array(fieldIdSchema).min(1),
  location: z
    .object({
      longitude: z.number().min(-180).max(180),
      latitude: z.number().min(-90).max(90),
    })
    .optional(),
});

export const researcherSchema = z.object({
  id: entityIdSchema,
  name: z.string().min(1),
  institutionId: entityIdSchema.optional(),
  fieldIds: z.array(fieldIdSchema).min(1),
  externalLinks: z
    .object({
      institutionalHomepage: z.string().url().optional(),
      personalWebsite: z.string().url().optional(),
      arxiv: z.string().url().optional(),
      github: z.string().url().optional(),
    })
    .optional(),
});

export const researchGroupSchema = z.object({
  id: entityIdSchema,
  name: z.string().min(1),
  institutionId: entityIdSchema,
  description: z.string().min(1),
  fieldIds: z.array(fieldIdSchema).min(1),
});

export const affiliationSchema = z.object({
  id: entityIdSchema,
  researcherId: entityIdSchema,
  institutionId: entityIdSchema,
  researchGroupId: entityIdSchema.optional(),
  startYear: z.number().int().min(1000).max(9999).optional(),
  endYear: z.number().int().min(1000).max(9999).optional(),
  provenance: z.literal('synthetic-demo'),
});

export const paperSchema = z.object({
  id: entityIdSchema,
  title: z.string().min(1),
  summary: z.string().min(1),
  year: z.number().int().min(1000).max(9999),
  fieldIds: z.array(fieldIdSchema).min(1),
  provenance: z.literal('synthetic-demo'),
});

export const authorshipSchema = z.object({
  id: entityIdSchema,
  paperId: entityIdSchema,
  researcherId: entityIdSchema,
  authorPosition: z.number().int().positive(),
});

export const historicalEventSchema = z.object({
  id: entityIdSchema,
  title: z.string().min(1),
  summary: z.string().min(1),
  year: z.number().int().min(1000).max(9999),
  fieldId: fieldIdSchema,
  relatedResearcherIds: z.array(entityIdSchema),
  relatedInstitutionIds: z.array(entityIdSchema),
  provenance: z.literal('synthetic-demo'),
});

export const metricObservationSchema = z.object({
  id: entityIdSchema,
  entityType: z.enum(['country', 'institution', 'researcher', 'field']),
  entityId: entityIdSchema,
  scienceDomainId: entityIdSchema.optional(),
  fieldId: fieldIdSchema.optional(),
  metricId: z.literal(prototypeMetricId),
  period: z.string().regex(/^\d{4}$/),
  value: z.number().min(0).max(100),
  provenance: z.literal('synthetic-demo'),
});

export const atlasDatasetSchema = z
  .object({
    metadata: z.object({
      schemaVersion: z.string().min(1),
      datasetKind: z.literal('synthetic-demo'),
      period: z.string().regex(/^\d{4}$/),
      generatedAt: z.string().datetime(),
      disclaimer: z.string().min(1),
    }),
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
    historicalEvents: z.array(historicalEventSchema).default([]),
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
    const geographicViewCountryIds = new Set<string>();
    const mappedGeometryIsoNumerics = new Set<string>();

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
      if (
        researcher.institutionId &&
        !institutionIds.has(researcher.institutionId)
      ) {
        context.addIssue({
          code: 'custom',
          path: ['researchers', index, 'institutionId'],
          message: `Unknown institution: ${researcher.institutionId}`,
        });
      }
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
    });
  });
