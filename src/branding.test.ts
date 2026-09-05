import { readFileSync } from 'node:fs';

const readProjectFile = (path: string) =>
  readFileSync(new URL(`../${path}`, import.meta.url), 'utf8');

describe('Atlas Physica public identity', () => {
  it('uses the product name in the Atlas heading and page metadata', () => {
    const explorer = readProjectFile('src/components/atlas/AtlasExplorer.tsx');
    const html = readProjectFile('index.html');

    expect(explorer).toContain('<h1>Atlas Physica</h1>');
    expect(html).toContain('<title>Atlas Physica — Knowledge Graph Alpha</title>');
    expect(html).toContain('property="og:title" content="Atlas Physica"');
    expect(html).toContain('name="twitter:title" content="Atlas Physica"');
    // The preserved legacy artwork has the old product name embedded in it.
    expect(html).not.toContain('og.png');
  });

  it('preserves attribution and stable technical identifiers', () => {
    expect(readProjectFile('README.md')).toContain(
      'Atlas Physica is developed and maintained by Tech Echo Collective.',
    );
    expect(readProjectFile('NOTICE')).toContain(
      'Copyright (c) 2026 Tech Echo Collective',
    );
    const citation = readProjectFile('CITATION.cff');
    expect(citation).toContain('title: "Atlas Physica"');
    expect(citation).toContain(
      'repository-code: "https://github.com/Tech-Echo-Collective/Physics-Atlas"',
    );
    expect(JSON.parse(readProjectFile('package.json')).name).toBe('physics-atlas');
  });
});
