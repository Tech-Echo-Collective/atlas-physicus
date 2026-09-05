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
)


@dataclass(frozen=True)
class PostgresStorageAuditQueries:
    """Queries are intentionally separate so operators can time costly counts."""

    summary: str
    relations: str
    exact_row_counts: str
    logical_payloads: str

    def transaction_script(self) -> str:
        return "\n".join(
            (
                "BEGIN TRANSACTION READ ONLY;",
                f"{self.summary};",
                f"{self.relations};",
                f"{self.exact_row_counts};",
                f"{self.logical_payloads};",
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
            "FROM public.source_snapshots) AS snapshot_payload_bytes, "
            "(SELECT coalesce(sum(pg_column_size(raw_payload)), 0)::bigint "
            "FROM public.raw_entity_records) AS raw_record_payload_bytes, "
            "(SELECT coalesce(sum(pg_column_size(attributes)), 0)::bigint "
            "FROM public.raw_entity_records) AS raw_record_attribute_bytes"
        ),
    )
