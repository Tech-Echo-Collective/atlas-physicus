"""Build PostgreSQL-only SELECT statements for an operator storage audit."""

from __future__ import annotations

import re
from dataclasses import dataclass

_IDENTIFIER_PATTERN = re.compile(r"^[a-z_][a-z0-9_]*$")

DEFAULT_EXACT_COUNT_TABLES = (
    "papers",
    "researchers",
    "authorships",
    "affiliations",
    "paper_affiliations",
    "institutions",
    "paper_fields",
    "citations",
    "metric_observations",
    "source_snapshots",
    "raw_entity_records",
    "identity_resolutions",
    "identity_reviews",
    "authority_identifiers",
    "entity_search_terms",
    "dataset_updates",
    "update_runs",
    "external_resources",
    "resource_checks",
    "source_cursors",
)

# Fixed schema columns only; no dynamic catalog traversal or source-payload export.
_STORED_DATUM_COLUMNS = (
    ("raw_entity_records", "provenance"),
    ("raw_entity_records", "external_ids"),
    ("source_snapshots", "provenance"),
    ("paper_affiliations", "provenance"),
    ("paper_affiliations", "resolution_evidence"),
    ("paper_affiliations", "contribution_evidence"),
    ("paper_fields", "provenance"),
    ("paper_fields", "provider_categories"),
    ("identity_resolutions", "provenance"),
    ("identity_resolutions", "evidence"),
    ("authority_identifiers", "provenance"),
    ("papers", "provenance"),
    ("researchers", "provenance"),
    ("authorships", "provenance"),
    ("dataset_updates", "affected_entities"),
    ("update_runs", "affected_entities"),
    ("update_runs", "affected_metric_partitions"),
    ("source_cursors", "checkpoint"),
)


@dataclass(frozen=True)
class PostgresStorageAuditQueries:
    """Queries are intentionally separate so operators can time costly counts."""

    summary: str
    relations: str
    exact_row_counts: str
    # Historical attribute name retained for callers. pg_column_size reports
    # stored datum size (possibly compressed), not serialized logical bytes.
    logical_payloads: str
    indexes: str = ""
    stored_datums: str = ""

    def transaction_script(self) -> str:
        return "\n".join(
            (
                "BEGIN TRANSACTION READ ONLY;",
                "SET LOCAL statement_timeout = '60s';",
                "SET LOCAL lock_timeout = '2s';",
                f"{self.summary};",
                f"{self.relations};",
                f"{self.exact_row_counts};",
                f"{self.logical_payloads};",
                *(f"{query};" for query in (self.indexes, self.stored_datums) if query),
                "COMMIT;",
            )
        )


def _validated_identifier(value: str) -> str:
    if _IDENTIFIER_PATTERN.fullmatch(value) is None:
        raise ValueError(f"unsafe PostgreSQL identifier: {value!r}")
    return value


def build_postgres_storage_audit_queries(
    table_names: tuple[str, ...] = DEFAULT_EXACT_COUNT_TABLES,
) -> PostgresStorageAuditQueries:
    """Return read-only audit SQL with safely quoted exact-count table names."""

    if not table_names:
        raise ValueError("at least one exact-count table is required")
    names = tuple(
        sorted(dict.fromkeys(_validated_identifier(item) for item in table_names))
    )
    # Every interpolated value passed the strict identifier allow-pattern above.
    exact_row_counts = " UNION ALL ".join(
        f"SELECT '{name}' AS relation, count(*)::bigint AS exact_rows "  # noqa: S608
        f'FROM public."{name}"'
        for name in names
    )
    return PostgresStorageAuditQueries(
        summary=(
            "SELECT pg_database_size(current_database())::bigint AS database_bytes, "
            "sum(pg_table_size(c.oid))::bigint AS public_table_bytes, "
            "sum(pg_indexes_size(c.oid))::bigint AS public_index_bytes, "
            "sum(pg_total_relation_size(c.oid))::bigint AS public_total_bytes "
            "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relkind = 'r'"
        ),
        relations=(
            "SELECT c.relname AS relation, "
            "pg_relation_size(c.oid, 'main')::bigint AS heap_main_bytes, "
            "(pg_relation_size(c.oid, 'fsm') + "
            "pg_relation_size(c.oid, 'vm') + "
            "pg_relation_size(c.oid, 'init'))::bigint AS heap_auxiliary_bytes, "
            "CASE WHEN c.reltoastrelid = 0 THEN 0::bigint ELSE "
            "pg_total_relation_size(c.reltoastrelid)::bigint END AS toast_bytes, "
            "pg_table_size(c.oid)::bigint AS table_bytes, "
            "pg_indexes_size(c.oid)::bigint AS index_bytes, "
            "pg_total_relation_size(c.oid)::bigint AS total_bytes "
            "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relkind = 'r' "
            "ORDER BY pg_total_relation_size(c.oid) DESC, c.relname"
        ),
        exact_row_counts=exact_row_counts,
        logical_payloads=(
            "SELECT "
            "(SELECT coalesce(sum(pg_column_size(raw_payload)), 0)::bigint "
            "FROM public.source_snapshots) AS snapshot_payload_stored_datum_bytes, "
            "(SELECT coalesce(sum(pg_column_size(raw_payload)), 0)::bigint "
            "FROM public.raw_entity_records) AS raw_record_payload_stored_datum_bytes, "
            "(SELECT coalesce(sum(pg_column_size(attributes)), 0)::bigint "
            "FROM public.raw_entity_records) AS raw_record_attribute_stored_datum_bytes"
        ),
        indexes=(
            "SELECT t.relname AS relation, i.relname AS index_name, "
            "pg_relation_size(i.oid)::bigint AS index_bytes, "
            "x.indisprimary AS is_primary, x.indisunique AS is_unique, "
            "s.idx_scan AS scans_since_statistics_reset, "
            "pg_get_indexdef(i.oid) AS definition "
            "FROM pg_index x JOIN pg_class i ON i.oid = x.indexrelid "
            "JOIN pg_class t ON t.oid = x.indrelid "
            "JOIN pg_namespace n ON n.oid = t.relnamespace "
            "LEFT JOIN pg_stat_user_indexes s ON s.indexrelid = i.oid "
            "WHERE n.nspname = 'public' AND t.relkind = 'r' "
            "ORDER BY pg_relation_size(i.oid) DESC, i.relname"
        ),
        stored_datums=" UNION ALL ".join(
            f"SELECT '{table}' AS relation, '{column}' AS column_name, "  # noqa: S608
            "count(*)::bigint AS exact_rows, "
            f'coalesce(sum(pg_column_size("{column}")), 0)::bigint '
            f'AS stored_datum_bytes FROM public."{table}"'
            for table, column in _STORED_DATUM_COLUMNS
        ),
    )
