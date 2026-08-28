import { useMemo, useState } from 'react';
import {
  getDatasetPresentation,
  type AtlasDatasetKind,
} from '../../data/DatasetPresentation';
import {
  compositeMetricId,
  type MetricDefinition,
  type MetricId,
  type MetricWeightConfiguration,
} from '../../domain/models';
import { metricProfiles } from '../../metrics/MetricProfiles';

interface MetricWeightingPanelProps {
  definitions: MetricDefinition[];
  selectedMetricId: MetricId;
  configuration: MetricWeightConfiguration;
  hasConfirmedProfile: boolean;
  compositeAvailable: boolean;
  datasetKind: AtlasDatasetKind;
  defaultOpen?: boolean;
  onMetricSelect: (metricId: MetricId) => void;
  onApply: (configuration: MetricWeightConfiguration) => void;
}

function getUnavailableMetricLayerMessage(dataLabel: string): string {
  return `No scientifically validated metric layer is available for this ${dataLabel}. The map remains neutral; missing data is not zero, and values from another dataset are never substituted.`;
}

function draftFromConfiguration(
  configuration: MetricWeightConfiguration,
): Record<MetricId, string> {
  return Object.fromEntries(
    Object.entries(configuration.weights).map(([metricId, weight]) => [
      metricId,
      String(weight),
    ]),
  );
}

