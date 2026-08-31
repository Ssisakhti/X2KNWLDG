# X2KNWLDG Knowledge Canvas — Project Management

**Status:** active execution tracker
**Last updated:** 2026-08-31 · Phase 0 in progress; `T-001`, `T-002`, `T-003`, `T-004`, and `T-006` complete
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
| `output/library/` | 1 video, 69 knowledge nodes, **17 canonical concepts**, 118 edges — unchanged by the `T-003` rebuild, which only added fields |
| Index projection (`T-004`) | The adapter maps the sample to **1 source, 85 artifacts, 86 entities, 118 relations** — 69 knowledge units + 17 concepts, and 56 canonical + 62 synthetic edges |
| Test baseline | **231 passed, 16 subtests** (`.venv/bin/python -m pytest -q`, all extras installed). Core package with no extras at all: **142 passed, 3 skipped** — the `jsonschema` and `legacy` tests skip cleanly |
| Toolchain | Node 26.5.0 · npm 11.17.0 · Python 3.14.6 · SQLite 3.53.4 with **FTS5 available** |

> **Correction of record.** Canvas plan §4 previously stated the sample had empty
> `knowledge_units.json` / `relationships.json` / `graph.json` and `coverage = PARTIAL`.
> That was stale. The sample run is **complete and `PASS`**. §4 has been corrected.
>
> Two consequences:
> - **Risk 7 (no valid graph data for development) is resolved** — real graph data exists.
> - The inverse gap is now open: **no `PARTIAL`/`FAIL` fixture exists**, so those UI
>   states are currently untestable. See `T-006`.

**Nothing of the UI has been built yet.** No `web/`, no `package.json`, no FastAPI code, no SQLite index.
Phase 0 contracts exist on disk: `docs/adr/` (`T-001`), `schemas/v1/` (`T-002`),
`src/x2knwldg/ids.py` (`T-003`), `src/x2knwldg/adapters/` (`T-004`), and the labelled run fixtures
in `tests/fixtures/runs/` (`T-006`).

> **Independent cross-check.** The adapter reaches 86 entities and 118 relations for the sample by
> reading `output/pqlWNihgdjI/` and `output/library/graph.json`; `library/status.json` independently
> reports 69 knowledge nodes + 17 concepts and 118 edges. Two code paths, the same numbers.

---

## 4. Phase board

Exit criteria live in canvas plan §16; this table tracks state only.

| Phase | Name | Status | Parallelizable | Gate to next phase |
|---|---|---|---|---|
| **0** | Contracts & scaffolding | `in progress` | ❌ **No — serialization point** | Schemas validate; contract frozen |
| **1** | Read-only Library & Reader | `not started` | ✅ Tracks A/B/C/D | Search works; status honest; rebuild is equivalent |
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
| ~~`T-002`~~ | ✅ **done** — v1 index model in [`schemas/v1/`](../schemas/v1/README.md): `common`, `Source`, `Artifact`, `Locator`, `EntityRef`, `IndexedRelation`. JSON Schema 2020-12, versioned by directory, 58 contract tests in `tests/test_index_schemas.py` | `S` | `T-001` |
| ~~`T-003`~~ | ✅ **done** — [`src/x2knwldg/ids.py`](../src/x2knwldg/ids.py): `GlobalId`/`SourceId`, both-way conversion to the library form, and the three cross-field invariants as `check_entity_ref_ids` / `check_source_ids` / `check_locator`. `library.py` nodes **gained** `source_type` + `global_id` and kept their two-part `id`. Stdlib-only; 51 tests in `tests/test_ids.py` | `S` | `T-002` |
| ~~`T-004`~~ | ✅ **done** — [`src/x2knwldg/adapters/`](../src/x2knwldg/adapters/README.md): `SourceAdapter` contract in `base.py`, `YouTubeAdapter` + `adapt_library` in `youtube.py`, `ADAPTERS`/`adapt_run`/`adapt_project` in `__init__.py`. Stdlib-only. The shape probe is deleted: `tests/test_index_schemas.py` validates the real adapter's records, and 43 new tests in `tests/test_adapters.py` cover what it refuses and never invents. No canonical file changed | `S` | `T-002` |
| `T-005` | Freeze the API contract (canvas plan §15) as a written schema; set up TypeScript type generation from it | `S` | `T-002` |
| ~~`T-006`~~ | ✅ **done** — [`tests/fixtures/runs/`](../tests/fixtures/runs/README.md): `pass-run`, `partial-run`, `fail-run`, generated by driving the real pipeline and regenerable byte-identically. Every `metadata.json` carries `"fixture": true`. The projection contract tests now run over them **always**, and over the real sample additionally | `P` | `T-002` |
| `T-007` | Decide the repository interface between indexer and API (Track A ↔ Track B seam) | `S` | `T-002` |
| `T-008` | Scaffold: `web/` dir, `ui` optional extra in `pyproject.toml`, `ui` CLI subcommand stub, `.gitignore` entries (`node_modules/`, `.vite/`, `*.tsbuildinfo`) | `S` | `T-005` |
| `T-009` | Confirm the core package still installs and tests with **no** UI extras once `T-008` adds the `ui` extra. Adapter tests landed with `T-004`; the CI `zero-dependency` job already proves the current state (142 passed, 3 skipped) | `S` | `T-004`, `T-008` |

