import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import Mock
from urllib.parse import urlencode

import pytest

from physics_atlas_api.certification.automatic_citations import (
    citation_population_query,
)
from physics_atlas_api.certification.citation_sessions import (
    CAPTURED_MEMBERSHIP_SEMANTICS,
    CITATION_MEASUREMENT_WINDOW_VERSION,
    MAX_CITATION_RESPONSE_BYTES,
    CitationMeasurementSession,
    CitationSessionPage,
    FrozenCitationPopulationEvidence,
    capture_citation_session_page,
    derive_session_citation_population,
    explicit_citation_id_query,
)
from physics_atlas_api.certification.contracts import (
    CertificationError,
    EvidenceReference,
    canonical_digest,
)
from physics_atlas_api.connectors.inspire import InspireConnector

_START = datetime(2026, 9, 5, 12, tzinfo=UTC)
_KEY = ("hep-th", 2020, "article")
_IDS = tuple(str(index) for index in range(1, 101))


def test_oversized_response_is_rejected_before_json_parsing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parser = Mock()
    monkeypatch.setattr(
        "physics_atlas_api.certification.citation_sessions.json.loads", parser
    )
    with pytest.raises(CertificationError, match="8 MiB parsing bound"):
        capture_citation_session_page(
            b"x" * (MAX_CITATION_RESPONSE_BYTES + 1),
            connector=InspireConnector(Mock(), "https://inspirehep.net/api"),
            request_url=_url(1),
            requested_at=_START,
            received_at=_START + timedelta(seconds=1),
            dataset_version="oversized-response-test-only-v1",
            calendar_year=2020,
            declared_date_basis="inspire-preprint-date",
            source_snapshot_id="oversized-response-test-only",
            canonical_paper_ids={},
        )
    parser.assert_not_called()


def _url(page: int, query: str | None = None) -> str:
    return "https://inspirehep.net/api/literature?" + urlencode(
        {
            "q": query or citation_population_query("hep-th-v1", 2020),
            "page": page,
            "size": 50,
        }
    )


def _payload(ids: tuple[str, ...], total: int, next_url: str | None) -> dict[str, Any]:
    return {
        "hits": {
            "total": total,
            "hits": [
                {
                    "id": item,
                    "metadata": {
                        "titles": [{"title": f"Explicit session test fixture {item}"}],
                        "preprint_date": "2020-01-01",
                        "earliest_date": "2019-12-01",
                        "document_type": ["article"],
                        "inspire_categories": [{"term": "Theory-HEP"}],
                        "citation_count": 2,
                        "citation_count_without_self_citations": 0,
                    },
                }
                for item in ids
            ],
        },
        "links": {"next": next_url} if next_url else {},
    }


def _page(index: int, *, explicit: bool = False, **changes: Any) -> CitationSessionPage:
    ids = _IDS[(index - 1) * 50 : index * 50]
    query = explicit_citation_id_query(ids) if explicit else None
    payload = _payload(
        ids, 50 if explicit else 100, None if explicit or index == 2 else _url(2)
    )
    transport = Mock()
    page = capture_citation_session_page(
        json.dumps(payload).encode(),
        **{
            "connector": InspireConnector(transport, "https://inspirehep.net/api"),
            "request_url": _url(1 if explicit else index, query),
            "requested_at": _START + timedelta(seconds=(index - 1) * 3),
            "received_at": _START + timedelta(seconds=(index - 1) * 3 + 2),
            "dataset_version": "session-test-only-v1",
            "calendar_year": 2020,
            "declared_date_basis": "inspire-preprint-date",
            "source_snapshot_id": f"session-test-page-{index}",
            "canonical_paper_ids": {item: f"paper-{item}" for item in ids},
            "expected_source_ids": ids if explicit else None,
            **changes,
        },
    )
    assert (
        page.response_sha256 == hashlib.sha256(json.dumps(payload).encode()).hexdigest()
    )
    transport.get_json.assert_not_called()
    return page


def _frozen() -> FrozenCitationPopulationEvidence:
    pairs = tuple((item, f"paper-{item}") for item in _IDS)
    return FrozenCitationPopulationEvidence(
        reference=EvidenceReference(
            provider="test-only-independent-canonical-population",
            source_record_id="test-only-source-population-v1",
            checksum=canonical_digest(tuple(sorted(pairs))),
            source_snapshot_id="test-only-frozen-inventory",
        ),
        dataset_version="session-test-only-v1",
        acquisition_scope="hep-th-v1",
        declared_date_basis="inspire-preprint-date",
        frozen_at=_START - timedelta(seconds=1),
        provider_to_canonical=pairs,
    )


