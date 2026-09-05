import { readFileSync } from 'node:fs';

const readProjectFile = (path: string) =>
  readFileSync(new URL(`../${path}`, import.meta.url), 'utf8');

describe('Atlas Physicus public identity', () => {
  it('uses the product name in the Atlas heading and page metadata', () => {
    const explorer = readProjectFile('src/components/atlas/AtlasExplorer.tsx');
    const html = readProjectFile('index.html');

    expect(explorer).toContain('<h1>Atlas Physicus</h1>');
    expect(html).toContain('<title>Atlas Physicus — Knowledge Graph Alpha</title>');
    expect(html).toContain('property="og:title" content="Atlas Physicus"');
    expect(html).toContain('name="twitter:title" content="Atlas Physicus"');
    // The preserved legacy artwork has the old product name embedded in it.
    expect(html).not.toContain('og.png');
  });

  it('uses the canonical family, repository and package identities', () => {
    expect(readProjectFile('README.md')).toContain(
      'Part of Tech Echo Physica, a Tech Echo Collective project family for exploring physics through research mapping, knowledge structures, and interactive physical systems.',
    );
    expect(readProjectFile('NOTICE')).toContain(
      'Copyright (c) 2026 Tech Echo Collective',
    );
    const citation = readProjectFile('CITATION.cff');
    expect(citation).toContain('title: "Atlas Physicus"');
    expect(citation).toContain(
      'repository-code: "https://github.com/Tech-Echo-Collective/atlas-physicus"',
    );
    expect(JSON.parse(readProjectFile('package.json')).name).toBe('atlas-physicus');
  });
});
