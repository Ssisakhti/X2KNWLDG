# API contract v1

The frozen HTTP contract of the Knowledge Canvas local web layer, delivered by `T-005`.
It fixes the provisional endpoint list of canvas plan §15 and is the seam that lets
Track B (the API) and Track C (the frontend) proceed concurrently: Track C compiles
against [`types.d.ts`](types.d.ts) and never waits on a running server.

| File | What it is |
|---|---|
| [`openapi.json`](openapi.json) | The contract. OpenAPI 3.1, `$ref`-ing `schemas/v1/` rather than restating it |
| [`types.d.ts`](types.d.ts) | Generated TypeScript declarations. **Committed, never edited by hand** |

```bash
python tools/generate_api_types.py            # regenerate types.d.ts
python tools/generate_api_types.py --check    # exit 1 if it is stale
```

## The one idea

**The API defines no shape of its own.** Every response body is a record the adapters in
[`src/x2knwldg/adapters/`](../../../src/x2knwldg/adapters/README.md) already produce —
`Source`, `Artifact`, `EntityRef`, `IndexedRelation` — wrapped in a versioned envelope.
`adapt_project(root).by_model()` *is* what an endpoint returns a page of. A second
vocabulary between the index and the browser would be a third place for the same fact to
drift, and there are already two identifier forms to keep honest (risk R12).

The two exceptions are deliberate, and both are grounded in code that already exists:

- **`/api/search`** returns the two result shapes `query.search_knowledge` already
  returns, discriminated by `type` (D-028). They are the de-facto contract that the CLI
  and the MCP tools ship today; FTS5 (`T-103`) replaces the linear scan behind them
  without changing them.
- **`/api/status`** describes the index rather than a source, so it has no record to
  reuse. Everything in it is a copied status or a count of one.

## The rules a server may not break

1. **Status is copied, never computed.** Every status in a response is the `Source.status`
   block verbatim, `UNKNOWN` included. `?status=UNKNOWN` is selectable so a run with a
   missing validator file can be found rather than quietly disappearing from the Library.
2. **A missing artifact is reported, never masked.** `available: false` on the record, and
   `404 unavailable` from `/api/media`. No placeholder bytes, ever.
3. **An id is resolved, never sanitised.** Every path parameter naming a run goes through
   `pipeline.resolve_run_dir` (D-020, risk R14). `T-108` must use that resolver and not
   invent a second rule.
4. **v1 is read-only.** Eleven endpoints, all `GET`. Nothing writes to `output/`, and
   nothing at all writes to `output/<id>/raw/`.

`tests/test_api_contract.py` asserts each of these against the document, and asserts the
payloads against records produced by the **real** adapters over the committed fixture
runs — including the `PARTIAL` and `FAIL` ones — not against hand-written examples.

It also validates the document against the **OpenAPI 3.1 meta-schema** itself, with
`base_uri` set so the `../../v1/` references resolve from the filesystem the way a real
generator resolves them. That guard exists because it caught something the structural
tests could not: the document originally carried a root `$id`, which is not a legal
OpenAPI field. Every hand-written test passed and the file still was not OpenAPI.

## Error taxonomy (D-030)

| Situation | Status | Code |
|---|---|---|
| Id rejected by `ids.py` / `resolve_run_dir` | `400` | `invalid_id` |
| Bad parameter, or a cursor the server cannot read | `400` | `invalid_request` |
| Well-formed id, nothing behind it | `404` | `not_found` |
| Record exists, the file it names does not | `404` | `unavailable` |
| Index absent, building, or in error | `503` | `index_unavailable` |
| Anything else | `500` | `internal` |

The `400`/`404` split is the point: a malformed id is a client error reported *before*
anything is read, and is never dressed up as absence.

## Pagination

`?limit=&cursor=`, answered with `page: { limit, next_cursor, total? }`.

The cursor is **opaque**. Its encoding belongs to the index (`T-007`), and a client that
parses one has coupled itself to a private detail. `next_cursor: null` ends a collection.
`total` may be `null`, which means *not counted* — never *zero*.

## Versioning