@pytest.mark.parametrize("explicit", [False, True])
def test_session_preserves_actual_page_times_and_exact_frozen_members(
    explicit: bool,
) -> None:
    pages = (_page(1, explicit=explicit), _page(2, explicit=explicit))
    session = CitationMeasurementSession(pages, _frozen())
    assert session.version == CITATION_MEASUREMENT_WINDOW_VERSION
    assert session.membership_semantics == CAPTURED_MEMBERSHIP_SEMANTICS
    assert session.measurement_started_at == _START
    assert session.measurement_finished_at == _START + timedelta(seconds=5)
    population = derive_session_citation_population(session, _KEY)
    assert len(population.eligible_paper_ids) == 100
    observations = population.observations
    assert all(item.state == "certified" for item in observations)
    assert {item.evidence.observed_at for item in observations} == {
        _START + timedelta(seconds=2),
        _START + timedelta(seconds=5),
    }
    assert all(item.cutoff == item.evidence.observed_at for item in observations)
    assert all(
        item.non_self_citation_count == 0 and item.maturity_months == 24
        for item in observations
    )
    assert CitationMeasurementSession(pages, _frozen()).session_id == session.session_id


@pytest.mark.parametrize(
    "failure",
    [
        "missing-page",
        "wrong-order",
        "wrong-query",
        "total-drift",
        "duplicate-id",
        "too-slow",
        "overlap",
    ],
)
def test_session_fails_closed_on_capture_inconsistency(failure: str) -> None:
    first, second = _page(1), _page(2)
    pages = (first, second)
    if failure == "missing-page":
        pages = (first,)
    elif failure == "wrong-order":
        pages = (second, first)
    elif failure == "wrong-query":
        second = replace(second, request_url=_url(2, "recid:1"))
        pages = (first, second)
    elif failure == "total-drift":
        second = replace(second, reported_total=99, records=second.records[:-1])
        pages = (first, second)
    elif failure == "duplicate-id":
        second = replace(second, records=(first.records[0], *second.records[1:]))
        pages = (first, second)
    elif failure == "too-slow":
        second = replace(
            second,
            requested_at=_START + timedelta(minutes=31),
            received_at=_START + timedelta(minutes=32),
        )
        pages = (first, second)
    else:
        second = replace(second, requested_at=_START + timedelta(seconds=1))
        pages = (first, second)
    with pytest.raises(CertificationError):
        CitationMeasurementSession(pages, _frozen())


def test_frozen_inventory_must_exist_before_measurement_and_match_exactly() -> None:
    pages = (_page(1), _page(2))
    frozen = _frozen()
    with pytest.raises(CertificationError, match="independently frozen"):
        CitationMeasurementSession(
            pages, replace(frozen, frozen_at=_START + timedelta(seconds=1))
        )
    altered = (*frozen.provider_to_canonical[:-1], ("999", "paper-999"))
    with pytest.raises(CertificationError, match="independently frozen"):
        CitationMeasurementSession(
            pages,
            replace(
                frozen,
                provider_to_canonical=altered,
                reference=replace(
                    frozen.reference, checksum=canonical_digest(tuple(sorted(altered)))
                ),
            ),
        )
    with pytest.raises(CertificationError, match="identity/reference"):
        CitationMeasurementSession(
            pages,
            replace(frozen, reference=replace(frozen.reference, checksum="0" * 64)),
        )


def test_next_link_cannot_skip_or_change_origin_and_scope() -> None:
    first = _page(1)
    for next_url in (
        _url(3),
        "https://example.invalid/api/literature",
        _url(2, "recid:999"),
    ):
        with pytest.raises(CertificationError):
            replace(first, next_url=next_url).validate()


def test_explicit_batches_cannot_mix_with_sort_pagination_or_change_requested_ids() -> (
    None
):
    with pytest.raises(CertificationError, match="lineage"):
        CitationMeasurementSession((_page(1, explicit=True), _page(2)), _frozen())
    first = _page(1, explicit=True)
    with pytest.raises(CertificationError):
        replace(first, expected_source_ids=(*_IDS[:49], "999")).validate()
    with pytest.raises(CertificationError, match="unique canonical INSPIRE IDs"):
        explicit_citation_id_query(("1", "1"))


def test_missing_counts_remain_missing_in_session_membership() -> None:
    first, second = _page(1), _page(2)
    first = replace(
        first,
        records=(
            replace(first.records[0], non_self_citation_count=None),
            *first.records[1:],
        ),
    )
    session = CitationMeasurementSession((first, second), _frozen())
    population = derive_session_citation_population(session, _KEY)
    assert len(population.eligible_paper_ids) == 100
    missing = next(
        item for item in population.observations if item.paper_id == "paper-1"
    )
    assert missing.non_self_citation_count is None
    assert missing.state == "insufficient_evidence"


def test_operational_policy_version_cannot_be_silently_changed() -> None:
    with pytest.raises(CertificationError, match="version"):
        CitationMeasurementSession(
            (_page(1), _page(2)), _frozen(), version="unversioned-tolerance"
        )
