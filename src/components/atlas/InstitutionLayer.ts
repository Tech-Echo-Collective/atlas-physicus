import type { FeatureCollection, Point } from 'geojson';
import type maplibregl from 'maplibre-gl';
import type { Institution, MetricObservation } from '../../domain/models';
import { researchActivityColor } from './visualScale';

export interface InstitutionFeatureProperties {
  institutionId: string;
  name: string;
  city: string;
  score: number;
}

export const institutionRadius: maplibregl.ExpressionSpecification = [
  'interpolate',
  ['linear'],
  ['get', 'score'],
  0,
  4,
  50,
  8,
  100,
  14,
];

export const institutionColor = researchActivityColor;

export function buildInstitutionFeatureCollection(
  institutions: Institution[],
  observations: MetricObservation[],
): FeatureCollection<Point, InstitutionFeatureProperties> {
  const observationsByInstitution = new Map(
    observations.map((observation) => [observation.entityId, observation]),
  );

  return {
    type: 'FeatureCollection',
    features: institutions.flatMap((institution) => {
      const observation = observationsByInstitution.get(institution.id);
      if (!institution.location || !observation) {
        return [];
      }

      return [
        {
          type: 'Feature' as const,
          id: institution.id,
          geometry: {
            type: 'Point' as const,
            coordinates: [
              institution.location.longitude,
              institution.location.latitude,
            ],
          },
          properties: {
            institutionId: institution.id,
            name: institution.name,
            city: institution.city,
            score: observation.value,
          },
        },
      ];
    }),
  };
}
