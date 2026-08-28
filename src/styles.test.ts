import { readFileSync } from 'node:fs';

const styles = readFileSync(new URL('./styles.css', import.meta.url), 'utf8');

describe('Atlas viewport layout safeguards', () => {
  it('keeps the desktop control panel bounded and delegates scrolling to the field list', () => {
    expect(styles).toMatch(
      /\.field-panel\s*\{[^}]*max-height:\s*calc\(100svh - 250px\);[^}]*overflow:\s*hidden;/s,
    );
    expect(styles).toMatch(
      /\.field-selector\s*\{[^}]*min-height:\s*0;[^}]*flex:\s*1 1 230px;[^}]*flex-direction:\s*column;/s,
    );
    expect(styles).toMatch(
      /\.field-list\s*\{[^}]*min-height:\s*0;[^}]*overflow-y:\s*auto;[^}]*overscroll-behavior:\s*contain;[^}]*scrollbar-width:\s*thin;/s,
    );
  });

  it('caps independently scrolling lists on narrow viewports', () => {
    expect(styles).toMatch(
      /@media \(max-width:\s*900px\)[\s\S]*?\.field-list,\s*\.institution-list\s*\{[^}]*max-height:\s*clamp\(180px, 38svh, 320px\);/,
    );
  });

  it('reserves tablet width between side panels for the timeline', () => {
    expect(styles).toMatch(
      /@media \(max-width:\s*1180px\) and \(min-width:\s*901px\)[\s\S]*?\.timeline\s*\{[^}]*width:\s*calc\(100vw - 620px\);[^}]*min-width:\s*0;/,
    );
  });
});
