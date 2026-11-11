#!/usr/bin/env bash
set -euo pipefail

psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  --set=app_user="$EVIDENCE_DB_USER" \
  --set=app_password="$EVIDENCE_DB_PASSWORD" \
  --set=db_name="$POSTGRES_DB" <<'SQL'
create extension if not exists vector;
revoke all on database :"db_name" from public;
revoke create on schema public from public;
create role :"app_user"
  login
  password :'app_password'
  nosuperuser
  nocreatedb
  nocreaterole
  noinherit;
grant connect, create on database :"db_name" to :"app_user";
grant usage on schema public to :"app_user";
SQL
