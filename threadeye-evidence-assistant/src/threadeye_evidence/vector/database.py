"""Isolated PostgreSQL/pgvector access with strict local-connection validation."""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import unquote, urlsplit

from threadeye_evidence.vector.embeddings import EmbeddingMetadata
from threadeye_evidence.vector.provenance import ApprovedChunkBatch

EXPECTED_DATABASE = "threadeye_evidence"
EXPECTED_USER = "threadeye_evidence"
ALLOWED_DATABASE_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
MAX_QUERY_RESULTS = 20
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class DatabaseSafetyError(ValueError):
    """Database configuration or identity violates companion isolation."""


class IndexingConflictError(ValueError):
    """Stored vector metadata is incompatible with the requested operation."""


@dataclass(frozen=True)
class DatabaseSettings:
    dsn: str = field(repr=False)
    host: str
    port: int
    database: str
    user: str

    @classmethod
    def from_dsn(cls, dsn: str) -> "DatabaseSettings":
        if not isinstance(dsn, str) or not dsn.strip():
            raise DatabaseSafetyError("an isolated companion database URL is required")
        parsed = urlsplit(dsn)
        if parsed.scheme not in {"postgres", "postgresql"}:
            raise DatabaseSafetyError("database URL must use PostgreSQL")
        if parsed.query or parsed.fragment:
            raise DatabaseSafetyError("database URL query parameters and fragments are not allowed")
        host = parsed.hostname or ""
        try:
            port = parsed.port or 5432
        except ValueError as exc:
            raise DatabaseSafetyError("database port is invalid") from exc
        database = unquote(parsed.path.lstrip("/"))
        user = unquote(parsed.username or "")
        if host not in ALLOWED_DATABASE_HOSTS:
            raise DatabaseSafetyError("only a loopback database host is allowed")
        if database != EXPECTED_DATABASE or user != EXPECTED_USER:
            raise DatabaseSafetyError("database name and user must match the isolated companion identity")
        if parsed.password is None or not parsed.password:
            raise DatabaseSafetyError("the isolated database password is missing")
        if not 1 <= port <= 65535:
            raise DatabaseSafetyError("database port is invalid")
        return cls(dsn.strip(), host, port, database, user)


