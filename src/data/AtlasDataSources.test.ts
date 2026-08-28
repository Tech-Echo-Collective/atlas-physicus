import demoData from './demo/atlas.json';
import { defaultMetricId, type AtlasDataset } from '../domain/models';
import { atlasDatasetSchema } from '../domain/schemas';
import type { AtlasNavigationState } from '../navigation/AtlasNavigation';
import {
  AtlasDataSourceRequestGate,
  assessDataSourceObservations,
  getInitialSourceFallback,
  mergeMetricObservationsById,
  neutralLiveMapNotice,
  reconcileNavigationForDataSource,
  resolveMetricForDataSource,
} from './AtlasDataSources';

const dataset = atlasDatasetSchema.parse(demoData);

function navigation(
  overrides: Partial<AtlasNavigationState> = {},
): AtlasNavigationState {
  return {
    selectedDomainId: 'physics',
    selectedFieldId: 'hep-th',
    selectedYear: 2026,
    selectedCountryId: null,
    selectedInstitutionId: null,
    selectedResearchGroupId: null,
    selectedResearcherId: null,
    isFieldOverviewOpen: false,
    ...overrides,
  };
}

describe('Atlas data-source state reconciliation', () => {
  it('preserves an in-range missing year without inventing an observation', () => {
    const reconciled = reconcileNavigationForDataSource(
      navigation({ selectedYear: 1975 }),
      dataset,
      defaultMetricId,
    );

    expect(reconciled.selectedYear).toBe(1975);
    expect(
      dataset.metricObservations.some(
        (observation) =>
          observation.metricId === defaultMetricId &&
          observation.entityType === 'country' &&
          observation.fieldId === 'hep-th' &&
          observation.period === '1975',
      ),
    ).toBe(false);
  });

  it('clamps an out-of-range year to the closest available observation', () => {
    expect(
      reconcileNavigationForDataSource(
        navigation({ selectedYear: 1800 }),
        dataset,
        defaultMetricId,
      ).selectedYear,
    ).toBe(1900);
  });

  it('rejects a retained field with no country values and uses a renderable fallback', () => {
    const destination: AtlasDataset = {
      ...dataset,
      metricObservations: dataset.metricObservations.filter(
        (observation) =>
          !(
            observation.metricId === defaultMetricId &&
            observation.entityType === 'country' &&
            (observation.fieldId === 'gr-qc' ||
              (observation.scienceDomainId === 'physics' &&
                observation.fieldId === undefined))
          ),
      ),
    };
    const reconciled = reconcileNavigationForDataSource(
      navigation({ selectedFieldId: 'gr-qc' }),
      destination,
      defaultMetricId,
    );

    expect(reconciled.selectedFieldId).toBe('hep-th');
    expect(
      destination.metricObservations.some(
        (observation) =>
          observation.metricId === defaultMetricId &&
          observation.entityType === 'country' &&
          observation.fieldId === reconciled.selectedFieldId,
      ),
    ).toBe(true);
  });

  it('preserves compatible entity context and clears it when the year has no values', () => {
    const previous = navigation({
      selectedCountryId: 'country-us',
      selectedInstitutionId: 'institution-mit',
      selectedResearchGroupId: 'group-mit-fields',
      selectedResearcherId: 'researcher-jonah-okafor',
    });

    expect(
      reconcileNavigationForDataSource(previous, dataset, defaultMetricId),
    ).toEqual(previous);
    expect(
      reconcileNavigationForDataSource(
        { ...previous, selectedYear: 1975 },
        dataset,
        defaultMetricId,
      ),
    ).toEqual(
      expect.objectContaining({
        selectedYear: 1975,
        selectedCountryId: null,
        selectedInstitutionId: null,
        selectedResearchGroupId: null,
        selectedResearcherId: null,
      }),
    );
  });

  it('preserves resolvable live entity context without inventing metric observations', () => {
    const destination: AtlasDataset = {
      ...dataset,
      metricObservations: [],
    };
    const reconciled = reconcileNavigationForDataSource(
      navigation({
        selectedYear: 2021,
        selectedCountryId: 'country-us',
        selectedInstitutionId: 'institution-mit',
        selectedResearchGroupId: 'group-mit-fields',
        selectedResearcherId: 'researcher-jonah-okafor',
      }),
      destination,
      defaultMetricId,
      { allowMissingMetricObservations: true },
    );

    expect(destination.metricObservations).toEqual([]);
    expect(reconciled).toEqual(
      expect.objectContaining({
        selectedFieldId: 'hep-th',
        selectedYear: 2021,
        selectedCountryId: 'country-us',
        selectedInstitutionId: 'institution-mit',
        selectedResearchGroupId: 'group-mit-fields',
        selectedResearcherId: 'researcher-jonah-okafor',
      }),
    );
  });
});

