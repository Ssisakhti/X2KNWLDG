# ADR 0001 — Local-first web layer for the Knowledge Canvas

- **Status:** Accepted
- **Date:** 2026-08-31
- **Decision ledger:** consolidates D-001 … D-013 (`KNOWLEDGE_CANVAS_PLAN.md` §19). D-014 (documentation language) is a project convention recorded in §19 and `docs/adr/README.md`, not an architecture decision.
- **Supersedes:** none
- **Superseded by:** none

## Context

The X2KNWLDG core is a provenance-first extraction pipeline. It has properties worth protecting:

- **Zero runtime dependencies.** `pyproject.toml` declares `dependencies = []`; everything optional sits behind an extra (`youtube`, `mcp`, `legacy`, `dev`) and is imported lazily inside the CLI branch that needs it (`src/x2knwldg/cli.py:174,180,188,196`).
- **Canonical files are the source of truth.** Every consumer reads `output/<source-id>/` directly.
- **Evidence integrity is the product.** `output/<id>/raw/` is immutable; timestamps, quotes, confidence, and coverage are never invented; `source` and `derived` knowledge are kept apart.

It has **three independent consumers already**, all of which read the filesystem by literal path and glob:

1. The CLI (`x2knwldg`, 8 subcommands).
2. The MCP server (`x2knwldg-mcp`, 10 tools + 3 resources), rooted at `X2KNWLDG_PROJECT_ROOT`.
3. Three Claude Code skills in `.claude/commands/` — `process`, `kg_navigator`, `video_specialist`.

**Verified data state (measured 2026-08-31, not assumed):** the sample source `pqlWNihgdjI` is a complete run — 69 knowledge units (61 `source`, 8 `derived`), 56 relationships, 69 graph nodes / 56 edges, `coverage.json` = `PASS`, `validation.json` = `PASS`; `output/library/` holds 1 video, 17 canonical concepts, 118 edges. Test baseline: 37 passed. Toolchain: Node 26.5.0, Python 3.14.6, SQLite 3.53.4 with FTS5 available.

What is missing is a way to **read, relate, and think with** this knowledge: a searchable library, a reader with timestamp navigation, a graph overview, and a freeform canvas with pen annotation.

### Constraints

1. Personal, single-user, fully local on macOS. No paid service, no cloud dependency, no telemetry.
2. Evidence integrity outranks convenience. The UI may never fabricate a graph, a status, or a locator, and may never write to `raw/`.
3. Must not calcify around YouTube; Twitter/X, Medium, articles, and PDFs are planned.
4. The zero-dependency core must stay installable and testable **without** any UI dependency.
5. The three existing consumers must keep working unchanged.
6. Personal-scale software. Solve the actual problem; do not over-engineer.

### Relationship to the build spec

`X2KNWLDG_build_spec.md` §39 lists a web UI under *"Not required in v1"*, immediately followed by *"Design interfaces so these can be added later."* This ADR is that "later". It does not contradict the spec; it moves past a v1 scope boundary that the spec explicitly anticipated.

## Decision

Build a **dedicated, thin, local-first layer** over the existing pipeline rather than adopting a general-purpose knowledge product.

1. **Do not fork a finished product.** AFFiNE, Logseq, and similar are studied for UX patterns and architectural lessons only. *(D-001)*
2. **Ship a local web app** served on loopback and viewed in the browser. *(D-002)*
3. **Stack:** React + TypeScript + Vite (frontend); React Flow `@xyflow/react` for Canvas *(D-003)*; Sigma.js + Graphology for the Knowledge Map *(D-004)*; Pointer Events + `perfect-freehand` for the pen *(D-007)*; FastAPI for the local service; SQLite + FTS5 as the index *(D-005)*.
4. **Two renderers over one dataset.** Canvas and Knowledge Map are different views with different performance profiles and must **not** share a renderer or a storage model. Canvas is a small, curated, deeply interactive set; the Map is a large, shallow, WebGL overview. This is the single most load-bearing structural decision here.
5. **Three storage tiers with hard boundaries** *(D-006)*:
   - `output/<source-id>/` — canonical pipeline output. **Read-only to the UI.**
   - `workspace/` — user canonical data (boards, notes, attachments). Portable, backup-able.
   - `.x2knwldg/` — rebuildable cache (`index.sqlite`, thumbnails). Deleting it must lose nothing.
