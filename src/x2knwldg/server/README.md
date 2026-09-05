# `x2knwldg.server` — the local read-only HTTP API

Track B, `T-105`–`T-108`. Thirteen `GET` endpoints, frozen in
[`schemas/api/v1/openapi.json`](../../../schemas/api/v1/README.md), served over the
repository seam of [ADR 0002](../../../docs/adr/0002-index-repository-seam.md).

`serve.py` was added later, by `T-116` (the integrator), and is the one module here that
is not a route: it binds the socket, mounts the built frontend beneath the API, and runs
`uvicorn`. It lives in this package rather than in `cli.py` because D-055 confines every
import of the `ui` extra to `server/` — `cli.py` reaches it lazily, from inside its own
dispatch branch, so importing the CLI on a bare core install still pulls in no framework.

## What it is allowed to touch

`IndexRepository`, and nothing else. This layer never reads `output/`, never opens the
SQLite file, never imports the adapters, and never re-derives a record. If an endpoint
needs something the repository does not expose, that is a **contract change** —
`schemas/api/v1/openapi.json` first, ADR 0002 second — not a local decision.

The one exception is the byte channel, and it is a deliberate, bounded one: `routes/media.py`
opens a file, because serving bytes is what it is for. See *Path safety* below.

## Layout

| File | Owns |
|---|---|
| `envelope.py` | The frozen response envelope and the closed `ErrorCode` vocabulary. **Stdlib only** — it is testable on a bare core install, where `fastapi` is absent. |
| `errors.py` | Refusal → response. Registers the handlers on the app. |
| `deps.py` | Which repository a request is answered from. |
| `params.py` | The shared `limit`/`cursor` declarations and their bounds. |
| `app.py` | `create_app`. Holds the repository on `app.state`, installs handlers, includes routers. Owns no route. |
| `serve.py` | `T-116`: locating the built frontend, binding the socket, mounting `web/dist` beneath the API, and running `uvicorn`. The only module here that `cli.py` imports. |
| `routes/` | One module per endpoint group. Each was written independently against the frozen document. |

## Five rules that are not negotiable

1. **A route catches no `RepositoryError`.** `code` and `http_status` live on the exception
   (D-030), so the repository decides what kind of refusal it is and the API renders it. A
   route that catches and re-raises puts the taxonomy in thirteen places instead of one.
2. **Malformed is not absent.** A bad id is `400 invalid_id`; a well-formed id matching
   nothing is `404 not_found` (D-020). Collapsing them is what lets a lookup silently read
   something else. This is also why enum filters are plain strings here (D-058): a FastAPI
   `pattern` on an id parameter turns `invalid_id` into `invalid_request`.
3. **Records go out verbatim.** The repository already produces the frozen shapes —
   `IndexStatus.payload()`, `Page.page_info()`, `GraphPage.payload()`. Nothing is renamed,
   reordered, filtered or enriched on the way out.
4. **No host path reaches a body**, error bodies included (ADR 0003, D-051). The generic
   `internal` handler exists because a framework default would return the exception's own
   text, and that text is routinely a path.
5. **Read-only.** No write endpoint exists in any version for a `raw/` artifact (ADR 0001
   invariant 1), and v1 has no write endpoint at all.

## Path safety

Every id from a path parameter is **rejected** when malformed — never rewritten. Read
[ADR 0003](../../../docs/adr/0003-reject-unsafe-identifiers.md): `_safe_identifier`
normalises, which is right when *creating* a run and wrong when looking one up, because
`../other` must fail rather than quietly become `_other`.

`routes/media.py` is the only route that opens a file, and two independent checks stand
between the parameter and the read:

1. the repository refuses a malformed id before anything is opened, and
2. the record's `path` — project-relative *by schema* — is resolved and re-checked against
   the project root anyway. A path is trusted because it was verified, not because of where
   it came from; the index is a rebuildable cache, and a cache is not a trust boundary.

A slash-bearing id answers `404` rather than `400`, because a path parameter matches one
segment and no `globalId` contains a slash (D-056).

## Testing it

`tests/api_harness.py` is the shared scaffolding: `project()`, `memory_repository()`,
`sqlite_repository()`, `client()`, `both_clients()`, `assert_contract()`, `assert_error()`.

**Test against SQLite, not only against the oracle.** D-052 was a bug in which every request
over `SqliteRepository` answered `503` — in production under uvicorn, on all thirteen
endpoints — while every `MemoryRepository` test passed, because `sqlite3` binds a connection
to its creating thread and a web server answers from a thread pool. A suite that reaches for
the oracle by default was green against a server that could not serve one request.
`test_every_endpoint_answers_over_sqlite_not_only_over_memory` exists so that cannot recur.

**Beware of testing your HTTP client.** httpx resolves `..` and rejects control bytes before
a request leaves the process, so a traversal battery that sends them proves nothing about
this code. `tests/test_api_hardening.py` splits them three ways: ids that reach the wire, ids
checked at the repository boundary, and raw paths handed straight to the ASGI app.

## Serving

`x2knwldg ui` is wired end to end (`T-116`): it resolves the project root, refuses a
non-loopback host before it probes for the extra, refreshes the index — passing
`index_documents` so the search corpus is built and not merely the records (D-068) — binds the
socket *before* printing a URL (D-066), and reports an unbuilt `web/dist` as its own exit code
`6` rather than as success or as a breakage. `serve.py` owns the socket; `create_app` is
untouched, so the document served still equals the frozen one.

`GET /api/openapi.json` serves `openapi.json` from **beside this module**, not from
`schemas/api/v1/`: the file is package data, because a path relative to a repo checkout made the
route a permanent 404 in every installed package (D-084). `schemas/api/v1/openapi.json` remains
the authored contract, and a test fails if the two differ by a byte.
