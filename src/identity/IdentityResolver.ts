import type {
  DataProvenance,
  ExternalIdentifier,
  IdentityEvidence,
  IdentityResolution,
  IdentityResolutionMethod,
  Institution,
  RawEntityRecord,
  Researcher,
} from '../domain/models';

type CanonicalIdentity = Institution | Researcher;

interface CandidateMatch {
  entity: CanonicalIdentity;
  evidence: IdentityEvidence;
}

export interface IdentityResolverOptions {
  resolverVersion: string;
  fuzzyThreshold?: number;
  ambiguityMargin?: number;
  now?: () => string;
}

const defaultFuzzyThreshold = 0.75;
const defaultAmbiguityMargin = 0.05;

export function normalizeIdentityName(value: string): string {
  return value
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLocaleLowerCase()
    .replace(/&/g, ' and ')
    .replace(/[^a-z0-9]+/g, ' ')
    .trim()
    .replace(/\s+/g, ' ');
}

function normalizedIdentifier(identifier: ExternalIdentifier): string {
  return `${identifier.scheme.trim().toLocaleLowerCase()}:${identifier.value
    .trim()
    .toLocaleLowerCase()}`;
}

function bigrams(value: string): Set<string> {
  const compact = value.replaceAll(' ', '');
  if (compact.length < 2) {
    return new Set(compact ? [compact] : []);
  }
  return new Set(
    Array.from({ length: compact.length - 1 }, (_, index) =>
      compact.slice(index, index + 2),
    ),
  );
}

function nameSimilarity(left: string, right: string): number {
  const normalizedLeft = normalizeIdentityName(left);
  const normalizedRight = normalizeIdentityName(right);
  if (normalizedLeft === normalizedRight) {
    return 1;
  }
  const leftPairs = bigrams(normalizedLeft);
  const rightPairs = bigrams(normalizedRight);
  if (!leftPairs.size || !rightPairs.size) {
    return 0;
  }
  const overlap = [...leftPairs].filter((pair) => rightPairs.has(pair)).length;
  return (2 * overlap) / (leftPairs.size + rightPairs.size);
}

function namesForEntity(
  entity: CanonicalIdentity,
): Array<{ value: string; method: IdentityResolutionMethod; score: number }> {
  return [
    {
      value: entity.canonicalName ?? entity.name,
      method: 'canonical-name',
      score: 0.99,
    },
    ...(entity.aliases ?? []).map((value) => ({
      value,
      method: 'alias' as const,
      score: 0.96,
    })),
    ...(entity.historicalNames ?? []).map((value) => ({
      value,
      method: 'historical-name' as const,
      score: 0.9,
    })),
  ];
}

function matchByExternalIdentifier(
  raw: RawEntityRecord,
  entities: CanonicalIdentity[],
): CandidateMatch[] {
  const rawIds = new Set(raw.externalIds.map(normalizedIdentifier));
  if (!rawIds.size) {
    return [];
  }
  return entities.flatMap((entity) => {
    const identifier = (entity.externalIds ?? []).find((candidate) =>
      rawIds.has(normalizedIdentifier(candidate)),
    );
    return identifier
      ? [
          {
            entity,
            evidence: {
              method: 'external-identifier' as const,
              inputValue: `${identifier.scheme}:${identifier.value}`,
              candidateEntityId: entity.id,
              canonicalValue: `${identifier.scheme}:${identifier.value}`,
              score: 1,
            },
          },
        ]
      : [];
  });
}

function matchByExactName(
  raw: RawEntityRecord,
  entities: CanonicalIdentity[],
): CandidateMatch[] {
  const rawName = normalizeIdentityName(raw.rawName);
  return entities.flatMap((entity) => {
    const match = namesForEntity(entity).find(
      (candidate) => normalizeIdentityName(candidate.value) === rawName,
    );
    return match
      ? [
          {
            entity,
            evidence: {
              method: match.method,
              inputValue: raw.rawName,
              candidateEntityId: entity.id,
              canonicalValue: match.value,
              score: match.score,
            },
          },
        ]
      : [];
  });
}

