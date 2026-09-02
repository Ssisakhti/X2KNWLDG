# X2KNWLDG Knowledge Canvas — Project Management

**Status:** active execution tracker
**Last updated:** 2026-09-01 · **Phase 0 complete**; **Phase 1 Tracks A and B complete** — the SQLite index serves the whole `IndexRepository` (`T-101`–`T-104`) and all **eleven** frozen endpoints are served over it (`T-105`–`T-108`). Tracks C and D may fan out
**Language:** English only — see the language rule in §2
**Architecture reference:** [`KNOWLEDGE_CANVAS_PLAN.md`](KNOWLEDGE_CANVAS_PLAN.md) — *that* document is the design authority
**Pipeline reference:** [`X2KNWLDG_build_spec.md`](X2KNWLDG_build_spec.md)

---

## 1. Purpose and how to use this file

`KNOWLEDGE_CANVAS_PLAN.md` says **what** to build and **why**. This file tracks **who does what, in what order, and what is safe to run in parallel**. It does not restate architecture — when the two disagree about design, the canvas plan wins; when they disagree about status, this file wins.

**Per-session ritual:**

1. Read `AGENTS.md`, then `WORKFLOW.md` (mandatory for any ingestion/extraction).
2. Read the canvas plan, then this file's §3 and §8.
3. `git status` — preserve any uncommitted user changes.
4. Claim **one** task ID from §5. Move it to `in progress`.
5. On finish: run the checks in §7, update the task row, append any new decision to §6.
6. If something is incomplete, record it as `PARTIAL` or `blocked` — never as done.

---

## 2. Scope guardrails (inherited, non-negotiable)

These come from `AGENTS.md`, `WORKFLOW.md`, and canvas plan §5. They apply to UI work too.

- `output/<id>/raw/` is **immutable evidence**. No UI interaction may write to it.
- The UI **reads** canonical files; it never redefines completion. `validation.json` and `coverage.json` are the only sources of run status.
- `PARTIAL` and `FAIL` must be displayed honestly and never coerced to `PASS`.
- Never invent a timestamp, quote, evidence excerpt, confidence, or coverage value.
- SQLite is a **rebuildable cache only**. Deleting it must lose nothing.
- User content (boards, notes, ink) stays separate from `source` and `derived` knowledge.
- Adding a new source type must not require a frontend rewrite — adapter + node renderer only.
- Never install or invoke Whisper/WhisperX.

**Language rule (D-014).** All project documentation is written in **English** — this file, the canvas plan, ADRs, `README.md`, `AGENTS.md`, `WORKFLOW.md`, `CLAUDE.md`, code comments, and commit messages. Persian is used in exactly two places: the **application UI** (switchable, English default — D-012) and **knowledge content extracted for the user** (knowledge units, reports, vault content, and answers delivered to the user, which follow the source material). Code that *supports* Persian content is expected and correct — for example `segmenter._ends_thought` uses the Arabic question mark for sentence-boundary detection.

---

## 3. Verified current state

Measured from disk on **2026-08-31**. Re-verify with the commands in §7.3.

| Item | Value |
|---|---|
| Ingested sources | 1 (`pqlWNihgdjI`) |
| Knowledge units | **69** (61 `source`, 8 `derived`) |
| Relationships | **56** |
| Per-video `graph.json` | 69 nodes, 56 edges |
| `coverage.json` status | **`PASS`** (5/5 windows covered, `audit_attempts: 1`) |
| `validation.json` status | **`PASS`** (all **6** sections: `transcript`, `evidence`, `knowledge_units`, `provenance`, `relationships`, `coverage`). `evidence` is the newest and is **additive** — it recomputes the SHA-256 of the preserved `raw/` original and compares it with what `metadata.json` and `transcript.json` each recorded, so tampering with evidence is now a `FAIL` that `finalize` refuses. No schema constrains this file and the adapter copies only its top-level `status`, so nothing downstream had to change |
| `output/library/` | 1 video, 69 knowledge nodes, **17 canonical concepts**, 118 edges — unchanged by the `T-003` rebuild, which only added fields. **Regenerated under D-043 on 2026-08-31** (`x2knwldg rebuild-library`, exit 0): the 17 `expresses_concept` edges now carry `confidence: null` rather than a fabricated `1.0`, `videos.json` entries carry `problems: []`, and `status.json` carries `runs_discovered: 1` / `runs_indexed: 1` / `runs_skipped: 0` / `skipped_runs: []` / `incomplete_runs: []`. `concepts.json` was byte-identical and the totals did not move; the 45 `derived_from` edges kept their real 0.88–0.97 confidences, since every unit here states one. ⚠️ `output/` is gitignored, so this is not in version control and a given clone's state cannot be read off the repository |
| Index projection (`T-004`) | The adapter maps the sample to **1 source, 85 artifacts, 86 entities, 118 relations** — 69 knowledge units + 17 concepts, and 56 canonical + 62 synthetic edges |
| API contract (`T-005`) | **11 endpoints, all `GET`**, frozen in [`schemas/api/v1/openapi.json`](../schemas/api/v1/README.md); **25** components (the 25th is `SkippedRun`, added additively by D-050), every response body a `$ref` into `schemas/v1/`. Valid against the OpenAPI 3.1 meta-schema, external `$ref`s resolving from disk. **956 lines** of generated, committed TypeScript in `types.d.ts`, checked against `tsc --strict`. **All eleven are now served** by `src/x2knwldg/server/` (Track B); `test_the_served_surface_is_exactly_the_frozen_one` compares the app's generated document against the frozen one, so the two cannot drift apart |
| Repository seam (`T-007`) | [`src/x2knwldg/repository/`](../src/x2knwldg/repository/README.md): `IndexRepository`, **10 methods** serving the 11 frozen endpoints, plus `MemoryRepository` over `adapt_project`. Stdlib-only. Fixed by [ADR 0002](adr/0002-index-repository-seam.md) |
| Scaffold (`T-008`) | [`web/`](../web/README.md) holds TypeScript only — `package.json`, `package-lock.json`, `tsconfig.json`, `src/api/contract.ts`. `npm run typecheck` (`tsc --noEmit`) passes and is a CI job. The `ui` extra is `fastapi` + `uvicorn`; `x2knwldg ui` exists as a refusing stub |
| Test baseline | **2141 passed, 0 failed, 0 skipped, 36 subtests** (2026-09-02, after `T-116`: +26 in `tests/test_ui_serving.py` and the rewritten wiring tests). Core package with no extras: **1475 passed, 462 skipped** — the API layer skips cleanly and no optional dependency crept in (re-verified on a throwaway venv holding only `x2knwldg` + `pytest`). Previously **2115 passed** after Tracks C and D; **2047** after Track B; **1647** after Track A and D-050; **1348** after the audit remediation on 2026-08-31; 1287 after the five-agent second wave, 765 before it, 515 before that. The bare-venv run is **not** a formality: it has failed before. See the note under §7.2 |
| SQLite index (Track A) | [`src/x2knwldg/index/`](../src/x2knwldg/index/README.md): `schema.py` (DDL + forward-only migrations), `scanner.py` (discovery, whole-subtree digests, incremental change detection, build lifecycle), `search.py` (FTS5 retrieval behind `query.rank_documents`), `repository.py` (`SqliteRepository`, all **ten** protocol methods, widening nothing). Stdlib-only, so it runs on a bare core install; `packages.find` auto-discovers it, so `pyproject.toml` is untouched. The index lives at `.x2knwldg/index.sqlite`, already gitignored. On the real sample it reaches **1 source, 85 artifacts, 86 entities, 118 relations** and a graph of **86 nodes / 118 edges** — the same figures `adapt_project` and `MemoryRepository` reach, now by a third independent path |
| HTTP API (Track B) | [`src/x2knwldg/server/`](../src/x2knwldg/server/): `envelope.py` (the frozen envelope, stdlib-only), `errors.py` (`RepositoryError` → HTTP by the status the repository chose, D-030), `app.py`, `deps.py`, `params.py`, and one module per endpoint group under `routes/`. **1263 lines**, **398 tests** across seven `tests/test_api_*.py` files. Talks to `IndexRepository` and nothing else — it never reads `output/`, never opens the SQLite file, never imports the adapters. Serves `SqliteRepository` in production and is tested against `MemoryRepository` as the oracle **and** SQLite, because the thread bug of D-052 was invisible to the oracle |
| Frontend (Track C) | [`web/`](../web/README.md): Vite + React + TypeScript, `HashRouter` (D-060), **50 files / ~6.2k lines** under `web/src/`, **125 tests** in 14 files. `npm run typecheck`, `npm test` and `npm run build` all pass and all three are now CI steps. Twelve of those tests are **integration** tests against a real `create_app(project_root=…)` over the committed fixtures — they skip without `X2KNWLDG_API_BASE`, so `npm test` stays hermetic. No endpoint, field, or query parameter was invented: the client's path table is typed against `Endpoints`, so the compiler refuses an incomplete or wrong one |
| Toolchain | Node 26.5.0 · npm 11.17.0 · Python 3.14.6 · SQLite 3.53.4 with **FTS5 available** |

> **Correction of record.** Canvas plan §4 previously stated the sample had empty
> `knowledge_units.json` / `relationships.json` / `graph.json` and `coverage = PARTIAL`.
> That was stale. The sample run is **complete and `PASS`**. §4 has been corrected.
>
> Two consequences:
> - **Risk 7 (no valid graph data for development) is resolved** — real graph data exists.
> - The inverse gap is now open: **no `PARTIAL`/`FAIL` fixture exists**, so those UI
>   states are currently untestable. See `T-006`.

**Phase 1 is built and runs.** `x2knwldg ui` refuses a non-loopback bind, resolves the root,
refreshes the SQLite index, binds a socket, prints the URL it actually reached, and serves the
Library and Reader over the eleven frozen endpoints. On the real sample it reports
`1 source, 85 artifacts, 86 entities, 118 relations` — the same figures `adapt_project`,
`MemoryRepository` and `SqliteRepository` reach. A clone that has not run `npm run build` gets
`6 UI_NOT_BUILT` (D-064), which is the default state of a fresh checkout because `web/dist` is
gitignored. The Map, the Canvas and the pen remain unbuilt (Phases 2–4).
Phase 0 contracts exist on disk: `docs/adr/` (`T-001`), `schemas/v1/` (`T-002`),
`src/x2knwldg/ids.py` (`T-003`), `src/x2knwldg/adapters/` (`T-004`), `schemas/api/v1/` plus
`tools/generate_api_types.py` (`T-005`), the labelled run fixtures in `tests/fixtures/runs/`
(`T-006`), `src/x2knwldg/repository/` (`T-007`), and the `web/` + `ui` scaffold (`T-008`,
re-confirmed zero-dependency by `T-009`).

> **Independent cross-check.** The adapter reaches 86 entities and 118 relations for the sample by
> reading `output/pqlWNihgdjI/` and `output/library/graph.json`; `library/status.json` independently
> reports 69 knowledge nodes + 17 concepts and 118 edges. Two code paths, the same numbers.

---

## 4. Phase board

Exit criteria live in canvas plan §16; this table tracks state only.

| Phase | Name | Status | Parallelizable | Gate to next phase |
|---|---|---|---|---|
| **0** | Contracts & scaffolding | ✅ `done` | ❌ **No — serialization point** | Schemas validate; contract frozen |
| **1** | Read-only Library & Reader | ✅ `done` — four tracks + `T-116`; §7.4 scenarios 1–3 walked and passing | — | Search works; status honest; rebuild is equivalent |
| **2** | Knowledge Map | `not started` | ✅ Partial (renderer vs inspector) | Provenance distinguishable; empty graph honest |
| **3** | Canvas & board persistence | `not started` | ⚠️ Sequential with Phase 4 | Layout survives restart; partial corruption tolerated |
| **4** | Pen & annotation | `not started` | ⚠️ Sequential with Phase 3 | Strokes stable under zoom/pan; no canonical leakage |
| **5** | Richer media & documents | `not started` | ✅ Per-format | Scoped only once real files are in use |
| **6** | New sources (Twitter/X, Medium) | `not started` | ✅ Per-adapter | Multi-source coexistence tested |
| **7** | Desktop packaging (conditional) | `not started` | — | Only on proven web-app limitation |

---

## 5. Task backlog

Flags: **`S`** = serialized (single owner) · **`P`** = parallel-safe once dependencies are met.

### Phase 0 — Contracts & scaffolding · one agent, no fan-out

