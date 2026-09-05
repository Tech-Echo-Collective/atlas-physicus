import pytest

from physics_atlas_api.storage import (
    DEFAULT_EXACT_COUNT_TABLES,
    build_postgres_storage_audit_queries,
)


def test_storage_audit_queries_are_read_only_and_cover_core_relations() -> None:
    queries = build_postgres_storage_audit_queries()

    for statement in (
        queries.summary,
        queries.relations,
        queries.exact_row_counts,
        queries.logical_payloads,
    ):
        assert statement.lstrip().startswith("SELECT ")
        assert ";" not in statement
    assert "BEGIN TRANSACTION READ ONLY;" in queries.transaction_script()
    assert queries.transaction_script().rstrip().endswith("COMMIT;")
    for table in DEFAULT_EXACT_COUNT_TABLES:
        assert f'public."{table}"' in queries.exact_row_counts


def test_storage_audit_rejects_identifier_injection_and_empty_scope() -> None:
    with pytest.raises(ValueError, match="unsafe PostgreSQL identifier"):
        build_postgres_storage_audit_queries(("papers; DROP TABLE papers",))
    with pytest.raises(ValueError, match="at least one"):
        build_postgres_storage_audit_queries(())


def test_storage_audit_deduplicates_and_sorts_exact_count_tables() -> None:
    queries = build_postgres_storage_audit_queries(
        ("researchers", "papers", "researchers")
    )

    assert queries.exact_row_counts.count('public."researchers"') == 1
    assert queries.exact_row_counts.index('public."papers"') < (
        queries.exact_row_counts.index('public."researchers"')
    )
