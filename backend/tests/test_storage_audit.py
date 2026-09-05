import pytest

from physics_atlas_api.storage import (
    DEFAULT_EXACT_COUNT_TABLES,
    PostgresStorageAuditQueries,
    build_postgres_storage_audit_queries,
)


def test_storage_audit_queries_are_read_only_and_cover_core_relations() -> None:
    queries = build_postgres_storage_audit_queries()

    for statement in (
        queries.summary,
        queries.relations,
        queries.exact_row_counts,
        queries.logical_payloads,
        queries.indexes,
        queries.stored_datums,
    ):
        assert statement.lstrip().startswith("SELECT ")
        assert ";" not in statement
    assert "BEGIN TRANSACTION READ ONLY;" in queries.transaction_script()
    assert "SET LOCAL statement_timeout = '60s';" in queries.transaction_script()
    assert "SET LOCAL lock_timeout = '2s';" in queries.transaction_script()
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


def test_storage_audit_separates_heap_toast_and_target_indexes() -> None:
    query = build_postgres_storage_audit_queries().relations

    for fork in ("main", "fsm", "vm", "init"):
        assert f"pg_relation_size(c.oid, '{fork}')" in query
    assert "CASE WHEN c.reltoastrelid = 0 THEN 0::bigint" in query
    assert "pg_total_relation_size(c.reltoastrelid)" in query
    assert "pg_indexes_size(c.oid)::bigint AS index_bytes" in query
    assert "pg_total_relation_size(c.oid)::bigint AS total_bytes" in query
    # TOAST total already includes its index; adding that index again would
    # double-count it. pg_table_size includes TOAST but not the target indexes.
    assert "pg_indexes_size(c.reltoastrelid)" not in query
    assert "pg_table_size(c.oid)::bigint AS table_bytes" in query


def test_audit_exposes_index_definitions_without_dropping_unused_indexes() -> None:
    query = build_postgres_storage_audit_queries().indexes

    assert "pg_get_indexdef(i.oid) AS definition" in query
    assert "scans_since_statistics_reset" in query
    assert "x.indisprimary" in query
    assert "x.indisunique" in query
    assert "LEFT JOIN pg_stat_user_indexes" in query
    assert "DROP" not in query


def test_stored_datum_accounting_does_not_claim_uncompressed_logical_bytes() -> None:
    queries = build_postgres_storage_audit_queries()

    assert "snapshot_payload_stored_datum_bytes" in queries.logical_payloads
    assert "raw_record_payload_stored_datum_bytes" in queries.logical_payloads
    assert "raw_record_attribute_stored_datum_bytes" in queries.logical_payloads
    assert "'paper_affiliations' AS relation, 'provenance' AS column_name" in (
        queries.stored_datums
    )
    assert "'paper_fields' AS relation, 'provenance' AS column_name" in (
        queries.stored_datums
    )
    assert "count(*)::bigint AS exact_rows" in queries.stored_datums
    assert "octet_length" not in queries.stored_datums


def test_legacy_four_query_constructor_still_builds_a_valid_script() -> None:
    queries = PostgresStorageAuditQueries(
        "SELECT 1", "SELECT 2", "SELECT 3", "SELECT 4"
    )

    assert queries.indexes == ""
    assert queries.stored_datums == ""
    assert "\n;" not in queries.transaction_script()
    assert queries.transaction_script().endswith("SELECT 4;\nCOMMIT;")
