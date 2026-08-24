import { useEffect, useRef, useState } from 'react';
import type { AtlasSearchResult } from '../../domain/models';

interface AtlasSearchProps {
  onSearch: (query: string) => Promise<AtlasSearchResult[]>;
  onSelect: (result: AtlasSearchResult) => void;
}

export function AtlasSearch({ onSearch, onSelect }: AtlasSearchProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<AtlasSearchResult[]>([]);
  const [searchedQuery, setSearchedQuery] = useState('');
  const isSearching = Boolean(query.trim()) && searchedQuery !== query;

  useEffect(() => {
    if (!isOpen || !query.trim()) {
      return;
    }

    let isCurrent = true;
    const activeQuery = query;
    const timer = window.setTimeout(() => {
      void onSearch(activeQuery).then((nextResults) => {
        if (isCurrent) {
          setResults(nextResults);
          setSearchedQuery(activeQuery);
        }
      });
    }, 120);

    return () => {
      isCurrent = false;
      window.clearTimeout(timer);
    };
  }, [isOpen, onSearch, query]);

  const openSearch = () => {
    setIsOpen(true);
    window.setTimeout(() => inputRef.current?.focus(), 0);
  };

  const chooseResult = (result: AtlasSearchResult) => {
    onSelect(result);
    setQuery('');
    setResults([]);
    setSearchedQuery('');
    setIsOpen(false);
  };

  return (
    <div className="atlas-search" data-open={isOpen}>
      {!isOpen ? (
        <button
          className="atlas-utility-button"
          type="button"
          onClick={openSearch}
          aria-label="Search the atlas"
          title="Search the atlas"
        >
          <span aria-hidden="true">⌕</span>
        </button>
      ) : (
        <div className="atlas-search-popover">
          <div className="atlas-search-input">
            <span aria-hidden="true">⌕</span>
            <input
              ref={inputRef}
              type="search"
              value={query}
              onChange={(event) => {
                setQuery(event.target.value);
                if (!event.target.value.trim()) {
                  setResults([]);
                  setSearchedQuery('');
                }
              }}
              onKeyDown={(event) => {
                if (event.key === 'Escape') {
                  setIsOpen(false);
                  setResults([]);
                  setSearchedQuery('');
                }
                if (event.key === 'Enter' && results[0]) {
                  event.preventDefault();
                  chooseResult(results[0]);
                }
              }}
              placeholder="Find a field, country, institution…"
              aria-label="Search science domains, fields, countries, institutions, and researchers"
              aria-controls="atlas-search-results"
            />
            <button
              type="button"
              onClick={() => {
                setIsOpen(false);
                setResults([]);
                setSearchedQuery('');
              }}
              aria-label="Close atlas search"
            >
              ×
            </button>
          </div>
          <div id="atlas-search-results" className="atlas-search-results">
            {query.trim() && isSearching ? (
              <p>Resolving canonical entities…</p>
            ) : query.trim() && results.length === 0 ? (
              <p>No sufficiently confident canonical match</p>
            ) : (
              results.map((result) => (
                <button
                  key={`${result.entityType}-${result.entityId}`}
                  type="button"
                  onClick={() => chooseResult(result)}
                >
                  <strong>{result.label}</strong>
                  <span>{result.context}</span>
                  <small>
                    {Math.round(result.matchConfidence * 100)}% search match ·{' '}
                    {result.matchedOn.replaceAll('-', ' ')}
                    {result.identityConfidence !== undefined && (
                      <> · {Math.round(result.identityConfidence * 100)}% identity</>
                    )}
                  </small>
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
