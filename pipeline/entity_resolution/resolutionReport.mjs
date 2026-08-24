export function summarizeEntityResolution(normalizedPilot) {
  const report = normalizedPilot.resolutionReport;
  const identityResolution = normalizedPilot.identityResolution;
  const resolutionRate = report.affiliationMentions
    ? report.resolvedAffiliationMentions / report.affiliationMentions
    : 0;

  const authoritativeResearcherMatches =
    (report.researcherIdentityMethods['inspire-author-record'] ?? 0) +
    (report.researcherIdentityMethods['inspire-bai'] ?? 0);
  const inferredResearcherIdentities =
    identityResolution.unresolved.inferredResearchers.length;
  const unresolvedInstitutionCount =
    report.unresolvedInstitutionRecords.length +
    report.unfetchedInstitutionReferences.length +
    report.failedInstitutionFetches.length;

  return {
    ...report,
    affiliationResolutionRate: Math.round(resolutionRate * 10_000) / 10_000,
    matchedEntities: {
      researchers: authoritativeResearcherMatches,
      institutions: report.normalizedInstitutions,
      affiliations: report.normalizedAffiliations,
      affiliationMentions: report.resolvedAffiliationMentions,
    },
    unresolvedEntities: {
      researchers: inferredResearcherIdentities,
      institutions: unresolvedInstitutionCount,
      affiliationMentions: report.unresolvedAffiliationMentions,
    },
    confidence: {
      meanResearcherIdentity: report.meanResearcherIdentityConfidence,
      affiliationResolutionRate: Math.round(resolutionRate * 10_000) / 10_000,
      authoritativeResearcherThreshold: 0.9,
      inferredResearcherConfidence: 0.62,
    },
    methodology: {
      researchers: [
        'INSPIRE author record identifier',
        'INSPIRE BAI identifier',
        'normalized name plus first resolved affiliation as an unresolved candidate only',
      ],
      institutions:
        'INSPIRE institution record identifier with address-derived ISO country mapping',
      affiliations:
        'direct literature-author affiliation record references; unresolved variants are retained in the report',
      unresolvedResearchers:
        'name-and-affiliation candidates are retained as inferred evidence and excluded from canonical entities until resolved',
      identityLayers:
        'Every source appearance is retained as a raw entity record, linked through an explicit matched, inferred, or unresolved decision, and kept separate from the canonical entity.',
      temporalAffiliations:
        'Publication affiliation mentions are stored as dated observations. They are evidence of an affiliation at that publication date, not asserted employment intervals.',
      externalResources:
        'URLs are stored in ExternalResource records linked by canonical entity ID; canonical entities contain identifiers but no embedded URLs.',
    },
    identityArchitecture: {
      schemaVersion: identityResolution.schemaVersion,
      resolutionVersion: identityResolution.resolutionVersion,
      rawEntities: {
        institutionRecords:
          identityResolution.rawEntities.institutionRecords.length,
        institutionMentions:
          identityResolution.rawEntities.institutionMentions.length,
        researcherAppearances:
          identityResolution.rawEntities.researcherAppearances.length,
      },
      decisions: {
        institution: identityResolution.resolvedIdentities.institutions.length,
        researcher: identityResolution.resolvedIdentities.researchers.length,
        matchedInstitution:
          identityResolution.resolvedIdentities.institutions.filter(
            (decision) => decision.status === 'matched',
          ).length,
        matchedResearcher:
          identityResolution.resolvedIdentities.researchers.filter(
            (decision) => decision.status === 'matched',
          ).length,
        inferredResearcher:
          identityResolution.resolvedIdentities.researchers.filter(
            (decision) => decision.status === 'inferred',
          ).length,
      },
      canonicalEntities: {
        institutions:
          identityResolution.canonicalEntities.institutions.length,
        researchers: identityResolution.canonicalEntities.researchers.length,
      },
      temporalAffiliationObservations:
        identityResolution.temporalAffiliations.length,
      externalResources: identityResolution.externalResources.length,
    },
  };
}
