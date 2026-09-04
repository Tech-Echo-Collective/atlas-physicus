from collections.abc import Iterable

import pytest

from physics_atlas_api.historical_replay import (
    BibliographicDateEvidence,
    PaperEvidenceOccurrence,
    StrongIdentifier,
    build_canonical_paper_merge_plan,
)
from physics_atlas_api.historical_replay_materialization import _author_names


def occurrence(
    provider: str,
    source_record_id: str,
    *,
    identifiers: Iterable[tuple[str, str]] = (),
    title: str = "A canonical paper",
    authors: tuple[str, ...] = ("Ada Lovelace", "Emmy Noether"),
    year: int | None = 2024,
    journal: str | None = "Journal of Exact Evidence",
    document_type: str | None = "article",
    dates: tuple[tuple[str, str, str], ...] = (),
) -> PaperEvidenceOccurrence:
    occurrence_id = f"{provider}:{source_record_id}"
    return PaperEvidenceOccurrence(
        occurrence_id=occurrence_id,
        provider=provider,
        source_record_id=source_record_id,
        source_reference=f"pages/{provider}/{source_record_id}",
        identifiers=tuple(
            StrongIdentifier(scheme, value)  # type: ignore[arg-type]
            for scheme, value in identifiers
        ),
        title=title,
        authors=authors,
        year=year,
        journal=journal,
        document_type=document_type,
        dates=tuple(
            BibliographicDateEvidence(
                source_occurrence_id=occurrence_id,
                kind=kind,
                value=value,
                precision=precision,  # type: ignore[arg-type]
            )
            for kind, value, precision in dates
        ),
    )


def test_strong_identifier_plan_is_order_invariant_and_prefers_doi() -> None:
    inspire = occurrence(
        "inspire",
        "1001",
        identifiers=(
            ("inspire", "1001"),
            ("arxiv", "2401.01234v2"),
            ("doi", "HTTPS://DOI.ORG/10.1234/Canonical"),
        ),
        dates=(
            ("formal-publication", "2024-09-17", "day"),
            ("preprint-submission", "2024-01-03", "day"),
        ),
    )
    arxiv = occurrence(
        "arxiv",
        "2401.01234",
        identifiers=(
            ("arxiv", "arXiv:2401.01234"),
            ("doi", "10.1234/canonical"),
        ),
        document_type="preprint",
        dates=(("preprint-submission", "2024-01-03", "day"),),
    )

    forward = build_canonical_paper_merge_plan([inspire, arxiv])
    reverse = build_canonical_paper_merge_plan([arxiv, inspire])

    assert forward.digest == reverse.digest
    assert forward.as_dict() == reverse.as_dict()
    assert forward.occurrence_count == 2
    assert len(forward.components) == 1
    component = forward.components[0]
    assert component.status == "matched"
    assert component.primary_identifier == StrongIdentifier("doi", "10.1234/canonical")
    assert component.canonical_id is not None
    assert component.canonical_id.startswith("paper-doi-")
    assert {item.occurrence_id for item in component.occurrences} == {
        "inspire:1001",
        "arxiv:2401.01234",
    }
    assert {item.source_reference for item in component.occurrences} == {
        "pages/inspire/1001",
        "pages/arxiv/2401.01234",
    }
    assert {
        (item.source_occurrence_id, item.kind, item.value, item.precision)
        for item in component.date_evidence
    } == {
        ("inspire:1001", "formal-publication", "2024-09-17", "day"),
        ("inspire:1001", "preprint-submission", "2024-01-03", "day"),
        ("arxiv:2401.01234", "preprint-submission", "2024-01-03", "day"),
    }
    assert component.as_dict()["canonical_date_selected"] is False


