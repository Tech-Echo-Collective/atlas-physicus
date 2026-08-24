import demoData from '../data/demo/atlas.json';
import { atlasDatasetSchema } from '../domain/schemas';
import { EntitySearchIndex } from './EntitySearchIndex';

function buildIndex() {
  const enrichedDemo = {
    ...demoData,
    institutions: demoData.institutions.map((institution) =>
      institution.id === 'institution-caltech'
        ? {
            ...institution,
            canonicalName: 'California Institute of Technology',
            aliases: ['Caltech', 'CIT'],
            historicalNames: ['Throop University'],
            identityConfidence: 1,
            externalIds: [{ scheme: 'demo-registry', value: 'DEMO-CALTECH' }],
          }
        : institution,
    ),
    researchers: demoData.researchers.map((researcher) =>
      researcher.id === 'researcher-jonah-okafor'
        ? {
            ...researcher,
            canonicalName: 'Jonah Okafor',
            aliases: ['J. Okafor'],
            identityConfidence: 0.96,
          }
        : researcher,
    ),
  };
  return new EntitySearchIndex(atlasDatasetSchema.parse(enrichedDemo));
}

describe('EntitySearchIndex', () => {
  it('resolves institution abbreviations and explicit aliases', () => {
    const index = buildIndex();

    expect(index.search('MIT')[0]).toEqual(
      expect.objectContaining({
        entityId: 'institution-mit',
        entityType: 'institution',
        matchedOn: 'alias',
      }),
    );
    expect(index.search('Caltech')[0]).toEqual(
      expect.objectContaining({
        entityId: 'institution-caltech',
        matchedOn: 'alias',
        matchConfidence: 0.98,
      }),
    );
    expect(index.search('CRI')[0]).toEqual(
      expect.objectContaining({
        entityId: 'institution-calder',
        matchedOn: 'abbreviation',
      }),
    );
  });

  it('uses identifiers and historical names without returning raw records', () => {
    const index = buildIndex();

    expect(index.search('DEMO-CALTECH')[0]).toEqual(
      expect.objectContaining({
        entityId: 'institution-caltech',
        matchedOn: 'external-identifier',
        matchConfidence: 1,
      }),
    );
    expect(index.search('Throop University')[0]).toEqual(
      expect.objectContaining({
        entityId: 'institution-caltech',
        matchedOn: 'historical-name',
      }),
    );
  });

  it('supports researcher initials and bounded spelling variation', () => {
    const index = buildIndex();

    expect(index.search('J. Okafor')[0]).toEqual(
      expect.objectContaining({
        entityId: 'researcher-jonah-okafor',
        entityType: 'researcher',
        identityConfidence: 0.96,
      }),
    );
    expect(index.search('Californa Institute of Technlogy')[0]).toEqual(
      expect.objectContaining({
        entityId: 'institution-caltech',
        matchedOn: 'fuzzy-name',
      }),
    );
  });

  it('does not return weak short-query guesses', () => {
    const index = buildIndex();
    expect(index.search('zx')).toEqual([]);
  });
});
