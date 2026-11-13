# Authenticated Streamable HTTP MCP

## Verified boundary

Prompt 09 adds an explicit authenticated localhost transport to the existing server. It reuses the same service,
four-tool registry, three resources, retrieval engine, extractive answer engine, citation validation, abstention,
trusted synthetic scope and `threadeye_evidence_mcp` database role. The stdio entry point remains independent and
unchanged in how it is launched.

The implementation uses Python 3.11.17, official `mcp==2.3.0`/`mcp-types==2.3.0`, SDK `MCPServer`, SDK `Client`,
SDK Streamable HTTP transport, PyJWT 2.15.1 and cryptography 50.0.2. The genuine clients negotiated MCP protocol
`2025-11-25`; the newer 2026-07-28 session behavior is not claimed or mixed into this pinned protocol.

```text
Official authenticated MCP client
  -> http://127.0.0.1:8765/mcp
  -> exact Host/Origin/body/header admission
  -> SDK Bearer authentication and exact resource audience
  -> request-local principal and least-privilege scope check
  -> fixed read-only MCP registry
  -> existing trusted synthetic authorization context
  -> existing retrieval/answer/citation/abstention pipeline
  -> dedicated SELECT-only PostgreSQL identity
```

The server binds only to `127.0.0.1`; configuration rejects `0.0.0.0`, a mismatched resource URL or any path other
than `/mcp`. It is not started by the stdio launcher and is not deployed publicly.

## Explicit launch

The HTTP launcher requires all Prompt 08 runtime values plus a trusted HTTP configuration and an operator-owned
Ed25519 public key:

```bash
export THREADEYE_EVIDENCE_MCP_CONFIG="$PWD/config/mcp-synthetic.json"
export THREADEYE_EVIDENCE_MCP_DATABASE_URL="postgresql://threadeye_evidence_mcp:REPLACE@127.0.0.1:55432/threadeye_evidence"
export THREADEYE_EVIDENCE_MODEL_CACHE="$PWD/build/model-cache"
export THREADEYE_EVIDENCE_HTTP_CONFIG="$PWD/config/mcp-http.json"
export THREADEYE_EVIDENCE_HTTP_PUBLIC_KEY="/absolute/operator-owned/path/ed25519-public-key.pem"
PYTHONPATH=src .venv/bin/python -m threadeye_evidence.mcp.http_server
```

The checked-in configuration contains no key or secret. The key path is passed through the environment, must resolve
to a bounded regular file owned by the current user, and cannot be a symlink or group/world-writable. The server does
not accept private keys and never issues tokens.

## Authentication model

`EdDSAAccessTokenVerifier` implements the official SDK `TokenVerifier` interface. It accepts only short-lived JWT
access tokens that satisfy every condition below:

- EdDSA signature under the one trusted Ed25519 public key;
- exact `kid` and `typ: at+jwt` header values;
- trusted HTTPS issuer;
- exact audience/resource `http://127.0.0.1:<configured-port>/mcp`;
- required `exp`, `iat`, `sub`, `client_id`, `scope`, `jti` and `token_use` claims;
- valid expiration and optional `nbf`, with no clock leeway;
- `token_use: access`, matching non-empty subject/client identity and maximum five-minute lifetime;
- an operator-allowlisted synthetic principal; and
- scopes that are both supported and allowed for that principal.

Missing, empty, malformed, expired, future-`nbf`, unsigned, wrong-signature, unknown-key, algorithm-confused,
wrong-issuer, wrong-audience, wrong-token-type, over-scoped, unknown-principal and oversized tokens fail closed. Normal
bearer reuse during a token's short lifetime is supported. There is no token revocation or denylist in Prompt 09.

The integration verifier creates an ephemeral Ed25519 keypair and short-lived synthetic tokens in a temporary
directory. Its private key exists only in the verifier process and is never passed to the server, exposed as an HTTP
token endpoint or committed.

## OAuth resource-server compliance

The unauthenticated RFC 9728 Protected Resource Metadata URL is:

`http://127.0.0.1:8765/.well-known/oauth-protected-resource/mcp`

It publishes the exact resource, configured authorization-server identifier, header bearer method and supported
scopes. Missing/invalid credentials receive HTTP 401 and an RFC 6750 `WWW-Authenticate` challenge containing the
`resource_metadata` URL. The SDK independently verifies that the returned `AccessToken.resource` matches the configured
resource server URL.

This demonstrates a standards-oriented local OAuth resource server. It does **not** demonstrate an authorization
server, discovery at the configured fictional issuer, interactive login, dynamic client registration, refresh tokens,
revocation, external OAuth onboarding or public interoperability. The offline issuer is a test fixture, not a service.

## Scopes and authorization

Authentication does not replace the fixed synthetic corpus policy. The token establishes a principal and limited
permissions; the Prompt 08 trusted context still fixes corpus, policy, authorization reference, source, classification
and embedding profile. No tool argument can change them.

| Scope | Permitted operations |
|---|---|
| `evidence:metadata:read` | `list_evidence_sources`, `get_evidence_capabilities`, and all three sanitized resource reads |
| `evidence:search` | `search_evidence` |
| `evidence:answer` | `answer_evidence_question` |

The full synthetic client receives all three scopes. The independent metadata client receives only
`evidence:metadata:read`; it can discover the unchanged registry and read sanitized policy metadata, but search and
answer calls return a generic authorization error without evidence. Authorization uses the SDK request-local auth
context—not a mutable global principal—and is reconstructed for every stateless request.

## Transport, Host, Origin and CORS

The HTTP app uses SDK-native Streamable HTTP with JSON POST responses and `stateless_http=True`. Every protected HTTP
request is authenticated. There is no protocol session state or `Mcp-Session-Id` ownership to carry between clients;
two independent official clients were verified without identity/scope inheritance.

