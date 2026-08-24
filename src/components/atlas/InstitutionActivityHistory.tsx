import type { CSSProperties } from 'react';
import type { MetricObservation } from '../../domain/models';
import { getResearchActivityCssColor } from './visualScale';

interface InstitutionActivityHistoryProps {
  observations: MetricObservation[];
}

type ActivityBarStyle = CSSProperties & {
  '--activity-color': string;
  '--activity-value': string;
};

export function InstitutionActivityHistory({
  observations,
}: InstitutionActivityHistoryProps) {
  const orderedObservations = [...observations].sort(
    (left, right) => Number(left.period) - Number(right.period),
  );

  return (
    <section className="entity-section activity-history">
      <div className="entity-section-heading">
        <div>
          <p className="section-kicker">Historical activity</p>
          <h3>Research activity over time</h3>
        </div>
        <span>Synthetic values</span>
      </div>

      {orderedObservations.length > 0 ? (
        <ol className="activity-bars" aria-label="Synthetic activity history">
          {orderedObservations.map((observation) => (
            <li key={observation.id}>
              <div
                className="activity-bar"
                style={
                  {
                    '--activity-color': getResearchActivityCssColor(
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
        <p className="muted-copy">No demo activity history for this scope.</p>
      )}
    </section>
  );
}
