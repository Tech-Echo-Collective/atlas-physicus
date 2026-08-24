import type { Institution, MetricObservation } from '../../domain/models';
import {
  buildInstitutionFeatureCollection,
  institutionColor,
} from './InstitutionLayer';
import {
  getResearchActivityCssColor,
  researchActivityColor,
} from './visualScale';

const institution: Institution = {
  id: 'institution-example',
  name: 'Example Institute',
  countryId: 'country-example',
  city: 'Example City',
  fieldIds: ['hep-th'],
  location: { longitude: 12.5, latitude: 42.25 },
};

const observation: MetricObservation = {
  id: 'observation-example',
  entityType: 'institution',
  entityId: institution.id,
  fieldId: 'hep-th',
  metricId: 'research_activity_score',
  period: '2026',
  value: 73,
  provenance: 'synthetic-demo',
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
  });
});