describe('data-source observation availability', () => {
  const destination: AtlasDataset = { ...dataset, metricObservations: [] };

  it('allows an honestly neutral live map when reviewed observations do not exist', () => {
    expect(
      assessDataSourceObservations(destination, defaultMetricId, 'live-api'),
    ).toEqual({
      canActivate: true,
      hasRenderableObservations: false,
      notice: neutralLiveMapNotice,
    });
  });

  it('keeps static and pilot visualization datasets strict', () => {
    expect(
      assessDataSourceObservations(
        destination,
        defaultMetricId,
        'synthetic-framework',
      ).canActivate,
    ).toBe(false);
    expect(
      assessDataSourceObservations(
        destination,
        defaultMetricId,
        'inspire-hep-pilot',
      ).canActivate,
    ).toBe(false);
  });

  it('withholds candidate observations even when an API row exists', () => {
    const candidateDataset: AtlasDataset = {
      ...dataset,
      metricDefinitions: dataset.metricDefinitions.map((definition) =>
        definition.id === defaultMetricId
          ? {
              ...definition,
              implementationStatus: 'experimental-candidate' as const,
            }
          : definition,
      ),
    };

    expect(
      assessDataSourceObservations(
        candidateDataset,
        defaultMetricId,
        'live-api',
      ),
    ).toEqual({
      canActivate: true,
      hasRenderableObservations: false,
      notice: neutralLiveMapNotice,
    });
    expect(resolveMetricForDataSource(candidateDataset, defaultMetricId)).not.toBe(
      defaultMetricId,
    );
  });
});

describe('scoped live metric merging', () => {
  it('preserves profile history and replaces only matching observation IDs', () => {
    const historical = dataset.metricObservations.find(
      (observation) =>
        observation.entityType === 'institution' &&
        observation.period !== '2026',
    );
    const current = dataset.metricObservations.find(
      (observation) =>
        observation.entityType === 'institution' &&
        observation.period === '2026',
    );
    expect(historical).toBeDefined();
    expect(current).toBeDefined();

    const replacement = { ...current!, value: 99 };
    const merged = mergeMetricObservationsById(
      [historical!, current!],
      [replacement],
    );

    expect(merged).toContainEqual(historical);
    expect(merged).toContainEqual(replacement);
    expect(merged).toHaveLength(2);
  });
});

describe('AtlasDataSourceRequestGate', () => {
  it('gives only the latest request ownership and supports invalidation', () => {
    const gate = new AtlasDataSourceRequestGate();
    const first = gate.begin();
    const second = gate.begin();

    expect(gate.isCurrent(first)).toBe(false);
    expect(gate.isCurrent(second)).toBe(true);

    gate.invalidate();

    expect(gate.isCurrent(second)).toBe(false);
  });
});

describe('initial source failure fallback', () => {
  it('falls back to synthetic only when no usable dataset exists', () => {
    expect(getInitialSourceFallback(false, 'live-api')).toBe(
      'synthetic-framework',
    );
    expect(getInitialSourceFallback(true, 'live-api')).toBeNull();
    expect(getInitialSourceFallback(false, 'synthetic-framework')).toBeNull();
  });
});
