function derivedProvenance(rawSnapshot, config, calculatedAt) {
  return {
    source: 'Physics Atlas INSPIRE-HEP pilot pipeline',
    sourceType: 'derived',
    version: config.pilotVersion,
    status: 'unverified',
    retrievedAt: calculatedAt,
  };
}

function rawEntityRecordsForAtlas(identityResolution) {
  const ingestedAt = identityResolution.generatedAt;
  const institutionRecords =
    identityResolution.rawEntities.institutionRecords.map((record) => ({
      id: record.id,
      entityType: 'institution',
      sourceRecordId: record.sourceRecordId,
      sourceSnapshotId: record.sourceSnapshotId,
      rawName: record.observedNames[0] ?? `Institution ${record.sourceRecordId}`,
      externalIds: record.externalIds,
      attributes: {
        sourceReference: record.sourceReference,
        observedNames: record.observedNames,
      },
      ingestedAt,
      provenance: record.provenance,
    }));
  const institutionMentions =
    identityResolution.rawEntities.institutionMentions.map((record) => ({
      id: record.id,
      entityType: 'institution',
      sourceRecordId: record.sourceRecordId,
      sourceSnapshotId: record.sourceSnapshotId,
      rawName: record.observedName ?? 'Unresolved institution mention',
      externalIds: [],
      attributes: {
        sourceReference: record.sourceReference,
        observedAt: record.observedAt,
      },
      ingestedAt,
      provenance: record.provenance,
    }));
  const researcherAppearances =
    identityResolution.rawEntities.researcherAppearances.map((record) => ({
      id: record.id,
      entityType: 'researcher',
      sourceRecordId: record.sourceRecordId ?? record.paperSourceId,
      sourceSnapshotId: record.sourceSnapshotId,
      rawName: record.observedName,
      externalIds: record.externalIds,
      attributes: {
        paperSourceId: record.paperSourceId,
        authorPosition: record.authorPosition,
        sourceReference: record.sourceReference,
        affiliationReferences: record.affiliationReferences.filter(Boolean),
        observedAt: record.observedAt,
      },
      ingestedAt,
      provenance: record.provenance,
    }));
  return [
    ...institutionRecords,
    ...institutionMentions,
    ...researcherAppearances,
  ];
}

function identityResolutionMethod(method) {
  if (
    method.includes('inspire') ||
    method === 'orcid'
  ) {
    return 'external-identifier';
  }
  if (method === 'normalized-name-and-affiliation') {
    return 'fuzzy-name';
  }
  return undefined;
}

function identityResolutionsForAtlas(identityResolution) {
  return [
    ...identityResolution.resolvedIdentities.institutions,
    ...identityResolution.resolvedIdentities.researchers,
  ].map((decision) => {
    const method = identityResolutionMethod(decision.method);
    const status =
      decision.status === 'inferred' ? 'ambiguous' : decision.status;
    const isMatched = status === 'matched';
    return {
      id: decision.id,
      rawEntityRecordId: decision.rawEntityId,
      entityType: decision.entityType,
      status,
      ...(isMatched && decision.canonicalEntityId
        ? { canonicalEntityId: decision.canonicalEntityId }
        : {}),
      ...(isMatched && method ? { method } : {}),
      confidence: decision.confidence,
      evidence: decision.evidence.map((evidence) => ({
        method: method ?? 'manual-review',
        inputValue: evidence.value,
        ...(isMatched && decision.canonicalEntityId
          ? { candidateEntityId: decision.canonicalEntityId }
          : {}),
        score: decision.confidence,
      })),
      resolverVersion: identityResolution.resolutionVersion,
      resolvedAt: identityResolution.generatedAt,
      provenance: decision.provenance,
    };
  });
}

function temporalAffiliationsForAtlas(identityResolution) {
  return identityResolution.temporalAffiliations.map((affiliation) => ({
    id: affiliation.id,
    researcherId: affiliation.researcherId,
    institutionId: affiliation.institutionId,
    startDate: affiliation.startDate,
    endDate: affiliation.endDate,
    startYear: affiliation.startYear,
    endYear: affiliation.endYear,
    source: `INSPIRE affiliation assertion on ${affiliation.sourcePaperId}`,
    confidence: affiliation.confidence,
    provenance: affiliation.provenance,
  }));
}