| ID | Task | Flag | Depends on |
|---|---|---|---|
| ~~`T-001`~~ | ✅ **done** — ADR convention (`docs/adr/README.md` + `0000-template.md`), [ADR 0001](adr/0001-local-web-ui.md) consolidating D-001…D-013, canvas plan §19 cross-linked | `S` | — |
| ~~`T-002`~~ | ✅ **done** — v1 index model in [`schemas/v1/`](../schemas/v1/README.md): `common`, `Source`, `Artifact`, `Locator`, `EntityRef`, `IndexedRelation`. JSON Schema 2020-12, versioned by directory, 106 collected tests in `tests/test_index_schemas.py` | `S` | `T-001` |
| ~~`T-003`~~ | ✅ **done** — [`src/x2knwldg/ids.py`](../src/x2knwldg/ids.py): `GlobalId`/`SourceId`, both-way conversion to the library form, and the three cross-field invariants as `check_entity_ref_ids` / `check_source_ids` / `check_locator`. `library.py` nodes **gained** `source_type` + `global_id` and kept their two-part `id`. Stdlib-only; 132 collected tests in `tests/test_ids.py` | `S` | `T-002` |
| ~~`T-004`~~ | ✅ **done** — [`src/x2knwldg/adapters/`](../src/x2knwldg/adapters/README.md): `SourceAdapter` contract in `base.py`, `YouTubeAdapter` + `adapt_library` in `youtube.py`, `ADAPTERS`/`adapt_run`/`adapt_project` in `__init__.py`. Stdlib-only. The shape probe is deleted: `tests/test_index_schemas.py` validates the real adapter's records, and 43 new tests in `tests/test_adapters.py` cover what it refuses and never invents. No canonical file changed | `S` | `T-002` |
| ~~`T-005`~~ | ✅ **done** — [`schemas/api/v1/`](../schemas/api/v1/README.md): 11 `GET` endpoints in OpenAPI 3.1, `$ref`-ing `schemas/v1/` so the API defines no second shape. `tools/generate_api_types.py` (stdlib-only) generates the committed `types.d.ts`, verified under `tsc --strict`. 80 tests in `tests/test_api_contract.py` validate the endpoints against records from the **real** adapters and real `query.search_knowledge` output over the fixture runs; 26 in `tests/test_api_types.py` guard the generator and its drift. `openapi-spec-validator` joins the `dev` extra and validates the document against the OpenAPI 3.1 meta-schema. Board endpoints deliberately **not** frozen (D-027) | `S` | `T-002` |
| ~~`T-006`~~ | ✅ **done** — [`tests/fixtures/runs/`](../tests/fixtures/runs/README.md): `pass-run`, `partial-run`, `fail-run`, generated by driving the real pipeline and regenerable byte-identically. Every `metadata.json` carries `"fixture": true`. The projection contract tests now run over them **always**, and over the real sample additionally | `P` | `T-002` |
| ~~`T-007`~~ | ✅ **done** — [`src/x2knwldg/repository/`](../src/x2knwldg/repository/README.md) and [ADR 0002](adr/0002-index-repository-seam.md): `IndexRepository` is a `Protocol` of 10 methods serving the 11 frozen endpoints, returning pages of the v1 records the adapters already produce. Keyset cursors, opaque and bound to their query; D-030 raised as typed errors carrying `code` and `http_status`; absence returned, never raised. `MemoryRepository` answers the whole contract from `adapt_project` today, so Track B does not wait on Track A and `T-104` gets a cache-free oracle. Stdlib-only. **114** collected tests in `tests/test_repository.py`, **33** in `tests/test_repository_hardening.py`, plus **14** in `tests/test_api_contract.py` §5 validating the repository's own payloads against the frozen components (counted with `--collect-only`; see §7.2). Closes R18 | `S` | `T-002` |
| ~~`T-008`~~ | ✅ **done** — [`web/`](../web/README.md) with TypeScript only (D-038), the `ui` extra in `pyproject.toml` (D-037), the `ui` subcommand in `cli.py` as a **refusing stub** that enforces loopback-only binding and resolves the root but exits `6 UI_NOT_IMPLEMENTED` (`2` at the time; D-040) rather than pretending to serve, `pipeline.project_root` as the one root rule (D-039), the three `.gitignore` entries, and a `web-typecheck` job in CI running `tsc --noEmit`. 52 tests in `tests/test_ui_scaffold.py`, all stdlib-only so they run on a bare core install. Closes R17 | `S` | `T-005` |
| ~~`T-009`~~ | ✅ **done** — re-confirmed on a venv holding **only** `x2knwldg` + `pytest`: `333 passed, 4 skipped, 16 subtests`, and none of `jsonschema`, `openapi-spec-validator`, `networkx`, `pyvis`, `yt-dlp`, `fastapi`, `uvicorn` present. `fastapi` and `uvicorn` joined the CI creep check, and `tests/test_ui_scaffold.py` proves structurally that no module in the package imports them at module scope | `S` | `T-004`, `T-008` |

**Phase 0 exit gate — ✅ met (2026-08-31):** schemas validate ✅, the sample source converts to the generic model with zero guessed fields ✅, the API contract is frozen ✅, the indexer↔API seam exists with a working implementation behind it ✅, and `pytest` is green with **no** UI dependencies installed ✅ (`T-009`: 333 passed, 4 skipped on a core-only venv). **The four tracks of §8.2 may now fan out.**

### Phase 1 — Read-only Library & Reader · fan out to 4 tracks

**Tracks A and B are complete** (`T-101`–`T-108`, 2026-09-01). Tracks C and D are unblocked and were never blocked *on* A: `MemoryRepository` served Track B from day one, and `SqliteRepository` now answers the same ten methods with `0` page-for-page differences from it, so a route written against either is written against both. Track B did exactly that, and D-052 is the reason it is worth repeating for Track D: the oracle answered correctly while the real implementation 503'd on every request, so a test that reaches only for `MemoryRepository` can be green against a broken server.