@dataclass(frozen=True)
class IndexReport:
    run_id: str
    corpus_version: str
    profile_key: str
    source_count: int
    chunk_count: int
    inserted: int
    updated: int
    removed: int
    source_changed: bool

    def to_mapping(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SearchResult:
    chunk_id: str
    source_relative_path: str
    source_sha256: str
    chunk_sha256: str
    sanitized_text: str
    heading_hierarchy: tuple[str, ...]
    normalized_start: int
    normalized_end: int
    processing_version: str
    sanitization_status: str
    authorization_reference: str
    intended_use: str
    model_id: str
    model_revision: str
    corpus_version: str
    cosine_distance: float
    cosine_similarity: float

    def to_mapping(self) -> dict[str, Any]:
        result = asdict(self)
        result["heading_hierarchy"] = list(self.heading_hierarchy)
        return result


def _imports() -> tuple[Any, Any, Any]:
    try:
        import psycopg
        from pgvector.psycopg import register_vector
        from psycopg.rows import dict_row
    except ImportError as exc:  # pragma: no cover - depends on optional environment
        raise RuntimeError("install the companion vector dependencies before database operations") from exc
    return psycopg, register_vector, dict_row


class EvidenceDatabase:
    """Small transactional store dedicated to sanitized synthetic vectors."""

    def __init__(self, settings: DatabaseSettings, *, migrations_dir: Path) -> None:
        self.settings = settings
        self.migrations_dir = Path(migrations_dir).resolve()

    def _connect(self, *, register: bool = True) -> Any:
        psycopg, register_vector, dict_row = _imports()
        connection = psycopg.connect(
            self.settings.dsn,
            autocommit=False,
            connect_timeout=5,
            row_factory=dict_row,
            options="-c statement_timeout=15000 -c lock_timeout=5000",
        )
        try:
            with connection.cursor() as cursor:
                cursor.execute("select current_database() as database, current_user as user")
                identity = cursor.fetchone()
            if identity != {"database": EXPECTED_DATABASE, "user": EXPECTED_USER}:
                raise DatabaseSafetyError("connected database identity is not the isolated companion database")
            if register:
                register_vector(connection)
            connection.commit()
            return connection
        except Exception:
            connection.close()
            raise

    def migrate(self) -> list[str]:
        if not self.migrations_dir.is_dir():
            raise DatabaseSafetyError("migration directory is missing")
        migration_paths = sorted(self.migrations_dir.glob("[0-9][0-9][0-9]_*.sql"))
        if not migration_paths:
            raise DatabaseSafetyError("no companion migrations were found")
        applied: list[str] = []
        with self._connect(register=False) as connection:
            for path in migration_paths:
                sql = path.read_text(encoding="utf-8")
                checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()
                with connection.transaction():
                    connection.execute("select pg_advisory_xact_lock(%s)", (801042004,))
                    migrations_exist = connection.execute(
                        "select to_regclass('evidence_assistant.schema_migrations') as relation"
                    ).fetchone()["relation"]
                    if migrations_exist is not None:
                        row = connection.execute(
                            "select sha256 from evidence_assistant.schema_migrations where version = %s",
                            (path.name,),
                        ).fetchone()
                        if row is not None and row["sha256"] != checksum:
                            raise DatabaseSafetyError("an applied migration checksum has changed")
                    connection.execute(sql, prepare=False)
                    connection.execute(
                        """
                        insert into evidence_assistant.schema_migrations (version, sha256)
                        values (%s, %s)
                        on conflict (version) do nothing
                        """,
                        (path.name, checksum),
                    )
                applied.append(path.name)
        return applied

    def index_batch(
        self,
        batch: ApprovedChunkBatch,
        vectors: Sequence[Sequence[float]],
        metadata: EmbeddingMetadata,
        *,
        run_id: str,
        corpus_version: str,
    ) -> IndexReport:
        if len(vectors) != len(batch.chunks):
            raise IndexingConflictError("vector count does not match the approved chunk count")
        if metadata.dimensions != 384:
            raise IndexingConflictError("database schema accepts only the pinned 384-dimensional model")
        if not _SHA256.fullmatch(corpus_version):
            raise IndexingConflictError("corpus version is invalid")
        profile_key = metadata.profile_key
        chunk_ids = [chunk.chunk_id for chunk in batch.chunks]
        if len(chunk_ids) != len(set(chunk_ids)):
            raise IndexingConflictError("duplicate chunks cannot be indexed")

        with self._connect() as connection:
            with connection.transaction():
                existing_rows = connection.execute(
                    """
                    select chunk_id, source_sha256
                    from evidence_assistant.chunk_embeddings
                    where profile_key = %s and source_relative_path = %s
                    """,
                    (profile_key, batch.source_relative_path),
                ).fetchall()
                existing = {row["chunk_id"]: row["source_sha256"] for row in existing_rows}
                source_changed = any(value != batch.source_sha256 for value in existing.values())
                inserted = sum(chunk_id not in existing for chunk_id in chunk_ids)
                updated = len(chunk_ids) - inserted

                connection.execute(
                    """
                    insert into evidence_assistant.index_runs (
                      run_id, corpus_version, profile_key, provider_id, model_id, model_revision,
                      embedding_dimension, distance_metric, status, source_count, chunk_count
                    ) values (%s, %s, %s, %s, %s, %s, %s, %s, 'completed', 1, %s)
                    """,
                    (
                        run_id,
                        corpus_version,
                        profile_key,
                        metadata.provider_id,
                        metadata.model_id,
                        metadata.model_revision,
                        metadata.dimensions,
                        metadata.distance_metric,
                        len(batch.chunks),
                    ),
                )

                rows = []
                for chunk, vector in zip(batch.chunks, vectors):
                    rows.append(
                        (
                            profile_key,
                            chunk.chunk_id,
                            chunk.source_relative_path,
                            chunk.source_sha256,
                            chunk.chunk_sha256,
                            chunk.content,
                            list(chunk.heading_path),
                            chunk.normalized_start,
                            chunk.normalized_end,
                            chunk.source_span_basis,
                            chunk.processing_version,
                            chunk.sanitization_status,
                            chunk.approval_reference,
                            batch.intended_use,
                            metadata.provider_id,
                            metadata.model_id,
                            metadata.model_revision,
                            metadata.dimensions,
                            metadata.distance_metric,
                            list(vector),
                            corpus_version,
                            run_id,
                        )
                    )
                with connection.cursor() as cursor:
                    cursor.executemany(
                        """
                    insert into evidence_assistant.chunk_embeddings (
                      profile_key, chunk_id, source_relative_path, source_sha256, chunk_sha256,
                      sanitized_text, heading_hierarchy, normalized_start, normalized_end,
                      source_span_basis, processing_version, sanitization_status,
                      authorization_reference, intended_use, provider_id, model_id, model_revision,
                      embedding_dimension, distance_metric, embedding, corpus_version,
                      last_index_run_id
                    ) values (
                      %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                      %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    on conflict (profile_key, chunk_id) do update set
                      source_relative_path = excluded.source_relative_path,
                      source_sha256 = excluded.source_sha256,
                      chunk_sha256 = excluded.chunk_sha256,
                      sanitized_text = excluded.sanitized_text,
                      heading_hierarchy = excluded.heading_hierarchy,
                      normalized_start = excluded.normalized_start,
                      normalized_end = excluded.normalized_end,
                      source_span_basis = excluded.source_span_basis,
                      processing_version = excluded.processing_version,
                      sanitization_status = excluded.sanitization_status,
                      authorization_reference = excluded.authorization_reference,
                      intended_use = excluded.intended_use,
                      provider_id = excluded.provider_id,
                      model_id = excluded.model_id,
                      model_revision = excluded.model_revision,
                      embedding_dimension = excluded.embedding_dimension,
                      distance_metric = excluded.distance_metric,
                      embedding = excluded.embedding,
                      corpus_version = excluded.corpus_version,
                      last_index_run_id = excluded.last_index_run_id,
                      indexed_at = now()
                        """,
                        rows,
                    )
                removed_rows = connection.execute(
                    """
                    delete from evidence_assistant.chunk_embeddings
                    where profile_key = %s
                      and source_relative_path = %s
                      and not (chunk_id = any(%s))
                    returning chunk_id
                    """,
                    (profile_key, batch.source_relative_path, chunk_ids),
                ).fetchall()
        return IndexReport(
            run_id,
            corpus_version,
            profile_key,
            1,
            len(batch.chunks),
            inserted,
            updated,
            len(removed_rows),
            source_changed,
        )

    def search(
        self,
        query_vector: Sequence[float],
        metadata: EmbeddingMetadata,
        *,
        top_k: int,
    ) -> list[SearchResult]:
        if not isinstance(top_k, int) or isinstance(top_k, bool) or not 1 <= top_k <= MAX_QUERY_RESULTS:
            raise ValueError(f"top_k must be from 1 through {MAX_QUERY_RESULTS}")
        if len(query_vector) != metadata.dimensions:
            raise IndexingConflictError("query vector dimension does not match the embedding profile")
        with self._connect() as connection:
            profiles = connection.execute(
                """
                select exists(select 1 from evidence_assistant.chunk_embeddings) as any_rows,
                       exists(
                         select 1 from evidence_assistant.chunk_embeddings where profile_key = %s
                       ) as compatible_rows
                """,
                (metadata.profile_key,),
            ).fetchone()
            if profiles["any_rows"] and not profiles["compatible_rows"]:
                raise IndexingConflictError("embedding model profile is not indexed; controlled re-embedding is required")
            rows = connection.execute(
                """
                select chunk_id, source_relative_path, source_sha256, chunk_sha256,
                       sanitized_text, heading_hierarchy, normalized_start, normalized_end,
                       processing_version, sanitization_status, authorization_reference,
                       intended_use, model_id, model_revision, corpus_version,
                       embedding <=> %s::vector as cosine_distance
                from evidence_assistant.chunk_embeddings
                where profile_key = %s
                order by cosine_distance asc, chunk_id asc
                limit %s
                """,
                (list(query_vector), metadata.profile_key, top_k),
            ).fetchall()
        return [
            SearchResult(
                row["chunk_id"],
                row["source_relative_path"],
                row["source_sha256"],
                row["chunk_sha256"],
                row["sanitized_text"],
                tuple(row["heading_hierarchy"]),
                row["normalized_start"],
                row["normalized_end"],
                row["processing_version"],
                row["sanitization_status"],
                row["authorization_reference"],
                row["intended_use"],
                row["model_id"],
                row["model_revision"],
                row["corpus_version"],
                float(row["cosine_distance"]),
                1.0 - float(row["cosine_distance"]),
            )
            for row in rows
        ]

    def status(self, metadata: EmbeddingMetadata | None = None) -> dict[str, Any]:
        with self._connect() as connection:
            extension = connection.execute(
                "select extversion from pg_extension where extname = 'vector'"
            ).fetchone()
            condition = "where profile_key = %s" if metadata is not None else ""
            parameters: tuple[Any, ...] = (metadata.profile_key,) if metadata is not None else ()
            totals = connection.execute(
                f"""
                select count(*)::integer as chunk_count,
                       count(distinct source_relative_path)::integer as source_count,
                       count(distinct profile_key)::integer as profile_count
                from evidence_assistant.chunk_embeddings
                {condition}
                """,
                parameters,
            ).fetchone()
            migrations = connection.execute(
                "select version, sha256, applied_at from evidence_assistant.schema_migrations order by version"
            ).fetchall()
        return {
            "database": EXPECTED_DATABASE,
            "pgvector_version": extension["extversion"] if extension else None,
            **totals,
            "migrations": [dict(row) for row in migrations],
            "search_strategy": "exact_cosine_sequential_scan",
        }

    def execute_rollback_probe(self) -> bool:
        """Integration-test helper proving a failing transaction leaves no run behind."""

        marker = "rollback-probe"
        try:
            with self._connect() as connection:
                with connection.transaction():
                    connection.execute(
                        """
                        insert into evidence_assistant.index_runs (
                          run_id, corpus_version, profile_key, provider_id, model_id, model_revision,
                          embedding_dimension, distance_metric, status, source_count, chunk_count
                        ) values (%s, %s, %s, 'probe', 'probe', 'probe', 384, 'cosine', 'completed', 1, 1)
                        """,
                        (marker, "0" * 64, "0" * 64),
                    )
                    raise RuntimeError("intentional rollback")
        except RuntimeError:
            pass
        with self._connect() as connection:
            row = connection.execute(
                "select count(*)::integer as count from evidence_assistant.index_runs where run_id = %s",
                (marker,),
            ).fetchone()
        return row["count"] == 0
