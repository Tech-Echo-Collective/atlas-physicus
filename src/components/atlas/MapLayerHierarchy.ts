export type MapLayerVisibility = 'visible' | 'none';

export interface AtlasMapLayerHierarchy {
  countryHeatmap: MapLayerVisibility;
  countryCanvas: MapLayerVisibility;
  institutionHeatmap: MapLayerVisibility;
  institutionSelection: MapLayerVisibility;
}

/**
 * Keeps geographic information density aligned with the exploration level.
 * This is presentation state only; it does not change metrics or entities.
 */
export function getAtlasMapLayerHierarchy(
  selectedCountryId: string | null,
  selectedInstitutionId: string | null,
): AtlasMapLayerHierarchy {
  const isCountryLevel = Boolean(selectedCountryId);

  return {
    countryHeatmap: isCountryLevel ? 'none' : 'visible',
    countryCanvas: isCountryLevel ? 'visible' : 'none',
    institutionHeatmap: isCountryLevel ? 'visible' : 'none',
    institutionSelection:
      isCountryLevel && selectedInstitutionId ? 'visible' : 'none',
  };
}
