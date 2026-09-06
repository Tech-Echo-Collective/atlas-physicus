"""Both adapters retain one shared implementation of the original alignment rule."""

from physics_atlas_api import paired_trial_certification
from physics_atlas_api.attribution.affiliation_identifiers import (
    align_affiliation_ror_evidence,
)
from physics_atlas_api.certification import launch_attribution


def test_launch_and_legacy_adapters_use_identical_alignment_function() -> None:
    assert (
        launch_attribution._align_affiliation_ror_evidence
        is paired_trial_certification._align_affiliation_ror_evidence
        is align_affiliation_ror_evidence
    )