function matchByFuzzyName(
  raw: RawEntityRecord,
  entities: CanonicalIdentity[],
): CandidateMatch[] {
  return entities
    .map((entity) => {
      const bestName = namesForEntity(entity)
        .map((candidate) => ({
          value: candidate.value,
          score: nameSimilarity(raw.rawName, candidate.value),
        }))
        .sort((left, right) => right.score - left.score)[0];
      return {
        entity,
        evidence: {
          method: 'fuzzy-name' as const,
          inputValue: raw.rawName,
          candidateEntityId: entity.id,
          canonicalValue: bestName.value,
          score: Math.min(0.89, bestName.score * 0.89),
        },
      };
    })
    .sort((left, right) => right.evidence.score - left.evidence.score);
}

function provenance(
  resolverVersion: string,
  confidence: number,
  resolvedAt: string,
): DataProvenance {
  return {
    source: 'Physics Atlas canonical identity resolver',
    sourceType: 'derived',
    version: resolverVersion,
    status: 'unverified',
    confidence,
    retrievedAt: resolvedAt,
  };
}

/**
 * Conservative resolver: authority IDs first, then exact canonical/alias names,
 * then an ambiguity-gated fuzzy fallback. Uncertain records remain explicit.
 */
export class CanonicalIdentityResolver {
  private readonly entitiesByType: Record<
    RawEntityRecord['entityType'],
    CanonicalIdentity[]
  >;
  private readonly options: Required<IdentityResolverOptions>;

  constructor(
    institutions: Institution[],
    researchers: Researcher[],
    options: IdentityResolverOptions,
  ) {
    this.entitiesByType = { institution: institutions, researcher: researchers };
    this.options = {
      resolverVersion: options.resolverVersion,
      fuzzyThreshold: options.fuzzyThreshold ?? defaultFuzzyThreshold,
      ambiguityMargin: options.ambiguityMargin ?? defaultAmbiguityMargin,
      now: options.now ?? (() => new Date().toISOString()),
    };
  }

  resolve(raw: RawEntityRecord): IdentityResolution {
    const candidates = this.entitiesByType[raw.entityType];
    const identifierMatches = matchByExternalIdentifier(raw, candidates);
    const exactMatches = identifierMatches.length
      ? identifierMatches
      : matchByExactName(raw, candidates);
    const fuzzyMatches = exactMatches.length
      ? []
      : matchByFuzzyName(raw, candidates);
    const eligibleFuzzy = fuzzyMatches.filter(
      (match) => match.evidence.score >= this.options.fuzzyThreshold,
    );
    const matches = exactMatches.length ? exactMatches : eligibleFuzzy;
    const top = matches[0];
    const second = matches[1];
    const isAmbiguous =
      matches.length > 1 &&
      (exactMatches.length > 0 ||
        top.evidence.score - second.evidence.score <
          this.options.ambiguityMargin);
    const status = !top ? 'unresolved' : isAmbiguous ? 'ambiguous' : 'matched';
    const auditMatches = matches.length ? matches : fuzzyMatches.slice(0, 3);
    const confidence = top?.evidence.score ?? auditMatches[0]?.evidence.score ?? 0;
    const resolvedAt = this.options.now();

    return {
      id: `resolution-${raw.id}`,
      rawEntityRecordId: raw.id,
      entityType: raw.entityType,
      status,
      ...(status === 'matched'
        ? {
            canonicalEntityId: top.entity.id,
            method: top.evidence.method,
          }
        : {}),
      confidence,
      evidence: auditMatches
        .slice(0, isAmbiguous || !top ? 3 : 1)
        .map(({ evidence }) => evidence),
      resolverVersion: this.options.resolverVersion,
      resolvedAt,
      provenance: provenance(
        this.options.resolverVersion,
        confidence,
        resolvedAt,
      ),
    };
  }

  resolveAll(records: RawEntityRecord[]): IdentityResolution[] {
    return records.map((record) => this.resolve(record));
  }
}
