function slug(value) {
  return (
    String(value ?? '')
      .normalize('NFKD')
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-|-$/g, '') || 'unresolved'
  );
}

function referencedId(reference) {
  return String(reference ?? '').split('/').filter(Boolean).at(-1) ?? null;
}

function uniqueStrings(values) {
  const seen = new Set();
  return values
    .map((value) => String(value ?? '').trim())
    .filter((value) => {
      if (!value || seen.has(value.toLocaleLowerCase('en'))) {
        return false;
      }
      seen.add(value.toLocaleLowerCase('en'));
      return true;
    });
}

function uniqueIdentifiers(identifiers) {
  const seen = new Set();
  return identifiers.filter((identifier) => {
    const key = `${identifier.scheme.toLocaleLowerCase('en')}|${identifier.value.toLocaleLowerCase('en')}`;
    if (!identifier.value || seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}

function sourceProvenance(rawSnapshot, confidence) {
  return {
    source: rawSnapshot.metadata.source,
    sourceType: 'external-api',
    version: rawSnapshot.metadata.sourceVersion,
    status: 'unverified',
    confidence,
    retrievedAt: rawSnapshot.metadata.retrievedAt,
  };
}

function resolutionProvenance(rawSnapshot, config, confidence) {
  return {
    source: 'Physics Atlas identity resolution pipeline',
    sourceType: 'derived',
    version: config.identityResolutionVersion,
    status: 'unverified',
    confidence,
    retrievedAt:
      rawSnapshot.metadata.calculatedAt ?? rawSnapshot.metadata.retrievedAt,
  };
}

function normalizeExternalIdentifier(identifier) {
  const scheme = String(identifier?.schema ?? '').trim();
  let value = String(identifier?.value ?? '').trim();
  if (!scheme || !value) {
    return null;
  }
  if (scheme.toUpperCase() === 'ROR') {
    value = value.replace(/^https?:\/\/ror\.org\//i, '').replace(/\/$/, '');
  }
  return { scheme, value };
}

function institutionIdentity(metadata, sourceId) {
  const hierarchy = metadata.institution_hierarchy ?? [];
  const canonicalName =
    hierarchy.at(-1)?.name ??
    metadata.legacy_ICN ??
    metadata.ICN?.find((name) => name !== 'obsolete') ??
    `INSPIRE institution ${sourceId}`;
  const hierarchyNames = hierarchy.flatMap((item) => [item.name, item.acronym]);
  const activeIndexNames = (metadata.ICN ?? []).filter(
    (name) => String(name).toLocaleLowerCase('en') !== 'obsolete',
  );
  const historicalNames = metadata.ICN?.some(
    (name) => String(name).toLocaleLowerCase('en') === 'obsolete',
  )
    ? uniqueStrings([metadata.legacy_ICN]).filter(
        (name) => name.toLocaleLowerCase('en') !== canonicalName.toLocaleLowerCase('en'),
      )
    : [];
  const aliases = uniqueStrings([
    metadata.legacy_ICN,
    ...activeIndexNames,
    ...hierarchyNames,
  ]).filter(
    (name) =>
      name.toLocaleLowerCase('en') !== canonicalName.toLocaleLowerCase('en') &&
      !historicalNames.some(
        (historicalName) =>
          historicalName.toLocaleLowerCase('en') === name.toLocaleLowerCase('en'),
      ),
  );
  const externalIds = uniqueIdentifiers([
    { scheme: 'INSPIRE Institution', value: sourceId },
    ...(metadata.external_system_identifiers ?? [])
      .map(normalizeExternalIdentifier)
      .filter(Boolean),
  ]);
  return { canonicalName, aliases, historicalNames, externalIds };
}

function appearanceIdentityKeys(author, fallbackInstitutionReference) {
  const keys = [];
  const recordId = referencedId(author.record?.$ref);
  if (recordId) {
    keys.push(`inspire-record:${recordId}`);
  }
  (author.ids ?? []).forEach((identifier) => {
    const normalized = normalizeExternalIdentifier(identifier);
    if (normalized) {
      keys.push(
        `${normalized.scheme.toLocaleLowerCase('en')}:${normalized.value.toLocaleLowerCase('en')}`,
      );
    }
  });
  if (keys.length === 0) {
    keys.push(
      `fallback:${slug(author.full_name)}:${slug(fallbackInstitutionReference ?? 'no-affiliation')}`,
    );
  }
  return uniqueStrings(keys);
}

function selectedResearcherIdentity(identityKeys) {
  const preference = [
    ['inspire-record:', 'inspire-author-record', 0.99, 'researcher-inspire-'],
    ['orcid:', 'orcid', 0.97, 'researcher-orcid-'],
    ['inspire bai:', 'inspire-bai', 0.93, 'researcher-bai-'],
    ['inspire id:', 'inspire-id', 0.91, 'researcher-inspire-id-'],
  ];
  for (const [prefix, method, confidence, idPrefix] of preference) {
    const key = identityKeys.find((candidate) => candidate.startsWith(prefix));
    if (key) {
      return {
        id: `${idPrefix}${slug(key.slice(prefix.length))}`,
        method,
        confidence,
      };
    }
  }
  return {
    id: `researcher-${slug(identityKeys[0])}`,
    method: 'normalized-name-and-affiliation',
    confidence: 0.62,
  };
}

class DisjointSet {
  constructor(size) {
    this.parents = Array.from({ length: size }, (_, index) => index);
  }

  find(index) {
    if (this.parents[index] !== index) {
      this.parents[index] = this.find(this.parents[index]);
    }
    return this.parents[index];
  }

  union(left, right) {
    const leftRoot = this.find(left);
    const rightRoot = this.find(right);
    if (leftRoot !== rightRoot) {
      this.parents[rightRoot] = leftRoot;
    }
  }
}

function normalizeObservedDate(value, fallbackYear) {
  const candidate = String(value ?? fallbackYear);
  return /^\d{4}(?:-\d{2}(?:-\d{2})?)?$/.test(candidate)
    ? candidate
    : String(fallbackYear);
}

function addExternalResource(resources, resource) {
  if (!resource.url) {
    return;
  }
  const duplicate = resources.some(
    (candidate) =>
      candidate.entityId === resource.entityId &&
      candidate.resourceType === resource.resourceType &&
      candidate.url === resource.url,
  );
  if (!duplicate) {
    resources.push({
      id: `external-resource-${slug(resource.entityId)}-${slug(resource.resourceType)}-${resources.length + 1}`,
      isPrimary: false,
      lastVerifiedAt: resource.provenance.retrievedAt,
      ...resource,
    });
  }
}

function identifierResource(identifier) {
  const scheme = identifier.scheme.toLocaleLowerCase('en');
  if (scheme === 'orcid') {
    return {
      resourceType: 'orcid',
      label: 'ORCID record',
      url: `https://orcid.org/${identifier.value}`,
      externalId: identifier,
    };
  }
  if (scheme.includes('arxiv')) {
    return {
      resourceType: 'arxiv',
      label: 'arXiv author information',
      url: identifier.value.startsWith('http')
        ? identifier.value
        : `https://arxiv.org/a/${encodeURIComponent(identifier.value)}`,
      externalId: identifier,
    };
  }
  return null;
}

export function buildIdentityResolution(rawSnapshot, config) {
  const sourceSnapshotId = `inspire-hep-${slug(
    rawSnapshot.metadata.retrievedAt ?? rawSnapshot.metadata.sourceVersion,
  )}`;
  const institutionRecords = [];
  const institutionMentions = [];
  const researcherAppearances = [];
  const institutionDecisions = [];
  const researcherDecisions = [];
  const canonicalInstitutions = [];
  const canonicalResearchers = [];
  const temporalAffiliations = [];
  const externalResources = [];
  const institutionIdByReference = new Map();
  const observedInstitutionNamesByReference = new Map();

  rawSnapshot.yearQueries.forEach((yearQuery) => {
    yearQuery.records.forEach((record) => {
      const paperSourceId = String(record.id ?? record.metadata?.control_number);
      (record.metadata?.authors ?? []).forEach((author, authorIndex) => {
        (author.affiliations ?? []).forEach((affiliation, affiliationIndex) => {
          const reference = affiliation.record?.$ref ?? null;
          const rawId = `raw-institution-mention-${slug(paperSourceId)}-${authorIndex + 1}-${affiliationIndex + 1}`;
          institutionMentions.push({
            id: rawId,
            entityType: 'institution',
            sourceSnapshotId,
            sourceRecordId: paperSourceId,
            sourceReference: reference,
            observedName: affiliation.value ?? null,
            observedAt: normalizeObservedDate(
              record.metadata?.earliest_date,
              yearQuery.year,
            ),
            provenance: sourceProvenance(rawSnapshot, 1),
          });
          if (reference && affiliation.value) {
            const names = observedInstitutionNamesByReference.get(reference) ?? [];
            names.push(affiliation.value);
            observedInstitutionNamesByReference.set(reference, names);
          }
        });

        const rawId = `raw-researcher-appearance-${slug(paperSourceId)}-${authorIndex + 1}`;
        const fallbackReference = author.affiliations?.[0]?.record?.$ref;
        researcherAppearances.push({
          id: rawId,
          entityType: 'researcher',
          sourceSnapshotId,
          sourceRecordId: referencedId(author.record?.$ref),
          sourceReference: author.record?.$ref ?? null,
          paperSourceId,
          authorPosition: authorIndex + 1,
          observedName: author.full_name ?? 'Unknown researcher',
          externalIds: uniqueIdentifiers(
            (author.ids ?? [])
              .map(normalizeExternalIdentifier)
              .filter(Boolean),
          ),
          identityKeys: appearanceIdentityKeys(author, fallbackReference),
          affiliationReferences: (author.affiliations ?? []).map(
            (affiliation) => affiliation.record?.$ref ?? null,
          ),
          observedAt: normalizeObservedDate(
            record.metadata?.earliest_date,
            yearQuery.year,
          ),
          provenance: sourceProvenance(rawSnapshot, 1),
        });
      });
    });
  });

  rawSnapshot.institutions.forEach(({ url, record }) => {
    const metadata = record.metadata ?? {};
    const sourceId = String(record.id ?? referencedId(url) ?? 'unresolved');
    const rawId = `raw-institution-record-${slug(sourceId)}`;
    const canonicalId = `institution-inspire-${slug(sourceId)}`;
    const identity = institutionIdentity(metadata, sourceId);
    const observedNames = observedInstitutionNamesByReference.get(url) ?? [];
    identity.aliases = uniqueStrings([...identity.aliases, ...observedNames]).filter(
      (name) =>
        name.toLocaleLowerCase('en') !== identity.canonicalName.toLocaleLowerCase('en') &&
        !identity.historicalNames.some(
          (historicalName) =>
            historicalName.toLocaleLowerCase('en') === name.toLocaleLowerCase('en'),
        ),
    );
    institutionRecords.push({
      id: rawId,
      entityType: 'institution',
      sourceSnapshotId,
      sourceRecordId: sourceId,
      sourceReference: url,
      observedNames: uniqueStrings([
        metadata.legacy_ICN,
        ...(metadata.ICN ?? []),
        ...(metadata.institution_hierarchy ?? []).flatMap((item) => [
          item.name,
          item.acronym,
        ]),
      ]),
      externalIds: identity.externalIds,
      provenance: sourceProvenance(rawSnapshot, 1),
    });
    const canonical = {
      id: canonicalId,
      entityType: 'institution',
      canonicalName: identity.canonicalName,
      aliases: identity.aliases,
      historicalNames: identity.historicalNames,
      externalIds: identity.externalIds,
      identityStatus: 'matched',
      confidence: 0.99,
      researchFieldIds: [config.fieldId],
      provenance: resolutionProvenance(rawSnapshot, config, 0.99),
    };
    canonicalInstitutions.push(canonical);
    institutionIdByReference.set(url, canonicalId);
    institutionDecisions.push({
      id: `resolution-institution-record-${slug(sourceId)}`,
      rawEntityId: rawId,
      canonicalEntityId: canonicalId,
      entityType: 'institution',
      status: 'matched',
      method: 'authoritative-inspire-institution-record',
      confidence: 0.99,
      evidence: [
        { type: 'INSPIRE institution record', value: sourceId },
        ...identity.externalIds.map((identifier) => ({
          type: identifier.scheme,
          value: identifier.value,
        })),
      ],
      provenance: resolutionProvenance(rawSnapshot, config, 0.99),
    });

    (metadata.urls ?? []).forEach((resource, index) => {
      addExternalResource(externalResources, {
        entityId: canonicalId,
        entityType: 'institution',
        resourceType: 'official-institution-website',
        label: index === 0 ? 'Official institution website' : 'Institution website',
        url: resource.value,
        isPrimary: index === 0,
        confidence: 0.85,
        provenance: sourceProvenance(rawSnapshot, 0.85),
      });
    });
    addExternalResource(externalResources, {
      entityId: canonicalId,
      entityType: 'institution',
      resourceType: 'inspire',
      label: 'INSPIRE institution record',
      url: `https://inspirehep.net/institutions/${sourceId}`,
      confidence: 1,
      provenance: sourceProvenance(rawSnapshot, 1),
    });
    identity.externalIds.forEach((identifier) => {
      const resource = identifierResource(identifier);
      if (resource) {
        addExternalResource(externalResources, {
          entityId: canonicalId,
          entityType: 'institution',
          ...resource,
          confidence: 0.99,
          provenance: sourceProvenance(rawSnapshot, 0.99),
        });
      }
    });
  });

  institutionMentions.forEach((mention) => {
    const canonicalEntityId = mention.sourceReference
      ? institutionIdByReference.get(mention.sourceReference)
      : null;
    institutionDecisions.push({
      id: `resolution-${mention.id}`,
      rawEntityId: mention.id,
      canonicalEntityId: canonicalEntityId ?? null,
      entityType: 'institution',
      status: canonicalEntityId ? 'matched' : 'unresolved',
      method: canonicalEntityId
        ? 'authoritative-inspire-affiliation-reference'
        : 'unresolved-affiliation-reference',
      confidence: canonicalEntityId ? 0.98 : 0,
      evidence: [
        ...(mention.sourceReference
          ? [{ type: 'INSPIRE institution reference', value: mention.sourceReference }]
          : []),
        ...(mention.observedName
          ? [{ type: 'raw affiliation label', value: mention.observedName }]
          : []),
      ],
      provenance: resolutionProvenance(
        rawSnapshot,
        config,
        canonicalEntityId ? 0.98 : 0,
      ),
    });
  });

  const disjointSet = new DisjointSet(researcherAppearances.length);
  const firstAppearanceByKey = new Map();
  researcherAppearances.forEach((appearance, index) => {
    appearance.identityKeys.forEach((key) => {
      const firstIndex = firstAppearanceByKey.get(key);
      if (firstIndex === undefined) {
        firstAppearanceByKey.set(key, index);
      } else {
        disjointSet.union(firstIndex, index);
      }
    });
  });
  const appearanceGroups = new Map();
  researcherAppearances.forEach((appearance, index) => {
    const root = disjointSet.find(index);
    const group = appearanceGroups.get(root) ?? [];
    group.push(appearance);
    appearanceGroups.set(root, group);
  });

  const researcherIdByAppearance = new Map();
  appearanceGroups.forEach((appearances) => {
    const identityKeys = uniqueStrings(
      appearances.flatMap((appearance) => appearance.identityKeys),
    ).sort();
    const identity = selectedResearcherIdentity(identityKeys);
    const aliases = uniqueStrings(
      appearances.map((appearance) => appearance.observedName),
    );
    const externalIds = uniqueIdentifiers([
      ...appearances.flatMap((appearance) => appearance.externalIds),
      ...identityKeys
        .filter((key) => key.startsWith('inspire-record:'))
        .map((key) => ({
          scheme: 'INSPIRE Author Record',
          value: key.slice('inspire-record:'.length),
        })),
    ]);
    const canonicalName =
      [...aliases].sort((left, right) => right.length - left.length)[0] ??
      'Unknown researcher';
    const canonical = {
      id: identity.id,
      entityType: 'researcher',
      canonicalName,
      aliases: aliases.filter(
        (name) =>
          name.toLocaleLowerCase('en') !== canonicalName.toLocaleLowerCase('en'),
      ),
      historicalNames: [],
      externalIds,
      identityStatus:
        identity.method === 'normalized-name-and-affiliation'
          ? 'inferred'
          : 'matched',
      confidence: identity.confidence,
      researchFieldIds: [config.fieldId],
      provenance: resolutionProvenance(
        rawSnapshot,
        config,
        identity.confidence,
      ),
    };
    const isCanonical = canonical.identityStatus === 'matched';
    if (isCanonical) {
      canonicalResearchers.push(canonical);
    }
    appearances.forEach((appearance) => {
      if (isCanonical) {
        researcherIdByAppearance.set(appearance.id, canonical.id);
      }
      researcherDecisions.push({
        id: `resolution-${appearance.id}`,
        rawEntityId: appearance.id,
        ...(isCanonical ? { canonicalEntityId: canonical.id } : {}),
        entityType: 'researcher',
        status: canonical.identityStatus,
        method: identity.method,
        confidence: identity.confidence,
        evidence: appearance.identityKeys.map((key) => ({
          type: 'identity key',
          value: key,
        })),
        provenance: resolutionProvenance(
          rawSnapshot,
          config,
          identity.confidence,
        ),
      });
    });

    if (!isCanonical) {
      return;
    }

    externalIds.forEach((identifier) => {
      const resource = identifierResource(identifier);
      if (resource) {
        addExternalResource(externalResources, {
          entityId: canonical.id,
          entityType: 'researcher',
          ...resource,
          confidence: identity.confidence,
          provenance: sourceProvenance(rawSnapshot, identity.confidence),
        });
      }
    });
    const authorRecord = externalIds.find(
      (identifier) => identifier.scheme === 'INSPIRE Author Record',
    );
    if (authorRecord) {
      addExternalResource(externalResources, {
        entityId: canonical.id,
        entityType: 'researcher',
        resourceType: 'inspire',
        label: 'INSPIRE author record',
        url: `https://inspirehep.net/authors/${authorRecord.value}`,
        confidence: 1,
        provenance: sourceProvenance(rawSnapshot, 1),
      });
    }
  });

  researcherAppearances.forEach((appearance) => {
    appearance.affiliationReferences.forEach((reference, affiliationIndex) => {
      const institutionId = reference
        ? institutionIdByReference.get(reference)
        : null;
      const researcherId = researcherIdByAppearance.get(appearance.id);
      if (!institutionId || !researcherId) {
        return;
      }
      const decision = researcherDecisions.find(
        (candidate) => candidate.rawEntityId === appearance.id,
      );
      const confidence = Math.min(decision?.confidence ?? 0, 0.98);
      const year = Number(appearance.observedAt.slice(0, 4));
      temporalAffiliations.push({
        id: `affiliation-observation-${slug(appearance.paperSourceId)}-${appearance.authorPosition}-${affiliationIndex + 1}`,
        researcherId,
        institutionId,
        sourcePaperId: `paper-inspire-${slug(appearance.paperSourceId)}`,
        startDate: appearance.observedAt,
        endDate: appearance.observedAt,
        startYear: year,
        endYear: year,
        temporalPrecision:
          appearance.observedAt.length === 4
            ? 'year'
            : appearance.observedAt.length === 7
              ? 'month'
              : 'day',
        relationshipStatus: 'observed-on-publication',
        confidence,
        provenance: resolutionProvenance(rawSnapshot, config, confidence),
      });
    });
  });

  rawSnapshot.yearQueries.forEach((yearQuery) => {
    yearQuery.records.forEach((record) => {
      const sourceId = String(record.id ?? record.metadata?.control_number);
      const paperId = `paper-inspire-${slug(sourceId)}`;
      addExternalResource(externalResources, {
        entityId: paperId,
        entityType: 'paper',
        resourceType: 'inspire',
        label: 'INSPIRE literature record',
        url: `https://inspirehep.net/literature/${sourceId}`,
        confidence: 1,
        provenance: sourceProvenance(rawSnapshot, 1),
      });
      (record.metadata?.dois ?? []).forEach((doi) => {
        addExternalResource(externalResources, {
          entityId: paperId,
          entityType: 'paper',
        resourceType: 'doi',
        label: 'DOI record',
        url: `https://doi.org/${doi.value}`,
          externalId: { scheme: 'DOI', value: doi.value },
          confidence: 1,
          provenance: sourceProvenance(rawSnapshot, 1),
        });
      });
      (record.metadata?.arxiv_eprints ?? []).forEach((eprint) => {
        addExternalResource(externalResources, {
          entityId: paperId,
          entityType: 'paper',
          resourceType: 'arxiv',
          label: 'arXiv record',
          url: `https://arxiv.org/abs/${eprint.value}`,
          externalId: { scheme: 'arXiv', value: eprint.value },
          confidence: 1,
          provenance: sourceProvenance(rawSnapshot, 1),
        });
      });
    });
  });

  canonicalInstitutions.forEach((institution) => {
    institution.aliases = uniqueStrings(institution.aliases);
    institution.historicalNames = uniqueStrings(institution.historicalNames);
  });

  return {
    schemaVersion: '1.0.0',
    resolutionVersion: config.identityResolutionVersion,
    sourceVersion: rawSnapshot.metadata.sourceVersion,
    generatedAt:
      rawSnapshot.metadata.calculatedAt ?? rawSnapshot.metadata.retrievedAt,
    rawEntities: {
      institutionRecords,
      institutionMentions,
      researcherAppearances,
    },
    resolvedIdentities: {
      institutions: institutionDecisions,
      researchers: researcherDecisions,
    },
    canonicalEntities: {
      institutions: canonicalInstitutions,
      researchers: canonicalResearchers,
    },
    temporalAffiliations,
    externalResources,
    unresolved: {
      institutionMentions: institutionDecisions.filter(
        (decision) => decision.status === 'unresolved',
      ),
      researcherAppearances: researcherDecisions.filter(
        (decision) => decision.status === 'unresolved',
      ),
      inferredResearchers: researcherDecisions.filter(
        (decision) => decision.status === 'inferred',
      ),
    },
    resolutionIndex: {
      institutionIdByReference: Object.fromEntries(institutionIdByReference),
      researcherIdByRawAppearance: Object.fromEntries(researcherIdByAppearance),
    },
  };
}
