import { renderToStaticMarkup } from 'react-dom/server';
import { CountryPanel } from './CountryPanel';
import type { Country, Institution } from '../../domain/models';

const provenance = { source: 'Test', sourceType: 'synthetic-demo' as const, version: 'test', status: 'synthetic' as const };
const country: Country = { id: 'country-sg', name: 'Singapore', isoAlpha3: 'SGP', isoNumeric: '702', region: 'World', provenance };
const institution: Institution = { id: 'institution-ntu', name: 'Nanyang Technological University', countryId: country.id, city: 'Singapore', fieldIds: [], provenance };

function render(institutions: Institution[]) {
  return renderToStaticMarkup(<CountryPanel country={country} institutions={institutions} countryObservation={null} institutionObservations={[]} metricLabel="Activity" activeScopeLabel="Physics" selectedYear={2025} datasetKind="synthetic-demo" onBackToWorld={() => {}} onInstitutionSelect={() => {}} />);
}

it('keeps institutions accessible without coordinates or a selected metric observation', () => {
  const html = render([institution]);
  expect(html).toContain('Nanyang Technological University');
  expect(html).toContain('Map location unavailable');
  expect(html).toContain('1 institutions');
});

it('bounds large-country rendering to 25 institutions with access to subsequent pages', () => {
  const html = render(Array.from({ length: 80 }, (_, index) => ({ ...institution, id: `institution-${index}`, name: `Institute ${String(index).padStart(3, '0')}` })));
  expect(html.match(/class="institution-item"/g)).toHaveLength(25);
  expect(html).toContain('80 institutions');
  expect(html).toContain('Next');
});
