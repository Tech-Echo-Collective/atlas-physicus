import demoData from '../data/demo/atlas.json';
import { atlasDatasetSchema } from '../domain/schemas';
import { ProfileService } from './ProfileService';

const dataset = atlasDatasetSchema.parse(demoData);

describe('ProfileService', () => {
  it('assembles institution profiles from graph relationships', () => {
    const profile = new ProfileService(dataset).getInstitutionProfile(
      'institution-mit',
    );

    expect(profile?.institution.id).toBe('institution-mit');
    expect(profile?.researchGroups.map((group) => group.id)).toEqual(
      expect.arrayContaining(['group-mit-fields', 'group-mit-quantum']),
    );
    expect(profile?.researchers.map((researcher) => researcher.id)).toEqual(
      expect.arrayContaining(['researcher-jonah-okafor', 'researcher-nila-patel']),
    );
    expect(profile?.papers.length).toBeGreaterThan(0);
  });

  it('keeps affiliation history separate from canonical researchers', () => {
    const profile = new ProfileService(dataset).getResearcherProfile(
      'researcher-jonah-okafor',
    );

    expect(profile?.affiliationHistory).toEqual([
      expect.objectContaining({
        institution: expect.objectContaining({ id: 'institution-mit' }),
        affiliation: expect.objectContaining({
          researcherId: 'researcher-jonah-okafor',
        }),
      }),
    ]);
    expect(profile?.collaborators.map((researcher) => researcher.id)).toEqual(
      expect.arrayContaining([
        'researcher-ethan-zhou',
        'researcher-maya-chen',
      ]),
    );
  });

  it('builds research-group members and papers without a new entity store', () => {
    const profile = new ProfileService(dataset).getResearchGroupProfile(
      'group-mit-fields',
    );

    expect(profile).toEqual(
      expect.objectContaining({
        institution: expect.objectContaining({ id: 'institution-mit' }),
        researchGroup: expect.objectContaining({ id: 'group-mit-fields' }),
      }),
    );
    expect(profile?.members.map((researcher) => researcher.id)).toContain(
      'researcher-jonah-okafor',
    );
    expect(profile?.papers.map((paper) => paper.id)).toContain(
      'paper-boundary-symmetries',
    );
  });

  it('returns null for an unknown canonical entity', () => {
    const profiles = new ProfileService(dataset);
    expect(profiles.getInstitutionProfile('missing')).toBeNull();
    expect(profiles.getResearcherProfile('missing')).toBeNull();
    expect(profiles.getResearchGroupProfile('missing')).toBeNull();
  });
});
