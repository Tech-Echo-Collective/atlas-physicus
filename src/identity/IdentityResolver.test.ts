import type {
  DataProvenance,
  Institution,
  RawEntityRecord,
  Researcher,
} from '../domain/models';
import { CanonicalIdentityResolver } from './IdentityResolver';

const provenance: DataProvenance = {
  source: 'identity resolver unit fixture',
  sourceType: 'external-api',
  version: 'fixture-v1',
  status: 'unverified',
};

const institutions: Institution[] = [
  {
    id: 'institution-caltech',
    name: 'California Institute of Technology',
    canonicalName: 'California Institute of Technology',
    aliases: ['Caltech', 'CIT'],
    historicalNames: ['Throop University'],
    externalIds: [{ scheme: 'ROR', value: '05dxps055' }],
    identityConfidence: 0.99,
    countryId: 'country-us',
    city: 'Pasadena',
    fieldIds: ['hep-th'],
    provenance,
  },
  {
    id: 'institution-caltech-library',
    name: 'Caltech Library',
    canonicalName: 'Caltech Library',
    aliases: [],
    historicalNames: [],
    externalIds: [],
    countryId: 'country-us',
    city: 'Pasadena',
    fieldIds: ['hep-th'],
    provenance,
  },
];

const researchers: Researcher[] = [
  {
    id: 'researcher-juan-maldacena',
    name: 'Juan Maldacena',
    canonicalName: 'Juan Maldacena',
    aliases: ['J. Maldacena'],
    historicalNames: [],
    externalIds: [
      { scheme: 'ORCID', value: '0000-0000-0000-0001' },
      { scheme: 'INSPIRE', value: '1012345' },
    ],
    identityConfidence: 0.99,
    fieldIds: ['hep-th'],
    provenance,
  },
  {
    id: 'researcher-juan-maldonado',
    name: 'Juan Maldonado',
    canonicalName: 'Juan Maldonado',
    aliases: [],
    historicalNames: [],
    externalIds: [],
    fieldIds: ['hep-th'],
    provenance,
  },
];

function rawRecord(
  overrides: Partial<RawEntityRecord> = {},
): RawEntityRecord {
  return {
    id: 'raw-institution-one',
    entityType: 'institution',
    sourceRecordId: 'source-1',
    rawName: 'Caltech',
    externalIds: [],
    attributes: {},
    ingestedAt: '2026-08-24T10:00:00.000Z',
    provenance,
    ...overrides,
  };
}

const resolver = new CanonicalIdentityResolver(institutions, researchers, {
  resolverVersion: 'identity-resolver-v1',
  now: () => '2026-08-24T12:00:00.000Z',
});

describe('CanonicalIdentityResolver', () => {
  it('resolves an institution alias to its canonical identity', () => {
    expect(resolver.resolve(rawRecord())).toEqual(
      expect.objectContaining({
        status: 'matched',
        canonicalEntityId: 'institution-caltech',
        method: 'alias',
        confidence: 0.96,
        resolverVersion: 'identity-resolver-v1',
      }),
    );
  });

  it('prioritizes authority identifiers over name similarity', () => {
    const resolution = resolver.resolve(
      rawRecord({
        id: 'raw-researcher-one',
        entityType: 'researcher',
        rawName: 'A completely different display name',
        externalIds: [{ scheme: 'orcid', value: '0000-0000-0000-0001' }],
      }),
    );

    expect(resolution).toEqual(
      expect.objectContaining({
        canonicalEntityId: 'researcher-juan-maldacena',
        method: 'external-identifier',
        confidence: 1,
      }),
    );
  });

  it('uses conservative fuzzy matching only above the configured threshold', () => {
    const resolution = resolver.resolve(
      rawRecord({
        id: 'raw-researcher-typo',
        entityType: 'researcher',
        rawName: 'Juan Maldacna',
      }),
    );

    expect(resolution).toEqual(
      expect.objectContaining({
        status: 'matched',
        canonicalEntityId: 'researcher-juan-maldacena',
        method: 'fuzzy-name',
      }),
    );
  });

  it('keeps low-confidence input explicitly unresolved', () => {
    const resolution = resolver.resolve(
      rawRecord({ id: 'raw-unknown', rawName: 'Unknown Laboratory' }),
    );

    expect(resolution).toEqual(
      expect.objectContaining({
        status: 'unresolved',
      }),
    );
    expect(resolution.confidence).toBeLessThan(0.75);
    expect(resolution.evidence.length).toBeGreaterThan(0);
    expect(resolution).not.toHaveProperty('canonicalEntityId');
  });

  it('does not choose silently when an exact alias is non-unique', () => {
    const ambiguousResolver = new CanonicalIdentityResolver(
      [
        ...institutions,
        {
          ...institutions[1],
          id: 'institution-duplicate-alias',
          aliases: ['Caltech'],
        },
      ],
      researchers,
      {
        resolverVersion: 'identity-resolver-v1',
        now: () => '2026-08-24T12:00:00.000Z',
      },
    );
    const resolution = ambiguousResolver.resolve(rawRecord());

    expect(resolution.status).toBe('ambiguous');
    expect(resolution).not.toHaveProperty('canonicalEntityId');
    expect(resolution.evidence).toHaveLength(2);
  });
});