export function MetricWeightingPanel({
  definitions,
  selectedMetricId,
  configuration,
  hasConfirmedProfile,
  compositeAvailable,
  datasetKind,
  defaultOpen = false,
  onMetricSelect,
  onApply,
}: MetricWeightingPanelProps) {
  const presentation = getDatasetPresentation(datasetKind);
  const hasValidatedMetricLayer = definitions.length > 0;
  const [isOpen, setIsOpen] = useState(defaultOpen);
  const [selectedProfileId, setSelectedProfileId] = useState(configuration.id);
  const [draftWeights, setDraftWeights] = useState(() =>
    draftFromConfiguration(configuration),
  );

  const validation = useMemo(() => {
    const parsedWeights: Record<MetricId, number> = {};
    const invalidMetricIds: MetricId[] = [];

    definitions.forEach((definition) => {
      const rawValue = draftWeights[definition.id]?.trim() ?? '';
      const value = Number(rawValue);
      if (rawValue === '' || !Number.isFinite(value) || value < 0) {
        invalidMetricIds.push(definition.id);
        return;
      }
      parsedWeights[definition.id] = value;
    });

    const total = Object.values(parsedWeights).reduce(
      (sum, weight) => sum + weight,
      0,
    );
    const isComplete = invalidMetricIds.length === 0;
    const isTotalValid = isComplete && Math.abs(total - 100) < 0.0001;

    return {
      invalidMetricIds,
      isValid: isTotalValid,
      parsedWeights,
      total,
    };
  }, [definitions, draftWeights]);

  const activePreset = metricProfiles.find(
    (profile) => profile.id === selectedProfileId,
  );

  const selectProfile = (profileId: string) => {
    const profile = metricProfiles.find((candidate) => candidate.id === profileId);
    setSelectedProfileId(profileId);
    if (profile) {
      setDraftWeights(draftFromConfiguration(profile));
    }
  };

  const updateDraftWeight = (metricId: MetricId, value: string) => {
    setSelectedProfileId('custom-profile');
    setDraftWeights((current) => ({ ...current, [metricId]: value }));
  };

  const confirmProfile = () => {
    if (!validation.isValid) {
      return;
    }
    onApply({
      id: activePreset?.id ?? 'custom-profile',
      name: activePreset?.name ?? 'Custom metric profile',
      weights: validation.parsedWeights,
    });
  };

  const validationMessage = validation.invalidMetricIds.length
    ? 'Enter a non-negative numeric value for every metric.'
    : validation.isValid
      ? 'Ready to confirm. Draft total is exactly 100%.'
      : `Total must equal 100%. Current draft: ${validation.total.toFixed(2)}%.`;

  return (
    <div className="metric-weighting-control" data-open={isOpen}>
      <button
        className="atlas-utility-button"
        type="button"
        onClick={() => setIsOpen((current) => !current)}
        aria-label="Configure metric visualization"
        aria-expanded={isOpen}
        title="Metric Engine"
      >
        <span aria-hidden="true">Σ</span>
      </button>

      {isOpen && (
        <section className="metric-weighting-panel" aria-live="polite">
          <header>
            <div>
              <p className="section-kicker">Metric Engine · exploration</p>
              <h2>
                {!hasValidatedMetricLayer
                  ? 'Metrics withheld'
                  : compositeAvailable
                  ? 'Define a perspective'
                  : 'Choose a metric'}
              </h2>
            </div>
            {compositeAvailable && (
              <span className="metric-total" data-valid={validation.isValid}>
                {validation.total.toFixed(2)}%
              </span>
            )}
          </header>

          {hasValidatedMetricLayer && (
            <label className="metric-layer-select">
              <span>Active metric layer</span>
              <select
                value={selectedMetricId}
                onChange={(event) => onMetricSelect(event.target.value)}
              >
                {definitions.map((definition) => (
                  <option key={definition.id} value={definition.id}>
                    {definition.name}
                  </option>
                ))}
                <option
                  value={compositeMetricId}
                  disabled={!hasConfirmedProfile || !compositeAvailable}
                >
                  Applied composite · {configuration.name}
                </option>
              </select>
            </label>
          )}

          {!hasValidatedMetricLayer ? (
            <p className="metric-pilot-limit" role="note">
              {getUnavailableMetricLayerMessage(
                presentation.dataLabelLower,
              )}
            </p>
          ) : compositeAvailable ? (
            <>
              <label className="metric-layer-select">
                <span>Predefined perspective</span>
                <select
                  value={selectedProfileId}
                  onChange={(event) => selectProfile(event.target.value)}
                >
                  {metricProfiles.map((profile) => (
                    <option key={profile.id} value={profile.id}>
                      {profile.name}
                    </option>
                  ))}
                  <option value="custom-profile">Custom profile</option>
                </select>
              </label>
              <p className="metric-profile-purpose">
                {activePreset?.purpose ??
                  'Enter a custom perspective. Changes remain a draft until confirmed.'}
              </p>

              <div className="metric-weight-list">
                {definitions.map((definition) => {
                  const isInvalid = validation.invalidMetricIds.includes(
                    definition.id,
                  );
                  return (
                    <label key={definition.id} className="metric-weight-row">
                      <span>
                        <strong>{definition.name}</strong>
                        <small>{definition.interpretation}</small>
                      </span>
                      <span className="metric-number-input">
                        <input
                          type="number"
                          min="0"
                          step="any"
                          inputMode="decimal"
                          value={draftWeights[definition.id] ?? ''}
                          aria-label={`${definition.name} weight`}
                          aria-invalid={isInvalid}
                          onChange={(event) =>
                            updateDraftWeight(definition.id, event.target.value)
                          }
                        />
                        <i aria-hidden="true">%</i>
                      </span>
                    </label>
                  );
                })}
              </div>

              <p
                className="metric-validation-message"
                data-valid={validation.isValid}
              >
                {validationMessage}
              </p>

              <div className="metric-profile-footer">
                <button
                  className="metric-apply-button"
                  type="button"
                  disabled={!validation.isValid}
                  onClick={confirmProfile}
                >
                  Confirm and generate heatmap
                </button>
                <span>
                  {hasConfirmedProfile
                    ? `Applied: ${configuration.name}`
                    : 'No composite has been confirmed'}
                </span>
              </div>
            </>
          ) : (
            <p className="metric-pilot-limit" role="note">
              Composite profiles are unavailable for this{' '}
              {presentation.dataLabelLower} because one or more required metric
              calculations are absent. Values from another dataset are never
              substituted.
            </p>
          )}

          <p className="metric-profile-disclaimer">
            This is a user-defined exploration profile. It is not an official
            ranking, objective scientific truth, or universal evaluation.
          </p>
        </section>
      )}
    </div>
  );
}