def test_conflicting_same_scheme_identifiers_are_withheld_for_review() -> None:
    first = occurrence(
        "inspire",
        "2001",
        identifiers=(("inspire", "2001"), ("arxiv", "2402.00001"), ("doi", "10.1/a")),
    )
    second = occurrence(
        "arxiv",
        "2402.00001",
        identifiers=(("arxiv", "2402.00001"), ("doi", "10.1/b")),
    )

    component = build_canonical_paper_merge_plan([first, second]).components[0]

    assert component.status == "needs_review"
    assert component.conflict_schemes == ("doi",)
    assert component.primary_identifier is None
    assert component.canonical_id is None
    assert component.candidate_id.startswith("paper-candidate-")


def test_secondary_merge_requires_all_exact_independent_evidence() -> None:
    inspire = occurrence(
        "inspire",
        "3001",
        identifiers=(("inspire", "3001"),),
        title="Symmetry, Geometry & Fields",
        authors=("Noether, Emmy", "Albert Einstein"),
        year=2023,
        journal="Annals of Physics, 42",
    )
    arxiv = occurrence(
        "arxiv",
        "2301.00301",
        identifiers=(("arxiv", "2301.00301"),),
        title="Symmetry Geometry and Fields",
        authors=("Einstein, Albert", "Emmy Noether"),
        year=2023,
        journal="Annals of Physics 42",
        document_type="preprint",
    )

    component = build_canonical_paper_merge_plan([inspire, arxiv]).components[0]

    assert component.status == "matched"
    assert component.primary_identifier == StrongIdentifier("arxiv", "2301.00301")
    assert component.canonical_id is not None
    assert component.canonical_id.startswith("paper-arxiv-")
    assert [item.method for item in component.merge_evidence] == [
        "secondary-bibliographic"
    ]


def test_merge_evidence_is_assigned_to_its_final_transitive_component() -> None:
    doi_side = occurrence(
        "inspire",
        "transitive-doi",
        identifiers=(("doi", "10.1234/transitive"),),
    )
    bridge = occurrence(
        "crossref",
        "transitive-bridge",
        identifiers=(
            ("doi", "10.1234/transitive"),
            ("arxiv", "2401.12345"),
        ),
    )
    arxiv_side = occurrence(
        "arxiv",
        "2401.12345",
        identifiers=(("arxiv", "2401.12345"),),
    )
    unrelated = occurrence(
        "inspire",
        "unrelated",
        identifiers=(("inspire", "999999"),),
        title="A separate paper",
    )

    plan = build_canonical_paper_merge_plan(
        [unrelated, arxiv_side, bridge, doi_side],
        enable_secondary_merge=False,
    )

    merged = next(item for item in plan.components if len(item.occurrences) == 3)
    singleton = next(item for item in plan.components if len(item.occurrences) == 1)
    assert [
        (item.method, item.scheme, item.value) for item in merged.merge_evidence
    ] == [
        ("strong-identifier", "arxiv", "2401.12345"),
        ("strong-identifier", "doi", "10.1234/transitive"),
    ]
    assert singleton.merge_evidence == ()


@pytest.mark.parametrize(
    ("authors", "year", "journal"),
    [
        (("A Different Author",), 2023, "Annals of Physics 42"),
        (("Emmy Noether", "Albert Einstein"), 2022, "Annals of Physics 42"),
        (("Emmy Noether", "Albert Einstein"), 2023, "Another Journal"),
        (("Emmy Noether", "Albert Einstein"), 2023, None),
    ],
)
def test_secondary_merge_withholds_when_any_required_evidence_differs(
    authors: tuple[str, ...],
    year: int,
    journal: str | None,
) -> None:
    first = occurrence(
        "inspire",
        "4001",
        identifiers=(("inspire", "4001"),),
        title="The same title",
        authors=("Emmy Noether", "Albert Einstein"),
        year=2023,
        journal="Annals of Physics 42",
    )
    second = occurrence(
        "arxiv",
        "2301.00401",
        identifiers=(("arxiv", "2301.00401"),),
        title="The same title",
        authors=authors,
        year=year,
        journal=journal,
    )

    plan = build_canonical_paper_merge_plan([first, second])

    assert len(plan.components) == 2
    assert all(not item.merge_evidence for item in plan.components)


