# X2KNWLDG Knowledge Canvas — Project Management

**Status:** active execution tracker
**Last updated:** 2026-08-31 · Phase 0 in progress, `T-001` complete
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
| `output/library/` | 1 video, 69 knowledge nodes, **17 canonical concepts**, 118 edges |
| Test baseline | **37 passed** (`.venv/bin/python -m pytest -q`) |
| Toolchain | Node 26.5.0 · npm 11.17.0 · Python 3.14.6 · SQLite 3.53.4 with **FTS5 available** |

> **Correction of record.** Canvas plan §4 previously stated the sample had empty
> `knowledge_units.json` / `relationships.json` / `graph.json` and `coverage = PARTIAL`.
> That was stale. The sample run is **complete and `PASS`**. §4 has been corrected.
>
> Two consequences:
> - **Risk 7 (no valid graph data for development) is resolved** — real graph data exists.
> - The inverse gap is now open: **no `PARTIAL`/`FAIL` fixture exists**, so those UI
>   states are currently untestable. See `T-006`.

**Nothing of the UI has been built yet.** No `web/`, no `package.json`, no FastAPI code, no SQLite index, no `docs/adr/`.

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
| `T-002` | Define v1 schemas: `Source`, `Artifact`, `Locator`, `EntityRef`, `IndexedRelation`. Versioned + machine-validatable | `S` | `T-001` |
| `T-003` | Implement the 3-part global ID helper (**D-011**) — additive only, see §6 warning | `S` | `T-002` |
| `T-004` | Write the YouTube adapter contract mapping `output/<id>/` → the generic model, changing **no** canonical output | `S` | `T-002` |
| `T-005` | Freeze the API contract (canvas plan §15) as a written schema; set up TypeScript type generation from it | `S` | `T-002` |
| `T-006` | Build clearly-labeled **test-only** `PARTIAL` and `FAIL` fixtures under `tests/fixtures/` | `P` | `T-002` |
| `T-007` | Decide the repository interface between indexer and API (Track A ↔ Track B seam) | `S` | `T-002` |
| `T-008` | Scaffold: `web/` dir, `ui` optional extra in `pyproject.toml`, `ui` CLI subcommand stub, `.gitignore` entries (`node_modules/`, `.vite/`, `*.tsbuildinfo`) | `S` | `T-005` |
| `T-009` | Add schema/adapter tests; confirm the core package still installs and tests with **no** UI extras | `S` | `T-004` |

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
.venv/bin/python -m pytest -q          # expect: 37 passed (plus new tests)
git diff --stat -- output/             # expect: empty, always
```

### 7.3 Re-verify the numbers in §3
```bash
python3 -c "import json;print(len(json.load(open('output/pqlWNihgdjI/knowledge_units.json'))['units']))"
python3 -c "import json;print(json.load(open('output/pqlWNihgdjI/coverage.json'))['status'])"
python3 -c "import json;print(json.load(open('output/pqlWNihgdjI/validation.json'))['status'])"
cat output/library/status.json
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
| **R11** No `PARTIAL`/`FAIL` fixture, so honest-status UI is untestable | 🔴 Open | `T-006` — synthetic fixtures, labeled test-only, never presented as real evidence |
| **R12** Dual ID vocabulary (2-part in library files, 3-part in index) drifts | 🟡 Watch | §6 warning; single owner for `library.py`; assert both forms in tests |
| **R13** `finalize_run` triggers a full `rebuild_library` over *all* sources every time — cost grows linearly | 🟡 Watch | Acceptable at current scale; revisit when source count grows. Do not fix speculatively |
| **R14** No path-traversal guard in existing `query.py` / `mcp_server.py` joins | 🟡 Watch | The new API must route ids through `pipeline._safe_identifier`, not copy the existing pattern (`T-108`) |
| **R15** Absolute host paths baked into `library/status.json` and `library/videos.json` | 🟡 Watch | Index must store project-relative paths; never trust the absolute value |
| **R16** `value` field on statistic units is polymorphic (`int` \| `list[float]`) | 🟡 Watch | Cannot map to one SQL column — store as JSON text, keep the canonical file authoritative |

Risks 1–6 and 8 from canvas plan §18 remain as written.

---

## 10. Reuse — do not reimplement these

| Existing code | Use it for |
|---|---|
| `io.write_json` (`io.py:19`) | **Already atomic** (same-dir temp + `os.replace`) — satisfies canvas plan §15 outright. Note: Markdown/report writes use plain `write_text` and are *not* atomic |
| `io.sha256_file` (`io.py:11`) | Incremental index change detection |
| `io.timestamp_url` (`io.py:42`) | YouTube deep links; `&t=<int>s` output is contract-locked by `tests/test_core_pipeline.py` |
| `pipeline.validate_run` (`pipeline.py:236`) | The **only** legitimate source of run status. Read it; never recompute |
| `pipeline._safe_identifier` (`pipeline.py:42`) | Sanitize every HTTP-supplied source id |
| `library.rebuild_library` (`library.py:24`) | Generalize **additively**; do not rewrite |
| `query.search_knowledge` (`query.py:27`) | Its two result shapes are the de-facto API contract to preserve while FTS5 replaces the linear scan |
| `constants.py` | The real controlled vocabulary: 22 source kinds, 8 derived kinds, 16 relation types, 10 omission reasons |
| `artifacts.SECTION_ORDER` (`artifacts.py:20`) | A ready-made 12-section UI grouping taxonomy for knowledge kinds |

**Conventions to follow:** lazy optional imports inside CLI branches (`cli.py:174,180,188,196`) so the core stays zero-dependency · `X2KNWLDG_PROJECT_ROOT` env var for root resolution (`mcp_server.py:17`) · `config/*.local.json` tracked-example / ignored-local pattern.

**Vocabulary the Map must style:** `derived_from` and `expresses_concept` are library-only synthetic relations that are **not** in `RELATION_TYPES`. In the current data they are the two most common edges (45 and 17 of 118).

---

## 11. Next step

**Start `T-002`** — define the v1 schemas for `Source`, `Artifact`, `Locator`, `EntityRef`, and `IndexedRelation`, versioned and machine-validatable.

`T-001` is complete: the ADR convention is established in [`adr/README.md`](adr/README.md) and the architecture decision is recorded in [ADR 0001](adr/0001-local-web-ui.md), which consolidates D-001…D-013 and lists the ten invariants the build must preserve. Read ADR 0001 §Invariants before writing schema code — invariant 4 (`library.py`'s 2-part ID is load-bearing for `kg_navigator`) and invariant 6 (source-neutrality belongs in the adapter layer, not the canonical files) both constrain `T-002` directly.

Phase 0 remains **one agent, no fan-out**. Do not begin Canvas or production UI design until the Phase 0 gate in §5 passes.