| ID | Task | Track | Flag |
|---|---|---|---|
| ~~`T-101`~~ | ✅ **done** — [`index/schema.py`](../src/x2knwldg/index/schema.py): the DDL as one ordered `MIGRATIONS` tuple, forward-only and appended never edited, with `schema_migrations` as the ledger `IndexStatus.index_version` is read from. A database newer than the code is refused (`SchemaTooNew`), never read from a schema this code does not understand. FTS5 is probed by creating a `temp` table, not by `PRAGMA compile_options`, and its absence is refused rather than worked around. Records are stored verbatim as JSON with `identity`/`digest` as **two** columns, because `repository.order_key`'s separator is a NUL byte. 31 tests in `tests/test_sqlite_schema.py` | `S` |
| ~~`T-102`~~ | ✅ **done** — [`index/scanner.py`](../src/x2knwldg/index/scanner.py): mirrors `adapt_project`'s walk rather than re-deriving it. The digest covers a run's **whole subtree**, not `metadata.json`: `adapt_run` also reads `is_file()`, `st_size`, the `raw/source.*` glob and `vault/**/*.md`, so a narrower digest would miss a deleted vault note. `(mtime_ns, size)` prefilters, `io.sha256_file` arbitrates, so a touched-but-identical file is not a re-index. Damage follows D-043's two tiers — *skipped* and *incomplete*, never a silent drop — and `adapt_library`'s silent empty-on-damage is closed from outside by reading both library files first. A deleted run leaves `library/graph.json` naming endpoints no entity has, so the fragment is dropped **whole** and named. 31 tests in `tests/test_sqlite_scanner.py` | `S` |
| ~~`T-103`~~ | ✅ **done** — [`index/search.py`](../src/x2knwldg/index/search.py). FTS5 is candidate **retrieval**; `query.rank_documents` stays the sole ranking rule (D-046), so `bm25()` appears nowhere. `derivation_note` **is** indexed; `context` is not and segment `text` is not stored, each because it is **measured** to cost no reachable word (D-047, D-048) — and each measurement is a test, so the claim cannot go stale. 168 tests in `tests/test_sqlite_search.py`, including a 6036-query differential fuzz against the in-memory ranker with 0 mismatches | `S` |
| ~~`T-104`~~ | ✅ **done** — `tests/test_sqlite_equivalence.py`: 21 tests, ~32k page-for-page observation comparisons over eight scenarios (full build ≡ cache-free `MemoryRepository`; refresh from no index and from an empty one; a no-op refresh; a run edited, added, removed; `library/` alone rebuilt; and `.x2knwldg/` deleted then rebuilt — Phase 1's own acceptance criterion). Items element-wise **and** `next_cursor` as an exact token, `total` with `null` distinguished from `0`. A fresh `MemoryRepository` per comparison (D-042). **0 differences.** `built_at`/`index_version` are excluded by name, because the seam's README requires SQLite to report them while `MemoryRepository` reports `None`. Mutation-checked: dropping the probe row, faking `total`, and bypassing the Python filter predicate are each caught | `S` |
| ~~`T-105`~~ | ✅ **done** — [`routes/status.py`](../src/x2knwldg/server/routes/status.py) and [`routes/sources.py`](../src/x2knwldg/server/routes/sources.py), five paths (`/api/status` plus the four `/api/sources*`). `/api/status` answers in **every** index state including `absent`, and passes D-050's optional `runs` through exactly as the repository produced it — never synthesising `skipped: []`. `/entities` and `/relations` call `get_source` first, because an empty page for an unknown source would assert the source exists. Enum filters validated by the query dataclasses, not restated as framework enums (D-058). **96 tests** in `tests/test_api_status.py` + `tests/test_api_sources.py`, every one over both implementations | B | `P` |
| ~~`T-106`~~ | ✅ **done** — [`routes/search.py`](../src/x2knwldg/server/routes/search.py). Hits pass through **verbatim**: no rename, reshape, sort, re-score or truncation, so `video_id` stays `video_id` (ADR 0001 invariant 6) and a caption hit still carries no `global_id` (D-023). `SearchResponse.query` echoes the query as executed, so a client batching requests cannot mis-attribute a response. Ranking remains `query.rank_documents` alone (D-046). **60 tests** in `tests/test_sqlite_search.py`'s sibling `tests/test_api_search.py`, including a paged walk reproducing the unpaged call exactly | B | `P` |
| ~~`T-107`~~ | ✅ **done** — [`routes/entities.py`](../src/x2knwldg/server/routes/entities.py). Records out verbatim; the only id grammar is `ids.parse_global_id` reached **through** the repository, so `invalid_id` (400) and `not_found` (404) stay distinct (D-020) and no route pre-validates or rewrites. A canonical concept — which belongs to no source (D-016) — resolves here. Slash-bearing ids answer 404 by segment matching (D-056). **17 tests** in `tests/test_api_entities.py`, including a 29-entry hostile-id battery over both endpoints and both implementations | B | `P` |
| ~~`T-108`~~ | ✅ **done** — [`routes/media.py`](../src/x2knwldg/server/routes/media.py) plus `tests/test_api_hardening.py`. Two independent checks stand between a path parameter and a read, **neither of which rewrites**: the repository refuses a malformed id before anything is opened, and the record's project-relative path is resolved and re-checked against the root anyway — the index is a rebuildable cache, and a cache is not a trust boundary. Ranges per RFC 9110: an unparseable `Range` is ignored, only a well-formed unsatisfiable one is a `416`, and it carries `Content-Range: bytes */size`. An `external` artifact answers `404 unavailable` rather than `503`, because there will never be local bytes for a YouTube video. **178 tests**, including a wire-hostile battery across all seven id-taking routes, a raw-id battery at the repository boundary, and dot segments handed to the ASGI app as a raw path (httpx normalises them, so the obvious test grades the client). Loopback binding stays in `cli.py` and is `T-116`'s to wire | B | `S` |
| ~~`T-109`~~ | ✅ **done** — Vite + React + TypeScript on the `T-008` toolchain, `HashRouter` (D-060), Vitest + jsdom, design tokens under `web/src/styles/`. The three things `tests/test_ui_scaffold.py` asserts structurally all still hold: `typecheck` is exactly `tsc --noEmit`, `skipLibCheck` stays `false`, and the generated declarations stay a root file of the program — R17 is not reopened. `src/env.d.ts` declares the ambient CSS-module shapes locally rather than adding a large `@types` package to a program that checks every `.d.ts` | C | `P` |
| ~~`T-110`~~ | ✅ **done** — `web/src/i18n/`: English is the source of truth and the default, `fa` is typed as `Record<MessageKey, string>` so a missing translation is a **compile** error rather than a blank label. The provider writes `lang`/`dir` on the document. Logical CSS properties are enforced rather than intended: `web/src/styles/logical.test.ts` fails the build on `margin-left`, bare `width:`, `text-align: left` and friends. Persian appears only in translated UI strings (D-014) | C | `P` |
| ~~`T-111`~~ | ✅ **done** — list + compact grid, cursor paging, and search over `/api/search`. **All five filters are served by the server**, none re-implemented in the browser, so `repository.matches_*` stays the single definition of every filter. The `/api/status` panel distinguishes `absent`/`building`/`ready`/`error` and renders D-050's optional `runs` honestly: absent reads *not reported*, never *nothing skipped*. Knowledge-unit mode shows per-source totals and **no aggregate** (D-062) | C | `P` |
| ~~`T-112`~~ | ✅ **done** — six tabs: metadata/counts, virtualized transcript (measured-height windowing over bytes from `/api/media`), report, knowledge units with evidence excerpt and locator coordinates, relations, and an artifact inventory. Status and the two D-045 diagnostic channels sit in the sidebar. The report is Markdown parsed to React nodes — there is no `dangerouslySetInnerHTML` anywhere in `web/` | C | `P` |
| ~~`T-113`~~ | ✅ **done** — every badge carries a glyph, a translated word **and** a border style as well as colour, and the test asserts the two non-colour signals differ across all three classes, so ADR 0001 invariant 10 is checked rather than described. `RunStatusPanel` renders the copied triple, so `fail-run`'s `coverage: PASS` under `validation: FAIL` stays visible instead of being reconciled; an unrecorded `audit_attempts` renders as *not recorded*, never `0` | C | `P` |
| ~~`T-114`~~ | ✅ **done** — `localMedium` accepts only a non-`external`, pathed, `available` artifact; otherwise the panel says there is no local media rather than requesting bytes that will never exist. The embed is a **click-to-load facade** (D-061). Seek is `postMessage` to the one allowed origin when the frame exists and the `start` parameter when it does not, with the frame URL fixed at load so seeking does not reload the player | C | `P` |
| ~~`T-115`~~ | ✅ **done** — reduced at the start to what Tracks A and B had not already delivered, then delivered. `tests/test_api_honest_status.py` (**32** collected): the `PARTIAL`/`FAIL` fixtures through **HTTP**, every test over both implementations (D-052). It asserts what the honest-status UI now depends on — nothing coerces toward `PASS` (checked over projects holding *only* the failed run, so a stray `PASS` has no innocent explanation, and with status objects found by a recursive walk rather than by path), a `FAIL` run is still listed, fetchable and searchable, and `/api/status`'s tally agrees with `/api/sources?status=` — each had been tested, their **agreement** had not. `tests/test_api_declarations.py` (**36** collected) plus `tests/ts_declarations.py` close the served → `types.d.ts` loop: all eleven operations called for real, each request built *from the declaration*, each body checked against the declared type rather than against the JSON Schema it came from. Sections 4 and 5 are mutation tests on the checker itself, so a green result can be made red. Found the D-063 leak | D | `P` |
| ~~`T-117`~~ | ✅ **done** — `GET /api/graph` and `GET /api/graph/neighborhood/{id}` in [`routes/graph.py`](../src/x2knwldg/server/routes/graph.py). Added because the backlog assigned only 7 of the 11 frozen endpoints while the repository has always served all ten methods, so leaving these unrouted would have shipped a contract advertising paths that answer nothing. `NeighborhoodResponse` carries no `page` — a neighborhood is bounded by `depth` and `limit` and says so with `truncated`. `depth` outside 1..3 is refused, never clamped. **32 tests**; see D-059 for what an edge on a *page* may legitimately reach | B | `P` |
| ~~`T-116`~~ | ✅ **done** — `_run_ui` in `cli.py` and [`server/serve.py`](../src/x2knwldg/server/serve.py). The five steps of canvas plan §8.3, in an order that is itself the contract: the bind address is refused **first** (before the dependency probe, or the invariant would hold only where it was least needed), the root is resolved by `pipeline.project_root` alone, the extra is probed and named, the index is refreshed (D-065), and only then is a socket bound, a URL printed and a browser opened (D-066). An unbuilt frontend stops it at `6 UI_NOT_BUILT` (D-064) **before** the index is touched, so a command about to refuse writes nothing. The eleven `/api` routes are registered first and `StaticFiles` is mounted at `/` last, so it catches only what no route claimed; D-060's hash routing is why no SPA-fallback rule is needed. **26 tests** — 24 in `tests/test_ui_serving.py` (11 of them stdlib-only and running on a bare core install) plus the rewritten wiring tests in `tests/test_ui_scaffold.py`. The traversal battery hands raw paths to the ASGI app, because httpx normalises `..` before sending and the obvious test grades the client; a companion test proves the probe reaches the mount at all | integrator | `S` |

### Phases 2–7 — epics only

Deliberately not broken down. Decomposing them before their contracts exist produces churn; expand each at its phase start.

| ID | Epic | Phase |
|---|---|---|
| `T-201` | Sigma.js/WebGL Map: styles by provenance + kind, search/focus/filter, neighborhood loading, inspector integration, link to Reader | 2 |
| `T-301` | Canvas: board CRUD, entity insertion, custom nodes, user relations, frames, autosave, undo/redo, portable `workspace/boards/` persistence | 3 |
| `T-401` | Pen: pointer events + `perfect-freehand`, world-coordinate strokes, eraser, layer toggle, mouse fallback | 4 |
| `T-501` | Rich media: PDF.js + page locators, image viewer, audio, anchored annotations | 5 |
| `T-601` | New source adapters (Twitter/X, Medium) + coexistence tests | 6 |
| `T-701` | Conditional Tauri spike — only on proven limitation | 7 |

---

## 6. Decisions

New decisions from this session, formatted for the canvas plan §19 table.

**Amending an accepted row.** Same discipline as `docs/adr/README.md` applies to a decision
that has already been built to: do not quietly edit what it decided. Add a new `D-0xx` that
states the new rule and names the row it amends, then mark the old row `accepted, amended by
D-0xx` and strike the superseded value in place, leaving the original visible. Correcting a
stale *fact* in a row — a moved line number, a renamed file — needs none of this. The test is
whether an agent who built to the old row would now be wrong.

`D-031`–`D-036` landed with `T-007` and are recorded in canvas plan §19; they are not
repeated here.

| ID | Decision | Status | Rationale |
|---|---|---|---|
| D-011 | 3-part global entity ID `<source-type>:<external-id>:<local-id>` for index, API, and boards | accepted | Source-neutral; adopted before any board file exists, so no board migration is ever needed |
| D-012 | UI language switchable, English default; bidi-safe content rendering | accepted | Text direction is architectural, not cosmetic — retrofitting it is expensive |
| D-013 | Correct canvas plan §4 and its dependent criteria; add labeled test-only `PARTIAL`/`FAIL` fixtures | accepted | Acceptance criteria were resting on a stale fact |
| D-014 | All project documentation in English; Persian only in the UI and in extracted knowledge content | accepted | One documentation language keeps the repo portable between agents and contributors; Persian stays where it serves the user directly |
| D-015 | Index model versioned by directory (`schemas/v1/`), JSON Schema 2020-12; controlled vocabularies mirrored from `constants.py` and drift-tested; `jsonschema` is a `dev`-extra dependency only | accepted | A breaking change becomes `schemas/v2/` rather than a silent reinterpretation of stored records; mirroring lets the schemas stand alone for TypeScript generation without letting them drift from the Python vocabulary |
| D-016 | Cross-source canonical concepts use the reserved source type `library` with external id `concepts` — `library:concepts:<hash>` | accepted | Gives `concept:<hash>` a well-formed three-part global id without touching what `library.py` emits, so D-011 covers every entity and not just per-source ones |
| D-017 | An identifier segment may begin with `-` or `_`; only a leading dot stays barred. `ids.py` is the single implementation of the identifier rules, and the v1 `idPart` pattern was widened to match | accepted | A YouTube id is base64url and legitimately starts with either — `pipeline._VIDEO_ID_RE` already accepts `[0-9A-Za-z_-]{11}`, so the narrower pattern would have made a real source unaddressable by the index. Widening accepts strictly more, so no stored record is invalidated and no `schemas/v2/` is needed; barring a leading dot keeps `.` and `..` out of every identifier |
| D-018 | A canonical knowledge unit id must be usable as one segment of a global id. `validators.py` reports `invalid_id`, and `extraction_bundle.schema.json` carries the same pattern | accepted | Otherwise an id that passes validation can still be unaddressable by the index, which is how a validator-`PASS` run came to crash `rebuild_library`. The rule now lives in one place — `ids.py` — and is enforced where the id first appears rather than where it first breaks |
| D-019 | Labelled, synthetic `PASS`/`PARTIAL`/`FAIL` run fixtures are committed under `tests/fixtures/runs/`, and the projection contract tests run over them unconditionally | accepted | `output/` is gitignored, so those tests skipped on every machine but the one holding the sample — a green suite that proved nothing. The fixtures also give `PARTIAL` and `FAIL` an on-disk existence for the first time (R11). They are generated by driving the real pipeline, so they cannot drift from what it writes, and regeneration is byte-identical so CI can prove it |
| D-020 | A run directory is resolved by `pipeline.resolve_run_dir`, which **rejects** an unsafe id rather than sanitising it ([ADR 0003](adr/0003-reject-unsafe-identifiers.md)) | accepted | `_safe_identifier` then rewrote `../other` into `_other` — defensible when creating a run, wrong when looking one up, because a lookup must fail rather than silently read a different run. Every externally supplied id goes through the resolver (R14); `T-108` must use it rather than inventing a second rule |
| D-021 | `src/` holds the `x2knwldg` package and nothing else. The unmaintained upstream scripts moved to `legacy/upstream/`, `pytest` gets an explicit `pythonpath`, and `requirements.txt` forwards to `pyproject.toml` | accepted | Loose modules beside the package were importable only because an editable install happened to put `src/` on `sys.path`, and two of them were Whisper transcribers that the project constraints forbid running. Quarantining them keeps upstream attribution without leaving them looking sanctioned |
| D-022 | Adapters live in `src/x2knwldg/adapters/`, one `SourceAdapter` subclass per source type, registered in `ADAPTERS`. `base.py` enforces four rules for every adapter: ids built through `ids.py`, project-relative paths, statuses copied, and an `AdapterError` wherever a value would have to be guessed | accepted | The generic seam is only real if an adapter cannot opt out of it, so the rules live in the base rather than in each implementation. The rules are not theoretical: the shape probe hard-coded `raw/source.json` (the extension follows the imported file — `pipeline.import_transcript` — so it is `.srt` in every fixture and the artifact read as missing) and asserted a media type for it. Both are now refusals |
| D-023 | In v1 the adapter emits entities for knowledge units and canonical concepts only. `caption`, `segment`, and `coverage_window` stay reserved in the `EntityRef` vocabulary and unemitted | accepted | Each already has a canonical representation the Reader and the indexer read directly — `T-103` indexes caption and segment text out of their artifacts — and none has a consumer needing a global handle yet. 500-odd caption entities per source, or a segment entity whose only honest `label` is `null` because the real text does not fit the field, would have to be undone later. The reserved names mean adding them costs no `schemas/v2/`. Coverage-window membership is likewise not an `IndexedRelation`: expressing it needs a fourth relation vocabulary, which is a schema change |
| D-024 | A source-class locator addresses the **segments** artifact, not the transcript. When a unit's provenance names a different video, `artifact_id` is omitted rather than pointed anywhere | accepted | `validators.validate_provenance` resolves `segment_id` against `segments.json` and requires the excerpt to appear in that segment's text, so that is where the evidence sits; the shape probe addressed `transcript.json`, which does not carry segment ids at all. A mis-attributed unit is a canonical error already reported in `validation.json` — the run stays indexable and honestly displayed, and its locator stays unaddressed rather than wrong |
| D-025 | *(index side; **amended by D-043** for the library side)* A `derived_from` edge carries `confidence: null`. `expresses_concept` edges come from `library/graph.json` via `adapt_library`; `derived_from` edges come only from the run that owns them | accepted | A unit's confidence is about the unit — no confidence about the edge exists in any canonical file, and copying one across would put a number on a claim nothing made. ~~(`library.py:70` writes its own value into its own graph for its own reasons)~~ — **withdrawn by D-043:** `library.py` was fabricating `1.0` and `0`, and has stopped. Splitting the two synthetic vocabularies by producer keeps a run indexable before `rebuild_library` has ever run, and stops the 45 `derived_from` edges being counted twice <!-- citation:history --> |
| D-026 | The API contract is frozen as OpenAPI 3.1 in [`schemas/api/v1/openapi.json`](../schemas/api/v1/README.md), which `$ref`s `schemas/v1/` instead of restating it. Every response body is an adapter record inside an envelope carrying `api_version` and `schema_version`. Versioned by directory like D-015: a breaking change becomes `schemas/api/v2/` and a `/api/v2/` prefix, leaving these paths answering v1 | accepted | The API is a reader. A response shape of its own would be a third place for the same fact to drift, and there are already two identifier vocabularies to keep honest (R12). `adapt_project(root).by_model()` is literally what an endpoint returns a page of — the contract tests validate the endpoints against records the **real** adapters produce, so the document cannot agree with the schemas while disagreeing with the code |
| D-027 | Only the read-only surface is frozen in v1 — 11 endpoints, all `GET`. The board endpoints of canvas plan §15 stay **reserved and unfrozen** until Phase 3 gives boards a record schema | accepted | Freezing a contract for a shape that does not exist is inventing one, and a board contract written before `T-301` would be rewritten by it. The same restraint as D-023: reserving a name costs nothing, guessing its shape costs a migration |
| D-028 | `/api/search` preserves the two result shapes `query.search_knowledge` already returns, discriminated by `type`, and adds `global_id` and `source_id` **additively**. A `transcript_caption` hit carries no `global_id` | accepted | Those shapes are the de-facto contract the CLI and the MCP tools ship today; FTS5 (`T-103`) is an implementation change and must not be a contract change. The caption hit has no global id because v1 emits no caption entities (D-023) — minting one for the response would create an address that resolves to nothing. A hit whose canonical metadata states no `video_id` gets `global_id: null` rather than a plausible string |
| D-029 | TypeScript types are generated by `tools/generate_api_types.py` — stdlib-only — into a **committed** `types.d.ts`, drift-guarded by a byte-identity test rather than by an npm toolchain | accepted | `T-005` runs before `T-008`, so there is no `web/`, no `package.json`, and no Node job in CI. Putting the frontend's types behind a dependency the core package does not have would cut against ADR 0001 invariant 5 and hand `T-008` a scaffold it did not choose. The generator **refuses** a construct it does not understand instead of emitting `unknown`, because a declaration that has quietly stopped describing the contract still compiles. `openapi-typescript` can be added later as a cross-check without touching the contract |
| D-030 | *(**extended by D-044**)* Error taxonomy: an id rejected by `ids.py`/`resolve_run_dir` is `400 invalid_id`; a well-formed id naming nothing is `404 not_found`; a record whose file is absent is `available: false` and `404 unavailable` from `/api/media`; an unbuilt index is `503 index_unavailable` | accepted | D-020 says a lookup must fail rather than silently read a different run — over HTTP that means a malformed id is reported as malformed, refused before anything is read, and never dressed up as absence. `503` exists so the UI can distinguish an empty index from an absent one; without it, 'no sources yet' would be presented as a fact about the user's data |
| D-037 | The `ui` extra is `fastapi` + `uvicorn`, each with **both** a floor and a ceiling, and `x2knwldg ui` ships as a **refusing stub**: it enforces loopback-only binding (ADR 0001 invariant 9) and resolves the project root, then exits ~~`2`~~ **`6`** with `UI_NOT_IMPLEMENTED` naming `T-116` (the code was `2`; **D-040** moved it). It never prints a URL, and `--port` defaults to unset rather than to a constant | accepted, **amended by D-040** | A scaffolded command that exits `0` is a claim the project can serve a UI, and one that prints `http://127.0.0.1:8000` is a claim about a socket nobody opened — the same class of dishonesty as coercing `PARTIAL` to `PASS`. The two checks that *are* real here are both refusals, and a refusal is worth having before the thing it guards exists: the host check runs **before** the dependency probe, so the invariant holds on every machine that has not installed the extra. Upper bounds because a FastAPI or uvicorn major bump would otherwise land in a `pip install` between Phase 0 and `T-105` |
| D-038 | `web/` gets **TypeScript and nothing else** — no Vite, no React, no router, no tokens; `T-109` chooses those. What it does add is CI: `tsc --noEmit` over `web/` with `skipLibCheck: false` and `schemas/api/v1/types.d.ts` as a *root file* of the program, plus `web/src/api/contract.ts` as the single re-export of the generated declarations | accepted | Same restraint as D-029: handing `T-109` a framework it did not choose is a cost it pays for the life of the project, and the task row asked for a directory, not an application. `skipLibCheck` is the load-bearing detail — TypeScript's default is to skip `.d.ts` files, so with it on the Node job would skip the one file it exists to check and pass without looking, leaving R17 closed on paper only. Verified by deliberately breaking `types.d.ts` and watching `tsc` fail. Routing every import through `contract.ts` keeps exactly one path to the generated file, so moving it breaks a test rather than a build |
| D-039 | `pipeline.project_root(explicit=None)` is the single root-resolution rule — explicit path, then `X2KNWLDG_PROJECT_ROOT`, then the working directory. `mcp_server.PROJECT_ROOT` now calls it instead of re-reading the env var | accepted | The `ui` command is the second consumer of 'where is the project', and a second implementation of a lookup rule is exactly what D-020 was written about. Behaviour is unchanged for the MCP server — the same three-step fallback, one copy of it — and `tests/test_ui_scaffold.py` asserts the env var is no longer read in `mcp_server.py`, so the duplication cannot quietly return |
| D-040 | Exit codes are a semantic contract, not a boolean. One table, one mapping (`cli.VERDICT_EXIT_CODES`), printed by `--help`: `0` `PASS` · `1` `ERROR` · `2` reserved for `argparse` · `3` `PARTIAL` · `4` `FAIL` · `5` `TRANSCRIPT_REQUIRED` · `6` ~~`UI_NOT_IMPLEMENTED`~~ **`UI_NOT_BUILT`** (renamed by D-064 when `T-116` landed the server). Completion may be claimed only on `0`. **Amends D-037**, whose `ui` refusal moves `2` → `6` | accepted, **amended by D-064** | `PARTIAL` exited `0`, so no shell or CI check could tell an honestly incomplete run from a passing one — the same dishonesty as coercing `PARTIAL` to `PASS`, dressed as a status code. Every refusal shared `1`, so "this video needs a transcript from you" and "the `ui` server does not exist yet" were indistinguishable from a broken install. `2` is given back to `argparse` because a semantic code sharing a number with a typo'd flag cannot be checked for. D-037's reasoning is untouched and still right — a stub that exits `0` is a false claim; only the number moved, and it moved so the refusal is distinguishable from a mistyped argument. One mapping rather than three literals so `validate`, `apply-bundle` and `finalize` cannot drift |
| D-041 | Which nodes a source's graph is drawn over is `relation_belongs_to_source` (D-034) — the same rule `/api/sources/{id}/relations` uses. A node belongs when it is an entity of that source **or** when a relation of that source names it as an endpoint. The **edge** rule of D-035 is unchanged: both endpoints must be nodes of the graph. **Extends D-035** ([ADR 0004](adr/0004-graph-membership-and-search-corpus.md)) | accepted | `/api/graph?source_id=` used its own rule — both endpoints had to be entities *of that source* — and a canonical concept belongs to no source (D-016), so all 17 `expresses_concept` edges vanished from the graph while the relations endpoint returned them: 101 edges against 118 on the sample. Two answers to one question, and the lossy one was the one a user calls 'the graph'. Widening the **node set** is the opposite of the either-endpoint **edge** rule ADR 0002 rejected: the far endpoint becomes a node rather than a dangling reference. Both views now report 118 edges over 86 nodes |
| D-042 | `MemoryRepository`'s search corpus is built from the `canonical_dir` each **indexed** `Source` carries, once per instance on the first search, and never invalidated. A run outside the index is not searched; a source whose files will not read is *unreadable*, so `total` is `null` rather than a zero ([ADR 0004](adr/0004-graph-membership-and-search-corpus.md)) | accepted | Walking `output/` per call made paging cost the whole library **per page**, and made search a second, disagreeing view: a run added after construction returned hits carrying `source_id: null`, because no `Source` existed to resolve them against — renderable and unnavigable. Resolving through the record also means no id is joined onto a path, so no host path reaches an error body (D-030, ADR 0003). Built lazily because a repository that never searches must not pay for a corpus and `/api/status` must stay cheap. Narrows ADR 0002's promise of a cache-free `T-104` oracle to *cache-free per instance* |
| D-043 | `library.rebuild_library` invents no confidence and drops no run in silence. `expresses_concept` edges carry `confidence: null`; a `derived_from` edge carries the unit's **own** confidence verbatim, `null` when the unit states none. A run missing a canonical file is indexed from what it has, and `status.json` gains `runs_discovered`, `runs_indexed`, `runs_skipped`, `skipped_runs[]` and `incomplete_runs[]`, with every `videos.json` entry gaining `problems: []`. **Amends D-025** | accepted | D-025 forbade the index fabricating an edge confidence; `library.py` was doing exactly that in its own graph — `1.0` on every `expresses_concept` edge, which is a match on a normalised string key and not a measurement, and `0` (the *least* confident value) on a `derived_from` edge whose unit stated none. The same reasoning applies to both producers, so the parenthetical in D-025 that excused `library.py` as writing 'its own value for its own reasons' is withdrawn. Separately, `relationships.json` was a precondition for indexing at all, so a run with units but no relationships file disappeared from `graph.json`, `videos.json` and the `videos` count while `adapt_run` indexed it without complaint — a count that omits a run without saying so is a claim of completeness the library has not got |
| D-044 | D-030's taxonomy gains two codes for boundaries that are not HTTP: `invalid_request` — an argument refused before anything is read, where no identifier is involved — and `internal_error`. The four original codes keep their meanings and their HTTP statuses. **Extends D-030** | accepted | Two MCP tool parameters are *paths*, not ids, so `resolve_run_dir` is not their check even though its behaviour is (ADR 0003 invariant 5). Reporting a refused path as `invalid_id` would name a thing the request never contained, which is the kind of small lie D-030 exists to prevent — the taxonomy's whole point is that a refusal says what was actually refused. `internal_error` is the boundary's own catch: a tool must let out one error type carrying a known code, so an unexpected exception is converted rather than leaked with its message and paths intact. Narrowing the MCP surface to the four HTTP codes was the alternative and was rejected: it would force one of them to mean something it does not |
| D-045 | An adapter **states what it could not do** rather than dropping it silently, and `Source.adapter_metadata` carries two diagnostic channels for it: `unmappable_artifacts` (a generated `vault/` note whose filename cannot spell an id — skipped and named, not fatal) and `unreadable_files` (a canonical file present but damaged — named, so a missing count is not read as a zero). Both are free-form by schema and absent when there is nothing to report. The line is drawn at index integrity: a run whose `knowledge_units.json` is damaged while its `relationships.json` is intact is **refused** at adapt time, naming the dangling edge. **Qualifies D-022** | accepted | D-022 requires an `AdapterError` wherever a value would have to be guessed, and that is still right for canonical evidence. Nothing here is guessed either way; the choice is between refusing everything and stating the one omission, and the rule that actually matters is that the omission is never silent — the recurring finding across this audit. One `vault/` note whose filename cannot spell an id took down a whole project's index, and that note is a generated export beside the canonical files, so it is skipped and named. A damaged canonical file is different again: its counts were already omitted rather than zeroed, but 'this count is missing' does not say 'this file is broken', and only one of those is actionable. The refusal stays where integrity is at stake: stranded edges would make the graph and `/api/sources/{id}/relations` disagree about one fact, `check_index_integrity` would refuse the whole project later anyway, and the failure belongs on the run that causes it. `adapter_metadata` is the only place in the frozen `Source` record an adapter may say any of this |
| D-046 | FTS5 is candidate **retrieval**; `query.rank_documents` is the only ranking rule. Two disjuncts, two indexes: `document_tokens` (a plain table holding `query._tokens`'s own output) for token overlap, and a `trigram` FTS5 index queried with **`GLOB`** for the substring test. `bm25()` is not used | accepted | `SearchDocument.score`'s `phrase_bonus` is a *raw substring* test, so partial matching is how this ranker works without a stemmer; BM25 would change the hit **set**, not merely the order, and D-028 licenses an implementation change rather than a contract change. Three measured reasons for the shape: (a) `LIKE '%q%'` reads `%` and `_` in the *user's* query as wildcards — a search for `100%` matched a document reading "100 percent", and `a_b` matched `axb` — while `GLOB` with an escaped needle is byte-exact and still consumes the index (`INDEX 0:G0`); (b) trigram `MATCH` silently returns **zero rows** for a needle under three characters, which is absence presented as a fact; (c) an FTS5 `unicode61` index is not `query._tokens` — it splits on `_` where `\w+` does not, and does not split scriptless CJK at all, so for `機習` against `機械学習のモデル` the scorer returns **0.667** while a token `MATCH` **and** a trigram substring scan both return nothing, the two characters not being adjacent. Storing the Python tokeniser's output makes the overlap disjunct exact *by construction* rather than approximately right. Ranking parity is then structural, which is what keeps `T-104` a real oracle instead of a coincidence two implementations must keep re-earning |
| D-047 | `derivation_note` **is** indexed. `context` is **not**, and the reason is measured rather than asserted: every token it holds already appears in the unit's own `content` or `normalized_statement` | accepted, **amends the deferral this decision originally recorded** | The first version of this decision deferred both fields and called the result "a real gap — text a reader can see and search cannot find". That was directionally true and quantitatively wrong, so it is corrected here rather than left standing. Measured on the real sample: `context` contributes **0** tokens no other field holds, so indexing it would answer no query it does not already answer; `derivation_note` contributes **25** out of **1095**, moving `the` from 253 to 258 while `learning` and `model` do not move at all. So the honest case for `derivation_note` is not recall but that a phrase a reader can see in the Reader should be a phrase they can search for. The accepted cost is to **precision**: `derivation_note` is *derived* commentary about provenance, so a domain term appearing only there ranks a unit for what the reasoning says rather than for what the unit claims — which is the source/derived separation `AGENTS.md` asks be kept, spent deliberately and only this far. Also corrected: the original claimed the two rankers must move together "or they silently disagree". They cannot silently disagree — `index.search` builds its corpus from `query.run_documents`, and `refresh_index` re-indexes every source on each pass, so a change in `query.py` is picked up even when no file under `output/` moved (verified: 253 → 258 through a plain refresh). No corpus-version column is needed. Both measurements are tests, so a future extraction whose `context` carries vocabulary of its own fails the suite instead of leaving this row stale |
| D-048 | No `transcript_segment` hit shape, and segment text is not stored. **Rejected, not deferred** | rejected | Measured first: a segment's `text` is **byte-identically** the concatenation of the captions it spans (3346 chars == 3346 chars on the sample's first segment), and segments contribute **0** words that appear in no caption. Captions are indexed, so a segment index would make **nothing** newly findable — it would only change the *granularity* of a hit, from a 12-second caption to a ~3.3k-character block. That is a presentation question with a presentation answer that costs no contract change: a Reader rendering a `transcript_caption` hit can show the surrounding captions, and `segments.json` carries `caption_ids` so it can group them exactly as the segmenter did. The alternative costs `openapi.json`, a regenerated `types.d.ts`, a third shape every future search consumer must handle, and double-counted evidence in any later scoring — all to reach text that is already reachable. Revisit only if a real need appears that caption-grouping cannot serve; `test_not_storing_segment_text_costs_no_reachable_word` fails if the premise stops holding |
| D-049 | The scanner **skips and names** an unmappable run where `adapters.adapt_project` refuses the whole project. `strict=True` reproduces the refusal exactly | accepted | D-043's reasoning transfers: the sin is the silence, not the skipping, and one broken run must not cost a reader every other run — D-045 already applies the same rule to a single unaddressable vault note. But the consequence is real and worth an id: on a *damaged* project the index is a named **superset** of what the `MemoryRepository` oracle can produce, because the oracle raises `AdapterError` and answers nothing at all. So `strict=True` exists for the one caller that needs the comparison well defined, and `T-104` asserts the divergence itself rather than hiding it |
| D-050 | `StatusPayload` gains an **optional** `runs` object — `{discovered, indexed, skipped[]}`, each skipped entry `{relative_path, reason}`. `openapi.json` first, `types.d.ts` regenerated, `IndexStatus` second (ADR 0002 invariant 3) | accepted | A run directory that produced no `Source` was in no page and in no count, so the only honest reading of `counts.sources` was "at most this many" — and nothing said so. `/api/status` described a project of two sources where three run directories existed, and D-043 exists precisely because "a count that omits a run without saying so is a claim of completeness the library has not got". The scanner already recorded both tiers; this is the reading of them the frozen payload had no field for. **Named, not counted**: "one run was skipped" is not actionable and "this directory, for this reason" is. **Optional in the schema, unconditional in an implementation that scans**: optional keeps v1 additive rather than forcing a `schemas/v2/` (a new *required* field is the versioning rule's breaking change), and unconditional means a reader can tell "nothing was skipped" from "this server does not report skipped runs" — D-043's `problems: []` rule applied to a payload. `MemoryRepository` **omits** it, for the reason it reports `index_version: null`: it has no scan, and `skipped: []` would assert it looked. Done now rather than after `T-105`, because the same edit costs a schema change today and a schema plus routes plus `IndexRepository` plus frontend once endpoints consume it |
| D-051 | A skipped run's stored `reason` is **project-relative**, sanitised where it is recorded rather than on the way out | accepted | `AdapterError` names the directory it refused and names it *absolutely*. That string was only ever stored and printed by the CLI, where a host path is unremarkable — D-050 turned it into an HTTP response body, at which point it leaks the user's filesystem layout to any client, which D-030 and ADR 0003 both forbid ("no host path reaches an error body"). Caught by the test written for D-050 rather than in review. Sanitised at the point of record so there is one rule and the CLI gains the same property, and to the same relative string the row is keyed by, so the reason and the path it names cannot disagree |
| D-052 | The SQLite **reader** opens with `check_same_thread` lifted and serialises all ten methods behind a re-entrant lock. A **writer** must not lift it | accepted | `sqlite3` binds a connection to its creating thread; Starlette and uvicorn both answer from a thread pool. So `SqliteRepository.open()` at app construction made **every** request answer `503 index_unavailable: SQLite objects created in a thread can only be used in that same thread` — in production, on all eleven endpoints, not only under a test client. It went unseen because `MemoryRepository` has no connection and answered fine: a suite that reaches for the oracle by default stays green while the implementation the UI will actually use is broken, which is why `test_every_endpoint_answers_over_sqlite_not_only_over_memory` now exists. The lock arrives **with** the lifted check rather than after it — lifting alone trades a loud failure for a silent one — and is held across a whole method rather than per statement, because `graph()` runs several statements that must describe one state. Writers stay single-threaded, where an unlocked multithreaded connection would be a corrupt index waiting for a second thread |
| D-053 | `ErrorBody.message` is bounded to its `maxLength` of 1024 in `envelope.error_body`, at the HTTP boundary | accepted | The refusals that quote the offending input back — `global id '…' must have three colon-separated parts` — produced 3061-character bodies for a 3000-character id, so a refusal **violated the contract it was enforcing**. Bounded where every error body is built rather than in the repository, whose message is also a log line and a CLI string where the full id is worth keeping: 1024 characters is an HTTP fact, so it is enforced at the HTTP edge. Found by the traversal battery's over-long id, which is the only hostile input whose damage lands on the response rather than on the read |
| D-054 | `redirect_slashes=False` on the app. An **empty** id is a `404`, never a redirect to the collection | accepted | Starlette redirects `/api/sources/` to `/api/sources` by default, so a request naming **no** source was answered `200` with a page of **every** source. The failure mode is a success carrying real data, which no status-code assertion elsewhere would have caught. `/api/sources` is the only prefix in this API that is both a collection and the parent of item paths, so it is the only place the default is wrong — but the setting is applied app-wide because `include_router` nests a router's own value and ignores it (FastAPI 0.141) |
| D-055 | ADR 0001 invariant 5's structural check narrows from "no module in `x2knwldg` imports the `ui` extra" to "nothing **outside** `src/x2knwldg/server/` imports it", plus two new tests | accepted, **amends the rule `T-008` recorded** | Read literally, the old rule forbade the server from importing the framework it *is*, which would have meant hiding a `fastapi` import inside every route function to satisfy a test rather than an invariant. What invariant 5 actually states is that installing and **using the core package** must not require an optional dependency. The replacement is two rules, and together they are stricter than the one they replace: nothing outside `server/` imports the extra, **and** nothing outside `server/` imports `server` at module scope — without the second, `cli.py` could pull the whole framework in transitively while every line still passed the first. `server/__init__` resolves `create_app` through a module `__getattr__`, so even `import x2knwldg.server` does not need the extra, and a third test pins that. Re-verified on a core-only venv: 1440 passed, 403 skipped, no creep |
| D-056 | A **slash-bearing** id answers `404`, not `400 invalid_id` | accepted | A path parameter matches one segment, so `/api/entities/%2e%2e%2f%2e%2e%2fetc%2fpasswd` never reaches the route at all. Making it a `400` needs a `:path` catch-all per endpoint, which adds paths the frozen surface does not have — a contract decision, not a route's, and `test_the_served_surface_is_exactly_the_frozen_one` would refuse it. Nothing is lost: no `globalId` contains a slash by schema, nothing is read, nothing is rewritten, and the D-020 distinction between *malformed* and *absent* is still enforced where ids actually live, inside a segment. The outcome is asserted rather than assumed, so a future `:path` route would have to change the test deliberately |
| D-057 | `MemoryRepository.project_root` is **public**, matching `SqliteRepository` | accepted | The byte channel resolves an artifact's project-relative path against the repository's root, and worked over SQLite while answering `500` over the oracle, because one implementation exposed the attribute and the other kept it private. `T-104` compares the **ten protocol methods** and nothing else, so a difference outside them passes straight through a harness whose whole purpose is to catch differences. Recorded as a decision rather than a typo fix because it marks the boundary of what the equivalence proof covers: interchangeable *for the protocol* is not interchangeable *for everything a caller may touch* |
| D-058 | Enum-valued query filters are declared as plain strings in the routes and validated by the query dataclasses, not restated as framework enums | accepted | `kind` alone is 31 values from `constants.py`, and a second copy in a route is the copy that goes stale. Both paths already produce `400 invalid_request`, so the framework enum buys only a duplicated vocabulary. It would also **cost** something: a FastAPI `pattern` on an id parameter collapses `invalid_id` and `invalid_request` into one status, destroying the D-020 distinction the routes exist to preserve. The bounds that *are* restated — `limit`'s 1..500 — are restated deliberately and in one shared place (`server/params.py`), so the generated document reflects the real limits, and `PagedQuery.__post_init__` still checks them for every non-HTTP caller |
| D-059 | On a **page** of `/api/graph`, an edge is included when both endpoints pass the node filter and **at least one** is on this page. The strict "every edge's endpoints are among the returned nodes" holds for an unpaged graph, a filtered whole graph, a neighborhood, and the accumulated result of a full paged walk | accepted | An edge straddling two pages appears in both, which is what `repository/README.md` already specified and what both implementations do; the strict form asserted against a single page fails against both. Recorded because the tempting test is the wrong one, and because the Map's real requirement is narrower than the strict form and is now asserted directly: every edge touches a node on the page, and neither endpoint was excluded by the filter — the dangling-edge rule. `truncated` remains stated rather than implied, so a partial graph is never presented as the whole one |
| D-060 | The frontend routes with `HashRouter`, not `BrowserRouter` | accepted | A history-API router needs an SPA fallback rule — every unmatched path rewritten to `index.html` — on whatever serves the built assets. That server is `T-116`, which is not written yet, so choosing `BrowserRouter` here would hand the integrator a requirement discovered at wiring time. The hash router needs no server cooperation at all, so `T-116` stays what §11 says it is: a uvicorn call, a loopback refusal and an exit code. Revisit only if a real requirement (deep-link sharing, SEO — neither of which applies to a loopback-only local UI) argues for it |
| D-061 | The YouTube embed is a **click-to-load facade**: nothing is requested from the embed host until the user asks for it, the host is named on the control, and `EMBED_HOSTS` is the allowlist (`youtube-nocookie`) | accepted | ADR 0001 makes this a local-first tool that runs on loopback. An `<iframe>` mounted on render would make every Reader visit a third-party request the user did not ask for, before they have decided to watch anything — a privacy fact, not a performance one, though it is also the load the Reader does not pay. Naming the host on the button keeps the moment the tool reaches the network visible rather than implicit |
| D-062 | The Library's knowledge-unit mode reports each source's own `page.total` and **no aggregate count** | accepted | `kind`, `provenance_class` and `min_confidence` exist only on `/api/sources/{source_id}/entities`; `/api/graph` takes `provenance_class` but neither of the other two. So there is no cross-source unit list to ask, and the view asks each listed source separately. Summing those totals would report a number **no endpoint computed** — the same rule that keeps `skipped: []` from being synthesised in D-050 and keeps a missing `audit_attempts` from rendering as `0`. Widening this is a contract change (`schemas/api/v1/openapi.json` first), not a frontend decision, and it is the one contract gap Phase 1 actually hit |
| D-063 | `Source.adapter_metadata.unreadable_files[].reason` is sanitised to the project-relative path **where it is recorded**, in `YouTubeAdapter._read` | accepted, **extends D-051 to D-045's other channel** | D-051 fixed exactly this leak for the *skipped run* channel and `unreadable_files` was left carrying the absolute path `io.read_json` formats into every `JsonReadError` — so a damaged canonical file put the user's filesystem layout into a **200** body, which D-030 and ADR 0003 both forbid. An agent who built to D-051 was not wrong, only incompletely applied, so this extends that row rather than amending it. Sanitised at the point of record for D-051's own reasons: one rule, the CLI gains it too, and it becomes the same relative string the entry's `path` is keyed by. Both implementations are asserted, because SQLite stores the record verbatim and a sanitise-on-the-way-out would pass on the oracle and leak here. Found by `T-115` — `test_api_hardening.test_no_response_body_names_a_host_path` sweeps every route but only over a **healthy** project, so it never populated a field that exists only when a file is broken |
| D-064 | Exit `6` is ~~`UI_NOT_IMPLEMENTED`~~ **`UI_NOT_BUILT`**: `ui` accepted its arguments and the server is ready, but `web/dist` holds no built frontend | accepted, **amends D-040 and D-037** | `T-116` landed the server, so the old name asserts something false — the UI *is* implemented. Recorded as an amendment rather than a fact fix because it meets §6's test exactly: a wrapper built to the old row, treating `6` as "wait for the feature", would now be wrong; it should run `npm run build`. The number does not move, because what it means for a caller is unchanged in the way that matters — `6` is still "do this next", the same shape of fact as `5`, and still distinct from `1` so a missing build step is not reported as a broken install. `web/dist` is gitignored, so a fresh clone reaches this state by default and it is the **common** path, not an edge case |
| D-065 | `x2knwldg ui` **refreshes** the index on every start, rather than checking it or building it only when absent | accepted | Canvas plan §8.3 step 2 says "check or rebuild the index if needed", and nothing else in the CLI builds one — without this, a project that had never been indexed could only ever be served an honest `503`, with no command to fix it. Refresh rather than build-if-absent because `T-102`'s scan is incremental: `(mtime_ns, size)` prefilters and `io.sha256_file` arbitrates, so an unchanged project pays a directory walk, while build-if-absent would show knowledge older than the files on disk after any `finalize`. The scan's own report is printed, `skipped_runs` named rather than merely counted (D-043) |
| D-066 | Serving lives in `src/x2knwldg/server/serve.py`, and the socket is **bound before** a URL is printed or a browser opened | accepted | D-055 confines every import of the `ui` extra to `server/`, and serving needs `uvicorn` and `starlette` — putting them in `cli.py` would have broken the rule that keeps the core zero-dependency, so the module goes where the extra is allowed to live and `cli.py` reaches it lazily from inside its dispatch branch. Binding first is what makes D-037's "never prints a URL it is not listening on" true rather than intended, and it is *required* by `--port` being optional: a port the OS chooses is not knowable before the bind. A port already in use therefore fails as a refusal, before a browser opens on a URL nothing answers. `SO_REUSEPORT` is deliberately unset — it would let a second `ui` bind the same port and split requests between two servers. `create_app` is untouched: the static mount is added to the app it returns, so the generated document still equals the frozen one |
| D-067 | The "nothing outside `server/` imports it eagerly" check parses the AST and flags an import only when no function encloses it | accepted | The rule was a regex over stripped lines, which cannot tell `from .server import serve` at column 0 from the same line indented inside a function — and the second is the lazy import the CLI convention *requires*, while the first is the eager one D-055 forbids. Matching unstripped lines instead fixes that but misses a module-scope import nested in a `try:`, which is eager and would slip through. The AST distinguishes them exactly, and the checker is itself tested against all four cases, because a structural rule that silently stops matching leaves the invariant unguarded while staying green. The behavioural guard — importing the CLI in a fresh interpreter and reading `sys.modules` — is unchanged and remains what actually proves the property |
| D-068 | `x2knwldg ui` passes `index_documents=document_indexer(root)` to `refresh_index`; a scan without it builds an index whose search corpus is empty | accepted | `T-116` called `refresh_index(root)` bare. The scan then indexes sources, artifacts, entities and relations correctly and leaves `documents` and both FTS5 tables at zero — so the UI came up, every count matched, and `/api/search` answered `0` for every query. On the real sample: 86 entities, **0 documents**. No test caught it and none could have: `search.build_searchable_index`, `tests/api_harness` and the equivalence tests all pass the hook themselves, so they prove the indexer works and cannot prove the *CLI* asks for it. `test_the_command_builds_a_searchable_index` goes through `cli.main` for that reason and fails without the fix. The general lesson is the one D-052 already taught in another key: a helper that every test supplies is a helper production can forget |
| D-069 | A search hit carries its position into the Reader: `#/sources/<id>?tab=…&t=…`, with the grammar owned by `web/src/lib/readerLink` | accepted | Canvas plan §17.3 scenario 2 is "search a transcript phrase and **jump to the timestamp**", and the jump was being lost — `SourceLink` linked to `/sources/{id}` with no offset and `ReaderView` held `tab`/`seek` as local state, so the Reader opened on Overview having discarded where the hit was found. Only the external YouTube link preserved it, which answers the scenario by *leaving the application*. Query parameters rather than path segments because D-060's `HashRouter` puts the whole location after `#`, so `useSearchParams` reads them untouched, both stay optional, and no existing link is invalidated. **Seconds, not a caption id**, because seconds address everything the Reader can jump to — a caption, a unit's locator, and the player's own seek — while a caption id addresses one of the three and must be resolved to seconds anyway; `io.timestamp_url` already spells a moment in this project as seconds. The internal `t=30` and the external `&t=30s` are deliberately different spellings: they sit side by side in every hit, and one spelling would invite feeding `youtubeTimestampUrl`'s output into the internal link. A malformed or negative `t` is **ignored, never coerced** — reading `t=x` as `0` would place the reader at the start of the medium while the URL claimed otherwise, which is the invented position the transcript panel already refuses. Built and parsed by one module so the two cannot drift |

### ⚠️ D-011 is **additive** — do not "clean up" the 2-part ID

`.claude/commands/kg_navigator.md` **mandates** the 2-part form `<video-id>:<knowledge-unit-id>` for `output/library/graph.json` nodes, and `library.rebuild_library`, through `ids.make_library_id`, emits exactly that.

**Rewriting `library.py` to emit 3-part IDs breaks that skill.**

Required approach:

- `library.py` keeps `id` in its current **2-part** form.
- It **gains** an additive `source_type` field and a 3-part `global_id`.
- The index, API, and board files use the **3-part** form as identity.
- No canonical file loses a field.

A future session must not consolidate these into one form without also updating `kg_navigator.md`.

---

## 7. Definition of done and checks

### 7.1 Per task
- Tests proportionate to risk, written and run.
- No canonical file or `raw/` evidence modified.
- Cache changes never reported as data achievements.
- New architectural decisions recorded in §6 and canvas plan §19.

### 7.2 Regression baseline
```bash
.venv/bin/python -m pytest -q               # expect: 2141 passed, 0 failed, 36 subtests (plus new tests)
git diff --stat -- output/                  # expect: empty, always
.venv/bin/python tests/fixtures/runs/build_fixtures.py
git diff --stat -- tests/fixtures/runs/     # expect: empty — regeneration is byte-identical
.venv/bin/python tools/generate_api_types.py --check   # expect: types.d.ts is up to date
(cd web && npm ci && npm run typecheck)     # expect: silent — tsc --noEmit, risk R17
(cd web && npm test && npm run build)       # expect: 113 passed, 12 skipped; then a clean build
```

`--check` duplicates `tests/test_api_types.py::test_the_committed_declarations_are_current`;
it is listed because it names the fix in its own error message.

**Per-task test counts drift; count them, do not trust them.** The counts quoted in the
§5 task rows are *collected pytest items*, which is what the suite reports and what
parametrisation multiplies — not the number of `def test_` lines, which is much smaller
(106 collected from 24 definitions in `tests/test_index_schemas.py`, 132 from 43 in
`tests/test_ids.py`). Re-derive one without running anything:

```bash
.venv/bin/python -m pytest --collect-only -q tests/test_index_schemas.py | tail -1
```

Every count in §5 and §7.2 is a snapshot. Phase 1 fans out to four tracks and Track D
owns `tests/`, so these numbers move under any session that reads them. Treat a mismatch
as staleness in this file, not as a regression, and re-run the command before quoting a
figure. Every count in this file moved twice in a single day: `test_index_schemas.py` went
58 → 83 → 106 and `test_ids.py` 51 → 67 → 132 across two waves of agents. The figures here
were counted this way after the second wave, 2026-08-31.

CI runs all of these on every push and pull request
([`.github/workflows/ci.yml`](../.github/workflows/ci.yml)), across five jobs:

| Job | What it proves |
|---|---|
| `tests` | The suite on Python **3.10, 3.12, 3.13 and 3.14**, installed as `.[dev,legacy]`. 3.10 is the `requires-python` floor; 3.14 is the interpreter in daily use here and was missing, so every number measured locally came from a version CI never ran |
| `zero-dependency` | The core package installs and tests with **no** extras (ADR 0001 invariant 5), and fails if an optional distribution creeps into that install |
| `extras` | All **five** declared extras — `youtube`, `mcp`, `ui`, `legacy`, `dev` — each installed, `pip check`ed, imported, and run against the suite. `dev` and `legacy` were the only two any job installed, so three of the five could have been broken with nothing to say so. `tests/test_ui_scaffold.py::test_ci_installs_every_declared_extra` fails if an extra is added to `pyproject.toml` without a row here, and the `mcp` row additionally asserts the server builds with 10 tools against the installed `mcp` |
| `fixtures` | The committed run fixtures regenerate byte-identically (`T-006`, R11) |
| `web-typecheck` | `tsc --noEmit` over `web/` and the generated declarations (R17, D-038) |

**The zero-dependency check (`T-009`), reproducible locally:**

```bash
python3 -m venv /tmp/bare && /tmp/bare/bin/pip install . pytest
for p in jsonschema openapi-spec-validator networkx pyvis yt-dlp fastapi uvicorn; do
  /tmp/bare/bin/pip show "$p" >/dev/null 2>&1 && echo "LEAKED: $p"
done                                        # expect: no output
/tmp/bare/bin/python -m pytest -q           # expect: 1438 passed, 5 skipped, 36 subtests
```

The 5 skips are the `jsonschema` and `legacy` tests, which skip by design. Every
`tests/test_ui_scaffold.py` test runs here — the scaffold's own guards must hold
on the install they are about.

> **Run this one. It is not a formality.** Re-measured 2026-08-31 for the first time
> since the suite was 515, it **failed** — and the failure was in the suite, not the
> package. `test_no_captions_asks_for_a_transcript` monkeypatched
> `youtube.process_youtube_url`, but `process` probes `YOUTUBE_DEPENDENCIES` *before* it
> calls the fetch and refuses outright when none of them import — correct behaviour, and
> the subject of its own test. So on the install ADR 0001 invariant 5 is *about*, the test
> never reached the branch it names: stdout was empty and `json.loads` raised. Its
> neighbour `test_a_name_collision_is_not_reported_as_transcript_required` was worse — it
> **passed for the wrong reason**, because the missing-extra error satisfies all four of
> its assertions without ever reaching the collision. Both now pin the probe through
> `_pretend_the_youtube_extra_is_installed`, and the collision test asserts the message is
> *not* the missing-extra one. The lesson generalises: **a test that monkeypatches past a
> dependency probe must pin the probe**, or it silently tests nothing on the install with
> no extras. The full-extras suite cannot see this class of defect — it was green at 1348
> throughout.

### 7.3 Re-verify the numbers in §3
```bash
python3 -c "import json;print(len(json.load(open('output/pqlWNihgdjI/knowledge_units.json'))['units']))"
python3 -c "import json;print(json.load(open('output/pqlWNihgdjI/coverage.json'))['status'])"
python3 -c "import json;print(json.load(open('output/pqlWNihgdjI/validation.json'))['status'])"
cat output/library/status.json
# status.json now reports runs_discovered / runs_indexed / runs_skipped / skipped_runs[]
# / incomplete_runs[] beside the counts, and each videos.json entry carries problems[]
# (D-043). Read runs_indexed, not videos, for "how many runs are in the library".
# NOTE: the committed output/library/ predates D-043 and will change on the next rebuild.

# The frozen API surface (T-005): 11 GET endpoints, and every payload a $ref into schemas/v1/.
python3 -c "
import json; d = json.load(open('schemas/api/v1/openapi.json'))
print(len(d['paths']), 'paths;', len(d['components']['schemas']), 'components')
print(sorted({m for ops in d['paths'].values() for m in ops}))"

# The same numbers, reached independently through the adapter (T-004).
.venv/bin/python -c "
from pathlib import Path
from x2knwldg.adapters import adapt_project
print({k: len(v) for k, v in adapt_project(Path('.')).by_model().items()})"

# And once more through the T-007 seam, which is what the API will call.
.venv/bin/python -c "
from pathlib import Path
from x2knwldg.repository import MemoryRepository
print(MemoryRepository.from_project(Path('.')).status().payload()['counts'])"

# And a fourth time through the SQLite index, which is what a route will call
# once T-105 wires it. Writes .x2knwldg/ and nothing else; delete it freely.
.venv/bin/python -c "
from pathlib import Path
from x2knwldg.index import build_index, SqliteRepository
from x2knwldg.index.search import document_indexer, search_retrieval
from x2knwldg.repository import SearchQuery
root = Path('.')
build_index(root, index_documents=document_indexer(root))
repo = SqliteRepository.open(root, search=search_retrieval)
print(repo.status().payload()['counts'])
print({q: repo.search(SearchQuery(q=q, limit=1)).total for q in ('learning', 'model', 'the')})"
# expect: the same 1/85/86/118, and {'learning': 4, 'model': 19, 'the': 258}
```

### 7.4 End-to-end scenarios (canvas plan §17.3)

**Walked 2026-09-02** against `x2knwldg ui` serving the three committed fixtures, driven
through a real headless browser rather than through jsdom — the point of the exercise being
to test what a person meets, not what a test harness meets. It earned its keep twice:
scenario 2 was unwalkable on the first attempt because search returned nothing at all
(D-068), and then failed a second time because the jump was discarded at the click (D-069).
2141 passing tests had reported neither. Both are fixed and the scenario was re-walked;
each now has a test that fails without its fix.

| # | Scenario | Verdict |
|---|---|---|
| 1 | Open a source with `PARTIAL` status and see the real warning | ✅ **pass** — `Overall/Validation/Coverage: PARTIAL`, `audit_attempts: 3`, both file paths cited, and the panel states in the UI that the values are copied and never raised toward `PASS`. `fail-run` shows `Validation: FAIL` beside `Coverage: PASS` unreconciled, which is what R11's fixture exists to prove |
| 2 | Search a transcript phrase and **jump to the timestamp** | ✅ **pass** — after D-068 (search returned nothing at all) and D-069 (the jump was lost at the click). Re-walked: the hit links to `#/sources/…?tab=transcript&t=30`, the Reader opens on **Transcript**, and the caption covering `0:30` is scrolled to and marked with a rail, a weight change and `aria-current="location"`. The URL is the state, so the position survives a reload and can be shared. A malformed or negative `t` is ignored rather than seeking to zero, and an unknown `tab` falls back to Overview — both checked in the browser |
| 3 | Select a knowledge unit and see its actual evidence | ✅ **pass** — statement, evidence excerpt, locator (`0:00 – 0:30`, `segment_id`, `artifact_id`), `Play from here`, and the canonical file named. The derived unit reads *No locator is recorded for this unit* rather than borrowing one, and the two classes differ by glyph (◆/◇), label, **and** rail style (solid/dashed), not by colour alone |
| 4 | Move an entity from Map to Canvas | ⛔ **out of scope** — Phase 2/3 |
| 5 | Create a user relation without touching any canonical file | ⛔ **out of scope** — Phase 3 |
| 6 | Draw with the pen, reload, strokes survive | ⛔ **out of scope** — Phase 4 |
| 7 | Delete the cache, rebuild, boards intact | ◐ **half met** — the cache half passes: `.x2knwldg/` deleted, the command rebuilt it on the next start to identical counts, search still answered, and nothing under `output/` was modified. *Boards intact* has nothing to assert against until Phase 3 |

Also checked while the browser was open, because both are Phase 1 claims that only a
rendered page can settle: the Persian switch flips `lang`/`dir` to `fa`/`rtl` and the layout
mirrors — sidebar, tabs and every label/value pair — while Latin identifiers, paths and URLs
stay LTR inside it (D-012, D-014); and the embed stays a facade, naming its host and
requesting nothing until asked (D-061).

**Phase 1's gate is met** for every scenario the phase owns: 1, 2 and 3 pass, and 7's cache
half passes with *boards intact* left to Phase 3. Scenarios 4–6 belong to Phases 2–4.

The lesson worth carrying into Phase 2: both defects lived in the seam between components
that were each correct and each well tested. `refresh_index` worked and the CLI did not ask
it for a corpus; the Reader could seek and the hit did not tell it where. A suite of unit
tests cannot see a gap that exists only between two of its subjects — walking the product
can, and did.

---

## 8. Agent parallelism model

### 8.1 Phase 0 is a serialization point

Phase 0 produces the entity, ID, and API contracts that every other track consumes. **Running parallel agents during Phase 0 guarantees rework.** One focused agent, start to finish.

### 8.2 After the Phase 0 gate — four tracks, disjoint file ownership

Exclusive file ownership is the mechanism that makes concurrent agents safe. An agent writes **only** inside its own paths.

| Track | Owns exclusively | Scope |
|---|---|---|
| **A — Indexer** ✅ **done** | `src/x2knwldg/index/` | SQLite schema, migrations, scanner, FTS5, incremental hashing — behind `repository.IndexRepository`. Delivered 2026-09-01 (`T-101`–`T-104`); see [`index/README.md`](../src/x2knwldg/index/README.md) |
| **B — API** | `src/x2knwldg/server/` | FastAPI routes, path safety, range requests, versioned responses |
| **C — Frontend** ✅ **done** | `web/` | Vite/React scaffold, tokens, i18n/bidi shell, Library, Reader. Delivered 2026-09-02 (`T-109`–`T-114`); see [`web/README.md`](../web/README.md) |
| **D — Fixtures & tests** ✅ **done** | `tests/` | Labeled `PARTIAL`/`FAIL` fixtures, contract tests, rebuild equivalence. Delivered 2026-09-02 (`T-115`) |

**What makes A, B, and C genuinely concurrent:** the API contract is frozen in `T-005` and TypeScript types are generated from it, so Track C develops against a mock and never waits on Track B. Tracks A and B meet only at the repository interface fixed in `T-007`, which now exists:
[`IndexRepository`](../src/x2knwldg/repository/README.md) with a working reference
implementation behind it, so **Track B can start before Track A finishes**.

### 8.3 Contention points — integrator only

These files are small, shared, and merge-hostile. **No track agent edits them.**

[`.github/CODEOWNERS`](../.github/CODEOWNERS) encodes this table and §8.2, so a PR that
crosses a boundary asks for a review instead of merging quietly. It is a tripwire, not a
lock: §8.2 is still the rule. Change the paths there and here together, never one alone.

- `src/x2knwldg/cli.py` — the `ui` subcommand. `T-008` left a refusing stub there; `T-116`
  replaced its body (2026-09-02) and no other task touches it. Note that `T-116` also added
  `src/x2knwldg/server/serve.py`: Track B's directory, entered by the integrator **after**
  Track B was complete, because D-055 forbids `cli.py` from importing the `ui` extra at all
- `pyproject.toml` — the `ui` extra
- `.gitignore`
- `.github/workflows/ci.yml` — small, shared, and merge-hostile. Track C may change what
  `npm run typecheck` covers, but the job itself is integrator-owned
- `docs/` — including this file
- `src/x2knwldg/library.py` — single owner, load-bearing for `kg_navigator` (see §6)
- `src/x2knwldg/repository/base.py` — the A↔B contract. Widening it is a contract change
  (`schemas/api/v1/openapi.json` first, ADR 0002 second), not a track's local decision

### 8.4 What must stay sequential

- **Phase 3 Canvas and Phase 4 pen.** Both mutate the same React Flow surface and pointer-event handling. Run sequentially, or in isolated git worktrees with a deliberate merge.
- **Schema migrations.** One writer, versioned, ever.
- **`library.py` ID generation.** Single owner.

### 8.5 Recommended concurrency

**3–4 agents maximum.** That is what the track split naturally supports. Beyond it, agents contend on §8.3 files and coordination cost exceeds the speedup.

---

## 9. Risks — delta from canvas plan §18

| Risk | Status | Mitigation |
|---|---|---|
| **R7** No valid graph data for development | ✅ **Resolved** | Real `PASS` extraction exists: 69 units, 56 relations, 17 concepts |
| **R11** No `PARTIAL`/`FAIL` fixture, so honest-status UI is untestable | ✅ **Resolved** | `T-006` delivered `tests/fixtures/runs/{pass,partial,fail}-run`, labelled test-only. `fail-run` is deliberately awkward: report, graph, and Obsidian export all exist while `validation.json` says `FAIL` |
| **R12** Dual ID vocabulary (2-part in library files, 3-part in index) drifts | 🟢 **Mitigated** | `T-003` made the two forms exact inverses and round-trip tested them; `T-004` removed the remaining f-string risk on the index side — every id in `src/x2knwldg/adapters/` is built through `ids.py`, and `base.check_records` re-asserts all three invariants at production, not only in tests. `adapt_library` also refuses a concept whose stated `global_id` disagrees with its `library_id` |
| **R13** `finalize_run` triggers a full `rebuild_library` over *all* sources every time — cost grows linearly | 🟡 Watch | Acceptable at current scale; revisit when source count grows. Do not fix speculatively |
| **R14** No path-traversal guard in existing `query.py` / `mcp_server.py` joins | 🟢 **Mitigated** | Every join now goes through `pipeline.resolve_run_dir`, which rejects rather than sanitises (D-020), with traversal tests in `tests/test_core_pipeline.py::RunLookupTests`. `T-108` must use the same resolver for HTTP path parameters — [ADR 0003](adr/0003-reject-unsafe-identifiers.md) makes that binding and supersedes ADR 0001 invariant 8, which named the rewriting sanitiser instead |
| **R15** Absolute host paths baked into `library/status.json` and `library/videos.json` | 🟢 **Mitigated** | `library.py` emits an additive `relative_path` beside each absolute `path`, and `T-004` closed the reading side structurally: every path in an index record goes through `adapters.project_relative`, which **refuses** a path outside the project root rather than storing it. `adapt_library` does not read `status.json` or `videos.json` at all. Tested by `test_no_record_carries_an_absolute_path` and `test_a_run_outside_the_project_root_is_refused` |
| **R16** `value` field on statistic units is polymorphic (`int` \| `list[float]`) | 🟡 Watch | Cannot map to one SQL column — store as JSON text, keep the canonical file authoritative. `EntityRef` has no `value` field and `additionalProperties: false`, so the adapter cannot carry it into the index by accident |
| **R17** Nothing in CI proves the generated `types.d.ts` is *valid* TypeScript | ✅ **Resolved** | `T-008` brought Node into CI: the `web-typecheck` job runs `npm ci && npm run typecheck` (`tsc --noEmit`). Two details make it real rather than decorative, and both are asserted by `tests/test_ui_scaffold.py`: `web/tsconfig.json` keeps `skipLibCheck: false`, without which `tsc` skips every `.d.ts` — including the only file the job exists to check — and lists `../schemas/api/v1/types.d.ts` as a root file so it is checked whether or not anything imports it. Verified by injecting a bad type into the generated file and watching `tsc` fail (D-038). **Turning `skipLibCheck` on reopens this risk silently** |
| **R18** D-028's additive search fields exist only as a test helper | ✅ **Resolved** | `T-007` moved them into `MemoryRepository.as_api_hit`, which is the code path `T-106` serves and the one `tests/test_api_contract.py` now exercises — one implementation, not two. It also stopped hard-coding `youtube`: the source type is read from the indexed source, so a hit from a source the index does not hold gets `source_id: null` and `global_id: null` rather than an address that resolves to nothing |

Risks 1–6 and 8 from canvas plan §18 remain as written.

---

## 10. Reuse — do not reimplement these

| Existing code | Use it for |
|---|---|
| `io.write_json` | **Already atomic** (same-dir temp + `os.replace`) — satisfies canvas plan §15 outright. Note: Markdown/report writes use plain `write_text` and are *not* atomic |
| `io.sha256_file` | Incremental index change detection |
| `io.timestamp_url` | YouTube deep links; `&t=<int>s` output is contract-locked by `tests/test_core_pipeline.py` |
| `pipeline.validate_run` | The **only** legitimate source of run status. Read it; never recompute |
| `pipeline.resolve_run_dir` | Resolve a run directory from an externally supplied id. It **rejects** an unsafe id; use it for every HTTP path parameter (D-020, [ADR 0003](adr/0003-reject-unsafe-identifiers.md)) |
| `pipeline._safe_identifier` | Guard the id a run is *created* at. **Never for a lookup, and never for an id that arrived from outside the process** — that is `resolve_run_dir`'s job, because only it also proves the resolved path stays under the output root. [ADR 0003](adr/0003-reject-unsafe-identifiers.md) forbids substituting any other check for it |
| `pipeline.project_root` (`T-008`) | Resolve the project root: explicit argument, then `X2KNWLDG_PROJECT_ROOT`, then the working directory. The MCP server and the `ui` command both call it. Do not re-read the env var anywhere else (D-039) |
| `cli.VERDICT_EXIT_CODES` / `cli.verdict_exit_code` | The one mapping from a run verdict to an exit code, and the `EXIT_*` constants beside it. Never write an integer literal for an exit code, and never give a new meaning to `2` — it belongs to `argparse` (D-040). The table is in [`README.md` § Exit codes](../README.md#exit-codes) and in `x2knwldg --help` |
| `constants.MAX_AUDIT_ATTEMPTS` | The three-attempt coverage-repair cap. `validators.validate_coverage` enforces it against the required `coverage.json` `audit_attempts` field; do not re-state the number anywhere else |
| `constants.SEGMENT_TARGET_SEC` / `SEGMENT_MIN_SEC` / `SEGMENT_MAX_SEC` / `SEGMENT_OVERLAP_SEC` | The segmentation timing contract, and coupled: `OVERLAP < MIN <= TARGET <= MAX`. `segmenter.create_segments` defaults to them and re-checks the relation on whatever it is actually given; `pipeline.import_transcript` takes `TARGET` and `OVERLAP` from here too. Never write one of these numbers as a literal |
| `constants.COVERAGE_WINDOW_SEC` | The coverage window width (`coverage.create_pending_coverage`). It is written into `coverage.json` as `window_size_sec`, so **its type is part of the file format** — keep it an `int`, or every stored document gains a `.0` |
| `constants.MAX_CAPTION_GAP_SEC` | The largest silence between captions that is not reported as a transcript gap (`transcripts.transcript_integrity`) |
| `constants.TIME_TOLERANCE_SEC` | The **one** epsilon for comparing two times in seconds, used throughout `validators`. Timestamps are parsed from millisecond text and round-tripped through JSON, so an exact `==` is a coin flip. There were six copies of this constant; six chances for two comparisons to disagree about whether the same pair of times matches. Do not write a seventh |
| `io.read_json` / `io.read_json_or_reason` | The package's **two** JSON readers, and there were five. `read_json` is strict and raises `JsonReadError` naming what is wrong — use it where a damaged file means stop. `read_json_or_reason` returns `(document, None)` or `(None, reason)` — use it where the caller must carry on and *state* the damage, as `library.rebuild_library` does. There is one sibling, for the callers that must also tell *absent* from *broken*: `adapters.base.read_optional_json_or_reason` returns `(None, None)` for a file that is not there and a reason only for one that is there and will not read (`read_optional_json` is now just its first element). So: `io.read_json` when the caller must stop, `io.read_json_or_reason` when it must carry on, the adapters' sibling when it must also distinguish "not there" from "broken". Do not add a sixth reader, and do not catch `json.JSONDecodeError` directly |
| `cli.LOOPBACK_HOSTS` (`T-008`) | The accepted bind addresses. `T-116` kept the check *before* the dependency probe, because otherwise the invariant lapses on any machine without the `ui` extra — the machines where it is least likely to be noticed. `server.serve.bind` resolves these three names rather than re-deciding them, and `test_every_accepted_loopback_host_can_actually_be_bound` proves all three are bindable, so none is accepted-but-unusable |
| `library.rebuild_library` | Generalize **additively**; do not rewrite. Its `status.json` now reports `runs_discovered`, `runs_indexed`, `runs_skipped`, `skipped_runs[]` and `incomplete_runs[]` beside the counts, and every `videos.json` entry carries `problems: []` — read `runs_indexed`, never `videos`, when you mean "how many runs are in the library" (D-043) |
| `query.search_knowledge` | Its two result shapes are the de-facto API contract to preserve while FTS5 replaces the linear scan |
| `ids.py` (`T-003`) | Every identifier operation: build, parse, convert between the global and library forms, and enforce the three cross-field invariants. Never assemble an id with an f-string |
| `adapters/` (`T-004`) | The **only** way to turn a canonical run into index records. `adapt_run` for one run, `adapt_library` for the cross-source concepts, `adapt_project` for everything — the scan `T-102` makes incremental. Pass `hash_artifacts=True` for `io.sha256_file` digests. Do not re-read canonical files into ad-hoc dicts elsewhere |
| `Source.adapter_metadata.unmappable_artifacts` / `.unreadable_files` | The adapters' two diagnostic channels, and the answer to the "silent drop" finding that recurs through this audit (D-045). `unmappable_artifacts`: a generated `vault/` note whose filename cannot spell an id, skipped and named. `unreadable_files`: a canonical file present but damaged, named so a missing count is not read as a zero. Each carries `path` + `reason`, is free-form by schema, and is **absent** when there is nothing to report — an empty list reads like an unread finding. A UI showing a source must surface both rather than let the omission disappear between the run and the Reader |
| `adapters.project_relative` | Every path that reaches an index record or an API response. It refuses a path outside the project root, which is what keeps risk R15 closed |
| `schemas/api/v1/openapi.json` (`T-005`) | The **specification** for `T-105`–`T-108`, not a suggestion. Eleven `GET` endpoints, response bodies `$ref`-ing `schemas/v1/`. Do not add an endpoint, a field, or a status code without editing this document and its tests first |
| `schemas/api/v1/types.d.ts` (`T-005`) | The frontend's types. Import it; never hand-edit it. Regenerate with `python tools/generate_api_types.py` |
| `web/src/api/contract.ts` (`T-008`) | The **only** place `web/` names the generated declarations. Frontend code imports API types from here, never by reaching up the tree (D-038) |
| `web/src/lib/readerLink.ts` (`T-116`, D-069) | The Reader's URL grammar — `readerPath` to build one, `parseTab`/`parseSeconds` to read one, `captionIndexAt` to resolve an offset to a caption. Anything linking into the Reader calls it rather than assembling a path, because a grammar written in one place and read in another is two implementations. `parseSeconds` **ignores** what it cannot read; do not make it return `0` |
| `repository/` (`T-007`) | The **only** thing `T-105`–`T-108` read. No route opens a database, a canonical file, or a run directory. `T-101`–`T-104` implement `IndexRepository` over SQLite without widening it; `MemoryRepository` is what Track B builds against until they do, and the oracle `T-104` proves equivalence against |
| `repository.encode_cursor` / `decode_cursor` | The one cursor encoding. The SQLite implementation issues its keyset cursors through it so both implementations produce the same token for the same position |
| `repository.matches_entity` / `matches_relation` / `matches_source` / `relation_belongs_to_source` | The definition of every filter the contract exposes. Where a SQL `WHERE` clause disagrees with them, they are right |
| `repository.graph_nodes` | The **one** rule for which nodes a source's graph is drawn over — an entity of the source, or an endpoint of a relation `relation_belongs_to_source` accepts (D-041, [ADR 0004](adr/0004-graph-membership-and-search-corpus.md)). `T-101`–`T-104` inherit it; do not re-derive it in SQL |
| `query.run_documents` / `query.rank_documents` | The searchable form of a run, and the ranking over it. `MemoryRepository` builds its corpus from these once per instance (D-042) and `query.search_knowledge` is the CLI's caller of the same pair. `T-103` replaced the corpus, **not** these shapes: `index.search` retrieves candidates and hands them to `rank_documents` unchanged, so the scoring rule has exactly one implementation (D-046). Widening `run_documents`' `searchable` join widens the index too, and needs no second edit: `refresh_index` re-indexes every source on each pass, so the change lands even when no file under `output/` moved. What it *does* move is `T-104`'s measured search totals, which are constants in two test files — expect to update them, and read D-047 before adding a field, because the question is precision rather than recall |
| `constants.py` | The real controlled vocabulary: 22 source kinds, 8 derived kinds, 16 relation types, 10 omission reasons |
| `artifacts.SECTION_ORDER` | A ready-made 12-section UI grouping taxonomy for knowledge kinds |

**Conventions to follow:** lazy optional imports inside the dispatch branches of `cli.main` (and `cli._run_process`) so the core stays zero-dependency · `pipeline.project_root` as the **only** root resolution — it reads `X2KNWLDG_PROJECT_ROOT` itself, and D-039 removed the second read from `mcp_server.py`, so no other module may re-read the env var · `config/*.local.json` tracked-example / ignored-local pattern.

**Citation rule (adopted after the Phase 0 audit).** Cite a **symbol**, never a `file:line`. The audit found roughly 3 in 5 line citations across these documents already stale after one session, and three more rotted while its findings were being fixed — one of them mid-session. A line number rots silently and sends the reader somewhere plausible and wrong; a symbol that moves or disappears makes `grep` return nothing, so the staleness announces itself. `tests/test_docs_citations.py` enforces this over every Markdown file in the repository. A line whose subject *is* a rotted citation — ADR 0003 exists partly because `_safe_identifier`'s citation had become a blank line — carries an HTML comment marking it as history — the `citation:history` marker `tests/test_docs_citations.py` defines — and is allowed.

**Vocabulary the Map must style:** `derived_from` and `expresses_concept` are library-only synthetic relations that are **not** in `RELATION_TYPES`. In the current data they are the two most common edges (45 and 17 of 118).

---

## 11. Next step

**All four Phase 1 tracks are complete** (2026-09-02). The SQLite index serves the whole
`IndexRepository` (`T-101`–`T-104`); all **eleven** frozen endpoints are served over it
(`T-105`–`T-108`, plus `T-117` for the two graph paths the backlog had left unassigned);
`web/` holds a Library and a Reader built against the real API (`T-109`–`T-114`); and
`T-115` closed the two gaps Tracks A and B did not own.

**Every Phase 1 task is done and the scenarios have been walked** (§7.4, 2026-09-02).
`x2knwldg ui` serves the Library and the Reader on loopback over a freshly refreshed index.

**The gate is met for every scenario Phase 1 owns.** It took two fixes the walk found and
the suite could not:

- **D-068** — `ui` built an index with an **empty search corpus**. Every count on every page
  was right and every query returned nothing. Each existing test supplied the hook the CLI
  had forgotten, so each proved the indexer worked and none could prove the CLI asked.
- **D-069** — the jump in *jump to the timestamp* was discarded at the click. The Reader
  could seek and the hit knew the offset; nothing carried it between them.

Both lived in a seam between components that were individually correct and individually well
tested, which is the pattern to expect again in Phase 2.

**Next: Phase 2 — Map** (`T-201`). Its consumers are already served and tested but uncalled:
`GET /api/graph`, `GET /api/graph/neighborhood/{id}`, and `/api/entities/{entity_id}`. Read
D-059 before drawing a paged graph. `readerLink` is the precedent for any new addressable
view: one module owning a grammar that is built in one place and read in another.

§10's note matters there too: `derived_from` and `expresses_concept` are library-only
synthetic relations, absent from `RELATION_TYPES` and the two most common edges in the real
data (45 and 17 of 118) — the Map must style what the data actually contains.

**What Track B changed that a later track must not undo:**

- **`redirect_slashes` is off** (D-054). Turning it back on makes an empty id serve the whole
  collection again, and the failure mode is a `200` with real data.
- **The reader's lock is load-bearing** (D-052). `check_same_thread` is lifted, so removing
  the lock trades a loud failure for a corrupt read. Writers must stay single-threaded.
- **Routes catch no `RepositoryError`.** The repository chooses the status (D-030); a route
  that catches and re-raises puts the taxonomy in eleven places.
- **Enum filters are not restated in routes** (D-058). A FastAPI `pattern` on an id parameter
  would collapse `invalid_id` into `invalid_request` and destroy the D-020 distinction.
- **`web/tsconfig.json` keeps `skipLibCheck: false`.** Turning it on reopens R17 in silence.

**What Tracks C and D changed that a later track must not undo:**

- **The client's endpoint path table is typed against `Endpoints`** (`T-109`). It is what
  makes "no endpoint was invented" a compiler guarantee rather than a review promise;
  loosening its type returns that claim to prose.
- **`contract.ts` stays the only place `web/` names the generated declarations** (D-038), and
  it re-exports with `export type *` so nothing about the contract reaches the bundle.
- **The logical-CSS guard is a test, not a convention** (`T-110`). `web/src/styles/logical.test.ts`
  fails on `margin-left` and friends; deleting it turns D-012 back into an intention, and a
  bidi retrofit is exactly the expense D-012 exists to avoid.
- **Provenance keeps two non-colour signals** (`T-113`, ADR 0001 invariant 10). The test
  asserts glyph and border style **differ** across the three classes, so restyling that
  collapses them is a failure rather than a regression nobody sees.
- **No aggregate is synthesised where no endpoint computed one** (D-062), and no status is
  reconciled toward `PASS` (`T-115`). Both are asserted over *both* repository
  implementations.
- **`test_a_damaged_file_is_reported_without_naming_the_host` must keep asserting that the
  reason still states the damage** (D-063). Sanitising a leak by deleting the sentence would
  satisfy a bare no-host-path assertion and silently close D-045's diagnostic channel.

**Two things the parallel run taught, worth repeating for C and D:**

- **Test against the implementation that ships, not only against the oracle.** D-052 was a
  bug in which every HTTP request over SQLite answered `503`, in production, while every
  memory-backed test passed. A suite that defaults to `MemoryRepository` was green against a
  server that could not serve a single request. `test_every_endpoint_answers_over_sqlite_not_only_over_memory`
  exists so that cannot recur.
- **A hostile-input test can end up grading the client.** httpx resolves `..` and rejects
  control bytes before a request leaves, so the obvious traversal battery proved nothing
  about the server for those cases. They are now split three ways: ids that reach the wire,
  ids checked at the repository boundary, and raw paths handed straight to the ASGI app.

**One limitation carried forward unchanged.** A single-caption segment gets no overlap and
cannot: overlap is re-emitted captions, and a segment holding one caption has only itself to
re-emit. It is in `segmenter`'s module docstring and pinned by
`tests/test_segmenter_hardening.test_a_single_caption_segment_carries_no_overlap`, alongside
the fact that `overlap_sec` is a **floor**, quantised up to one caption length. The one
honest improvement left is to record the *realised* overlap in each segment record, which
changes `segments.json` and is a decision for whoever owns that schema, not a repair.
