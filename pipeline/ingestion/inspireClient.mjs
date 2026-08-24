import { pilotYears } from '../config.mjs';

const retryableStatuses = new Set([429, 500, 502, 503, 504]);

export function buildLiteratureUrl(year, config) {
  const url = new URL(`${config.apiBaseUrl}/literature`);
  url.searchParams.set(
    'q',
    `primarch:${config.fieldId} and de:${year}`,
  );
  url.searchParams.set('sort', config.literatureSort);
  url.searchParams.set('size', String(config.recordsPerYear));
  url.searchParams.set('fields', config.literatureFields.join(','));
  return url.toString();
}

async function requestJson(url, fetchImplementation, attempts = 3) {
  let lastError;
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      const response = await fetchImplementation(url, {
        headers: {
          accept: 'application/json',
          'user-agent': 'Physics-Atlas-v3.0.3-alpha-pilot',
        },
      });
      if (response.ok) {
        return await response.json();
      }
      const error = new Error(`INSPIRE request failed (${response.status})`);
      if (!retryableStatuses.has(response.status) || attempt === attempts) {
        throw error;
      }
      lastError = error;
    } catch (error) {
      lastError = error;
      if (attempt === attempts) {
        throw error;
      }
    }
    await new Promise((resolve) => setTimeout(resolve, attempt * 5_500));
  }
  throw lastError;
}

function matchingRecordCount(total) {
  if (typeof total === 'number') {
    return total;
  }
  return Number(total?.value ?? 0);
}

function institutionReferences(yearQueries) {
  const references = new Set();
  yearQueries.forEach((query) => {
    query.records.forEach((record) => {
      (record.metadata?.authors ?? []).forEach((author) => {
        (author.affiliations ?? []).forEach((affiliation) => {
          const reference = affiliation.record?.$ref;
          if (typeof reference === 'string') {
            references.add(reference);
          }
        });
      });
    });
  });
  return [...references].sort();
}

async function fetchInBatches(
  urls,
  concurrency,
  batchPauseMs,
  fetchImplementation,
) {
  const records = [];
  const failures = [];
  for (let index = 0; index < urls.length; index += concurrency) {
    const batch = urls.slice(index, index + concurrency);
    const results = await Promise.all(
      batch.map(async (url) => {
        try {
          return {
            status: 'fulfilled',
            url,
            record: await requestJson(url, fetchImplementation),
          };
        } catch (error) {
          return {
            status: 'rejected',
            url,
            error:
              error instanceof Error
                ? error.message
                : 'Unknown institution request failure',
          };
        }
      }),
    );
    results.forEach((result) => {
      if (result.status === 'fulfilled') {
        records.push({ url: result.url, record: result.record });
      } else {
        failures.push({ url: result.url, error: result.error });
      }
    });
    if (index + concurrency < urls.length) {
      await new Promise((resolve) => setTimeout(resolve, batchPauseMs));
    }
  }
  return { records, failures };
}

export async function ingestInspirePilot(
  config,
  fetchImplementation = globalThis.fetch,
) {
  if (typeof fetchImplementation !== 'function') {
    throw new Error('A Fetch API implementation is required.');
  }

  const retrievedAt = new Date().toISOString();
  const yearQueries = [];
  for (const year of pilotYears(config)) {
    const url = buildLiteratureUrl(year, config);
    const response = await requestJson(url, fetchImplementation);
    yearQueries.push({
      year,
      url,
      totalMatchingRecords: matchingRecordCount(response.hits?.total),
      records: response.hits?.hits ?? [],
    });
    if (year < config.endYear) {
      await new Promise((resolve) =>
        setTimeout(resolve, config.literatureRequestPauseMs),
      );
    }
  }

  const allInstitutionReferences = institutionReferences(yearQueries);
  const selectedInstitutionReferences = allInstitutionReferences.slice(
    0,
    config.maxInstitutionRecords,
  );
  const institutionFetch = await fetchInBatches(
    selectedInstitutionReferences,
    config.requestConcurrency,
    config.requestBatchPauseMs,
    fetchImplementation,
  );

  return {
    metadata: {
      source: config.sourceName,
      sourceVersion: `inspire-hep-snapshot:${retrievedAt}`,
      sourceDocumentationVersion: config.sourceDocumentationVersion,
      apiDocumentation: config.apiDocumentation,
      sourceTerms: config.sourceTerms,
      sourceCitation: config.sourceCitation,
      retrievedAt,
      fieldId: config.fieldId,
      startYear: config.startYear,
      endYear: config.endYear,
      recordsPerYear: config.recordsPerYear,
      sampling: `Up to ${config.recordsPerYear} ${config.literatureSort} primary-category records per year`,
      rateLimitPolicy: `Literature requests are spaced by ${config.literatureRequestPauseMs} ms; institution requests use batches of ${config.requestConcurrency} with a ${config.requestBatchPauseMs} ms pause. HTTP 429 retries wait at least 5.5 s.`,
    },
    yearQueries,
    institutions: institutionFetch.records,
    failedInstitutionFetches: institutionFetch.failures,
    unresolvedInstitutionReferences: allInstitutionReferences.slice(
      config.maxInstitutionRecords,
    ),
  };
}