**Phase 0 exit gate:** schemas validate, the sample source converts to the generic model with zero guessed fields, the API contract is frozen, and `pytest` is green without UI dependencies installed. **Do not fan out before this gate.**

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
| `T-108` | Path-traversal hardening + loopback-only binding + media range requests | B | `S` |
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
| D-020 | A run directory is resolved by `pipeline.resolve_run_dir`, which **rejects** an unsafe id rather than sanitising it | accepted | `_safe_identifier` rewrites `../other` into `_other`, which is right when creating a run and wrong when looking one up — a lookup must fail, not silently read a different run. Every externally supplied id goes through the resolver (R14); `T-108` must use it rather than inventing a second rule |
| D-021 | `src/` holds the `x2knwldg` package and nothing else. The unmaintained upstream scripts moved to `legacy/upstream/`, `pytest` gets an explicit `pythonpath`, and `requirements.txt` forwards to `pyproject.toml` | accepted | Loose modules beside the package were importable only because an editable install happened to put `src/` on `sys.path`, and two of them were Whisper transcribers that the project constraints forbid running. Quarantining them keeps upstream attribution without leaving them looking sanctioned |
| D-022 | Adapters live in `src/x2knwldg/adapters/`, one `SourceAdapter` subclass per source type, registered in `ADAPTERS`. `base.py` enforces four rules for every adapter: ids built through `ids.py`, project-relative paths, statuses copied, and an `AdapterError` wherever a value would have to be guessed | accepted | The generic seam is only real if an adapter cannot opt out of it, so the rules live in the base rather than in each implementation. The rules are not theoretical: the shape probe hard-coded `raw/source.json` (the extension follows the imported file — `pipeline.py:203` — so it is `.srt` in every fixture and the artifact read as missing) and asserted a media type for it. Both are now refusals |
| D-023 | In v1 the adapter emits entities for knowledge units and canonical concepts only. `caption`, `segment`, and `coverage_window` stay reserved in the `EntityRef` vocabulary and unemitted | accepted | Each already has a canonical representation the Reader and the indexer read directly — `T-103` indexes caption and segment text out of their artifacts — and none has a consumer needing a global handle yet. 500-odd caption entities per source, or a segment entity whose only honest `label` is `null` because the real text does not fit the field, would have to be undone later. The reserved names mean adding them costs no `schemas/v2/`. Coverage-window membership is likewise not an `IndexedRelation`: expressing it needs a fourth relation vocabulary, which is a schema change |
| D-024 | A source-class locator addresses the **segments** artifact, not the transcript. When a unit's provenance names a different video, `artifact_id` is omitted rather than pointed anywhere | accepted | `validators.py:166` resolves `segment_id` against `segments.json` and requires the excerpt to appear in that segment's text, so that is where the evidence sits; the shape probe addressed `transcript.json`, which does not carry segment ids at all. A mis-attributed unit is a canonical error already reported in `validation.json` — the run stays indexable and honestly displayed, and its locator stays unaddressed rather than wrong |
| D-025 | A `derived_from` edge carries `confidence: null`. `expresses_concept` edges come from `library/graph.json` via `adapt_library`; `derived_from` edges come only from the run that owns them | accepted | A unit's confidence is about the unit — no confidence about the edge exists in any canonical file, and copying one across would put a number on a claim nothing made (`library.py:70` writes its own value into its own graph for its own reasons). Splitting the two synthetic vocabularies by producer keeps a run indexable before `rebuild_library` has ever run, and stops the 45 `derived_from` edges being counted twice |

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
.venv/bin/python -m pytest -q               # expect: 231 passed, 16 subtests (plus new tests)
git diff --stat -- output/                  # expect: empty, always
.venv/bin/python tests/fixtures/runs/build_fixtures.py
git diff --stat -- tests/fixtures/runs/     # expect: empty — regeneration is byte-identical
```

CI runs all three, plus an install of the core package with **no** extras, on
every push and pull request: [`.github/workflows/ci.yml`](../.github/workflows/ci.yml).

### 7.3 Re-verify the numbers in §3
```bash
python3 -c "import json;print(len(json.load(open('output/pqlWNihgdjI/knowledge_units.json'))['units']))"
python3 -c "import json;print(json.load(open('output/pqlWNihgdjI/coverage.json'))['status'])"
python3 -c "import json;print(json.load(open('output/pqlWNihgdjI/validation.json'))['status'])"
cat output/library/status.json

