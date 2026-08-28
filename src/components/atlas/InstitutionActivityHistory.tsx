import type { CSSProperties } from 'react';
import {
  getDatasetPresentation,
  type AtlasDatasetKind,
} from '../../data/DatasetPresentation';
import type { MetricObservation } from '../../domain/models';
import { getMetricValueCssColor } from './visualScale';

interface InstitutionActivityHistoryProps {
  observations: MetricObservation[];
  metricLabel: string;
  datasetKind: AtlasDatasetKind;
}

type ActivityBarStyle = CSSProperties & {
  '--activity-color': string;
  '--activity-value': string;
};

export function InstitutionActivityHistory({
  observations,
  metricLabel,
  datasetKind,
}: InstitutionActivityHistoryProps) {
  const presentation = getDatasetPresentation(datasetKind);
  const orderedObservations = [...observations].sort(
    (left, right) => Number(left.period) - Number(right.period),
  );

  return (
    <section className="entity-section activity-history">
      <div className="entity-section-heading">
        <div>
          <p className="section-kicker">Metric history</p>
          <h3>{metricLabel} over time</h3>
        </div>
        <span>{presentation.valuesLabel}</span>
      </div>

      {orderedObservations.length > 0 ? (
        <ol
          className="activity-bars"
          aria-label={`${presentation.dataLabel} ${metricLabel} history`}
        >
          {orderedObservations.map((observation) => (
            <li key={observation.id}>
              <div
                className="activity-bar"
                style={
                  {
                    '--activity-color': getMetricValueCssColor(
                      observation.value,
                    ),
                    '--activity-value': `${observation.value}%`,
                  } as ActivityBarStyle
                }
              >
                <span>{observation.value}</span>
                <i aria-hidden="true" />
              </div>
              <small>{observation.period}</small>
            </li>
          ))}
        </ol>
      ) : (
        <p className="muted-copy">
          No {presentation.recordLabel} metric history for this scope.
        </p>
      )}
    </section>
  );
}
