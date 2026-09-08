import type { Institution } from '../domain/models';

/** Display metadata only. Existing entity IDs, paper links and metrics stay intact. */
export const ntuMetadataCorrection = {
  datasetVersion: 'arxiv-attributed-20260908-v1',
  institutionId: 'institution-inspire-911953',
  name: 'Nanyang Technological University',
  aliases: ['NTU', '南洋理工大学', 'Nanyang Technol. U.'],
  ror: 'https://ror.org/02e7b5302',
  // Campus reference point from NTU's official Photonics Institute visitor map.
  // ROR's Singapore city-centre coordinates are not a campus location.
  location: { longitude: 103.680128, latitude: 1.343164 },
  evidence: [
    { url: 'https://inspirehep.net/api/institutions/911953' },
    {
      url: 'https://api.ror.org/v2/organizations/02e7b5302',
      retrievedAt: '2026-09-08T13:06:02Z',
      sha256: '800b1be558eec7eff5ae2fa1660226c92ea0b570b6a8a4091f8b85ef20c5a0b9',
    },
    {
      url: 'https://personal.ntu.edu.sg/hcdang/visitus.html',
      retrievedAt: '2026-09-08T13:06:02Z',
      sha256: '8e3314b34eb1dda3287867efecc46b9cbb5840d9a7e4c2215d2665be29a04a5b',
    },
  ],
};

export function applyInstitutionMetadataCorrections(
  institutions: Institution[],
  datasetVersion: string,
): Institution[] {
  const correction = ntuMetadataCorrection;
  if (datasetVersion !== correction.datasetVersion) return institutions;
  return institutions.map((institution) => {
    if (
      institution.id !== correction.institutionId ||
      institution.countryId !== 'country-sg' ||
      !institution.externalIds?.some((id) => id.scheme === 'INSPIRE' && id.value === '911953')
    ) return institution;
    return {
      ...institution,
      name: correction.name,
      canonicalName: correction.name,
      aliases: [...new Set([...institution.aliases ?? [], institution.name, ...correction.aliases])]
        .filter((alias) => alias !== correction.name),
      externalIds: [
        ...institution.externalIds.filter((id) => id.scheme !== 'ROR'),
        { scheme: 'ROR', value: correction.ror },
      ],
      location: { ...correction.location },
    };
  });
}