6. **The backend is an optional extra.** A new `ui` extra plus a `ui` CLI subcommand using the established lazy-import pattern. Installing the core must not pull FastAPI, uvicorn, or any frontend tooling.
7. **A source-neutral index model** — `Source`, `Artifact`, `Locator`, `EntityRef`, `IndexedRelation` — with per-source **adapters** mapping canonical directories onto it. YouTube is the first adapter; its interface is generic from the start. Adding a source must require an adapter and possibly a node renderer, never a frontend rewrite.
8. **3-part global entity IDs** `<source-type>:<external-id>:<local-id>`, adopted **before the first board file exists** so no board migration is ever needed. This is **additive** — see *Invariants*. *(D-011)*
9. **Canonical API is read-only** in the first phase. Write endpoints target `workspace/` and the cache only. Mutations are atomic.
10. **UI language switchable, English default**, with bidi-correct content rendering and logical CSS properties from the first component. *(D-012)*
11. **No graph database.** SQLite adjacency tables plus Graphology in memory cover the current need. *(D-009)*
12. **No desktop packaging yet.** Tauri is evaluated only if the local web app shows a *proven* limitation in file access, launch UX, or performance; Electron is not planned. Any such migration must not require a frontend rewrite. *(D-010)*

## Alternatives considered

| Alternative | Why rejected |
|---|---|
| Fork AFFiNE or Logseq | Both carry large runtimes and their own data models. Retrofitting provenance-first, source/derived/user separation into someone else's block model costs more than building a thin layer, and every upstream merge becomes a risk to evidence integrity. *(D-001)* |
| tldraw for the canvas | Production use requires a commercial licence key. Excluded on licensing grounds alone. *(D-008)* |
| Excalidraw as the canvas core | Excellent freeform sketching, but the canvas here must host live typed entity nodes with provenance, not shapes. Possible later as an isolated "sketch document" import/export feature. *(D-004 area)* |
| BlockSuite | A powerful document + edgeless editor, but it imports a whole framework and data model for a need the first phases do not have. Revisit via an independent spike only if a fully integrated document editor becomes necessary. *(D-005 area)* |
| Electron shell | Extra runtime and packaging burden with no offsetting benefit for a personal local app. |
| Tauri now | Premature. Packaging cost before any evidence that a browser cannot do the job. *(D-010)* |
| A graph database (Neo4j, KùzuDB) | The graph is small — currently 86 nodes / 118 edges library-wide. Adjacency tables plus Graphology are sufficient, and a second database is a real operational cost. *(D-009)* |
| One renderer for both Canvas and Map | The two views have opposed requirements: rich HTML nodes and deep interaction versus tens of thousands of cheap WebGL nodes. A single renderer would be bad at both. |
| Extend the MCP server instead of adding HTTP | MCP tools are agent-facing and defined inside an `if MCPServer is not None:` block, so they are not importable without the `mcp` extra. A browser needs HTTP, static assets, and range requests regardless. |
| Skip the index; scan files per request | `query.search_knowledge` already scans every file on every call (`query.py:36-102`). That is fine for a CLI, but not for interactive search-as-you-type across a growing library. |
| A vector database / embeddings | Not needed for the current retrieval task, and the build spec §39 already lists it as a v1 non-goal ("if local files suffice"). FTS5 first; revisit only on demonstrated need. |

## Consequences

**Positive**

- Provenance stays first-class: three storage tiers make "evidence vs. synthesis vs. my own notes" a structural property, not a UI convention.
- The zero-dependency core is preserved; `pip install x2knwldg` remains stdlib-only.
- The CLI, MCP server, and the three skills keep working untouched, because the index is a pure derived cache.
- Deleting `.x2knwldg/` is always safe.
- New source types need an adapter, not a rewrite.
- Every library chosen is MIT/permissive with no paid tier.