# The same numbers, reached independently through the adapter (T-004).
.venv/bin/python -c "
from pathlib import Path
from x2knwldg.adapters import adapt_project
print({k: len(v) for k, v in adapt_project(Path('.')).by_model().items()})"
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
| **A — Indexer** | `src/x2knwldg/index/` | SQLite schema, migrations, scanner, FTS5, incremental hashing |
| **B — API** | `src/x2knwldg/server/` | FastAPI routes, path safety, range requests, versioned responses |
| **C — Frontend** | `web/` | Vite/React scaffold, tokens, i18n/bidi shell, Library, Reader |
| **D — Fixtures & tests** | `tests/` | Labeled `PARTIAL`/`FAIL` fixtures, contract tests, rebuild equivalence |

**What makes A, B, and C genuinely concurrent:** the API contract is frozen in `T-005` and TypeScript types are generated from it, so Track C develops against a mock and never waits on Track B. Tracks A and B meet only at the repository interface fixed in `T-007`.

### 8.3 Contention points — integrator only

These files are small, shared, and merge-hostile. **No track agent edits them.**

- `src/x2knwldg/cli.py` — the `ui` subcommand
- `pyproject.toml` — the `ui` extra
- `.gitignore`
- `docs/` — including this file
- `src/x2knwldg/library.py` — single owner, load-bearing for `kg_navigator` (see §6)

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
| **R14** No path-traversal guard in existing `query.py` / `mcp_server.py` joins | 🟢 **Mitigated** | Every join now goes through `pipeline.resolve_run_dir`, which rejects rather than sanitises (D-020), with traversal tests in `tests/test_core_pipeline.py::RunLookupTests`. `T-108` must use the same resolver for HTTP path parameters |
| **R15** Absolute host paths baked into `library/status.json` and `library/videos.json` | 🟢 **Mitigated** | `library.py` emits an additive `relative_path` beside each absolute `path`, and `T-004` closed the reading side structurally: every path in an index record goes through `adapters.project_relative`, which **refuses** a path outside the project root rather than storing it. `adapt_library` does not read `status.json` or `videos.json` at all. Tested by `test_no_record_carries_an_absolute_path` and `test_a_run_outside_the_project_root_is_refused` |
| **R16** `value` field on statistic units is polymorphic (`int` \| `list[float]`) | 🟡 Watch | Cannot map to one SQL column — store as JSON text, keep the canonical file authoritative. `EntityRef` has no `value` field and `additionalProperties: false`, so the adapter cannot carry it into the index by accident |

Risks 1–6 and 8 from canvas plan §18 remain as written.

---

## 10. Reuse — do not reimplement these