def test_title_alone_never_merges_provider_occurrences() -> None:
    first = occurrence(
        "inspire",
        "5001",
        identifiers=(("inspire", "5001"),),
        title="A deceptively common title",
        authors=(),
        journal=None,
    )
    second = occurrence(
        "arxiv",
        "2301.00501",
        identifiers=(("arxiv", "2301.00501"),),
        title="A deceptively common title",
        authors=(),
        journal=None,
    )

    plan = build_canonical_paper_merge_plan([first, second])

    assert len(plan.components) == 2
    assert {
        item.primary_identifier.scheme
        for item in plan.components
        if item.primary_identifier
    } == {
        "arxiv",
        "inspire",
    }


def test_missing_author_names_never_become_secondary_merge_placeholders() -> None:
    extracted_authors = _author_names([{"full_name": "Ada Example"}, {"full_name": ""}])
    assert extracted_authors == ()

    plan = build_canonical_paper_merge_plan(
        [
            occurrence(
                "inspire",
                "missing-author-1",
                identifiers=(("inspire", "9001"),),
                title="Same bibliographic title",
                authors=extracted_authors,
                year=2024,
                journal="Journal of Exact Evidence",
            ),
            occurrence(
                "arxiv",
                "2401.09001",
                identifiers=(("arxiv", "2401.09001"),),
                title="Same bibliographic title",
                authors=extracted_authors,
                year=2024,
                journal="Journal of Exact Evidence",
            ),
        ]
    )

    assert len(plan.components) == 2
    assert all(not item.merge_evidence for item in plan.components)


def test_occurrence_without_strong_or_complete_secondary_evidence_needs_review() -> (
    None
):
    evidence = occurrence(
        "inspire",
        "missing-identifiers",
        identifiers=(),
        authors=(),
        year=None,
        journal=None,
    )

    component = build_canonical_paper_merge_plan([evidence]).components[0]

    assert component.status == "needs_review"
    assert component.canonical_id is None
    assert component.primary_identifier is None


def test_plan_digest_is_idempotent_and_changes_with_source_lineage() -> None:
    evidence = occurrence(
        "inspire",
        "6001",
        identifiers=(("inspire", "6001"),),
    )
    first = build_canonical_paper_merge_plan([evidence])
    second = build_canonical_paper_merge_plan([evidence])
    changed = build_canonical_paper_merge_plan(
        [
            PaperEvidenceOccurrence(
                **{
                    **evidence.__dict__,
                    "source_reference": "pages/inspire/a-different-checksum",
                }
            )
        ]
    )

    assert first.digest == second.digest
    assert first.components[0].digest == second.components[0].digest
    assert changed.digest != first.digest


def test_invalid_or_misattributed_date_evidence_fails_closed() -> None:
    with pytest.raises(ValueError, match="does not have month precision"):
        BibliographicDateEvidence(
            source_occurrence_id="inspire:7001",
            kind="formal-publication",
            value="2024-01-02",
            precision="month",
        )

    date_evidence = BibliographicDateEvidence(
        source_occurrence_id="inspire:another-record",
        kind="formal-publication",
        value="2024",
        precision="year",
    )
    with pytest.raises(ValueError, match="containing occurrence"):
        occurrence("inspire", "7001", dates=()).__class__(
            occurrence_id="inspire:7001",
            provider="inspire",
            source_record_id="7001",
            source_reference="pages/inspire/7001",
            dates=(date_evidence,),
        )


def test_duplicate_occurrence_ids_fail_closed() -> None:
    evidence = occurrence(
        "inspire",
        "8001",
        identifiers=(("inspire", "8001"),),
    )

    with pytest.raises(ValueError, match="must be unique"):
        build_canonical_paper_merge_plan([evidence, evidence])
