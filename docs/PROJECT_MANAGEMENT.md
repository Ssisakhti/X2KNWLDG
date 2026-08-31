# X2KNWLDG Knowledge Canvas — Project Management

**Status:** active execution tracker
**Last updated:** 2026-08-31 · **Phase 0 complete** — `T-001`–`T-009` done, exit gate met. Phase 1 may fan out to the four tracks of §8.2
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

**Language rule (D-014).** All project documentation is written in **English** — this file, the canvas plan, ADRs, `README.md`, `AGENTS.md`, `WORKFLOW.md`, `CLAUDE.md`, code comments, and commit messages. Persian is used in exactly two places: the **application UI** (switchable, English default — D-012) and **knowledge content extracted for the user** (knowledge units, reports, vault content, and answers delivered to the user, which follow the source material). Code that *supports* Persian content is expected and correct — for example `segmenter.py:7` uses the Arabic question mark for sentence-boundary detection.

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
| `validation.json` status | **`PASS`** (all 5 sections) |
| `output/library/` | 1 video, 69 knowledge nodes, **17 canonical concepts**, 118 edges — unchanged by the `T-003` rebuild, which only added fields. ⚠️ **The committed tree predates D-043 and has not been regenerated.** Its `expresses_concept` edges still carry a fabricated `confidence: 1.0` (verified by reading the adapter's output over it), and `status.json` lacks `runs_discovered` / `runs_indexed` / `runs_skipped` / `skipped_runs[]` / `incomplete_runs[]`. The next `x2knwldg rebuild-library` will change these files; nobody has run it |
| Index projection (`T-004`) | The adapter maps the sample to **1 source, 85 artifacts, 86 entities, 118 relations** — 69 knowledge units + 17 concepts, and 56 canonical + 62 synthetic edges |
| API contract (`T-005`) | **11 endpoints, all `GET`**, frozen in [`schemas/api/v1/openapi.json`](../schemas/api/v1/README.md); 24 components, every response body a `$ref` into `schemas/v1/`. Valid against the OpenAPI 3.1 meta-schema, external `$ref`s resolving from disk. **925 lines** of generated, committed TypeScript in `types.d.ts`, checked against `tsc --strict` |
| Repository seam (`T-007`) | [`src/x2knwldg/repository/`](../src/x2knwldg/repository/README.md): `IndexRepository`, **10 methods** serving the 11 frozen endpoints, plus `MemoryRepository` over `adapt_project`. Stdlib-only. Fixed by [ADR 0002](adr/0002-index-repository-seam.md) |
| Scaffold (`T-008`) | [`web/`](../web/README.md) holds TypeScript only — `package.json`, `package-lock.json`, `tsconfig.json`, `src/api/contract.ts`. `npm run typecheck` (`tsc --noEmit`) passes and is a CI job. The `ui` extra is `fastapi` + `uvicorn`; `x2knwldg ui` exists as a refusing stub |
| Test baseline | **1287 passed, 0 failed, 36 subtests** (`.venv/bin/python -m pytest -q`, all extras installed) — reported 2026-08-31 by the coordinator after the five-agent second wave; 765 before it, 515 before that. Core package with no extras at all: **333 passed, 4 skipped** (not re-measured since; re-run the bare-venv check below before quoting it) — the `jsonschema` and `legacy` tests skip cleanly, and the stdlib-only `tests/test_api_types.py`, `tests/test_repository.py`, and `tests/test_ui_scaffold.py` all run |
| Toolchain | Node 26.5.0 · npm 11.17.0 · Python 3.14.6 · SQLite 3.53.4 with **FTS5 available** |

> **Correction of record.** Canvas plan §4 previously stated the sample had empty
> `knowledge_units.json` / `relationships.json` / `graph.json` and `coverage = PARTIAL`.
> That was stale. The sample run is **complete and `PASS`**. §4 has been corrected.
>
> Two consequences:
> - **Risk 7 (no valid graph data for development) is resolved** — real graph data exists.
> - The inverse gap is now open: **no `PARTIAL`/`FAIL` fixture exists**, so those UI
>   states are currently untestable. See `T-006`.

**No UI behaviour has been built yet.** `web/` exists but holds no application — no Vite, no
React, no component; there is no FastAPI code and no SQLite index. `x2knwldg ui` resolves a root,
refuses a non-loopback host, and then reports `UI_NOT_IMPLEMENTED`.
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
| **1** | Read-only Library & Reader | `not started` — **gate open, may fan out** | ✅ Tracks A/B/C/D | Search works; status honest; rebuild is equivalent |
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

| ID | Task | Track | Flag |
|---|---|---|---|
| `T-101` | SQLite schema + explicit versioned migrations | A | `P` |
| `T-102` | Scanner over `output/*/metadata.json`; incremental via `io.sha256_file`; skip dotfiles and `library/` | A | `P` |
| `T-103` | FTS5 tables for KU `content`, `normalized_statement`, `derivation_note`, `evidence_excerpt`, `context`; caption and segment `text` | A | `P` |
| `T-104` | Full-rebuild path proven equivalent to incremental | A | `P` |
| `T-105` | `GET /api/status`, `/api/sources`, `/api/sources/{id}` | B | `P` |
| `T-106` | `GET /api/search` — cursor/page based, preserving `query.search_knowledge` result shapes | B | `P` |
| `T-107` | `GET /api/entities/{id}`, `/api/artifacts/{id}` | B | `P` |
| `T-108` | Path-traversal hardening + loopback-only binding + media range requests. **Read [ADR 0003](adr/0003-reject-unsafe-identifiers.md) first:** every id from a path parameter goes through `pipeline.resolve_run_dir`, which **rejects**; a rewriting sanitiser (`_safe_identifier`) must not stand in for it, and ADR 0001 invariant 8 — which said otherwise — is superseded | B | `S` |
| `T-109` | Vite/React/TS scaffold, routing, design tokens | C | `P` |
| `T-110` | i18n + `dir` switching shell, English default (**D-012**), logical CSS properties throughout | C | `P` |
| `T-111` | Library view: list + compact grid, filters (source type, kind, source class, confidence, validation status) | C | `P` |
| `T-112` | Reader: metadata, virtualized transcript, report, knowledge units, evidence, relations | C | `P` |
| `T-113` | Provenance/status components — `source` vs `derived` vs `user`, distinguished by icon/label/line style, **not colour alone** | C | `P` |
| `T-114` | YouTube embed + timestamp seek; never assume a local media file exists | C | `P` |
| `T-115` | Contract tests against the frozen API schema; index rebuild-equivalence test; path-traversal tests | D | `P` |
| `T-116` | Wire `x2knwldg ui` end to end (root resolve → index check → loopback serve → open browser) | integrator | `S` |

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
| D-017 | An identifier segment may begin with `-` or `_`; only a leading dot stays barred. `ids.py` is the single implementation of the identifier rules, and the v1 `idPart` pattern was widened to match | accepted | A YouTube id is base64url and legitimately starts with either — `pipeline.py:39` already accepts `[0-9A-Za-z_-]{11}`, so the narrower pattern would have made a real source unaddressable by the index. Widening accepts strictly more, so no stored record is invalidated and no `schemas/v2/` is needed; barring a leading dot keeps `.` and `..` out of every identifier |
| D-018 | A canonical knowledge unit id must be usable as one segment of a global id. `validators.py` reports `invalid_id`, and `extraction_bundle.schema.json` carries the same pattern | accepted | Otherwise an id that passes validation can still be unaddressable by the index, which is how a validator-`PASS` run came to crash `rebuild_library`. The rule now lives in one place — `ids.py` — and is enforced where the id first appears rather than where it first breaks |
| D-019 | Labelled, synthetic `PASS`/`PARTIAL`/`FAIL` run fixtures are committed under `tests/fixtures/runs/`, and the projection contract tests run over them unconditionally | accepted | `output/` is gitignored, so those tests skipped on every machine but the one holding the sample — a green suite that proved nothing. The fixtures also give `PARTIAL` and `FAIL` an on-disk existence for the first time (R11). They are generated by driving the real pipeline, so they cannot drift from what it writes, and regeneration is byte-identical so CI can prove it |
| D-020 | A run directory is resolved by `pipeline.resolve_run_dir`, which **rejects** an unsafe id rather than sanitising it ([ADR 0003](adr/0003-reject-unsafe-identifiers.md)) | accepted | `_safe_identifier` then rewrote `../other` into `_other` — defensible when creating a run, wrong when looking one up, because a lookup must fail rather than silently read a different run. Every externally supplied id goes through the resolver (R14); `T-108` must use it rather than inventing a second rule |
| D-021 | `src/` holds the `x2knwldg` package and nothing else. The unmaintained upstream scripts moved to `legacy/upstream/`, `pytest` gets an explicit `pythonpath`, and `requirements.txt` forwards to `pyproject.toml` | accepted | Loose modules beside the package were importable only because an editable install happened to put `src/` on `sys.path`, and two of them were Whisper transcribers that the project constraints forbid running. Quarantining them keeps upstream attribution without leaving them looking sanctioned |
| D-022 | Adapters live in `src/x2knwldg/adapters/`, one `SourceAdapter` subclass per source type, registered in `ADAPTERS`. `base.py` enforces four rules for every adapter: ids built through `ids.py`, project-relative paths, statuses copied, and an `AdapterError` wherever a value would have to be guessed | accepted | The generic seam is only real if an adapter cannot opt out of it, so the rules live in the base rather than in each implementation. The rules are not theoretical: the shape probe hard-coded `raw/source.json` (the extension follows the imported file — `pipeline.py:203` — so it is `.srt` in every fixture and the artifact read as missing) and asserted a media type for it. Both are now refusals |
| D-023 | In v1 the adapter emits entities for knowledge units and canonical concepts only. `caption`, `segment`, and `coverage_window` stay reserved in the `EntityRef` vocabulary and unemitted | accepted | Each already has a canonical representation the Reader and the indexer read directly — `T-103` indexes caption and segment text out of their artifacts — and none has a consumer needing a global handle yet. 500-odd caption entities per source, or a segment entity whose only honest `label` is `null` because the real text does not fit the field, would have to be undone later. The reserved names mean adding them costs no `schemas/v2/`. Coverage-window membership is likewise not an `IndexedRelation`: expressing it needs a fourth relation vocabulary, which is a schema change |
| D-024 | A source-class locator addresses the **segments** artifact, not the transcript. When a unit's provenance names a different video, `artifact_id` is omitted rather than pointed anywhere | accepted | `validators.py:166` resolves `segment_id` against `segments.json` and requires the excerpt to appear in that segment's text, so that is where the evidence sits; the shape probe addressed `transcript.json`, which does not carry segment ids at all. A mis-attributed unit is a canonical error already reported in `validation.json` — the run stays indexable and honestly displayed, and its locator stays unaddressed rather than wrong |
| D-025 | *(index side; **amended by D-043** for the library side)* A `derived_from` edge carries `confidence: null`. `expresses_concept` edges come from `library/graph.json` via `adapt_library`; `derived_from` edges come only from the run that owns them | accepted | A unit's confidence is about the unit — no confidence about the edge exists in any canonical file, and copying one across would put a number on a claim nothing made. ~~(`library.py:70` writes its own value into its own graph for its own reasons)~~ — **withdrawn by D-043:** `library.py` was fabricating `1.0` and `0`, and has stopped. Splitting the two synthetic vocabularies by producer keeps a run indexable before `rebuild_library` has ever run, and stops the 45 `derived_from` edges being counted twice |
| D-026 | The API contract is frozen as OpenAPI 3.1 in [`schemas/api/v1/openapi.json`](../schemas/api/v1/README.md), which `$ref`s `schemas/v1/` instead of restating it. Every response body is an adapter record inside an envelope carrying `api_version` and `schema_version`. Versioned by directory like D-015: a breaking change becomes `schemas/api/v2/` and a `/api/v2/` prefix, leaving these paths answering v1 | accepted | The API is a reader. A response shape of its own would be a third place for the same fact to drift, and there are already two identifier vocabularies to keep honest (R12). `adapt_project(root).by_model()` is literally what an endpoint returns a page of — the contract tests validate the endpoints against records the **real** adapters produce, so the document cannot agree with the schemas while disagreeing with the code |
| D-027 | Only the read-only surface is frozen in v1 — 11 endpoints, all `GET`. The board endpoints of canvas plan §15 stay **reserved and unfrozen** until Phase 3 gives boards a record schema | accepted | Freezing a contract for a shape that does not exist is inventing one, and a board contract written before `T-301` would be rewritten by it. The same restraint as D-023: reserving a name costs nothing, guessing its shape costs a migration |
| D-028 | `/api/search` preserves the two result shapes `query.search_knowledge` already returns, discriminated by `type`, and adds `global_id` and `source_id` **additively**. A `transcript_caption` hit carries no `global_id` | accepted | Those shapes are the de-facto contract the CLI and the MCP tools ship today; FTS5 (`T-103`) is an implementation change and must not be a contract change. The caption hit has no global id because v1 emits no caption entities (D-023) — minting one for the response would create an address that resolves to nothing. A hit whose canonical metadata states no `video_id` gets `global_id: null` rather than a plausible string |
| D-029 | TypeScript types are generated by `tools/generate_api_types.py` — stdlib-only — into a **committed** `types.d.ts`, drift-guarded by a byte-identity test rather than by an npm toolchain | accepted | `T-005` runs before `T-008`, so there is no `web/`, no `package.json`, and no Node job in CI. Putting the frontend's types behind a dependency the core package does not have would cut against ADR 0001 invariant 5 and hand `T-008` a scaffold it did not choose. The generator **refuses** a construct it does not understand instead of emitting `unknown`, because a declaration that has quietly stopped describing the contract still compiles. `openapi-typescript` can be added later as a cross-check without touching the contract |
| D-030 | *(**extended by D-044**)* Error taxonomy: an id rejected by `ids.py`/`resolve_run_dir` is `400 invalid_id`; a well-formed id naming nothing is `404 not_found`; a record whose file is absent is `available: false` and `404 unavailable` from `/api/media`; an unbuilt index is `503 index_unavailable` | accepted | D-020 says a lookup must fail rather than silently read a different run — over HTTP that means a malformed id is reported as malformed, refused before anything is read, and never dressed up as absence. `503` exists so the UI can distinguish an empty index from an absent one; without it, 'no sources yet' would be presented as a fact about the user's data |
| D-037 | The `ui` extra is `fastapi` + `uvicorn`, each with **both** a floor and a ceiling, and `x2knwldg ui` ships as a **refusing stub**: it enforces loopback-only binding (ADR 0001 invariant 9) and resolves the project root, then exits ~~`2`~~ **`6`** with `UI_NOT_IMPLEMENTED` naming `T-116` (the code was `2`; **D-040** moved it). It never prints a URL, and `--port` defaults to unset rather than to a constant | accepted, **amended by D-040** | A scaffolded command that exits `0` is a claim the project can serve a UI, and one that prints `http://127.0.0.1:8000` is a claim about a socket nobody opened — the same class of dishonesty as coercing `PARTIAL` to `PASS`. The two checks that *are* real here are both refusals, and a refusal is worth having before the thing it guards exists: the host check runs **before** the dependency probe, so the invariant holds on every machine that has not installed the extra. Upper bounds because a FastAPI or uvicorn major bump would otherwise land in a `pip install` between Phase 0 and `T-105` |
| D-038 | `web/` gets **TypeScript and nothing else** — no Vite, no React, no router, no tokens; `T-109` chooses those. What it does add is CI: `tsc --noEmit` over `web/` with `skipLibCheck: false` and `schemas/api/v1/types.d.ts` as a *root file* of the program, plus `web/src/api/contract.ts` as the single re-export of the generated declarations | accepted | Same restraint as D-029: handing `T-109` a framework it did not choose is a cost it pays for the life of the project, and the task row asked for a directory, not an application. `skipLibCheck` is the load-bearing detail — TypeScript's default is to skip `.d.ts` files, so with it on the Node job would skip the one file it exists to check and pass without looking, leaving R17 closed on paper only. Verified by deliberately breaking `types.d.ts` and watching `tsc` fail. Routing every import through `contract.ts` keeps exactly one path to the generated file, so moving it breaks a test rather than a build |
| D-039 | `pipeline.project_root(explicit=None)` is the single root-resolution rule — explicit path, then `X2KNWLDG_PROJECT_ROOT`, then the working directory. `mcp_server.PROJECT_ROOT` now calls it instead of re-reading the env var | accepted | The `ui` command is the second consumer of 'where is the project', and a second implementation of a lookup rule is exactly what D-020 was written about. Behaviour is unchanged for the MCP server — the same three-step fallback, one copy of it — and `tests/test_ui_scaffold.py` asserts the env var is no longer read in `mcp_server.py`, so the duplication cannot quietly return |
| D-040 | Exit codes are a semantic contract, not a boolean. One table, one mapping (`cli.VERDICT_EXIT_CODES`), printed by `--help`: `0` `PASS` · `1` `ERROR` · `2` reserved for `argparse` · `3` `PARTIAL` · `4` `FAIL` · `5` `TRANSCRIPT_REQUIRED` · `6` `UI_NOT_IMPLEMENTED`. Completion may be claimed only on `0`. **Amends D-037**, whose `ui` refusal moves `2` → `6` | accepted | `PARTIAL` exited `0`, so no shell or CI check could tell an honestly incomplete run from a passing one — the same dishonesty as coercing `PARTIAL` to `PASS`, dressed as a status code. Every refusal shared `1`, so "this video needs a transcript from you" and "the `ui` server does not exist yet" were indistinguishable from a broken install. `2` is given back to `argparse` because a semantic code sharing a number with a typo'd flag cannot be checked for. D-037's reasoning is untouched and still right — a stub that exits `0` is a false claim; only the number moved, and it moved so the refusal is distinguishable from a mistyped argument. One mapping rather than three literals so `validate`, `apply-bundle` and `finalize` cannot drift |
| D-041 | Which nodes a source's graph is drawn over is `relation_belongs_to_source` (D-034) — the same rule `/api/sources/{id}/relations` uses. A node belongs when it is an entity of that source **or** when a relation of that source names it as an endpoint. The **edge** rule of D-035 is unchanged: both endpoints must be nodes of the graph. **Extends D-035** ([ADR 0004](adr/0004-graph-membership-and-search-corpus.md)) | accepted | `/api/graph?source_id=` used its own rule — both endpoints had to be entities *of that source* — and a canonical concept belongs to no source (D-016), so all 17 `expresses_concept` edges vanished from the graph while the relations endpoint returned them: 101 edges against 118 on the sample. Two answers to one question, and the lossy one was the one a user calls 'the graph'. Widening the **node set** is the opposite of the either-endpoint **edge** rule ADR 0002 rejected: the far endpoint becomes a node rather than a dangling reference. Both views now report 118 edges over 86 nodes |
| D-042 | `MemoryRepository`'s search corpus is built from the `canonical_dir` each **indexed** `Source` carries, once per instance on the first search, and never invalidated. A run outside the index is not searched; a source whose files will not read is *unreadable*, so `total` is `null` rather than a zero ([ADR 0004](adr/0004-graph-membership-and-search-corpus.md)) | accepted | Walking `output/` per call made paging cost the whole library **per page**, and made search a second, disagreeing view: a run added after construction returned hits carrying `source_id: null`, because no `Source` existed to resolve them against — renderable and unnavigable. Resolving through the record also means no id is joined onto a path, so no host path reaches an error body (D-030, ADR 0003). Built lazily because a repository that never searches must not pay for a corpus and `/api/status` must stay cheap. Narrows ADR 0002's promise of a cache-free `T-104` oracle to *cache-free per instance* |
| D-043 | `library.rebuild_library` invents no confidence and drops no run in silence. `expresses_concept` edges carry `confidence: null`; a `derived_from` edge carries the unit's **own** confidence verbatim, `null` when the unit states none. A run missing a canonical file is indexed from what it has, and `status.json` gains `runs_discovered`, `runs_indexed`, `runs_skipped`, `skipped_runs[]` and `incomplete_runs[]`, with every `videos.json` entry gaining `problems: []`. **Amends D-025** | accepted | D-025 forbade the index fabricating an edge confidence; `library.py` was doing exactly that in its own graph — `1.0` on every `expresses_concept` edge, which is a match on a normalised string key and not a measurement, and `0` (the *least* confident value) on a `derived_from` edge whose unit stated none. The same reasoning applies to both producers, so the parenthetical in D-025 that excused `library.py` as writing 'its own value for its own reasons' is withdrawn. Separately, `relationships.json` was a precondition for indexing at all, so a run with units but no relationships file disappeared from `graph.json`, `videos.json` and the `videos` count while `adapt_run` indexed it without complaint — a count that omits a run without saying so is a claim of completeness the library has not got |
| D-044 | D-030's taxonomy gains two codes for boundaries that are not HTTP: `invalid_request` — an argument refused before anything is read, where no identifier is involved — and `internal_error`. The four original codes keep their meanings and their HTTP statuses. **Extends D-030** | accepted | Two MCP tool parameters are *paths*, not ids, so `resolve_run_dir` is not their check even though its behaviour is (ADR 0003 invariant 5). Reporting a refused path as `invalid_id` would name a thing the request never contained, which is the kind of small lie D-030 exists to prevent — the taxonomy's whole point is that a refusal says what was actually refused. `internal_error` is the boundary's own catch: a tool must let out one error type carrying a known code, so an unexpected exception is converted rather than leaked with its message and paths intact. Narrowing the MCP surface to the four HTTP codes was the alternative and was rejected: it would force one of them to mean something it does not |
| D-045 | An adapter **states what it could not do** rather than dropping it silently, and `Source.adapter_metadata` carries two diagnostic channels for it: `unmappable_artifacts` (a generated `vault/` note whose filename cannot spell an id — skipped and named, not fatal) and `unreadable_files` (a canonical file present but damaged — named, so a missing count is not read as a zero). Both are free-form by schema and absent when there is nothing to report. The line is drawn at index integrity: a run whose `knowledge_units.json` is damaged while its `relationships.json` is intact is **refused** at adapt time, naming the dangling edge. **Qualifies D-022** | accepted | D-022 requires an `AdapterError` wherever a value would have to be guessed, and that is still right for canonical evidence. Nothing here is guessed either way; the choice is between refusing everything and stating the one omission, and the rule that actually matters is that the omission is never silent — the recurring finding across this audit. One `vault/` note whose filename cannot spell an id took down a whole project's index, and that note is a generated export beside the canonical files, so it is skipped and named. A damaged canonical file is different again: its counts were already omitted rather than zeroed, but 'this count is missing' does not say 'this file is broken', and only one of those is actionable. The refusal stays where integrity is at stake: stranded edges would make the graph and `/api/sources/{id}/relations` disagree about one fact, `check_index_integrity` would refuse the whole project later anyway, and the failure belongs on the run that causes it. `adapter_metadata` is the only place in the frozen `Source` record an adapter may say any of this |

### ⚠️ D-011 is **additive** — do not "clean up" the 2-part ID

`.claude/commands/kg_navigator.md` **mandates** the 2-part form `<video-id>:<knowledge-unit-id>` for `output/library/graph.json` nodes, and `src/x2knwldg/library.py:49` emits exactly that.

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
.venv/bin/python -m pytest -q               # expect: 1287 passed, 0 failed, 36 subtests (plus new tests)
git diff --stat -- output/                  # expect: empty, always
.venv/bin/python tests/fixtures/runs/build_fixtures.py
git diff --stat -- tests/fixtures/runs/     # expect: empty — regeneration is byte-identical
.venv/bin/python tools/generate_api_types.py --check   # expect: types.d.ts is up to date
(cd web && npm ci && npm run typecheck)     # expect: silent — tsc --noEmit, risk R17
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
/tmp/bare/bin/python -m pytest -q           # expect: 333 passed, 4 skipped, 16 subtests
```

The 4 skips are the `jsonschema` and `legacy` tests, which skip by design. Every
`tests/test_ui_scaffold.py` test runs here — the scaffold's own guards must hold
on the install they are about.

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
```

### 7.4 End-to-end scenarios (canvas plan §17.3)
1. Open a source and see its **real** status.
2. Search a transcript phrase and jump to the timestamp.
3. Select a knowledge unit and see its actual evidence.
4. Move an entity from Map to Canvas.
5. Create a user relation without touching any canonical file.
6. Draw with the pen, reload, strokes survive.
7. Delete the cache, rebuild, boards intact.

---

## 8. Agent parallelism model

### 8.1 Phase 0 is a serialization point

Phase 0 produces the entity, ID, and API contracts that every other track consumes. **Running parallel agents during Phase 0 guarantees rework.** One focused agent, start to finish.

### 8.2 After the Phase 0 gate — four tracks, disjoint file ownership

Exclusive file ownership is the mechanism that makes concurrent agents safe. An agent writes **only** inside its own paths.

| Track | Owns exclusively | Scope |
|---|---|---|
| **A — Indexer** | `src/x2knwldg/index/` | SQLite schema, migrations, scanner, FTS5, incremental hashing — behind `repository.IndexRepository` |
| **B — API** | `src/x2knwldg/server/` | FastAPI routes, path safety, range requests, versioned responses |
| **C — Frontend** | `web/` | Vite/React scaffold, tokens, i18n/bidi shell, Library, Reader |
| **D — Fixtures & tests** | `tests/` | Labeled `PARTIAL`/`FAIL` fixtures, contract tests, rebuild equivalence |

**What makes A, B, and C genuinely concurrent:** the API contract is frozen in `T-005` and TypeScript types are generated from it, so Track C develops against a mock and never waits on Track B. Tracks A and B meet only at the repository interface fixed in `T-007`, which now exists:
[`IndexRepository`](../src/x2knwldg/repository/README.md) with a working reference
implementation behind it, so **Track B can start before Track A finishes**.

### 8.3 Contention points — integrator only

These files are small, shared, and merge-hostile. **No track agent edits them.**

[`.github/CODEOWNERS`](../.github/CODEOWNERS) encodes this table and §8.2, so a PR that
crosses a boundary asks for a review instead of merging quietly. It is a tripwire, not a
lock: §8.2 is still the rule. Change the paths there and here together, never one alone.

- `src/x2knwldg/cli.py` — the `ui` subcommand. `T-008` left a refusing stub there; `T-116`
  replaces its body and no other task touches it
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
| `io.write_json` (`io.py:19`) | **Already atomic** (same-dir temp + `os.replace`) — satisfies canvas plan §15 outright. Note: Markdown/report writes use plain `write_text` and are *not* atomic |
| `io.sha256_file` (`io.py:11`) | Incremental index change detection |
| `io.timestamp_url` (`io.py:42`) | YouTube deep links; `&t=<int>s` output is contract-locked by `tests/test_core_pipeline.py` |
| `pipeline.validate_run` (`pipeline.py:236`) | The **only** legitimate source of run status. Read it; never recompute |
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
| `cli.LOOPBACK_HOSTS` (`T-008`) | The accepted bind addresses. `T-116` must keep the check *before* the dependency probe, or the invariant lapses on any machine without the `ui` extra |
| `library.rebuild_library` | Generalize **additively**; do not rewrite. Its `status.json` now reports `runs_discovered`, `runs_indexed`, `runs_skipped`, `skipped_runs[]` and `incomplete_runs[]` beside the counts, and every `videos.json` entry carries `problems: []` — read `runs_indexed`, never `videos`, when you mean "how many runs are in the library" (D-043) |
| `query.search_knowledge` (`query.py:27`) | Its two result shapes are the de-facto API contract to preserve while FTS5 replaces the linear scan |
| `ids.py` (`T-003`) | Every identifier operation: build, parse, convert between the global and library forms, and enforce the three cross-field invariants. Never assemble an id with an f-string |
| `adapters/` (`T-004`) | The **only** way to turn a canonical run into index records. `adapt_run` for one run, `adapt_library` for the cross-source concepts, `adapt_project` for everything — the scan `T-102` makes incremental. Pass `hash_artifacts=True` for `io.sha256_file` digests. Do not re-read canonical files into ad-hoc dicts elsewhere |
| `Source.adapter_metadata.unmappable_artifacts` / `.unreadable_files` | The adapters' two diagnostic channels, and the answer to the "silent drop" finding that recurs through this audit (D-045). `unmappable_artifacts`: a generated `vault/` note whose filename cannot spell an id, skipped and named. `unreadable_files`: a canonical file present but damaged, named so a missing count is not read as a zero. Each carries `path` + `reason`, is free-form by schema, and is **absent** when there is nothing to report — an empty list reads like an unread finding. A UI showing a source must surface both rather than let the omission disappear between the run and the Reader |
| `adapters.project_relative` | Every path that reaches an index record or an API response. It refuses a path outside the project root, which is what keeps risk R15 closed |
| `schemas/api/v1/openapi.json` (`T-005`) | The **specification** for `T-105`–`T-108`, not a suggestion. Eleven `GET` endpoints, response bodies `$ref`-ing `schemas/v1/`. Do not add an endpoint, a field, or a status code without editing this document and its tests first |
| `schemas/api/v1/types.d.ts` (`T-005`) | The frontend's types. Import it; never hand-edit it. Regenerate with `python tools/generate_api_types.py` |
| `web/src/api/contract.ts` (`T-008`) | The **only** place `web/` names the generated declarations. Frontend code imports API types from here, never by reaching up the tree (D-038) |
| `repository/` (`T-007`) | The **only** thing `T-105`–`T-108` read. No route opens a database, a canonical file, or a run directory. `T-101`–`T-104` implement `IndexRepository` over SQLite without widening it; `MemoryRepository` is what Track B builds against until they do, and the oracle `T-104` proves equivalence against |
| `repository.encode_cursor` / `decode_cursor` | The one cursor encoding. The SQLite implementation issues its keyset cursors through it so both implementations produce the same token for the same position |
| `repository.matches_entity` / `matches_relation` / `matches_source` / `relation_belongs_to_source` | The definition of every filter the contract exposes. Where a SQL `WHERE` clause disagrees with them, they are right |
| `repository.graph_nodes` | The **one** rule for which nodes a source's graph is drawn over — an entity of the source, or an endpoint of a relation `relation_belongs_to_source` accepts (D-041, [ADR 0004](adr/0004-graph-membership-and-search-corpus.md)). `T-101`–`T-104` inherit it; do not re-derive it in SQL |
| `query.run_documents` / `query.rank_documents` | The searchable form of a run, and the ranking over it. `MemoryRepository` builds its corpus from these once per instance (D-042) and `query.search_knowledge` is the CLI's caller of the same pair. `T-103` replaces the corpus, not these shapes |
| `constants.py` | The real controlled vocabulary: 22 source kinds, 8 derived kinds, 16 relation types, 10 omission reasons |
| `artifacts.SECTION_ORDER` (`artifacts.py:20`) | A ready-made 12-section UI grouping taxonomy for knowledge kinds |

**Conventions to follow:** lazy optional imports inside the dispatch branches of `cli.main` (and `cli._run_process`) so the core stays zero-dependency · `pipeline.project_root` as the **only** root resolution — it reads `X2KNWLDG_PROJECT_ROOT` itself, and D-039 removed the second read from `mcp_server.py`, so no other module may re-read the env var · `config/*.local.json` tracked-example / ignored-local pattern.

**Vocabulary the Map must style:** `derived_from` and `expresses_concept` are library-only synthetic relations that are **not** in `RELATION_TYPES`. In the current data they are the two most common edges (45 and 17 of 118).

---

## 11. Next step

**Phase 0 is complete and its exit gate is met.** The next session opens Phase 1, which is
the first phase that may run more than one agent: fan out to the four tracks of §8.2, with
`T-116` held back as the integrator step.

All nine Phase 0 tasks are done: `T-001` (ADRs), `T-002`
([`schemas/v1/`](../schemas/v1/README.md)), `T-003` ([`ids.py`](../src/x2knwldg/ids.py)),
`T-004` ([`adapters/`](../src/x2knwldg/adapters/README.md)), `T-005`
([`schemas/api/v1/`](../schemas/api/v1/README.md)), `T-006`
([run fixtures](../tests/fixtures/runs/README.md)), `T-007`
([`repository/`](../src/x2knwldg/repository/README.md)), `T-008`
([`web/`](../web/README.md) + the `ui` extra), and `T-009` (the zero-dependency
re-confirmation).

**What `T-008` deliberately did not do.** It scaffolded a directory, not an application.
There is no Vite, no React, no router, and no design token in `web/` — `T-109` chooses those
(D-038), the same restraint D-029 applied to the type generator. `x2knwldg ui` is a refusing
stub: it enforces loopback-only binding and resolves the project root, then exits `6` with
`UI_NOT_IMPLEMENTED` rather than starting something that cannot serve (D-037, renumbered from
`2` by D-040 so the refusal cannot be mistaken for a mistyped flag).

**Suggested fan-out, 3–4 agents (§8.5):**

| Track | Start with | Has everything it needs |
|---|---|---|
| **A — Indexer** (`src/x2knwldg/index/`) | `T-101` SQLite schema + migrations | Implements `IndexRepository` (`T-007`) over SQLite without widening it; `MemoryRepository` is the oracle `T-104` proves equivalence against |
| **B — API** (`src/x2knwldg/server/`) | `T-105` `/api/status`, `/api/sources` | Calls the repository only. The contract is frozen (`T-005`) and `MemoryRepository` answers all of it today, so B does not wait on A |
| **C — Frontend** (`web/`) | `T-109` Vite/React/TS scaffold on top of the `T-008` toolchain | Types are generated and compile: `import type { … } from "./api/contract"`. Develops against a mock, never waits on B |
| **D — Fixtures & tests** (`tests/`) | `T-115` contract tests, rebuild equivalence, traversal | The labelled `PASS`/`PARTIAL`/`FAIL` fixtures exist (`T-006`) |

**Rules a track agent must not break:**

- Write only inside your track's directory (§8.2). The files in §8.3 — `cli.py`,
  `pyproject.toml`, `.gitignore`, `.github/workflows/ci.yml`, `docs/`, `library.py`,
  `repository/base.py` — are integrator-only.
- Widening `IndexRepository` is a contract change: `schemas/api/v1/openapi.json` first,
  [ADR 0002](adr/0002-index-repository-seam.md) second, never a local decision.
- Do not begin Phase 3 Canvas or Phase 4 pen work. They are sequential with each other
  (§8.4) and belong to a later phase.
- `web/tsconfig.json` keeps `skipLibCheck: false`. Turning it on reopens R17 in silence.
