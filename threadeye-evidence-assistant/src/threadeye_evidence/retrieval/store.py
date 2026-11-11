"""Parameterized PostgreSQL keyword and filtered vector retrieval."""

from __future__ import annotations

from typing import Any, Sequence

from threadeye_evidence.retrieval.models import EvidenceCandidate, RetrievalFilters, validate_limit, validate_query
from threadeye_evidence.vector.database import EvidenceDatabase, IndexingConflictError
from threadeye_evidence.vector.embeddings import EmbeddingMetadata


class RetrievalStore:
    def __init__(self, database: EvidenceDatabase) -> None:
        self.database = database

    @staticmethod
    def _scope(filters: RetrievalFilters, profile_key: str) -> tuple[str, list[Any]]:
        clauses = [
            "retrieval_authorized = true",
            "retrieval_corpus_id = %s",
            "retrieval_access_policy = %s",
            "authorization_reference = %s",
            "profile_key = %s",
        ]
        parameters: list[Any] = [
            filters.corpus_id,
            filters.access_policy,
            filters.authorization_reference,
            profile_key,
        ]
        optional_columns = (
            ("source_relative_path", filters.source_relative_path),
            ("source_sha256", filters.source_sha256),
            ("corpus_version", filters.corpus_version),
            ("processing_version", filters.processing_version),
            ("document_classification", filters.document_classification),
        )
        for column, value in optional_columns:
            if value is not None:
                clauses.append(f"{column} = %s")
                parameters.append(value)
        return " and ".join(clauses), parameters

    @staticmethod
    def _candidate(row: dict[str, Any]) -> EvidenceCandidate:
        return EvidenceCandidate(
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
            row["profile_key"],
            row["corpus_version"],
            row["retrieval_corpus_id"],
            row["retrieval_access_policy"],
            row["document_classification"],
            float(row["keyword_score"]) if row.get("keyword_score") is not None else None,
            float(row["cosine_distance"]) if row.get("cosine_distance") is not None else None,
            float(row["cosine_similarity"]) if row.get("cosine_similarity") is not None else None,
        )

    @staticmethod
    def _select_columns() -> str:
        return """
          chunk_id, source_relative_path, source_sha256, chunk_sha256, sanitized_text,
          heading_hierarchy, normalized_start, normalized_end, processing_version,
          sanitization_status, authorization_reference, intended_use, model_id,
          model_revision, profile_key, corpus_version, retrieval_corpus_id,
          retrieval_access_policy, document_classification
        """

    def keyword_search(
        self,
        query: str,
        metadata: EmbeddingMetadata,
        filters: RetrievalFilters,
        *,
        top_k: int,
    ) -> list[EvidenceCandidate]:
        value = validate_query(query)
        validate_limit(top_k)
        scope, parameters = self._scope(filters, metadata.profile_key)
        sql = f"""
            with search_query as (
              select websearch_to_tsquery('english'::regconfig, %s) as query
            )
            select {self._select_columns()},
                   ts_rank_cd(search_vector, search_query.query, 32) as keyword_score
            from evidence_assistant.chunk_embeddings
            cross join search_query
            where {scope}
              and search_vector @@ search_query.query
            order by keyword_score desc, chunk_id asc
            limit %s
        """
        with self.database._connect() as connection:
            rows = connection.execute(sql, (value, *parameters, top_k)).fetchall()
        return [self._candidate(row) for row in rows]

    def vector_search(
        self,
        query_vector: Sequence[float],
        metadata: EmbeddingMetadata,
        filters: RetrievalFilters,
        *,
        top_k: int,
    ) -> list[EvidenceCandidate]:
        validate_limit(top_k)
        if len(query_vector) != metadata.dimensions:
            raise IndexingConflictError("query vector dimension does not match the embedding profile")
        scope, parameters = self._scope(filters, metadata.profile_key)
        sql = f"""
            select {self._select_columns()},
                   embedding <=> %s::vector as cosine_distance,
                   1.0 - (embedding <=> %s::vector) as cosine_similarity
            from evidence_assistant.chunk_embeddings
            where {scope}
            order by cosine_distance asc, chunk_id asc
            limit %s
        """
        with self.database._connect() as connection:
            scoped = connection.execute(
                """
                select
                  exists(
                    select 1 from evidence_assistant.chunk_embeddings
                    where retrieval_authorized = true
                      and retrieval_corpus_id = %s
                      and retrieval_access_policy = %s
                      and authorization_reference = %s
                  ) as any_authorized,
                  exists(
                    select 1 from evidence_assistant.chunk_embeddings
                    where retrieval_authorized = true
                      and retrieval_corpus_id = %s
                      and retrieval_access_policy = %s
                      and authorization_reference = %s
                      and profile_key = %s
                  ) as compatible
                """,
                (
                    filters.corpus_id,
                    filters.access_policy,
                    filters.authorization_reference,
                    filters.corpus_id,
                    filters.access_policy,
                    filters.authorization_reference,
                    metadata.profile_key,
                ),
            ).fetchone()
            if scoped["any_authorized"] and not scoped["compatible"]:
                raise IndexingConflictError(
                    "authorized corpus uses an incompatible embedding profile; controlled re-embedding is required"
                )
            rows = connection.execute(
                sql,
                (list(query_vector), list(query_vector), *parameters, top_k),
            ).fetchall()
        return [self._candidate(row) for row in rows]

    def keyword_plan(
        self,
        query: str,
        metadata: EmbeddingMetadata,
        filters: RetrievalFilters,
        *,
        top_k: int = 5,
    ) -> dict[str, Any]:
        value = validate_query(query)
        validate_limit(top_k)
        scope, parameters = self._scope(filters, metadata.profile_key)
        sql = f"""
            explain (analyze, buffers, format json)
            with search_query as (
              select websearch_to_tsquery('english'::regconfig, %s) as query
            )
            select chunk_id,
                   ts_rank_cd(search_vector, search_query.query, 32) as keyword_score
            from evidence_assistant.chunk_embeddings
            cross join search_query
            where {scope}
              and search_vector @@ search_query.query
            order by keyword_score desc, chunk_id asc
            limit %s
        """
        with self.database._connect() as connection:
            row = connection.execute(sql, (value, *parameters, top_k)).fetchone()
        return row["QUERY PLAN"][0]

    def environment_info(self) -> dict[str, str]:
        with self.database._connect() as connection:
            row = connection.execute(
                """
                select current_setting('server_version') as postgresql_version,
                       (select extversion from pg_extension where extname = 'vector') as pgvector_version
                """
            ).fetchone()
        return dict(row)

    def authorization_scope_count(self, filters: RetrievalFilters, metadata: EmbeddingMetadata) -> int:
        """Return only a count; never reveal metadata for a denied or empty scope."""

        scope, parameters = self._scope(filters, metadata.profile_key)
        with self.database._connect() as connection:
            row = connection.execute(
                f"select count(*)::integer as count from evidence_assistant.chunk_embeddings where {scope}",
                parameters,
            ).fetchone()
        return int(row["count"])
