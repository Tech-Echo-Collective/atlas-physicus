import isoCountries from 'i18n-iso-countries';
import { buildIdentityResolution } from '../entity_resolution/identityResolution.mjs';

function slug(value) {
  return String(value ?? '')
    .normalize('NFKD')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '') || 'unresolved';
}

function referencedId(reference) {
  return String(reference ?? '').split('/').filter(Boolean).at(-1) ?? null;
}

function sourceProvenance(rawSnapshot, confidence) {
  return {
    source: 'INSPIRE-HEP REST API',
    sourceType: 'external-api',
    version: rawSnapshot.metadata.sourceVersion,
    status: 'unverified',
    ...(confidence === undefined ? {} : { confidence }),
    retrievedAt: rawSnapshot.metadata.retrievedAt,
  };
}

function preferredInstitutionName(metadata, fallback) {
  const hierarchy = metadata.institution_hierarchy ?? [];
  return (
    hierarchy.at(-1)?.name ??
    metadata.legacy_ICN ??
    fallback ??
    'Unresolved institution'
  );
}

export function normalizeInstitutionRecords(
  rawSnapshot,
  config,
  identityResolution = buildIdentityResolution(rawSnapshot, config),
) {
  const countriesById = new Map();
  const institutionsById = new Map();
  const institutionIdByReference = new Map();
  const unresolvedInstitutions = [];

  rawSnapshot.institutions.forEach(({ url, record }) => {
    const sourceId = String(record.id ?? referencedId(url) ?? 'unresolved');
    const metadata = record.metadata ?? {};
    const address = (metadata.addresses ?? []).find(
      (candidate) => candidate.country_code,
    );
    const alpha2 = String(address?.country_code ?? '').toUpperCase();
    const isoAlpha3 = isoCountries.alpha2ToAlpha3(alpha2);
    const isoNumeric = isoCountries.alpha2ToNumeric(alpha2);

    if (!address || !isoAlpha3 || !isoNumeric) {
      unresolvedInstitutions.push({
        sourceId,
        reference: url,
        reason: 'No resolvable ISO country address',
        sourceName: metadata.legacy_ICN ?? null,
      });
      return;
    }

    const countryId = `country-${isoAlpha3.toLowerCase()}`;
    if (!countriesById.has(countryId)) {
      countriesById.set(countryId, {
        id: countryId,
        isoAlpha3,
        isoNumeric: String(isoNumeric).padStart(3, '0'),
        name:
          address.country ??
          isoCountries.getName(alpha2, 'en') ??
          isoAlpha3,
        region: 'INSPIRE-HEP pilot geography',
        provenance: sourceProvenance(rawSnapshot, 0.99),
      });
    }

    const institutionId = `institution-inspire-${slug(sourceId)}`;
    const canonicalIdentity =
      identityResolution.canonicalEntities.institutions.find(
        (candidate) => candidate.id === institutionId,
      );
    institutionsById.set(institutionId, {
      id: institutionId,
      name:
        canonicalIdentity?.canonicalName ?? preferredInstitutionName(metadata),
      ...(canonicalIdentity
        ? {
            canonicalName: canonicalIdentity.canonicalName,
            aliases: canonicalIdentity.aliases,
            historicalNames: canonicalIdentity.historicalNames,
            externalIds: canonicalIdentity.externalIds,
            identityConfidence: canonicalIdentity.confidence,
          }
        : {}),
      countryId,
      city: address.cities?.[0] ?? address.state ?? 'Location unavailable',
      fieldIds: [config.fieldId],
      ...(Number.isFinite(address.longitude) &&
      Number.isFinite(address.latitude)
        ? {
            location: {
              longitude: Number(address.longitude),
              latitude: Number(address.latitude),
            },
          }
        : {}),
      provenance: sourceProvenance(rawSnapshot, 0.99),
    });
    institutionIdByReference.set(url, institutionId);
  });

  return {
    countries: [...countriesById.values()],
    institutions: [...institutionsById.values()],
    institutionIdByReference,
    unresolvedInstitutions,
  };
}

function validDoi(value) {
  return typeof value === 'string' && /^10\.\d{4,9}\/\S+$/.test(value);
}

function validArxivId(value) {
  return (
    typeof value === 'string' &&
    /^(?:arXiv:)?(?:\d{4}\.\d{4,5}|[a-z-]+\/\d{7})$/i.test(value)
  );
}

