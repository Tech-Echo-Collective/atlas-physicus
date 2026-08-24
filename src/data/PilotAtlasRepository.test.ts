import {
  atlasDataSourceOptions,
  buildDataSourceAwareAtlasUrl,
  resolveAtlasDataSource,
} from './AtlasDataSources';
import {
  defaultMetricWeightConfiguration,
  hasCompositeMetricInputs,
} from '../metrics/CompositeMetric';
import { pilotAtlasRepository } from './PilotAtlasRepository';
import { atlasRepository } from './StaticAtlasRepository';

describe('INSPIRE-HEP pilot frontend integration', () => {
  it('offers distinct synthetic and pilot sources with shareable pilot URLs', () => {
    expect(atlasDataSourceOptions.map((source) => source.id)).toEqual([
      'synthetic-framework',
      'inspire-hep-pilot',
    ]);
    const pilotUrl = buildDataSourceAwareAtlasUrl(
      '/atlas/physics/hep-th?year=2026',
      'inspire-hep-pilot',
    );
    expect(pilotUrl).toBe(
      '/atlas/physics/hep-th?year=2026&source=inspire-hep-pilot',
    );
    expect(resolveAtlasDataSource(pilotUrl.split('?')[1] ?? '')).toBe(
      'inspire-hep-pilot',
    );
    expect(
      buildDataSourceAwareAtlasUrl(pilotUrl, 'synthetic-framework'),
    ).toBe('/atlas/physics/hep-th?year=2026');
  });

  it('retains stored pilot provenance without synthetic recalculation', async () => {
    const metadata = await pilotAtlasRepository.getMetadata();
    const observations = await pilotAtlasRepository.getMetricObservations();
    const representative = observations.find(
      (observation) =>
        observation.entityType === 'country' &&
        observation.metricId === 'research_activity_score' &&
        observation.period === '2026',
    );

    expect(metadata.datasetKind).toBe('inspire-hep-pilot');
    expect(observations.length).toBeGreaterThan(0);
    expect(representative).toMatchObject({
      source: 'INSPIRE-HEP REST API',
      calculationVersion: 'v3.0.3-alpha-pilot.1',
      calculatedAt: metadata.generatedAt,
      provenance: {
        source: 'Derived from the INSPIRE-HEP pilot snapshot',
        sourceType: 'derived',
        version: metadata.provenance.version,
        status: 'unverified',
      },
    });
    expect(representative?.algorithmVersion).toMatch(/^pilot-activity-/);
    expect(
      observations.some((observation) =>
        observation.algorithmVersion.includes('synthetic'),
      ),
    ).toBe(false);
  });

  it('keeps composite profiles available for demo data but not the pilot', async () => {
    const [demoDefinitions, pilotDefinitions] = await Promise.all([
      atlasRepository.getMetricDefinitions(),
      pilotAtlasRepository.getMetricDefinitions(),
    ]);

    expect(
      hasCompositeMetricInputs(
        demoDefinitions,
        defaultMetricWeightConfiguration,
      ),
    ).toBe(true);
    expect(
      hasCompositeMetricInputs(
        pilotDefinitions,
        defaultMetricWeightConfiguration,
      ),
    ).toBe(false);
    expect(
      pilotDefinitions.find(
        (definition) => definition.id === 'research_diversity',
      )?.implementationStatus,
    ).toBe('taxonomy-only');
  });
});
