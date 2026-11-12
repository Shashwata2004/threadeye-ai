#!/usr/bin/env bash
set -euo pipefail

psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  --set=app_user="$EVIDENCE_DB_USER" \
  --set=app_password="$EVIDENCE_DB_PASSWORD" \
  --set=mcp_user="$EVIDENCE_MCP_DB_USER" \
  --set=mcp_password="$EVIDENCE_MCP_DB_PASSWORD" \
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
create role :"mcp_user"
  login
  password :'mcp_password'
  nosuperuser
  nocreatedb
  nocreaterole
  noinherit;
alter role :"mcp_user" set default_transaction_read_only = on;
grant connect on database :"db_name" to :"mcp_user";
SQL
