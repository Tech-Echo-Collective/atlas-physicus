import { pilotYears } from '../config.mjs';

const metricIds = {
  activity: 'research_activity_score',
  impact: 'research_impact',
  collaboration: 'collaboration',
  momentum: 'momentum',
};

function entityYearKey(entityType, entityId, year) {
  return `${entityType}|${entityId}|${year}`;
}

function ensureAccumulator(accumulators, entityType, entityId, year) {
  const key = entityYearKey(entityType, entityId, year);
  if (!accumulators.has(key)) {
    accumulators.set(key, {
      entityType,
      entityId,
      year,
      papers: 0,
      citations: 0,
      partners: new Set(),
    });
  }
  return accumulators.get(key);
}

function accumulateEntities(
  accumulators,
  entityType,
  entityIds,
  year,
  citations,
) {
  entityIds.forEach((entityId) => {
    const accumulator = ensureAccumulator(
      accumulators,
      entityType,
      entityId,
      year,
    );
    accumulator.papers += 1;
    accumulator.citations += citations;
    entityIds.forEach((partnerId) => {
      if (partnerId !== entityId) {
        accumulator.partners.add(partnerId);
      }
    });
  });
}

function normalizedValues(rawValues) {
  const values = [...rawValues.values()];
  if (values.length === 0) {
    return new Map();
  }
  const minimum = Math.min(...values);
  const maximum = Math.max(...values);
  if (maximum === minimum) {
    return new Map(
      [...rawValues.keys()].map((key) => [key, maximum === 0 ? 0 : 50]),
    );
  }
  return new Map(
    [...rawValues].map(([key, value]) => [
      key,
      Math.round(((value - minimum) / (maximum - minimum)) * 1_000) / 10,
    ]),
  );
}

function observationProvenance(rawSnapshot, confidence) {
  return {
    source: 'Derived from the INSPIRE-HEP pilot snapshot',
    sourceType: 'derived',
    version: rawSnapshot.metadata.sourceVersion,
    status: 'unverified',
    confidence,
    retrievedAt: rawSnapshot.metadata.retrievedAt,
  };
}

function metricObservation({
  entityType,
  entityId,
  year,
  metricId,
  value,
  algorithmVersion,
  calculationVersion,
  calculatedAt,
  rawSnapshot,
  confidence,
  config,
}) {
  return {
    id: `pilot-${metricId.replaceAll('_', '-')}-${entityType}-${entityId}-${year}`,
    entityType,
    entityId,
    scienceDomainId: config.scienceDomainId,
    fieldId: config.fieldId,
    metricId,
    period: String(year),
    value,
    source: config.sourceName,
    algorithmVersion,
    calculationVersion,
    calculatedAt,
    provenance: observationProvenance(
      rawSnapshot,
      confidence,
    ),
  };
}

