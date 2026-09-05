"""Operational limits for verbose validation outputs, never scientific thresholds.

Production ingestion must not call paired/replay/comparison generators. These
checks also protect installed validation commands from accidental production use.
They do not authorize a sample, change certification, or prevent privileged code
from bypassing the application boundary.
"""

from ..config import Settings
from .contracts import CertificationError

MAX_VALIDATION_PAPERS = 2_500  # Accommodates the existing 2,498-occurrence trial.
MAX_VALIDATION_DECISIONS = 100_000  # Existing in-memory replay ceiling.
MAX_VALIDATION_DECISION_BYTES = 128 * 1024 * 1024


def require_validation_runtime() -> None:
    """Read current environment/.env settings, without opening any DB/network."""

    try:
        environment = Settings().environment
    except ValueError:
        # Do not echo settings validation inputs: they can include credentials.
        raise CertificationError("invalid runtime for validation artifacts") from None
    if environment not in ("development", "test"):
        raise CertificationError("validation artifacts are forbidden in production")


def validation_paper_limit(value: int | None) -> int:
    if type(value) is not int or not 1 <= value <= MAX_VALIDATION_PAPERS:
        raise CertificationError(
            "verbose validation requires explicit validation_max_papers "
            f"between 1 and {MAX_VALIDATION_PAPERS}"
        )
    return value


def check_validation_size(
    *,
    paper_count: int = 0,
    paper_limit: int = MAX_VALIDATION_PAPERS,
    decision_count: int = 0,
    decision_bytes: int = 0,
) -> None:
    limit = validation_paper_limit(paper_limit)
    if any(
        type(value) is not int or value < 0
        for value in (paper_count, decision_count, decision_bytes)
    ):
        raise CertificationError("invalid validation artifact counts")
    if paper_count > limit:
        raise CertificationError("validation paper count exceeds bounded sample limit")
    if decision_count > MAX_VALIDATION_DECISIONS:
        raise CertificationError("validation decision count exceeds hard limit")
    if decision_bytes > MAX_VALIDATION_DECISION_BYTES:
        raise CertificationError("validation decision bytes exceed hard limit")
