import { renderToStaticMarkup } from 'react-dom/server';
import { neutralLiveMapNotice } from '../../data/AtlasDataSources';
import { DataSourceSelector } from './DataSourceSelector';

function renderLiveSelector(options: {
  error?: string;
  isLoading?: boolean;
  notice?: string;
} = {}) {
  return renderToStaticMarkup(
    <DataSourceSelector
      selectedSourceId="live-api"
      liveApiAvailable
      onSelect={() => undefined}
      {...options}
    />,
  );
}

describe('data source selector', () => {
  it('keeps the neutral live-map disclaimer once without a duplicate live note', () => {
    const markup = renderLiveSelector({ notice: neutralLiveMapNotice });

    expect(markup.match(/missing data is not zero/g)).toHaveLength(1);
    expect(markup).toContain('Live scientific metadata is available');
    expect(markup).not.toContain('API-backed Atlas metadata');
    expect(markup).toContain('role="status"');
  });

  it('shows the compact live provenance note when no status overrides it', () => {
    const markup = renderLiveSelector();

    expect(markup).toContain('API-backed Atlas metadata');
    expect(markup).toContain('role="note"');
  });

  it('does not compete with loading or error feedback', () => {
    const loadingMarkup = renderLiveSelector({
      isLoading: true,
    });
    const errorMarkup = renderLiveSelector({
      error: 'The production source is temporarily unavailable.',
    });

    expect(loadingMarkup).toContain('The current map remains active');
    expect(loadingMarkup).not.toContain('API-backed Atlas metadata');
    expect(errorMarkup).toContain('role="alert"');
    expect(errorMarkup).not.toContain('API-backed Atlas metadata');
  });
});
