from dataclasses import dataclass


def _validate_fraction(name: str, value: float) -> None:
    if not 0 <= value <= 1:
        raise ValueError(f"{name} must be between zero and one")


@dataclass(frozen=True)
class CoverageThresholds:
    paper_time_affiliation: float
    canonical_institution: float
    citation: float
    field_attribution: float

    def __post_init__(self) -> None:
        _validate_fraction("paper_time_affiliation", self.paper_time_affiliation)
        _validate_fraction("canonical_institution", self.canonical_institution)
        _validate_fraction("citation", self.citation)
        _validate_fraction("field_attribution", self.field_attribution)


@dataclass(frozen=True)
class ActivityThresholds:
    minimum_fractional_papers: float
    minimum_distinct_researchers: int
    minimum_normalization_cohort: int


@dataclass(frozen=True)
class ImpactThresholds:
    minimum_eligible_papers: int
    citation_maturity_months: int
    minimum_reference_cohort: int
    minimum_normalization_cohort: int


@dataclass(frozen=True)
class ConnectivityThresholds:
    minimum_fractional_papers: float
    minimum_identifiable_researchers: int
    minimum_relationship_coverage: float

    def __post_init__(self) -> None:
        _validate_fraction(
            "minimum_relationship_coverage", self.minimum_relationship_coverage
        )


@dataclass(frozen=True)
class DiversityThresholds:
    minimum_fractional_papers: float


@dataclass(frozen=True)
class MomentumThresholds:
    required_complete_years: int
    minimum_fractional_papers_per_window: float
    minimum_normalization_cohort: int
    robust_z_clip: float


@dataclass(frozen=True)
class MetricValidationThresholds:
    """Versioned policy inputs, not immutable claims of scientific truth."""

    version: str
    coverage: CoverageThresholds
    activity: ActivityThresholds
    impact: ImpactThresholds
    connectivity: ConnectivityThresholds
    diversity: DiversityThresholds
    momentum: MomentumThresholds

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("threshold version must be non-empty")
        positive_values = (
            self.activity.minimum_fractional_papers,
            self.activity.minimum_distinct_researchers,
            self.activity.minimum_normalization_cohort,
            self.impact.minimum_eligible_papers,
            self.impact.citation_maturity_months,
            self.impact.minimum_reference_cohort,
            self.impact.minimum_normalization_cohort,
            self.connectivity.minimum_fractional_papers,
            self.connectivity.minimum_identifiable_researchers,
            self.diversity.minimum_fractional_papers,
            self.momentum.required_complete_years,
            self.momentum.minimum_fractional_papers_per_window,
            self.momentum.minimum_normalization_cohort,
            self.momentum.robust_z_clip,
        )
        if any(value <= 0 for value in positive_values):
            raise ValueError("metric validation minimums must be positive")


METRIC_VALIDATION_THRESHOLDS_V1 = MetricValidationThresholds(
    version="metric-validation-thresholds-v1",
    coverage=CoverageThresholds(
        paper_time_affiliation=0.90,
        canonical_institution=0.95,
        citation=0.90,
        field_attribution=0.90,
    ),
    activity=ActivityThresholds(
        minimum_fractional_papers=10.0,
        minimum_distinct_researchers=5,
        minimum_normalization_cohort=30,
    ),
    impact=ImpactThresholds(
        minimum_eligible_papers=10,
        citation_maturity_months=24,
        minimum_reference_cohort=50,
        minimum_normalization_cohort=30,
    ),
    connectivity=ConnectivityThresholds(
        minimum_fractional_papers=10.0,
        minimum_identifiable_researchers=5,
        minimum_relationship_coverage=0.90,
    ),
    diversity=DiversityThresholds(minimum_fractional_papers=15.0),
    momentum=MomentumThresholds(
        required_complete_years=6,
        minimum_fractional_papers_per_window=10.0,
        minimum_normalization_cohort=30,
        robust_z_clip=3.0,
    ),
)