**Negative / accepted costs**

- Two renderers means two mental models, two sets of styling rules, and two performance budgets.
- An index is a cache, and caches drift. Rebuild-equivalence needs an explicit test (`T-104`, `T-115`).
- Two ID vocabularies coexist for now (2-part in library files, 3-part in the index) — see *Invariants*.
- A browser-based pen depends on Pointer Events behaving well on the user's actual hardware; this needs a spike on the real device, not an assumption. *(D-007 is accepted for a spike, not yet proven)*
- More languages and toolchains in one repo: Python, TypeScript, SQL.
- No `PARTIAL`/`FAIL` source exists today, so honest-status rendering must be validated against labelled test-only fixtures (`T-006`).

**Neutral**

- FastAPI and uvicorn become optional dependencies; pinned at implementation time.
- The React Flow free-tier attribution stays in place; Pro examples are not copied.
- SQLite 3.53.4 is far past the WAL-reset fix the canvas plan §9.4 flagged, so WAL is available — but a single controlled writer is preferred over concurrency for a single-user app.

## Invariants this decision must preserve

1. **`output/<id>/raw/` is never written by the UI.** No exception.
2. **Run status comes only from `validation.json` and `coverage.json`,** read via `pipeline.validate_run`. The UI must never recompute or infer status, and never coerce `PARTIAL`/`FAIL` toward `PASS`.
3. **SQLite is a cache.** Nothing may exist only in the index. Deleting `.x2knwldg/` must lose no evidence, no canonical knowledge, and no user content.
4. **`library.py`'s 2-part ID stays.** `.claude/commands/kg_navigator.md` *mandates* `<video-id>:<knowledge-unit-id>` for `output/library/graph.json` nodes, and `library.py:49` emits exactly that. The 3-part ID of decision 8 is **additive**: `library.py` keeps `id` and gains a `source_type` field plus a 3-part `global_id`. Consolidating the two forms without also updating `kg_navigator.md` is a breaking change.
5. **The core package installs and tests with zero dependencies.** Any import of FastAPI, uvicorn, or an adapter dependency stays lazy and behind an extra.
6. **Source-neutrality lives in the adapter and index layer**, not in the canonical files. `video_id` is required in the canonical provenance contract (`validators.py:50`) and stays there; adapters map it to `external_id`.
7. **Writes are atomic.** Reuse `io.write_json` (`io.py:19`), which is already temp-file + `os.replace`. Note that Markdown/report writes elsewhere use plain `write_text` and are *not* atomic.
8. **Path traversal is closed at the boundary.** Every source id arriving over HTTP goes through `pipeline._safe_identifier` (`pipeline.py:42`). The existing `query.py` and `mcp_server.py` joins have no such guard; the API must not copy that pattern.
9. **The server binds loopback only,** with no telemetry, no default outbound requests, and an allowlist for external embeds.
10. **Provenance is never signalled by colour alone** — icon, label, or line style must also distinguish `source` / `derived` / `user`.

## References

- [`KNOWLEDGE_CANVAS_PLAN.md`](../KNOWLEDGE_CANVAS_PLAN.md) — full product and architecture design; §19 decision ledger
- [`PROJECT_MANAGEMENT.md`](../PROJECT_MANAGEMENT.md) — execution tracker, task backlog, agent parallelism model
- [`X2KNWLDG_build_spec.md`](../X2KNWLDG_build_spec.md) — pipeline contract; §39 v1 non-goals
- `AGENTS.md`, `WORKFLOW.md` — inherited invariants
- React Flow attribution: <https://reactflow.dev/remove-attribution>
- tldraw licence: <https://tldraw.dev/community/license>
- SQLite FTS5: <https://www.sqlite.org/fts5.html>
- Pointer Events pressure: <https://developer.mozilla.org/en-US/docs/Web/API/PointerEvent/pressure>
