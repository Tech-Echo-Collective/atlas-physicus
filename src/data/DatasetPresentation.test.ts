import { getDatasetPresentation } from './DatasetPresentation';

describe('dataset presentation', () => {
  it('never labels API-backed data as synthetic or pilot data', () => {
    const presentation = getDatasetPresentation('live-api');

    expect(presentation.badgeLabel).toContain('Live API');
    expect(presentation.dataLabel.toLocaleLowerCase()).not.toContain('synthetic');
    expect(presentation.dataLabel.toLocaleLowerCase()).not.toContain('pilot');
    expect(presentation.disclaimer).toContain('source-dependent coverage');
  });
});