The same rule as the index model (D-015): **the version is the directory.** A breaking
change becomes `schemas/api/v2/` and adds a `/api/v2/` path prefix, leaving these paths
answering v1. Until then every response carries `api_version: "v1"` and
`schema_version: "1.0"` — the latter naming which `schemas/v1/` model the records inside
conform to.

Additive, optional fields are edited in place.

## What is deliberately not frozen (D-027)

The board endpoints of canvas plan §15 — `GET/POST /api/boards`, `GET/PUT
/api/boards/{board_id}`. Boards are Phase 3 and have no record schema yet; freezing a
contract for a shape that does not exist would be inventing one. `T-301` adds a `Board`
schema and this document grows the endpoints then, additively.

Also not here: `caption`, `segment`, and `coverage_window` entities, reserved in the
`EntityRef` vocabulary and unemitted in v1 (D-023). Caption *text* is still searchable —
it reaches the client as a `transcript_caption` search hit and through `/api/media` on the
transcript artifact — it simply has no global id to be addressed by.

## TypeScript

`types.d.ts` is generated by [`tools/generate_api_types.py`](../../../tools/generate_api_types.py),
which is stdlib-only. `T-005` ran before `T-008`, when there was no `web/`, no
`package.json`, and no Node job in CI: putting the contract behind an npm toolchain would
have made the frontend's types depend on a dependency the core package does not have
(ADR 0001 invariant 5), and handed `T-008` a scaffold it did not choose (D-029). That
reasoning still holds — the generator remains stdlib-only now that Node *is* in CI, and
`tsc` is a checker of the committed file rather than its producer.

The generator refuses any construct it does not understand rather than emitting `unknown`,
because a declaration that has quietly stopped describing the contract still compiles.
`tests/test_api_types.py` regenerates the file in memory and fails if the committed copy
differs — the same drift guard the run fixtures use.

What it produces:

- every shared primitive, record, and envelope as an exported type;
- `Locator` as a **discriminated union** tagged by `type`, so the Reader narrows a locator
  without a cast;
- `Endpoints`, mapping each `operationId` to its path, params, query, and response body,
  so a typed fetch wrapper cannot call a path the contract does not define.

The conditional `allOf` constraints on `EntityRef`, `Artifact`, and `IndexedRelation` —
"a derived unit must carry `derived_from` and a `derivation_note`", "a user relation may
not carry a confidence" — are runtime invariants that TypeScript cannot express. They are
emitted as documentation on the type rather than dropped, and remain enforced by the
schemas and by `adapters/base.py`.

The declarations are checked against `tsc --strict`; the frontend imports them directly,
with no build step, through [`web/src/api/contract.ts`](../../../web/README.md) — the one
place in `web/` that names this file.

**R17 is closed.** `T-008` added the `web-typecheck` job to
[`.github/workflows/ci.yml`](../../../.github/workflows/ci.yml), which runs `tsc --noEmit`
over `web/` on every push and pull request. `web/tsconfig.json` lists `types.d.ts` as a root
file and keeps `skipLibCheck: false`, because TypeScript's default is to skip `.d.ts` files —
with the default, the job would skip the only file it exists to check and pass without
looking (D-038). So there are now two independent guards: `tests/test_api_types.py` proves
the committed file matches the generator, and CI proves it compiles.

Regenerating? Run both:

```bash
python tools/generate_api_types.py
(cd web && npm run typecheck)
```

## Consumers

- `T-105`–`T-108` — the FastAPI server. This document is the specification, not a suggestion.
  `T-106` in particular should lift `_as_api_hit` out of `tests/test_api_contract.py` into
  the server rather than writing a second implementation of D-028's additive fields (R18).
- `T-109`–`T-114` — the frontend, compiling against `types.d.ts` while the server is built.
- `T-115` — contract tests against the frozen schema; `tests/test_api_contract.py` is their
  starting point.
- `T-007` — ✅ delivered: [`src/x2knwldg/repository/`](../../../src/x2knwldg/repository/README.md)
  is the interface behind the API. Ten methods serve these eleven endpoints, returning pages of
  the same v1 records; the cursor encoding is its business alone, and the API passes the token
  through unparsed. `MemoryRepository` already answers the whole document from the adapters, and
  §5 of `tests/test_api_contract.py` validates what it returns against these components.