| Existing code | Use it for |
|---|---|
| `io.write_json` (`io.py:19`) | **Already atomic** (same-dir temp + `os.replace`) — satisfies canvas plan §15 outright. Note: Markdown/report writes use plain `write_text` and are *not* atomic |
| `io.sha256_file` (`io.py:11`) | Incremental index change detection |
| `io.timestamp_url` (`io.py:42`) | YouTube deep links; `&t=<int>s` output is contract-locked by `tests/test_core_pipeline.py` |
| `pipeline.validate_run` (`pipeline.py:236`) | The **only** legitimate source of run status. Read it; never recompute |
| `pipeline.resolve_run_dir` | Resolve a run directory from an externally supplied id. It **rejects** an unsafe id; use it for every HTTP path parameter (D-020) |
| `pipeline._safe_identifier` | Sanitize an id when *creating* a run. Never for a lookup — it would rewrite `../other` into `_other` |
| `library.rebuild_library` (`library.py:24`) | Generalize **additively**; do not rewrite |
| `query.search_knowledge` (`query.py:27`) | Its two result shapes are the de-facto API contract to preserve while FTS5 replaces the linear scan |
| `ids.py` (`T-003`) | Every identifier operation: build, parse, convert between the global and library forms, and enforce the three cross-field invariants. Never assemble an id with an f-string |
| `adapters/` (`T-004`) | The **only** way to turn a canonical run into index records. `adapt_run` for one run, `adapt_library` for the cross-source concepts, `adapt_project` for everything — the scan `T-102` makes incremental. Pass `hash_artifacts=True` for `io.sha256_file` digests. Do not re-read canonical files into ad-hoc dicts elsewhere |
| `adapters.project_relative` | Every path that reaches an index record or an API response. It refuses a path outside the project root, which is what keeps risk R15 closed |
| `constants.py` | The real controlled vocabulary: 22 source kinds, 8 derived kinds, 16 relation types, 10 omission reasons |
| `artifacts.SECTION_ORDER` (`artifacts.py:20`) | A ready-made 12-section UI grouping taxonomy for knowledge kinds |

**Conventions to follow:** lazy optional imports inside CLI branches (`cli.py:174,180,188,196`) so the core stays zero-dependency · `X2KNWLDG_PROJECT_ROOT` env var for root resolution (`mcp_server.py:17`) · `config/*.local.json` tracked-example / ignored-local pattern.

**Vocabulary the Map must style:** `derived_from` and `expresses_concept` are library-only synthetic relations that are **not** in `RELATION_TYPES`. In the current data they are the two most common edges (45 and 17 of 118).

---

## 11. Next step

**Start `T-005`** — freeze the API contract of canvas plan §15 as a written schema, and set up
TypeScript type generation from it.

Phase 0 now has five of its nine tasks done: `T-001` (ADRs), `T-002` ([`schemas/v1/`](../schemas/v1/README.md)),
`T-003` ([`ids.py`](../src/x2knwldg/ids.py)), `T-004` ([`adapters/`](../src/x2knwldg/adapters/README.md)),
and `T-006` ([run fixtures](../tests/fixtures/runs/README.md)). Remaining: `T-005`, `T-007`, `T-008`,
`T-009`.

`T-005` is the gate that makes Tracks B and C genuinely concurrent (§8.2), so it is the highest-value
remaining item. Ground it in what already exists rather than in a fresh design:

- The response bodies are the v1 records the adapter already produces. Do not invent a second shape —
  `adapt_project(root).by_model()` is what an endpoint returns a page of.
- `Locator` uses `type` as its discriminated-union tag; generate it as such.
- `query.search_knowledge`'s two result shapes are the de-facto contract for `/api/search` (§10).
- Path parameters that name a run go through `pipeline.resolve_run_dir` (D-020, R14) — `T-108` must
  not invent a second rule.
- Statuses in a response are the `Source.status` block verbatim, `UNKNOWN` included. The API has no
  more right to compute a status than the UI does.

Then `T-007` (the indexer ↔ API repository seam) and `T-008` (scaffolding). `T-009` shrank to
confirming the no-extras install still passes once `T-008` adds the `ui` extra — the adapter tests
landed with `T-004`, and CI's `zero-dependency` job already proves the current state.

Phase 0 remains **one agent, no fan-out**. Do not begin Canvas or production UI design until the
Phase 0 gate in §5 passes.
