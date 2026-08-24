import type { Institution, MetricObservation } from '../../domain/models';
import {
  buildInstitutionFeatureCollection,
  getInstitutionPulseFrame,
  institutionColor,
  institutionHeatmapColor,
  institutionHeatmapWeight,
  institutionNodeDisplayConfig,
  institutionPulseDurationMs,
  selectMajorInstitutionsForMap,
} from './InstitutionLayer';
import {
  getResearchActivityCssColor,
  researchActivityColor,
} from './visualScale';

const provenance = {
  source: 'Physics Atlas synthetic demonstration dataset',
  sourceType: 'synthetic-demo' as const,
  version: 'v2.3-alpha',
  status: 'synthetic' as const,
};

const institution: Institution = {
  id: 'institution-example',
  name: 'Example Institute',
  countryId: 'country-example',
  city: 'Example City',
  fieldIds: ['hep-th'],
  location: { longitude: 12.5, latitude: 42.25 },
  provenance,
};

const observation: MetricObservation = {
  id: 'observation-example',
  entityType: 'institution',
  entityId: institution.id,
  fieldId: 'hep-th',
  metricId: 'research_activity_score',
  period: '2026',
  value: 73,
  provenance,
};

describe('buildInstitutionFeatureCollection', () => {
  it('joins provided locations and observations into map points', () => {
    const collection = buildInstitutionFeatureCollection(
      [institution],
      [observation],
    );

    expect(collection.features).toEqual([
      expect.objectContaining({
        geometry: {
          type: 'Point',
          coordinates: [12.5, 42.25],
        },
        properties: expect.objectContaining({
          institutionId: institution.id,
          score: 73,
        }),
      }),
    ]);
  });

  it('does not render missing observations as zero activity', () => {
    const collection = buildInstitutionFeatureCollection([institution], []);

    expect(collection.features).toEqual([]);
  });

  it('shares the standardized full-spectrum activity scale', () => {
    expect(institutionColor).toBe(researchActivityColor);
    expect(researchActivityColor).toContain('#8b3ffc');
    expect(researchActivityColor).toContain('#3157e8');
    expect(researchActivityColor).toContain('#00b7d6');
    expect(researchActivityColor).toContain('#2db96f');
    expect(researchActivityColor).toContain('#d8c83f');
    expect(researchActivityColor).toContain('#f07a2b');
    expect(researchActivityColor).toContain('#df2f3f');
    expect(getResearchActivityCssColor(0)).toContain('hsl(270');
    expect(getResearchActivityCssColor(100)).toContain('hsl(0');
    expect(JSON.stringify(institutionHeatmapWeight)).toContain('"score"');
    expect(institutionHeatmapColor).toContain('rgba(139, 63, 252, 0.48)');
    expect(institutionHeatmapColor).toContain('rgba(223, 47, 63, 0.76)');
  });

  it('filters institution density with a configurable threshold and node limit', () => {
    const secondInstitution: Institution = {
      ...institution,
      id: 'institution-second',
      name: 'Second Institute',
      location: { longitude: 13, latitude: 43 },
    };
    const thirdInstitution: Institution = {
      ...institution,
      id: 'institution-third',
      name: 'Third Institute',
      location: { longitude: 14, latitude: 44 },
    };
    const observations: MetricObservation[] = [
      observation,
      {
        ...observation,
        id: 'observation-second',
        entityId: secondInstitution.id,
        value: 91,
      },
      {
        ...observation,
        id: 'observation-third',
        entityId: thirdInstitution.id,
        value: 12,
      },
    ];

    expect(
      selectMajorInstitutionsForMap(
        [institution, secondInstitution, thirdInstitution],
        observations,
        { maxNodes: 2, minimumActivity: 20 },
      ).map((candidate) => candidate.id),
    ).toEqual([secondInstitution.id, institution.id]);
    expect(institutionNodeDisplayConfig.maxNodes).toBeGreaterThan(0);
  });

  it('keeps the pulse timing independent from scientific metrics', () => {
    const startFrame = getInstitutionPulseFrame(0);
    const halfFrame = getInstitutionPulseFrame(
      institutionPulseDurationMs / 2,
    );

    expect(institutionPulseDurationMs).toBeGreaterThanOrEqual(2_000);
    expect(institutionPulseDurationMs).toBeLessThanOrEqual(3_000);
    expect(halfFrame.innerRadiusOffset).toBeGreaterThan(
      startFrame.innerRadiusOffset,
    );
    expect(halfFrame.outerRadiusOffset).toBeGreaterThan(
      startFrame.outerRadiusOffset,
    );
    expect(halfFrame.opacity).toBeLessThan(startFrame.opacity);
  });
});
