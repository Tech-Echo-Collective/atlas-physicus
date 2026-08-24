import type {
  AtlasDataset,
  AtlasSearchEntityType,
  AtlasSearchResult,
  ExternalIdentifier,
} from '../domain/models';

type SearchMatchMethod = AtlasSearchResult['matchedOn'];

interface SearchTerm {
  value: string;
  method: SearchMatchMethod;
  ceiling: number;
}

interface SearchCandidate {
  entityId: string;
  entityType: AtlasSearchEntityType;
  label: string;
  context: string;
  identityConfidence?: number;
  terms: SearchTerm[];
  externalIds: ExternalIdentifier[];
}

interface ScoredMatch {
  score: number;
  method: SearchMatchMethod;
  matchedValue: string;
}

const acronymStopWords = new Set([
  'a',
  'an',
  'and',
  'at',
  'for',
  'in',
  'of',
  'on',
  'the',
]);

export function normalizeSearchText(value: string): string {
  return value
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLocaleLowerCase()
    .replace(/&/g, ' and ')
    .replace(/[^a-z0-9]+/g, ' ')
    .trim()
    .replace(/\s+/g, ' ');
}

function acronym(value: string): string {
  return normalizeSearchText(value)
    .split(' ')
    .filter((token) => token && !acronymStopWords.has(token))
    .map((token) => token[0])
    .join('');
}

function editDistance(left: string, right: string): number {
  if (left === right) {
    return 0;
  }
  if (!left.length) {
    return right.length;
  }
  if (!right.length) {
    return left.length;
  }

  const previous = Array.from({ length: right.length + 1 }, (_, index) => index);
  const current = new Array<number>(right.length + 1);

  for (let leftIndex = 1; leftIndex <= left.length; leftIndex += 1) {
    current[0] = leftIndex;
    for (let rightIndex = 1; rightIndex <= right.length; rightIndex += 1) {
      const substitutionCost =
        left[leftIndex - 1] === right[rightIndex - 1] ? 0 : 1;
      current[rightIndex] = Math.min(
        current[rightIndex - 1] + 1,
        previous[rightIndex] + 1,
        previous[rightIndex - 1] + substitutionCost,
      );
    }
    previous.splice(0, previous.length, ...current);
  }
  return previous[right.length];
}

function tokenSimilarity(left: string, right: string): number {
  const leftTokens = new Set(left.split(' ').filter(Boolean));
  const rightTokens = new Set(right.split(' ').filter(Boolean));
  if (!leftTokens.size || !rightTokens.size) {
    return 0;
  }
  const overlap = [...leftTokens].filter((token) => rightTokens.has(token)).length;
  return (2 * overlap) / (leftTokens.size + rightTokens.size);
}

function scoreText(query: string, term: SearchTerm): ScoredMatch | null {
  const candidate = normalizeSearchText(term.value);
  if (!candidate) {
    return null;
  }
  if (candidate === query) {
    return { score: term.ceiling, method: term.method, matchedValue: term.value };
  }

  const abbreviation = acronym(term.value);
  if (query.length >= 2 && abbreviation === query.replaceAll(' ', '')) {
    return {
      score: Math.min(term.ceiling, 0.97),
      method: 'abbreviation',
      matchedValue: abbreviation.toLocaleUpperCase(),
    };
  }

  if (candidate.startsWith(query) && query.length >= 3) {
    return {
      score: Math.min(term.ceiling, 0.91),
      method: term.method,
      matchedValue: term.value,
    };
  }

  if (query.length < 4) {
    return null;
  }

  const characterSimilarity =
    1 - editDistance(query, candidate) / Math.max(query.length, candidate.length);
  const tokens = tokenSimilarity(query, candidate);
  const combined = 0.68 * characterSimilarity + 0.32 * tokens;
  if (combined < 0.58) {
    return null;
  }

  return {
    score: Math.min(term.ceiling, 0.48 + combined * 0.48),
    method: 'fuzzy-name',
    matchedValue: term.value,
  };
}

function nameTerms(
  canonicalName: string,
  aliases: string[] = [],
  historicalNames: string[] = [],
): SearchTerm[] {
  return [
    { value: canonicalName, method: 'canonical-name', ceiling: 1 },
    ...aliases.map((value) => ({
      value,
      method: 'alias' as const,
      ceiling: 0.98,
    })),
    ...historicalNames.map((value) => ({
      value,
      method: 'historical-name' as const,
      ceiling: 0.94,
    })),
  ];
}

