do $$
begin
  if current_database() <> 'threadeye_evidence' then
    raise exception 'refusing migration outside the isolated threadeye_evidence database';
  end if;
  if not exists (select 1 from pg_extension where extname = 'vector') then
    raise exception 'pgvector must be installed by the isolated companion bootstrap';
  end if;
end
$$;

create schema if not exists evidence_assistant;

create table if not exists evidence_assistant.schema_migrations (
  version text primary key,
  sha256 text not null check (sha256 ~ '^[0-9a-f]{64}$'),
  applied_at timestamptz not null default now()
);

create table if not exists evidence_assistant.index_runs (
  run_id text primary key,
  corpus_version text not null check (corpus_version ~ '^[0-9a-f]{64}$'),
  profile_key text not null check (profile_key ~ '^[0-9a-f]{64}$'),
  provider_id text not null,
  model_id text not null,
  model_revision text not null,
  embedding_dimension integer not null check (embedding_dimension = 384),
  distance_metric text not null check (distance_metric = 'cosine'),
  status text not null check (status in ('completed')),
  source_count integer not null check (source_count > 0),
  chunk_count integer not null check (chunk_count > 0),
  indexed_at timestamptz not null default now()
);

create table if not exists evidence_assistant.chunk_embeddings (
  profile_key text not null check (profile_key ~ '^[0-9a-f]{64}$'),
  chunk_id text not null check (chunk_id ~ '^[0-9a-f]{24}$'),
  source_relative_path text not null,
  source_sha256 text not null check (source_sha256 ~ '^[0-9a-f]{64}$'),
  chunk_sha256 text not null check (chunk_sha256 ~ '^[0-9a-f]{64}$'),
  sanitized_text text not null check (length(btrim(sanitized_text)) > 0),
  heading_hierarchy text[] not null,
  normalized_start integer not null check (normalized_start >= 0),
  normalized_end integer not null check (normalized_end > normalized_start),
  source_span_basis text not null,
  processing_version text not null,
  sanitization_status text not null check (sanitization_status in ('clean', 'redacted')),
  authorization_reference text not null,
  intended_use text not null,
  provider_id text not null,
  model_id text not null,
  model_revision text not null,
  embedding_dimension integer not null check (embedding_dimension = 384),
  distance_metric text not null check (distance_metric = 'cosine'),
  embedding vector(384) not null,
  corpus_version text not null check (corpus_version ~ '^[0-9a-f]{64}$'),
  last_index_run_id text not null references evidence_assistant.index_runs(run_id),
  indexed_at timestamptz not null default now(),
  primary key (profile_key, chunk_id),
  check (normalized_end - normalized_start = length(sanitized_text))
);

create index if not exists chunk_embeddings_source_idx
  on evidence_assistant.chunk_embeddings (profile_key, source_relative_path);

create index if not exists index_runs_profile_time_idx
  on evidence_assistant.index_runs (profile_key, indexed_at desc);

comment on table evidence_assistant.chunk_embeddings is
  'Synthetic, approval-gated, sanitized evidence chunks only; exact cosine search is used for the small Prompt 04 corpus.';
