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

export interface InstitutionNodeDisplayConfig {
  maxNodes: number;
  minimumActivity: number;
}

/**
 * Presentation-only density control for Country View. It can be tuned as the
 * atlas grows without changing metric values or geographic attribution.
 */
export const institutionNodeDisplayConfig: InstitutionNodeDisplayConfig = {
  maxNodes: 12,
  minimumActivity: 1,
};

export const institutionPulseDurationMs = 2_600;

export interface InstitutionPulseFrame {
  innerRadiusOffset: number;
  outerRadiusOffset: number;
  opacity: number;
}

/**
 * Produces the same pulse frame for every institution. The pulse is a visual
 * emphasis effect and deliberately has no score or metric input.
 */
export function getInstitutionPulseFrame(
  elapsedMs: number,
): InstitutionPulseFrame {
  const progress =
    (((elapsedMs % institutionPulseDurationMs) + institutionPulseDurationMs) %
      institutionPulseDurationMs) /
    institutionPulseDurationMs;

  return {
    innerRadiusOffset: 5 + progress * 10,
    outerRadiusOffset: 9 + progress * 18,
    opacity: (1 - progress) * 0.3,
  };
}

export function selectMajorInstitutionsForMap(
  institutions: Institution[],
  observations: MetricObservation[],
  config: InstitutionNodeDisplayConfig = institutionNodeDisplayConfig,
): Institution[] {
  const observationsByInstitution = new Map(
    observations.map((observation) => [observation.entityId, observation]),
  );
  const maxNodes = Math.max(0, Math.floor(config.maxNodes));

  return institutions
    .filter((institution) => {
      const observation = observationsByInstitution.get(institution.id);
      return Boolean(
        institution.location &&
          observation &&
          observation.value >= config.minimumActivity,
      );
    })
    .sort((left, right) => {
      const scoreDifference =
        (observationsByInstitution.get(right.id)?.value ?? 0) -
        (observationsByInstitution.get(left.id)?.value ?? 0);
      return scoreDifference || left.name.localeCompare(right.name);
    })
    .slice(0, maxNodes);
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

export const institutionHeatmapWeight: maplibregl.ExpressionSpecification = [
  'interpolate',
  ['linear'],
  ['get', 'score'],
  0,
  0.15,
  100,
  1,
];

/**
 * Diffuse context for institution nodes. Scientific values remain encoded by
 * the node color and size; this layer only makes research centers legible
 * against a large country canvas.
 */
export const institutionHeatmapColor: maplibregl.ExpressionSpecification = [
  'interpolate',
  ['linear'],
  ['heatmap-density'],
  0,
  'rgba(139, 63, 252, 0)',
  0.15,
  'rgba(139, 63, 252, 0.48)',
  0.32,
  'rgba(49, 87, 232, 0.52)',
  0.48,
  'rgba(0, 183, 214, 0.56)',
  0.62,
  'rgba(45, 185, 111, 0.6)',
  0.75,
  'rgba(216, 200, 63, 0.64)',
  0.87,
  'rgba(240, 122, 43, 0.7)',
  1,
  'rgba(223, 47, 63, 0.76)',
];

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