export function normalizeLiterature(rawSnapshot, config) {
  const identityResolution = buildIdentityResolution(rawSnapshot, config);
  const institutionNormalization = normalizeInstitutionRecords(
    rawSnapshot,
    config,
    identityResolution,
  );
  const researchersById = new Map();
  const affiliationsByKey = new Map();
  const papers = [];
  const authorships = [];
  const paperFacts = [];
  const unresolvedAffiliations = [];
  const authorAppearanceIdentityMethods = new Map();
  const researcherIdentityMethods = new Map();
  const researcherConfidenceById = new Map();
  const inferredResearcherSamples = [];
  let authorAppearances = 0;
  let affiliationMentions = 0;
  let resolvedAffiliationMentions = 0;

  rawSnapshot.yearQueries.forEach((yearQuery) => {
    yearQuery.records.forEach((record) => {
      const metadata = record.metadata ?? {};
      const sourceId = String(record.id ?? metadata.control_number);
      const paperId = `paper-inspire-${slug(sourceId)}`;
      const year = Number(
        String(metadata.earliest_date ?? yearQuery.year).slice(0, 4),
      );
      const doi = (metadata.dois ?? []).map((item) => item.value).find(validDoi);
      const arxivId = (metadata.arxiv_eprints ?? [])
        .map((item) => item.value)
        .find(validArxivId);
      const title =
        metadata.titles?.find((candidate) => candidate.title)?.title ??
        `INSPIRE literature record ${sourceId}`;

      papers.push({
        id: paperId,
        title,
        summary:
          'INSPIRE-HEP pilot metadata record. Abstract text is intentionally omitted from the export.',
        year,
        fieldIds: [config.fieldId],
        ...(doi ? { doi } : {}),
        ...(arxivId ? { arxivId } : {}),
        externalIdentifiers: [{ scheme: 'INSPIRE', value: sourceId }],
        provenance: sourceProvenance(rawSnapshot, 1),
      });

      const paperInstitutionIds = new Set();
      const paperCountryIds = new Set();
      (metadata.authors ?? []).forEach((author, authorIndex) => {
        authorAppearances += 1;
        const resolvedInstitutionIds = [];
        (author.affiliations ?? []).forEach((affiliation) => {
          affiliationMentions += 1;
          const reference = affiliation.record?.$ref;
          const institutionId = reference
            ? institutionNormalization.institutionIdByReference.get(reference)
            : undefined;
          if (institutionId) {
            resolvedAffiliationMentions += 1;
            resolvedInstitutionIds.push(institutionId);
            paperInstitutionIds.add(institutionId);
            const institution = institutionNormalization.institutions.find(
              (candidate) => candidate.id === institutionId,
            );
            if (institution) {
              paperCountryIds.add(institution.countryId);
            }
          } else {
            unresolvedAffiliations.push({
              paperId,
              researcher: author.full_name ?? 'Unknown researcher',
              value: affiliation.value ?? null,
              reference: reference ?? null,
            });
          }
        });

        const rawAppearanceId = `raw-researcher-appearance-${slug(sourceId)}-${authorIndex + 1}`;
        const canonicalResearcherId =
          identityResolution.resolutionIndex.researcherIdByRawAppearance[
            rawAppearanceId
          ];
        const canonicalResearcher =
          identityResolution.canonicalEntities.researchers.find(
            (candidate) => candidate.id === canonicalResearcherId,
          );
        const resolutionDecision =
          identityResolution.resolvedIdentities.researchers.find(
            (candidate) => candidate.rawEntityId === rawAppearanceId,
          );
        if (
          !canonicalResearcher ||
          resolutionDecision?.status !== 'matched'
        ) {
          const method =
            resolutionDecision?.method ?? 'unresolved-researcher-identity';
          authorAppearanceIdentityMethods.set(
            method,
            (authorAppearanceIdentityMethods.get(method) ?? 0) + 1,
          );
          if (resolutionDecision?.status === 'inferred') {
            inferredResearcherSamples.push({
              rawEntityId: rawAppearanceId,
              name: author.full_name ?? 'Unknown researcher',
              confidence: resolutionDecision.confidence,
            });
          }
          return;
        }
        const identity = {
          id: canonicalResearcher.id,
          method:
            resolutionDecision.method ?? 'identity-resolution-layer',
          confidence: canonicalResearcher.confidence,
        };
        authorAppearanceIdentityMethods.set(
          identity.method,
          (authorAppearanceIdentityMethods.get(identity.method) ?? 0) + 1,
        );
        if (!researchersById.has(identity.id)) {
          researcherIdentityMethods.set(
            identity.method,
            (researcherIdentityMethods.get(identity.method) ?? 0) + 1,
          );
          researcherConfidenceById.set(identity.id, identity.confidence);
          researchersById.set(identity.id, {
            id: identity.id,
            name:
              canonicalResearcher?.canonicalName ??
              author.full_name ??
              'Unknown researcher',
            ...(canonicalResearcher
              ? {
                  canonicalName: canonicalResearcher.canonicalName,
                  aliases: canonicalResearcher.aliases,
                  externalIds: canonicalResearcher.externalIds,
                  identityConfidence: canonicalResearcher.confidence,
                }
              : {}),
            fieldIds: [config.fieldId],
            provenance: sourceProvenance(rawSnapshot, identity.confidence),
          });
        }

        authorships.push({
          id: `authorship-${slug(sourceId)}-${authorIndex + 1}`,
          paperId,
          researcherId: identity.id,
          authorPosition: authorIndex + 1,
          provenance: sourceProvenance(rawSnapshot, identity.confidence),
        });

        resolvedInstitutionIds.forEach((institutionId) => {
          const key = `${identity.id}|${institutionId}`;
          const existing = affiliationsByKey.get(key);
          if (existing) {
            existing.startYear = Math.min(existing.startYear, year);
            existing.endYear = Math.max(existing.endYear, year);
            return;
          }
          affiliationsByKey.set(key, {
            id: `affiliation-${slug(identity.id)}-${slug(institutionId)}`,
            researcherId: identity.id,
            institutionId,
            startYear: year,
            endYear: year,
            provenance: sourceProvenance(
              rawSnapshot,
              Math.min(identity.confidence, 0.98),
            ),
          });
        });
      });

      paperFacts.push({
        paperId,
        year,
        citationCount: Number(metadata.citation_count ?? 0),
        citationCountWithoutSelfCitations: Number(
          metadata.citation_count_without_self_citations ??
            metadata.citation_count ??
            0,
        ),
        institutionIds: [...paperInstitutionIds],
        countryIds: [...paperCountryIds],
      });
    });
  });

  const confidenceValues = [...researcherConfidenceById.values()];
  const averageConfidence = confidenceValues.length
    ? confidenceValues.reduce((sum, value) => sum + value, 0) /
      confidenceValues.length
    : 0;

  return {
    fields: [
      {
        id: config.fieldId,
        label: 'High Energy Physics — Theory',
        description: `INSPIRE-HEP primary-category pilot scope for ${config.startYear}–${config.endYear}.`,
        provenance: sourceProvenance(rawSnapshot, 1),
      },
    ],
    countries: institutionNormalization.countries,
    institutions: institutionNormalization.institutions,
    researchers: [...researchersById.values()],
    affiliations: [...affiliationsByKey.values()],
    papers,
    authorships,
    paperFacts,
    identityResolution,
    temporalAffiliationObservations:
      identityResolution.temporalAffiliations,
    externalResources: identityResolution.externalResources,
    resolutionReport: {
      sourceRecords: papers.length,
      sourceInstitutionRecords: rawSnapshot.institutions.length,
      normalizedResearchFields: 1,
      normalizedCountries: institutionNormalization.countries.length,
      normalizedInstitutions: institutionNormalization.institutions.length,
      normalizedResearchers: researchersById.size,
      authorAppearances,
      researcherIdentityMethods: Object.fromEntries(
        researcherIdentityMethods,
      ),
      authorAppearanceIdentityMethods: Object.fromEntries(
        authorAppearanceIdentityMethods,
      ),
      meanResearcherIdentityConfidence:
        Math.round(averageConfidence * 1_000) / 1_000,
      inferredResearcherSamples: inferredResearcherSamples.slice(0, 25),
      affiliationMentions,
      resolvedAffiliationMentions,
      unresolvedAffiliationMentions: unresolvedAffiliations.length,
      normalizedAffiliations: affiliationsByKey.size,
      unresolvedInstitutionRecords:
        institutionNormalization.unresolvedInstitutions,
      unfetchedInstitutionReferences:
        rawSnapshot.unresolvedInstitutionReferences,
      failedInstitutionFetches: rawSnapshot.failedInstitutionFetches ?? [],
      unresolvedAffiliationSamples: unresolvedAffiliations.slice(0, 25),
      identityLayer: {
        rawInstitutionRecords:
          identityResolution.rawEntities.institutionRecords.length,
        rawInstitutionMentions:
          identityResolution.rawEntities.institutionMentions.length,
        rawResearcherAppearances:
          identityResolution.rawEntities.researcherAppearances.length,
        institutionDecisions:
          identityResolution.resolvedIdentities.institutions.length,
        researcherDecisions:
          identityResolution.resolvedIdentities.researchers.length,
        canonicalInstitutions:
          identityResolution.canonicalEntities.institutions.length,
        canonicalResearchers:
          identityResolution.canonicalEntities.researchers.length,
        unresolvedInstitutionMentions:
          identityResolution.unresolved.institutionMentions.length,
        inferredResearcherAppearances:
          identityResolution.unresolved.inferredResearchers.length,
        temporalAffiliationObservations:
          identityResolution.temporalAffiliations.length,
        externalResources: identityResolution.externalResources.length,
      },
      provenance: {
        source: rawSnapshot.metadata.source,
        sourceVersion: rawSnapshot.metadata.sourceVersion,
        retrievedAt: rawSnapshot.metadata.retrievedAt,
        fieldId: config.fieldId,
      },
    },
  };
}