function genericTerms(label: string, identifier: string): SearchTerm[] {
  return [
    { value: label, method: 'canonical-name', ceiling: 1 },
    { value: identifier, method: 'alias', ceiling: 0.92 },
  ];
}

function buildCandidates(dataset: AtlasDataset): SearchCandidate[] {
  return [
    ...dataset.scienceDomains.map((domain) => ({
      entityId: domain.id,
      entityType: 'science-domain' as const,
      label: domain.label,
      context: 'Science domain',
      terms: genericTerms(domain.label, domain.id),
      externalIds: [],
    })),
    ...dataset.fields.map((field) => ({
      entityId: field.id,
      entityType: 'research-field' as const,
      label: field.label,
      context: `Research field · ${field.id}`,
      terms: genericTerms(field.label, field.id),
      externalIds: [],
    })),
    ...dataset.countries.map((country) => ({
      entityId: country.id,
      entityType: 'country' as const,
      label: country.name,
      context: `Country · ${country.region}`,
      terms: [
        ...genericTerms(country.name, country.id),
        { value: country.isoAlpha3, method: 'alias' as const, ceiling: 0.98 },
      ],
      externalIds: [],
    })),
    ...dataset.institutions.map((institution) => {
      const canonicalName = institution.canonicalName ?? institution.name;
      return {
        entityId: institution.id,
        entityType: 'institution' as const,
        label: canonicalName,
        context: `Institution · ${institution.city}`,
        identityConfidence: institution.identityConfidence,
        terms: [
          ...nameTerms(
            canonicalName,
            institution.aliases,
            institution.historicalNames,
          ),
          { value: institution.id, method: 'alias' as const, ceiling: 0.9 },
        ],
        externalIds: institution.externalIds ?? [],
      };
    }),
    ...dataset.researchers.map((researcher) => {
      const canonicalName = researcher.canonicalName ?? researcher.name;
      return {
        entityId: researcher.id,
        entityType: 'researcher' as const,
        label: canonicalName,
        context: `Researcher · ${researcher.fieldIds.join(' · ')}`,
        identityConfidence: researcher.identityConfidence,
        terms: [
          ...nameTerms(
            canonicalName,
            researcher.aliases,
            researcher.historicalNames,
          ),
          { value: researcher.id, method: 'alias' as const, ceiling: 0.9 },
        ],
        externalIds: researcher.externalIds ?? [],
      };
    }),
    ...dataset.researchGroups.map((group) => ({
      entityId: group.id,
      entityType: 'research-group' as const,
      label: group.name,
      context: `Research group · ${group.fieldIds.join(' · ')}`,
      terms: genericTerms(group.name, group.id),
      externalIds: [],
    })),
  ];
}

function bestCandidateMatch(
  query: string,
  candidate: SearchCandidate,
): ScoredMatch | null {
  for (const identifier of candidate.externalIds) {
    if (normalizeSearchText(identifier.value) === query) {
      return {
        score: 1,
        method: 'external-identifier',
        matchedValue: `${identifier.scheme}: ${identifier.value}`,
      };
    }
  }

  return candidate.terms.reduce<ScoredMatch | null>((best, term) => {
    const match = scoreText(query, term);
    return !match || (best && best.score >= match.score) ? best : match;
  }, null);
}

/**
 * Searches canonical entities only. Raw records enter the result space only
 * after an auditable IdentityResolution has attached their aliases or IDs to a
 * canonical entity.
 */
export class EntitySearchIndex {
  private readonly candidates: SearchCandidate[];

  constructor(dataset: AtlasDataset) {
    this.candidates = buildCandidates(dataset);
  }

  search(query: string, limit = 8): AtlasSearchResult[] {
    const normalizedQuery = normalizeSearchText(query);
    if (!normalizedQuery) {
      return [];
    }

    return this.candidates
      .map((candidate) => ({
        candidate,
        match: bestCandidateMatch(normalizedQuery, candidate),
      }))
      .filter(
        (result): result is { candidate: SearchCandidate; match: ScoredMatch } =>
          result.match !== null && result.match.score >= 0.62,
      )
      .sort(
        (left, right) =>
          right.match.score - left.match.score ||
          left.candidate.label.localeCompare(right.candidate.label),
      )
      .slice(0, limit)
      .map(({ candidate, match }) => ({
        entityId: candidate.entityId,
        entityType: candidate.entityType,
        label: candidate.label,
        context: candidate.context,
        matchConfidence: Math.round(match.score * 1_000) / 1_000,
        matchedOn: match.method,
        matchedValue: match.matchedValue,
        identityConfidence: candidate.identityConfidence,
      }));
  }
}