export function calculatePilotMetrics(
  normalizedPilot,
  rawSnapshot,
  config,
  calculatedAt = new Date().toISOString(),
) {
  const accumulators = new Map();
  normalizedPilot.paperFacts.forEach((fact) => {
    accumulateEntities(
      accumulators,
      'institution',
      fact.institutionIds,
      fact.year,
      fact.citationCountWithoutSelfCitations,
    );
    accumulateEntities(
      accumulators,
      'country',
      fact.countryIds,
      fact.year,
      fact.citationCountWithoutSelfCitations,
    );
  });

  const entitySets = {
    country: normalizedPilot.countries.map((country) => country.id),
    institution: normalizedPilot.institutions.map(
      (institution) => institution.id,
    ),
  };
  const years = pilotYears(config);
  const observations = [];
  const sampledEntityYears = {
    country: 0,
    institution: 0,
  };
  const confidence = Math.max(
    0,
    Math.min(
      1,
      normalizedPilot.resolutionReport.affiliationMentions
        ? normalizedPilot.resolutionReport.resolvedAffiliationMentions /
            normalizedPilot.resolutionReport.affiliationMentions
        : 0,
    ),
  );

  Object.entries(entitySets).forEach(([entityType, entityIds]) => {
    years.forEach((year) => {
      const activeEntityIds = entityIds.filter(
        (entityId) =>
          (accumulators.get(entityYearKey(entityType, entityId, year))
            ?.papers ?? 0) > 0,
      );
      sampledEntityYears[entityType] += activeEntityIds.length;

      const activityRaw = new Map();
      const impactRaw = new Map();
      const collaborationRaw = new Map();
      const momentumRaw = new Map();

      activeEntityIds.forEach((entityId) => {
        const current = accumulators.get(
          entityYearKey(entityType, entityId, year),
        );
        activityRaw.set(entityId, current?.papers ?? 0);
        impactRaw.set(entityId, Math.log1p(current?.citations ?? 0));
        collaborationRaw.set(entityId, current?.partners.size ?? 0);

        const recent = [year - 2, year - 1, year].reduce(
          (sum, candidateYear) =>
            sum +
            (accumulators.get(
              entityYearKey(entityType, entityId, candidateYear),
            )?.papers ?? 0),
          0,
        );
        const previous = [year - 5, year - 4, year - 3].reduce(
          (sum, candidateYear) =>
            sum +
            (accumulators.get(
              entityYearKey(entityType, entityId, candidateYear),
            )?.papers ?? 0),
          0,
        );
        momentumRaw.set(
          entityId,
          (recent - previous) / Math.max(1, recent + previous),
        );
      });

      const normalizedByMetric = {
        activity: normalizedValues(activityRaw),
        impact: normalizedValues(impactRaw),
        collaboration: normalizedValues(collaborationRaw),
        momentum: normalizedValues(momentumRaw),
      };

      Object.entries(normalizedByMetric).forEach(([metricKey, values]) => {
        activeEntityIds.forEach((entityId) => {
          observations.push(
            metricObservation({
              entityType,
              entityId,
              year,
              metricId: metricIds[metricKey],
              value: values.get(entityId),
              algorithmVersion: config.algorithms[metricKey],
              calculationVersion: config.pilotVersion,
              calculatedAt,
              rawSnapshot,
              confidence,
              config,
            }),
          );
        });
      });
    });
  });

  return {
    calculatedAt,
    observations,
    summary: {
      observationCount: observations.length,
      entityCounts: {
        countries: entitySets.country.length,
        institutions: entitySets.institution.length,
      },
      sampledEntityYears: {
        countries: sampledEntityYears.country,
        institutions: sampledEntityYears.institution,
      },
      period: `${config.startYear}-${config.endYear}`,
      fieldId: config.fieldId,
      metrics: Object.values(metricIds),
      attribution:
        'Each paper fully attributes participation to every resolved affiliated institution and country.',
      normalization:
        'Within-year min-max scaling by entity type among entities with sampled participation in that year.',
      formulas: {
        research_activity_score:
          'Count of distinct sampled papers with at least one resolved affiliation to the entity in year t.',
        research_impact:
          'log1p(sum of INSPIRE citation_count_without_self_citations across the entity\'s fully attributed sampled papers in year t).',
        collaboration:
          'Count of distinct peer entities co-participating with the entity in at least one sampled paper in year t.',
        momentum:
          '(sampled participation in t-2..t minus sampled participation in t-5..t-3) / max(1, the sum of both windows).',
        outputScaling:
          'For each metric, year, and entity type: 100 * (raw - active minimum) / (active maximum - active minimum); a constant positive cohort maps to 50 and a constant zero cohort maps to 0.',
      },
      missingDataTreatment:
        'No observation is emitted when an entity has no resolved sampled paper participation in a year; absence from the bounded sample is not encoded as measured zero.',
      resolutionConfidence: Math.round(confidence * 1_000) / 1_000,
    },
  };
}