The outer admission middleware and SDK transport both validate the exact loopback Host and allowed local Origin.
Missing/wrong/duplicated Host data, unexpected Origin, DNS-rebinding hosts, duplicate Authorization, oversized
Authorization, duplicate/oversized Content-Length and disallowed methods fail before evidence work. No unrestricted
CORS middleware is installed and neither MCP nor metadata responses advertise `Access-Control-Allow-Origin: *`.
`X-Forwarded-For` is ignored because no trusted proxy is configured.

## Limits and cancellation

- Per-principal fixed-window limit: 60 HTTP requests per 60 seconds.
- Per-client-IP fixed-window limit: 120 HTTP requests per 60 seconds.
- Rate state: in-memory, bounded to 1,024 active keys with expired/oldest cleanup.
- HTTP concurrency: four; excess requests receive HTTP 429 immediately.
- HTTP body: 65,536 bytes.
- Token text: 8,192 characters.
- Query/question: 1,000 characters; top-k: 5; result: 65,536 bytes.
- Tool/resource deadline: 10 seconds; database statement: 8 seconds; lock: 2 seconds; connect: 5 seconds.

Limits are local-process controls, not distributed rate limiting. The source socket IP is used directly. Unit tests
use a deterministic clock to prove exhaustion, bounded cleanup and recovery; the real HTTP verifier also observes 429
then recovery after the configured test window.

Prompt 08 abandoned worker threads could release their async limiter slot before underlying work finished. Prompt 09
uses a bounded worker semaphore released by the worker itself: after a timeout, new work fails fast until that worker
actually exits. Database work remains bounded by the shorter statement timeout. A permanently stuck non-database
native inference call can still occupy one of the four slots indefinitely, causing safe unavailability rather than
unbounded accumulation. HTTP cancellation always releases HTTP concurrency capacity.

## Security audit events

Local HTTP security events are JSON lines on stderr under `threadeye_evidence.http.audit`, separate from ThreadEye's
original audit chain. They include a server-created correlation ID, timestamp, non-reversible truncated principal/IP
digest, transport, safe operation category, authorization/rate decision, HTTP or MCP category and duration where
applicable.

They never include raw bearer tokens, keys, database passwords, Authorization headers, queries, evidence excerpts or
unredacted exceptions. The verifier confirms those values are absent. These local logs are not signed, chained,
persisted by default or claimed to be tamper-proof.

## Reproduction

The genuine verifier starts the real localhost server twice, uses two official SDK clients and removes its ephemeral
key material on exit:

```bash
PYTHONPATH=src .venv/bin/python -m threadeye_evidence.mcp.verify_http

THREADEYE_RUN_MODEL_TESTS=1 \
THREADEYE_RUN_DB_TESTS=1 \
THREADEYE_RUN_MCP_TESTS=1 \
THREADEYE_RUN_HTTP_TESTS=1 \
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
```

The real demonstration covers initialization, exact discovery, metadata resource read, hybrid search with provenance,
extractive answer with validated citation, abstention, Client B scope denial, scope non-inheritance, malformed tokens,
metadata challenge, Host/Origin/DNS rebinding, CORS, method/content/JSON/body/protocol failures, invalid resource,
unknown tool, extra scope arguments, production-access request, rate exhaustion/recovery and clean shutdown/restart.
Fault injection continues to cover database, embedding, branch and citation failures through the shared server/service
path; neither transport contains a fallback or degraded success route.

The final combined run passed 162 tests with genuine BGE, PostgreSQL/pgvector, stdio and authenticated HTTP flags:
zero failures and zero skips. The unchanged retrieval dataset completed all 35 queries with hybrid Hit@1 `0.906`,
Hit@3/5 and Recall@5 `1.000`, MRR `0.948` and zero runtime failures. Both unchanged answer splits remained perfect
(20 development plus 24 held-out cases). The security dataset remained 30/30 development and the intentionally honest
29/30 final holdout, with zero measured injection successes, 7/7 correct failure cases per split and no runtime
failures. A sanitized machine-readable summary is stored in `docs/evidence/prompt09-http-verification.json`.

## Database guarantee and unsupported claims

Both launchers require `THREADEYE_EVIDENCE_MCP_DATABASE_URL`. Actual integration tests reconfirm SELECT-only access,
read-only transactions, non-superuser/non-creator/non-inheriting role flags and denials for INSERT, UPDATE, DELETE,
TRUNCATE, schema/temporary DDL, role creation and database creation.

Prompt 09 demonstrates authenticated local Streamable HTTP and genuine usage by two independently authenticated
official clients. It does not demonstrate public deployment, TLS, distributed controls, complete OAuth onboarding,
cross-project reuse, multiple custom MCP servers, a generative LLM, production data or security certification.

## Prompt 10 judge UI consumer

The local judge UI is a real Prompt 09 client, not an alternate retrieval route. Its server-side gateway uses the
official SDK `Client` and `streamable_http_client`, exact resource audience, short-lived EdDSA access token and all
three allowlisted scopes. Overview verifies the exact four-tool/three-resource registry, then calls
`get_evidence_capabilities`, `list_evidence_sources` and the sanitized security-policy resource. Search and answer call
only `search_evidence` and `answer_evidence_question`. The UI has no fallback to direct Python retrieval or database
access and does not silently downgrade transport.

The development launcher owns an ephemeral keypair and MCP subprocess. Only the temporary public key is passed to the
MCP server; the browser never sees either key, a bearer token, a database credential or MCP configuration. This is
still the offline local issuer model documented above, not production OAuth onboarding.
