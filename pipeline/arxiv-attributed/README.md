# Attributed arXiv release

Owner-directed PA-065: acquire provider records, confirm paper-time institution links, and publish observed normalized metrics in the original explorer under the official 51-category arXiv physics taxonomy. This is separate from the strict certified-release experiment.

Run with the backend virtual environment (including pycountry), from the source repository:

```
PYTHONPATH=backend/src backend/.venv/bin/python pipeline/arxiv-attributed/acquire.py --work-dir /path/to/evidence
PYTHONPATH=backend/src backend/.venv/bin/python pipeline/arxiv-attributed/build.py --work-dir /path/to/evidence --output-dir /path/to/web/public/data/arxiv-20260908
```

The retained SQLite source snapshot stores compact source records, source IDs, retrieval timestamps, checksums, and institution authority responses. Exact capture URLs/counts and category/year attribution counts are published in `coverage.json`. Acquisition resumes existing successful partitions. The dated output/version must be changed for another publication; never overwrite an already released immutable directory.

The September 8 capture covers 2018–2026, up to 250 most-recent INSPIRE records per native category/year. Cross-lists are preserved and INSPIRE/arXiv identities deduplicated. INSPIRE does not index all of arXiv uniformly. This is neither an exhaustive census nor a representative probability sample. Empty/unretrieved data is not zero.

Attribution follows the source paper's institution ID to its authority record, requiring an unambiguous country; alternatively a unique exact full authority-name segment in the paper affiliation resolves it. Institutions sharing an exact ROR are unified. No fuzzy matching. All source authors remain in the denominator, including unresolved authors; an author's share divides equally over their verified institutions and separately over their verified countries. Unallocated mass stays missing. Researcher identities without an INSPIRE author ID are local to a paper. Affiliations describe the paper year, not current employment.

Five dimensions are computed on the retrieved attributed corpus: trailing three-year fractional Activity (within-category/year/type robust log 5–95% display transform); mature-paper Impact (mean non-self citations relative to the same category/publication-year cohort, then robust display normalization); confirmed Collaboration share; normalized Shannon entropy over 51 native categories; Momentum (adjacent three-year log change, robust cohort centering/scaling, 2023–2025 only). Cohorts require two distinct-supported values rather than the old 30-entity certification gate. A degenerate distribution stays missing. Impact uses citations captured September 8, 2026 even for older selected years; it is retrospective, not a historical citation snapshot. Momentum is sensitive to unequal source capture completeness. Physics overview is an equal mean of available normalized category scores.

Initial data contains canonical catalogs; metrics load by year and paper-time relationship records load on demand. The exact compact relationship index has a 32 MiB decoded limit (19.55 MiB measured), while each relationship shard remains bounded at 4 MiB. Checksums and size receipts are validated by the public loader. No provider credentials enter the browser.