function metricDefinitions(rawSnapshot, config, calculatedAt) {
  const provenance = derivedProvenance(rawSnapshot, config, calculatedAt);
  const calculated = 'pilot-calculated';
  const taxonomy = 'taxonomy-only';
  return [
    {
      id: 'research_activity_score',
      name: 'Research Activity',
      category: 'Research Activity',
      description:
        'Count of distinct sampled papers fully attributed to the entity, followed by active-cohort within-year scaling.',
      interpretation:
        'Relative publication participation in this technical sample, not research quality or complete output.',
      unit: 'within-year pilot index (0–100)',
      version: 'pilot-metric-definition-v1',
      requiredData: ['resolved paper affiliations', 'paper year'],
      implementationStatus: calculated,
      provenance,
    },
    {
      id: 'research_impact',
      name: 'Research Impact',
      category: 'Research Impact',
      description:
        'log1p of the summed non-self-citation count across fully attributed sampled papers, followed by active-cohort within-year scaling.',
      interpretation:
        'Relative citation metadata in this sample; it is age-dependent and not a quality evaluation.',
      unit: 'within-year pilot index (0–100)',
      version: 'pilot-metric-definition-v1',
      requiredData: ['citation count without self citations', 'paper year'],
      implementationStatus: calculated,
      provenance,
    },
    {
      id: 'collaboration',
      name: 'Collaboration / Connectivity',
      category: 'Collaboration',
      description:
        'Count of distinct co-participating institutions or countries in sampled papers, followed by active-cohort within-year scaling.',
      interpretation:
        'Relative connectivity visible in the bounded sample, not a measure of collaboration quality.',
      unit: 'within-year pilot index (0–100)',
      version: 'pilot-metric-definition-v1',
      requiredData: ['resolved affiliations', 'paper co-participation'],
      implementationStatus: calculated,
      provenance,
    },
    {
      id: 'research_diversity',
      name: 'Research Diversity',
      category: 'Research Diversity',
      description: 'Reserved taxonomy definition for future pilot expansion.',
      interpretation:
        'No diversity value is calculated from the bounded pilot sample.',
      unit: 'taxonomy definition only',
      version: 'pilot-metric-definition-v1',
      requiredData: ['future validated topic and subfield representation'],
      implementationStatus: taxonomy,
      provenance,
    },
    {
      id: 'momentum',
      name: 'Research Momentum / Sustainability',
      category: 'Research Momentum',
      description:
        'Participation difference between t-2..t and t-5..t-3 divided by the combined-window participation (with a denominator floor of one), followed by active-cohort within-year scaling.',
      interpretation:
        'Relative change inside the bounded sample; it is neither a forecast nor evidence of sustainability.',
      unit: 'within-year pilot index (0–100)',
      version: 'pilot-metric-definition-v1',
      requiredData: ['resolved paper affiliations', 'paper year'],
      implementationStatus: calculated,
      provenance,
    },
    {
      id: 'talent_ecosystem',
      name: 'Talent Ecosystem',
      category: 'Talent Ecosystem',
      description: 'Reserved taxonomy definition for future pilot expansion.',
      interpretation:
        'No researcher-development or mobility value is calculated in this release.',
      unit: 'taxonomy definition only',
      version: 'pilot-metric-definition-v1',
      requiredData: ['future validated researcher career-path data'],
      implementationStatus: taxonomy,
      provenance,
    },
    {
      id: 'concentration_vulnerability',
      name: 'Concentration / Vulnerability',
      category: 'Concentration / Vulnerability',
      description: 'Reserved taxonomy definition for future pilot expansion.',
      interpretation:
        'No concentration or vulnerability value is calculated in this release.',
      unit: 'taxonomy definition only',
      version: 'pilot-metric-definition-v1',
      requiredData: ['future validated dependency and concentration data'],
      implementationStatus: taxonomy,
      provenance,
    },
  ];
}

export function buildPilotAtlasDataset(
  normalizedPilot,
  metricResult,
  rawSnapshot,
  config,
  snapshotManifest,
) {
  const calculatedAt = metricResult.calculatedAt;
  const provenance = derivedProvenance(rawSnapshot, config, calculatedAt);
  return {
    metadata: {
      schemaVersion: '0.7.0',
      datasetKind: 'inspire-hep-pilot',
      period: String(config.endYear),
      generatedAt: calculatedAt,
      latestUpdateAt:
        snapshotManifest?.datasetUpdates?.at(-1)?.appliedAt ?? calculatedAt,
      sourceSnapshotIds: snapshotManifest?.activeSnapshotId
        ? [snapshotManifest.activeSnapshotId]
        : [],
      updateSequence: snapshotManifest?.datasetUpdates?.length ?? 0,
      disclaimer:
        'Bounded, selection-biased INSPIRE-HEP metadata pilot for software validation only. Values are incomplete, uncertain, and must not be used as rankings or scientific conclusions.',
      provenance: {
        source: config.sourceName,
        sourceType: 'external-api',
        version: rawSnapshot.metadata.sourceVersion,
        status: 'unverified',
        retrievedAt: rawSnapshot.metadata.retrievedAt,
      },
    },
    scienceDomains: [
      {
        id: config.scienceDomainId,
        label: 'Physics',
        description:
          'INSPIRE-HEP pilot limited to primary-category high-energy theory records.',
        fieldIds: [config.fieldId],
        provenance,
      },
    ],
    fields: normalizedPilot.fields,
    countries: normalizedPilot.countries,
    geographicViews: [],
    institutions: normalizedPilot.institutions,
    researchers: normalizedPilot.researchers,
    researchGroups: [],
    affiliations: temporalAffiliationsForAtlas(
      normalizedPilot.identityResolution,
    ),
    papers: normalizedPilot.papers,
    authorships: normalizedPilot.authorships,
    externalResources: normalizedPilot.externalResources,
    rawEntityRecords: rawEntityRecordsForAtlas(
      normalizedPilot.identityResolution,
    ),
    identityResolutions: identityResolutionsForAtlas(
      normalizedPilot.identityResolution,
    ),
    historicalEvents: [],
    sourceSnapshots: snapshotManifest?.snapshots ?? [],
    datasetUpdates: snapshotManifest?.datasetUpdates ?? [],
    knowledgeGraph: {
      schemaVersion: normalizedPilot.identityResolution.schemaVersion,
      resolutionVersion:
        normalizedPilot.identityResolution.resolutionVersion,
      sourceVersion: normalizedPilot.identityResolution.sourceVersion,
      canonicalEntities:
        normalizedPilot.identityResolution.canonicalEntities,
      resolutionDecisions:
        normalizedPilot.identityResolution.resolvedIdentities,
      temporalAffiliations:
        normalizedPilot.identityResolution.temporalAffiliations,
      externalResources:
        normalizedPilot.identityResolution.externalResources,
      unresolved: normalizedPilot.identityResolution.unresolved,
    },
    metricDefinitions: metricDefinitions(rawSnapshot, config, calculatedAt),
    metricObservations: metricResult.observations,
  };
}
