"""Bounded mocked transport; no scientific acquisition or file persistence."""

import json
from datetime import UTC, datetime
from unittest.mock import Mock
from urllib.parse import parse_qs, urlsplit

import pytest

from physics_atlas_api.certification import CertificationError
from physics_atlas_api.certification.launch_capture import (
    FetchedLaunchPage,
    collect_launch_year,
)
from physics_atlas_api.certification.launch_scope import bounded_launch_source_plan
from physics_atlas_api.connectors.inspire import InspireConnector

NOW = datetime(2026, 9, 6, tzinfo=UTC)
PLAN = bounded_launch_source_plan(
    calendar_year=2020, cutoff=NOW, dataset_version="fixture-launch"
)


def page_payload(ids: list[int], total: int) -> bytes:
    return json.dumps(
        {
            "hits": {
                "total": total,
                "hits": [
                    {
                        "id": str(identifier),
                        "metadata": {
                            "control_number": identifier,
                            "titles": [{"title": "Synthetic fixture"}],
                            "preprint_date": "2020-03-01",
                            "document_type": ["article"],
                            "authors": [{"recid": "123"}],
                            "inspire_categories": [{"term": "Theory-Nucl"}],
                        },
                    }
                    for identifier in ids
                ],
            }
        }
    ).encode()


def test_reconciles_exact_multiple_pages_without_retaining_raw_payloads() -> None:
    requests = []

    def fetch(uri: str) -> FetchedLaunchPage:
        params = parse_qs(urlsplit(uri).query)
        assert params["q"] == [PLAN.query_partitions[0].query]
        assert params["sort"] == ["mostrecent"]
        requests.append(uri)
        ids = list(range(1, 251)) if params["page"] == ["1"] else [251]
        return FetchedLaunchPage(uri, NOW, NOW, page_payload(ids, 251))

    result = collect_launch_year(
        PLAN,
        connector=InspireConnector(Mock(), "https://inspirehep.net/api"),
        fetch=fetch,
    )
    assert len(requests) == 2 and len(result.occurrences) == 251
    assert result.partition.reconciles
    assert len(result.requests) == 2
    assert not hasattr(result, "payload")
    assert not hasattr(result.occurrences[0], "raw")
    assert (
        result.partition.page_checksums[0] != result.occurrences[0].reference.checksum
    )


@pytest.mark.parametrize(
    "failure", ["changed-total", "duplicate", "empty", "wrong-query", "unbounded"]
)
def test_acquisition_fails_closed_before_scientific_certification(failure: str) -> None:
    def fetch(uri: str) -> FetchedLaunchPage:
        first = parse_qs(urlsplit(uri).query)["page"] == ["1"]
        if failure == "wrong-query":
            return FetchedLaunchPage(
                "https://example.invalid", NOW, NOW, page_payload([1], 1)
            )
        if failure == "unbounded":
            return FetchedLaunchPage(uri, NOW, NOW, page_payload([1], 20_001))
        ids, total = (list(range(1, 251)), 251) if first else ([251], 251)
        if not first:
            if failure == "changed-total":
                total = 252
            if failure == "duplicate":
                ids = [1]
            if failure == "empty":
                ids = []
        return FetchedLaunchPage(uri, NOW, NOW, page_payload(ids, total))

    with pytest.raises(CertificationError):
        collect_launch_year(
            PLAN,
            connector=InspireConnector(Mock(), "https://inspirehep.net/api"),
            fetch=fetch,
        )
