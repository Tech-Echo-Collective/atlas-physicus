import { z } from 'zod';
import { prototypeMetricId } from './models';

const entityIdSchema = z.string().min(1).regex(/^[a-z0-9-]+$/);
const fieldIdSchema = z.string().min(1).regex(/^[a-z0-9-]+$/);

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

export const institutionSchema = z.object({
  id: entityIdSchema,
  name: z.string().min(1),
  countryId: entityIdSchema,
  city: z.string().min(1),
  fieldIds: z.array(fieldIdSchema).min(1),
});

export const researcherSchema = z.object({
  id: entityIdSchema,
  name: z.string().min(1),
  institutionId: entityIdSchema,
  fieldIds: z.array(fieldIdSchema).min(1),
});

export const metricObservationSchema = z.object({
  id: entityIdSchema,
  entityType: z.enum(['country', 'institution', 'researcher', 'field']),
  entityId: entityIdSchema,
  fieldId: fieldIdSchema,
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
    fields: z.array(researchFieldSchema).min(1),
    countries: z.array(countrySchema).min(1),
    institutions: z.array(institutionSchema),
    researchers: z.array(researcherSchema),
    metricObservations: z.array(metricObservationSchema),
  })
  .superRefine((dataset, context) => {
    const fieldIds = new Set(dataset.fields.map((field) => field.id));
    const countryIds = new Set(dataset.countries.map((country) => country.id));
    const institutionIds = new Set(
      dataset.institutions.map((institution) => institution.id),
    );

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
      if (!institutionIds.has(researcher.institutionId)) {
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

    dataset.metricObservations.forEach((observation, index) => {
      if (!fieldIds.has(observation.fieldId)) {
        context.addIssue({
          code: 'custom',
          path: ['metricObservations', index, 'fieldId'],
          message: `Unknown field: ${observation.fieldId}`,
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
    });
  });
