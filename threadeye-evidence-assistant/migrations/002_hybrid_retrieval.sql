do $$
begin
  if current_database() <> 'threadeye_evidence' then
    raise exception 'refusing migration outside the isolated threadeye_evidence database';
  end if;
end
$$;

alter table evidence_assistant.chunk_embeddings
  add column if not exists retrieval_corpus_id text not null default 'unassigned',
  add column if not exists retrieval_access_policy text not null default 'deny',
  add column if not exists retrieval_authorized boolean not null default false,
  add column if not exists document_classification text not null default 'unclassified',
  add column if not exists search_vector tsvector
    generated always as (to_tsvector('english'::regconfig, coalesce(sanitized_text, ''))) stored;

do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conname = 'chunk_embeddings_retrieval_policy_check'
      and conrelid = 'evidence_assistant.chunk_embeddings'::regclass
  ) then
    alter table evidence_assistant.chunk_embeddings
      add constraint chunk_embeddings_retrieval_policy_check check (
        not retrieval_authorized
        or (
          retrieval_corpus_id <> 'unassigned'
          and retrieval_access_policy <> 'deny'
          and document_classification <> 'unclassified'
        )
      );
  end if;
end
$$;

create index if not exists chunk_embeddings_search_vector_idx
  on evidence_assistant.chunk_embeddings using gin (search_vector);

create index if not exists chunk_embeddings_retrieval_scope_idx
  on evidence_assistant.chunk_embeddings (
    retrieval_corpus_id,
    retrieval_access_policy,
    retrieval_authorized,
    profile_key
  );

comment on column evidence_assistant.chunk_embeddings.retrieval_authorized is
  'Separate serving authorization; ingestion approval alone never enables retrieval.';

comment on column evidence_assistant.chunk_embeddings.search_vector is
  'Stored English tsvector derived only from sanitized chunk text.';
