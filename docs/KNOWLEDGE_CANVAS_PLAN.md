# X2KNWLDG Knowledge Canvas — Product and Architecture Plan

---

**Document status:** active; the design authority for continuing this work
**Current stage:** Phases 0 and 1 complete; Phase 2 Knowledge Map approved and decomposed as the `T-201` epic (`T-202` is next)
**Last updated:** 2026-09-02
**Current scope:** personal, fully local execution on macOS, YouTube first
**Data owner:** the user; no dependency on any paid service or cloud storage

---

## 1. Purpose of this document

This file is the primary reference for designing and building the X2KNWLDG visual layer across multiple sessions. Any agent or developer continuing the work must read `AGENTS.md` and `WORKFLOW.md` before changing anything here.

This document must always keep the answers to these questions clear:

- Exactly what product is being built, and what is out of scope?
- Which decisions are settled, and which remain open?
- Where is the boundary between evidence, extracted knowledge, and the user's own content?
- How do the architecture and data contract avoid being locked to YouTube?
- What does each phase deliver, and what are its acceptance criteria?
- Where should the next session pick up?

This is a living document. At the end of each execution session, the "Execution status", "Decisions", "Risks", and "Next step" sections must be updated.

**Language:** all project documentation is written in English. Persian is used only in the application UI (see D-012) and in knowledge content extracted for the user. See D-014.

## 2. Summary of the final decision

X2knwldg gets a dedicated, lightweight, local-first layer. Complete products such as AFFiNE and Logseq will not be forked; they are used only for UX patterns and architectural lessons.

Proposed stack:

- **Frontend:** React + TypeScript + Vite
- **Interactive canvas:** React Flow (`@xyflow/react`)
- **Global graph:** Sigma.js + Graphology
- **Pen and freeform drawing:** Pointer Events + `perfect-freehand` + an SVG layer
- **Local service:** FastAPI on top of the existing Python package
- **Search and index:** SQLite + FTS5
- **Initial delivery:** a local web app on `localhost`
- **Desktop packaging:** Tauri only if a need is proven in later phases

The key architectural principle:

> Canvas and Knowledge Map are two different views of one dataset, and they must not be implemented with a single renderer or a single storage model.

- Canvas is for a limited number of selected items, deep interaction, notes, media, and the pen.
- Knowledge Map is for quickly surveying the global graph, its clusters, and relationship neighbourhoods.

## 3. Firm user requirements

### 3.1. Environment and ownership

- Personal use on a MacBook only.
- All data and processing local wherever possible.
- No paid service in this part of the system.
- Designed from the start for a growing volume of sources, but not over-engineered.
- Technology chosen for fit to the problem, not out of preference for the web, Rust, or any particular tool.

### 3.2. Product experience

- A clean, minimal, professional, low-friction UI.
- A combination of content library, reader, knowledge graph, and canvas.
- Opening and reading documents, transcripts, audio, video, and sources inside the application.
- Showing the relationships between sources, knowledge units, concepts, and evidence.
- Placing selected items on the canvas and connecting them.
- Writing and drawing freely with a stylus.
- The pen is annotation only; it is not meant to become text or a knowledge unit.

### 3.3. Sources

- First phase: YouTube.
- Later: Twitter/X, Medium, web pages, PDFs, and other content types.
- Neither the UI core nor the index model may treat `video_id` as a concept common to all sources.

## 4. Current state of the repository

The current X2KNWLDG core is a provenance-based pipeline that produces these files for each video:

```text
output/<video-id>/
  raw/
    source.<ext>
    transcript.json
    transcript.md
  metadata.json
  transcript.json
  segments.json
  knowledge_units.json
  relationships.json
  coverage.json
  validation.json
  report.md
  graph.json
  vault/
```

Files under `raw/` are immutable evidence; the UI has no right to modify them.

The core also produces a cross-video graph, canonical concepts, and a video list under `output/library/`. The current logic lives in `src/x2knwldg/library.py` and should be generalized incrementally rather than rewritten.

`library/status.json` reports what it *could not* do as well as what it did (D-043):
`runs_discovered`, `runs_indexed`, `runs_skipped`, `skipped_runs[]` (each with a
`relative_path` and a `reason`) and `incomplete_runs[]` beside the counts, and every
`videos.json` entry carries `problems: []`. **Read `runs_indexed`, not `videos`, when you
mean "how many runs are in the library"** — a run missing a canonical file is now indexed
from what it has and named in these fields, where it used to disappear from `graph.json`,
`videos.json` and the count with no hint anywhere. No edge invents a confidence:
`expresses_concept` is `null`, and `derived_from` copies the unit's own value, `null` when
the unit states none.

The current sample `pqlWNihgdjI` has a complete extraction. State measured on 2026-08-31:

- `validation.json` is `PASS` (all five sections `PASS`).
- `coverage.json` is `PASS` (5 of 5 windows, `audit_attempts: 1`).
- `knowledge_units.json` contains 69 units (61 `source`, 8 `derived`).
- `relationships.json` contains 56 relationships.
- `graph.json` contains 69 nodes and 56 edges.
- `output/library/` contains 1 video, 69 knowledge nodes, 17 canonical concepts, and 118 edges.

> **`output/library/` was regenerated under D-043 on 2026-08-31** (`x2knwldg rebuild-library`,
> exit 0), so the sample on disk now shows current behaviour. What moved: the 17
> `expresses_concept` edges went from the fabricated `confidence: 1.0` to `null`;
> `videos.json` gained `problems: []`; `status.json` gained `runs_discovered: 1`,
> `runs_indexed: 1`, `runs_skipped: 0`, `skipped_runs: []`, `incomplete_runs: []`.
> `concepts.json` came back byte-identical, and the totals did not move — 118 edges over 86
> nodes, before and after. The 45 `derived_from` edges kept their real confidences (0.88–0.97):
> every unit in this sample states one, so the fabricated `0` D-043 removed was a default this
> data never reached.
>
> ⚠️ `output/` is gitignored, so this regeneration is **not** in version control. The tree on
> one machine can differ from another's, and nothing in the repository records which state a
> given clone holds — re-run `rebuild-library` rather than assuming.

> **Document correction:** an earlier version of this section described these files as "empty" and coverage as `PARTIAL`. That description was stale and has been corrected. Execution details are recorded in `PROJECT_MANAGEMENT.md`.

Real, valid data is therefore available for developing the Knowledge Map, and there is no need to construct a synthetic graph. The core rule does not change, however: the UI must display status exactly as `validation.json` and `coverage.json` report it, and must never produce a fabricated graph, evidence, or content.

No *real* source has `PARTIAL` or `FAIL` status. Honest rendering of those two states is covered instead by the clearly labelled test-only runs in `tests/fixtures/runs/` (`T-006`, D-019), which are synthetic and must never be presented as evidence about a real video.

## 5. Invariant principles

These principles carry over from `AGENTS.md` and `WORKFLOW.md` to the UI as well:

1. Evidence comes before summarization and before displaying derived knowledge.
2. A timestamp, quote, evidence excerpt, confidence, or coverage value is never fabricated or guessed.
3. `PARTIAL` and `FAIL` status must be displayed clearly and never converted to `PASS`.
4. The canonical files are the source of truth.
5. SQLite is only a rebuildable index/cache.
6. The user's notes, strokes, node positions, and manual relations are separate from canonical knowledge.
7. No UI interaction may modify files under `raw/`.
8. Whether knowledge is source-grounded or derived must be distinguishable in both the data model and the UI.
9. Deleting the cache must not cause the loss of evidence, canonical knowledge, or the user's own content.
10. Adding a new source must not require a frontend rewrite; only an adapter and a node renderer.

## 6. Product model

The product has four main surfaces that share selection and navigation.

### 6.1. Library

A searchable, filterable library of sources:

- Videos, and later articles, tweets/threads, PDFs, audio, and local files
- Title, source, language, date added, duration, and pipeline status
- Knowledge unit count, relationship count, and coverage status
- Search across transcript, knowledge units, evidence, and report
- Filters by source type, kind, source class, confidence, and validation status
- List and compact grid modes

### 6.2. Reader

The view for reading and inspecting a single source:

- Video or audio player
- PDF/document viewer
- Timed transcript with jump-to-timestamp
- Markdown report
- Related knowledge units
- Evidence excerpt and precise locator
- Incoming and outgoing relationships
- Validation and coverage status
- Adding the selected item to the Canvas

For YouTube there are two playback modes:

1. Online embed using `video_url`, with seek to a timestamp;
2. Local file playback, only if the media file is genuinely available.

The existence of a local video file must not be assumed; the current pipeline stores the transcript, not necessarily the video itself.

### 6.3. Knowledge Map

The automatic global graph view:

- Rendered with Sigma.js/WebGL
- Displays concepts, knowledge units, and sources
- Filters for relationships and source classes
- Search and focus on a node
- Shows a neighbourhood rather than loading details for every node
- Swappable cluster and layout algorithms if needed
- Opens node details in the inspector
- Moves a selected node or subgraph to the Canvas

The Knowledge Map is not the primary environment for editing or media playback.

### 6.4. Canvas

A freeform, saveable board for the user's own arrangement:

- Knowledge Unit node
- Concept node
- Source/Video node
- Transcript Segment node
- Evidence/Quote node
- Markdown/User Note node
- PDF/Document node
- Audio node
- Image node
- Group/Frame
- Ink stroke
- Canonical relation reference
- User-created relation

The Canvas must not render the entire library graph at once. Items are added to a board explicitly by the user, or from a bounded subgraph.

## 7. UI/UX outline

Proposed base layout:

```text
┌───────────────┬─────────────────────────────────┬──────────────────┐
│ Navigation    │ Main View                       │ Inspector        │
│               │                                 │                  │
│ Library       │ Library / Reader / Map / Canvas │ Details          │
│ Sources       │                                 │ Evidence         │
│ Boards        │                                 │ Relations        │
│ Saved views   │                                 │ Validation       │
└───────────────┴─────────────────────────────────┴──────────────────┘
```

UX principles:

- Focus on content, not on many permanent panels.
- The inspector must be collapsible.
- A command/search palette for fast navigation.
- Selecting a node in the Map, Canvas, or Reader must refer to one shared entity.
- Heavy details load only on selection.
- Colour must not be the only indicator of provenance; icon, label, or line style must also be used.
- The exact visual language is settled after wireframes, but distinguishing these three categories is mandatory:
  - source-grounded
  - derived
  - user-authored
- Coverage and validation status must always be available, but must not interfere with reading.
- Layout and typography must handle bidirectional text correctly for both Persian and English content.

## 8. System architecture

```text
Canonical filesystem
output/<source-id>/...
        │ read-only
        ▼
Source adapters + Indexer
        │
        ▼
SQLite FTS5 index/cache ───── FastAPI local API
        │                           │
        └───────────────────────────┤
                                    ▼
                         React/Vite application
                     ┌──────────┬──────────┬──────────┐
                     │ Library  │ Map      │ Canvas   │
                     │ Reader   │ Sigma.js │ ReactFlow│
                     └──────────┴──────────┴──────────┘
                                    │ writes
                                    ▼
                           workspace/ user data
```

### 8.1. Local backend

FastAPI is added to the existing package as an optional extra; the CLI and the core pipeline must not be forced to install frontend/backend dependencies for headless use.

Backend responsibilities:

- Scanning and indexing the canonical outputs
- APIs for search, library, graph, and entity detail
- Serving transcript/report/metadata
- Serving local files and media safely, with proper range-request support where needed
- Persisting workspace data
- Rebuilding the index
- Exposing health/status and schema version information

The backend is not responsible for extracting knowledge or for altering validator results.

### 8.2. Frontend

The frontend is a standalone React/Vite app in the proposed `web/` directory.

Frontend responsibilities:

- Navigation and search
- Library and Reader
- Map renderer and interaction
- Canvas renderer and persistence interaction
- Pen and drawing tools
- Inspector and provenance display
- Optimistic UI for workspace data only, never for canonical output

### 8.3. Local execution

The expected final command, once implemented:

```text
x2knwldg ui
```

This command must:

1. Resolve the project root;
2. Check or rebuild the index if needed;
3. Run the local-only service on loopback;
4. Open the default browser;
5. Not expose paths outside the project root without permission.

The exact port and how it is chosen are decided during implementation, and must not rely on a brittle hard-coded value.

## 9. Storage boundaries

### 9.1. The existing source of truth

```text
output/<source-id>/...
```

- Produced by the pipeline.
- Normally read-only to the UI.
- The validators are the authority on status.

### 9.2. The user's canonical data

Proposed structure:

```text
workspace/
  boards/
    <board-id>.json
  notes/
    <note-id>.md
  attachments/
```

This data is backup-able, version-controllable, and portable. The exact directories are created during the persistence phase.

### 9.3. Rebuildable cache

```text
.x2knwldg/
  index.sqlite
  thumbnails/
  cache/
```

- Deleting this directory must not destroy any primary data.
- This directory is not suitable for version control by default.
- Thumbnails and media derivatives never replace the original file.

### 9.4. SQLite rules

- FTS5 is used for text search.
- A separate graph database is not used in the first phase.
- A plain adjacency table is sufficient for relationships.
- Schema migrations must be explicit and versioned.
- If WAL is used, SQLite must include the WAL-reset fix; verify the actual version and runtime before enabling it. *(Verified 2026-08-31: SQLite 3.53.4 with FTS5 available — well past that fix.)*
- A single controlled writer is preferred; complex concurrency is unnecessary for a personal app.

## 10. Generic data model

The UI/index model must be source-neutral.

### 10.1. Source

Represents the primary source:

```json
{
  "id": "youtube:pqlWNihgdjI",
  "source_type": "youtube",
  "external_id": "pqlWNihgdjI",
  "url": "https://www.youtube.com/watch?v=pqlWNihgdjI",
  "title": "...",
  "language": "en",
  "status": "PASS"
}
```

### 10.2. Artifact

A representation or file belonging to a Source:

- video
- audio
- transcript
- article
- PDF
- report
- raw evidence
- image

### 10.3. Locator

The precise location of evidence or an anchor:

```json
{
  "type": "time_range",
  "start_sec": 120.5,
  "end_sec": 138.2
}
```

Future types:

- `time_range`
- `page`
- `page_bbox`
- `text_span`
- `post_id`
- `url_fragment`

A Locator must never be constructed without canonical data.

### 10.4. KnowledgeUnit

The current fields are preserved:

- stable ID
- kind
- source class
- content
- confidence
- source/locator for a source-grounded unit
- derived_from and derivation_note for a derived unit

Proposed global identifier:

```text
<source-type>:<external-id>:<local-unit-id>
```

Examples:

```text
youtube:pqlWNihgdjI:KU-001
twitter:1840000000000000000:KU-001
medium:article-slug:KU-001
```

See D-011: this identifier is **additive**. `library.py` keeps its existing two-part form.

### 10.5. Relation

Every relation must carry an explicit origin class:

- `source`: directly supportable from the source
- `derived`: the result of recorded synthesis or inference
- `user`: a manual link in the workspace

A user relation must never be written automatically into `relationships.json`.

### 10.6. Board and BoardItem

A board holds only layout and the user's selection:

- board metadata
- entity reference
- position and dimensions
- collapsed/expanded state
- per-node view state such as the current timestamp or page, where needed
- user edges
- ink strokes
- frames and groups

Canonical content must not be duplicated inside a board, except as an explicit snapshot for link durability; the snapshot decision is made during the schema phase.

## 11. Source Adapter contract

Every new source must be converted to the shared indexer contract.

Minimum adapter output:

- Source record
- Artifact records
- KnowledgeUnit records
- Relation records
- Locator records
- validation/coverage status
- paths to the canonical files

Planned adapters:

1. YouTube adapter, from the current `output/<video-id>` structure
2. Twitter/X adapter, after the corresponding extraction pipeline is designed
3. Medium/article adapter
4. Generic file/PDF adapter

Only the YouTube adapter is implemented in the first phase, but its interface will be generic.

### 11.1 What an adapter does with what it cannot map

An adapter never drops something in silence. Two free-form channels on
`Source.adapter_metadata` carry it (D-045):

- `unmappable_artifacts` — a generated `vault/` note whose filename cannot spell an id. The
  note is left out of the index and named here, with its path and reason, rather than one
  unaddressable export making a whole project unindexable.
- `unreadable_files` — a canonical file that is present and damaged. Its counts were already
  omitted rather than zeroed, but "this count is missing" does not say "this file is broken",
  and only one of those is actionable.

Both are absent when there is nothing to report; an empty list reads like an unread finding.
A UI showing a source must surface them.

The line is index integrity, not convenience. A run whose `knowledge_units.json` is damaged
while its `relationships.json` is intact is **refused** at adapt time, naming the dangling
edge: stranded edges would make `/api/graph` and `/api/sources/{id}/relations` disagree about
one fact, `check_index_integrity` would refuse the whole project later anyway, and the
failure belongs on the run that causes it.

## 12. Library choices and constraints

### 12.1. React Flow

Used for:

- Custom HTML nodes
- Connecting and moving nodes
- Zoom/pan/selection
- Frames and groups
- Saving layout

Rules:

- React Flow's free-tier attribution is not removed.
- Pro examples are not copied.
- Pen capability is built with the project's own implementation and MIT-licensed libraries.
- Components and callbacks must be memoized.
- Nodes not needed by the board must not be rendered.

### 12.2. Sigma.js + Graphology

Used for:

- The global graph and WebGL rendering
- Focus, filtering, neighbourhood, and cluster visualization
- In-memory graph algorithms

The Map must not place heavy HTML components on each node. Details are shown in the inspector.

Phase 2 starts with an exactly pinned Sigma v4 beta, subject to the real-graph and real-device
compatibility gate in `T-202` ([ADR 0005](adr/0005-knowledge-map-client.md), D-117). The
official v4 site now describes this line as beta and documents `4.0.0-beta.5`; it began as an
alpha and remains prerelease, so a moving semver range is forbidden. If `T-202` finds a
blocking v4 defect, it records that evidence and selects stable v3 before any later Map task
begins. The phase carries one renderer API, never a compatibility layer for both.

### 12.3. perfect-freehand

Used for:

- Stroke smoothing
- Pressure-sensitive drawing
- Converting points to an SVG path

Strokes must be stored in world/canvas coordinates, not viewport coordinates.

### 12.4. Excalidraw

Not used in the Canvas core. If a standalone "sketch document" is needed later, embedding or Excalidraw import/export can be evaluated as a separate feature.

### 12.5. BlockSuite

Not used in the first phase. If the need for a fully integrated document and edgeless editor exceeds the current scope, an independent spike will compare it against the existing architecture.

### 12.6. tldraw

Excluded from the current choice because of its production licence and the requirement for a licence key.

### 12.7. Tauri and Electron

- Electron is not recommended in the current architecture; the extra runtime and packaging burden is not sufficiently justified for a personal local app.
- Tauri is evaluated only when the local web app shows a proven limitation in file access, native integration, launch UX, or performance.
- Any eventual migration to Tauri must not require a frontend rewrite.

## 13. Performance strategy

### 13.1. General rules

- Metadata and summary first; heavy text and media on demand.
- Long transcripts must be virtualized.
- Thumbnails must be lazy and cacheable.
- Media files are not stored inside SQLite.
- The index reloads only changed sources, based on hash/mtime.
- A full index rebuild must always be possible.
- UI queries must be page-based or cursor-based.
- Graph layout runs in a worker only if the real data size blocks the UI thread — not sooner.

### 13.2. Canvas

- A board is naturally curated and bounded.
- Players outside the viewport are paused or made lightweight.
- Only the selected or expanded node renders a full reader.
- Heavy shadow, blur, and animation are forbidden across large numbers of nodes.
- Completed strokes are converted to an optimized path; raw points are kept only when necessary.

### 13.3. Knowledge Map

- WebGL renderer.
- Labels for all nodes are not displayed simultaneously.
- Edges are tiered by filter and zoom level.
- Overview first; then neighbourhood and details.
- A page is not presented as a whole graph: loaded nodes/edges, known totals and `truncated`
  remain explicit until the progressive snapshot is complete (D-118).
- Cross-page edges wait until both endpoints have arrived and dedupe by their canonical edge
  `id`; placeholder nodes are never invented.
- Search, selection, neighbourhood and inspector also exist in a bounded semantic DOM surface;
  no operation is WebGL- or pointer-only (D-120).
- The full graph and the Canvas layout are two separate states.

### 13.4. Performance targets

Firm numbers are not set before a real dataset exists. During the performance phase, small, medium, and large fixtures of real or valid synthetic data must be prepared and targets measured on the user's MacBook. No arbitrary threshold is recorded in this document as fact.

## 14. Security and privacy

- The server must listen on loopback only.
- There must be no telemetry or analytics by default.
- No file or content is uploaded without an explicit user action.
- File paths must be validated and path traversal must be impossible.
- Untrusted raw HTML and Markdown must be sanitized.
- External embeds must be allowlisted.
- Opening an external URL must be an explicit, visible action.
- Write APIs are permitted only against `workspace/` and the cache.
- The canonical API is read-only in the first phase.

## 15. API

**Frozen by `T-005`.** The names below are no longer provisional: the contract is
[`schemas/api/v1/openapi.json`](../schemas/api/v1/README.md), and that document — not this
section — is what `T-105`–`T-108` implement and `T-115` tests.

```text
GET  /api/status
GET  /api/sources
GET  /api/sources/{source_id}
GET  /api/sources/{source_id}/entities      # added by T-005: the Reader needs them
GET  /api/sources/{source_id}/relations     # added by T-005
GET  /api/entities/{entity_id}
GET  /api/artifacts/{artifact_id}
GET  /api/media/{artifact_id}
GET  /api/search?q=...
GET  /api/graph
GET  /api/graph/neighborhood/{entity_id}
```

Eleven endpoints, all `GET`. **v1 is read-only** — nothing writes to `output/`, and nothing
at all to `output/<id>/raw/`.

The board endpoints are **reserved and deliberately not frozen** (D-027): boards are
Phase 3 and have no record schema yet, and a contract written for a shape that does not
exist would be rewritten by `T-301`. They return here, additively, once `Board` exists.

API rules:

- IDs are opaque and URL-safe: the two-part `<source_type>:<external_id>` and the
  three-part global id (D-011). A colon is a legal path character and needs no escaping.
- Every response carries `api_version` and `schema_version`.
- The API defines **no response shape of its own**. Bodies are the records the adapters
  already produce, `$ref`-ed from `schemas/v1/` (D-026). The two exceptions are
  `/api/search`, which preserves what `query.search_knowledge` returns (D-028), and
  `/api/status`, which describes the index rather than a source.
- Canonical status is read from the validator files, copied verbatim, `UNKNOWN` included.
- A missing artifact is reported — `available: false`, and `404 unavailable` from
  `/api/media` — never masked with a placeholder (D-030).
- An id is resolved by `pipeline.resolve_run_dir` and **rejected** when unsafe, never
  sanitised (D-020, [ADR 0003](adr/0003-reject-unsafe-identifiers.md) — which supersedes
  ADR 0001 invariant 8, the one place that said to sanitise). A malformed id is
  `400 invalid_id`, not `404`.
- The four HTTP codes above are the whole taxonomy **for HTTP**. Boundaries that are not
  HTTP — the MCP server — add `invalid_request` for an argument refused before anything is
  read where no identifier is involved (two tool parameters are *paths*, not ids), and
  `internal_error` as the boundary's own catch. Reporting a refused path as `invalid_id`
  would name something the request never contained (D-044).
- Mutations, when Phase 3 introduces them, must be atomic: write to a temp file, then
  replace safely. `io.write_json` already is.

## 16. Execution phases

### Phase 0 — Contracts and scaffolding

**Goal:** fix the boundaries before any heavy UI work.

Deliverables:

- A short ADR for the architecture choice
- Version 1 schemas for Source/Artifact/Locator/EntityRef
- The YouTube adapter contract
- A frozen API contract (§15), with TypeScript types generated from it
- The repository interface between the indexer and the API ([ADR 0002](adr/0002-index-repository-seam.md))
- ~~The `web/` structure and the optional backend~~ — done: [`web/`](../web/README.md) plus the
  `ui` extra (`T-008`)
- ~~A defined development command~~ — done: `x2knwldg ui`, scaffolded as a refusing stub that
  `T-116` wires end to end (D-037)
- Valid fixtures for `PASS`, `PARTIAL`, and `FAIL` states

Acceptance criteria — **all met, 2026-08-31**:

- No canonical file is modified. ✅
- Schemas are versioned and validate. ✅
- One existing source converts to the generic model with no guessing. ✅
- The Python project still installs and tests without the UI extra. ✅ — `T-009`: 333 passed,
  4 skipped on a venv holding only `x2knwldg` and `pytest`.

### Phase 1 — Read-only Library and Reader

**Goal:** usable value before the Canvas.

Deliverables:

- SQLite/FTS5 index
- Incremental scan and rebuild
- Source and search APIs
- Library UI
- Reader for metadata, transcript, report, and knowledge units
- Timestamp jump to YouTube
- Validation/coverage display

Acceptance criteria:

- Transcript and knowledge unit search work.
- Each source's status is displayed exactly as `validation.json` and `coverage.json` report it; verification uses both the real `PASS` source and a labelled test-only fixture in `PARTIAL` and `FAIL` states.
- Deleting the index and rebuilding produces an equivalent result.
- Raw and canonical files remain unchanged.

### Phase 2 — Knowledge Map

**Goal:** surveying relationships at source and library level.

Deliverables:

- Exactly pinned Sigma v4 beta after the `T-202` real-graph/real-device gate
- Typed `MultiDirectedGraph` projection preserving node/edge identity, direction, parallel
  edges and intentional self-loops
- Progressive graph pages that dedupe D-059 straddling edges and state partiality
- Sigma.js/WebGL view with deterministic initial positions and measured layout
- Node/edge styles based on provenance and kind
- Server-backed source/provenance/relation-vocabulary filters
- Search/focus with one addressable `mapLink` URL grammar
- Bounded neighbourhood view (depth 1–3), with truncation stated
- Collapsible inspector over `/api/entities/{entity_id}`
- Link from Map to Reader through the existing `readerLink` grammar
- Keyboard-operable semantic DOM companion and honest WebGL-unavailable fallback

Acceptance criteria:

- An empty graph is displayed honestly.
- A partial graph is never presented as whole, even on the last page of a paged walk.
- Canonical and derived relationships are distinguishable.
- Selecting a node shows real details and evidence.
- Pointer and keyboard selection resolve the same existing `global_id`, and selection/filter
  state survives reload without inventing a default for malformed URL state.
- The real 86-node/118-edge sample has no lost or duplicated identities after accumulation.
- Sigma and any layout worker release their resources on replacement/unmount.
- The graph is fed from `output/library/graph.json` or an equivalent index.
- Raw and canonical files remain unchanged.

Moving a selected node or subgraph to the Canvas is deliberately not an acceptance criterion
for this phase: the board schema and write API do not exist until Phase 3. Phase 2 may expose
selection in a form Phase 3 can consume, but it must not guess that contract.

### Phase 3 — Canvas and board persistence

**Goal:** building a personal workspace on top of existing knowledge.

Deliverables:

- Create/rename/delete a board, with recoverable behaviour
- Adding entities from Library/Reader/Map
- The core custom nodes
- Connections and user relations
- Frames/groups
- Autosave and undo/redo
- Portable persistence in `workspace/boards/`

Acceptance criteria:

- Closing and reopening the application preserves layout.
- A corrupt or incomplete node does not make the whole board unopenable.
- A user relation is distinguishable from a canonical relation.
- Deleting a board requires confirmation and is preferably recoverable.

### Phase 4 — Pen and annotation

**Goal:** fluid stylus drawing on the canvas.

Deliverables:

- pen/eraser/select
- Pressure, where the hardware supports it
- A minimal, bounded set of colours and widths
- Stroke persistence
- Undo/redo
- Hide/show the ink layer

Acceptance criteria:

- Strokes do not shift under zoom/pan.
- The pen and node dragging do not conflict.
- Drawing has a mouse fallback.
- No stroke ever becomes canonical knowledge.

### Phase 5 — Richer media and documents

**Goal:** more complete multimedia reading.

Possible deliverables, based on real priority:

- PDF.js viewer and page locator
- A lightweight audio waveform, if needed
- Image viewer
- Local media range streaming
- Annotations anchored to a page or timestamp

This phase is scoped only after the actual files in use are known.

### Phase 6 — New sources

**Goal:** adding Twitter/X and Medium without changing the UI core.

Deliverables:

- A canonical ingestion contract per source
- The adapter
- Appropriate locators
- A node renderer, only if needed
- Coexistence tests across multiple source types

### Phase 7 — Desktop packaging, conditional

Only if real evidence shows the local web app is insufficient:

- Tauri spike
- Evaluation of a sidecar or backend launch
- File access and macOS signing
- Comparison of startup, memory, and maintenance cost

## 17. Testing and validation

### 17.1. Backend

- Unit tests for adapters and IDs
- Schema validation
- Index rebuild test
- Search correctness
- Path traversal and file access tests
- Atomic workspace writes
- Migration tests

### 17.2. Frontend

- Component tests for status/provenance
- Interaction tests for Library/Reader/Map/Canvas
- Board save/restore
- Timestamp navigation
- Keyboard accessibility
- RTL/LTR mixed content
- Pen coordinate transform tests

### 17.3. End-to-end

Essential scenarios:

1. Open a source with `PARTIAL` status and see the real warning.
2. Search for a transcript phrase and jump to the timestamp.
3. Select a knowledge unit and inspect its evidence.
4. Move an entity from Map to Canvas.
5. Create a user relation without modifying any canonical file.
6. Draw with the pen, reload, and keep the strokes.
7. Delete the cache and rebuild without losing a board.

### 17.4. Existing validators

The existing validators still run before any claim of pipeline success. The UI has no right to define completion independently of `validation.json` and `coverage.json`.

## 18. Risks and mitigations

### Risk 1: truth and annotation becoming mixed

Mitigation: three separate namespaces and storage tiers for source, derived, and user content; promotion only through an explicit future workflow.

### Risk 2: Canvas slowing down as the library grows

Mitigation: a curated Canvas; the full graph in Sigma; lazy details and no rendering of every node.

### Risk 3: the frontend becoming dependent on YouTube

Mitigation: generic Source/Artifact/Locator and an independent adapter.

### Risk 4: losing a board or strokes

Mitigation: portable files, atomic writes, backup/recovery, and a partial-corruption test.

### Risk 5: premature editor complexity

Mitigation: read-only first phase; minimal rich text; BlockSuite/Tiptap only after a proven need.

### Risk 6: browser pen limitations

Mitigation: a Pointer Events spike on the user's real hardware before finalizing the tools; mouse fallback.

### Risk 7: no valid graph data for development — resolved

Status: **resolved on 2026-08-31.** The `pqlWNihgdjI` sample has a complete, `PASS` extraction with 69 knowledge units, 56 relationships, and 17 canonical concepts; real data is available for Map development.

Residual risk: no `PARTIAL` or `FAIL` source exists, so honest rendering of those states is untested.

Mitigation: build schema-valid fixtures clearly labelled as test data for `PARTIAL` and `FAIL`; never pass them off as real evidence.

### Risk 8: library and licence changes

Mitigation: pin versions at implementation time; review licences before any major upgrade; do not use tldraw in its current state.

## 19. Recorded decisions

This table is the canonical index of decisions and answers "what was decided". The reasoning, rejected alternatives, and consequences are recorded in `docs/adr/`. The ADR convention is described in `docs/adr/README.md`.

Decisions D-001 through D-013 are consolidated and documented in [ADR 0001](adr/0001-local-web-ui.md).

| ID | Decision | Status | Rationale |
|---|---|---|---|
| D-001 | Build a dedicated layer instead of forking a complete product | accepted | Control over provenance and lower complexity |
| D-002 | A local web app in the first phase | accepted | Fits the Python core with the least overhead |
| D-003 | React Flow for the Canvas | accepted | Custom HTML nodes and suitable interaction |
| D-004 | Sigma.js for the Knowledge Map | accepted | WebGL and a good fit for a large graph |
| D-005 | SQLite FTS5 as a rebuildable index | accepted | Local, simple, and sufficient for a single user |
| D-006 | Separate `workspace/` from `output/` | accepted | Protects canonical evidence |
| D-007 | Pen via Pointer Events and perfect-freehand | accepted for a spike | Lightweight and free of paid licensing |
| D-008 | Do not use tldraw | accepted | Production licence restriction |
| D-009 | No graph database initially | accepted | Current need is covered by SQLite/Graphology |
| D-010 | Tauri only after a proven need | accepted | Avoids premature packaging |
| D-011 | Three-part identifier `<source-type>:<external-id>:<local-id>` for index, API, and boards | accepted | Source-neutral; adopted before the first board exists so no migration is needed. **Additive:** `library.py` keeps its two-part identifier so the `kg_navigator` skill does not break |
| D-012 | Switchable UI language, English default | accepted | Text direction is architectural, not cosmetic; adding it later is expensive |
| D-013 | Correct §4 and its dependent criteria, and add labelled test-only fixtures | accepted | Acceptance criteria were resting on a stale fact |
| D-014 | All project documentation in English; Persian only in the UI and in extracted knowledge content | accepted | One documentation language keeps the repo portable between agents and contributors; Persian remains available where it serves the user directly |
| D-015 | The index model is versioned by directory — `schemas/v1/`, JSON Schema 2020-12. Controlled vocabularies are mirrored from `constants.py` and drift-tested; `jsonschema` stays a `dev`-extra dependency | accepted | A breaking change becomes `schemas/v2/` instead of a silent reinterpretation of stored records; mirroring lets the schemas stand alone for TypeScript generation without drifting from the Python vocabulary. Operates inside [ADR 0001](adr/0001-local-web-ui.md); see [`schemas/v1/README.md`](../schemas/v1/README.md) |
| D-016 | Cross-source canonical concepts use the reserved source type `library` with external id `concepts`, giving `library:concepts:<hash>` | accepted | Extends D-011 to entities that belong to no single source, without changing what `library.py` emits |
| D-017 | An identifier segment may begin with `-` or `_`; only a leading dot stays forbidden. `src/x2knwldg/ids.py` is the single implementation of the identifier rules, and the v1 `idPart` pattern was widened to match | accepted | A YouTube id is base64url and legitimately begins with either character — `pipeline.py` already accepts `[0-9A-Za-z_-]{11}` at ingestion, so the narrower schema pattern would have made real sources unaddressable. Widening accepts strictly more, so no stored record is invalidated and no `schemas/v2/` is needed. Barring a leading dot keeps `.` and `..` out of every identifier |
| D-018 | A canonical knowledge unit id must be usable as one segment of a global id; `validators.py` and `extraction_bundle.schema.json` both enforce it | accepted | An id that passes validation but cannot be addressed by the index is a defect deferred to the worst possible moment — it crashed `rebuild_library` at the end of `finalize_run`, after the canonical files were already written |
| D-019 | Labelled synthetic `PASS`/`PARTIAL`/`FAIL` run fixtures are committed under `tests/fixtures/runs/`, and the contract tests run over them unconditionally | accepted | `output/` is gitignored, so the tests that project a real run onto the index model skipped everywhere else. The fixtures also give the honest-status UI something to render before a real `PARTIAL` or `FAIL` ever occurs |
| D-020 | Run directories are resolved by `pipeline.resolve_run_dir`, which rejects an unsafe id instead of sanitising it ([ADR 0003](adr/0003-reject-unsafe-identifiers.md)) | accepted | Sanitising is correct when creating a run and wrong when looking one up: a lookup must fail rather than silently read a different run |
| D-021 | `src/` holds the package only; unmaintained upstream scripts live in `legacy/upstream/` | accepted | They were importable only by accident of an editable install, and two of them are Whisper transcribers the project forbids running |
| D-022 | *(**qualified by D-045** for generated exports)* Adapters live in `src/x2knwldg/adapters/`, one `SourceAdapter` subclass per source type, registered in `ADAPTERS`. `base.py` enforces four rules for all of them: ids built through `ids.py`, project-relative paths, statuses copied, and a refusal (`AdapterError`) wherever a value would have to be guessed | accepted | The generic seam is only real if an adapter cannot opt out of it. Putting the rules in the base rather than in each implementation means a second adapter inherits them instead of re-deriving them — and the two guesses the shape probe made, a hard-coded `raw/source.json` and an assumed media type, are exactly what the rules now forbid |
| D-023 | In v1 the adapter emits entities for knowledge units and canonical concepts only. `caption`, `segment`, and `coverage_window` stay reserved in the `EntityRef` vocabulary and unemitted | accepted | Each already has a canonical representation the Reader and the indexer read directly, and none has a consumer needing a global handle yet. 500-odd caption entities per source, or a segment entity whose only honest `label` is `null`, would have to be undone later. The reserved names mean adding them when a consumer exists needs no `schemas/v2/` |
| D-024 | A source-class locator addresses the **segments** artifact, not the transcript. When a unit's provenance names a different video, `artifact_id` is omitted rather than pointed anywhere | accepted | `validators.validate_provenance` resolves a unit's `segment_id` against `segments.json` and requires the excerpt to appear in that segment's text, so that is where the evidence sits — the shape probe addressed the transcript, which does not hold the segment ids at all. A mis-attributed unit is a canonical error already reported in `validation.json`; the run stays indexable and honest, and the locator stays unaddressed rather than wrong |
| D-025 | *(index side; **amended by D-043** for the library side)* A `derived_from` edge carries `confidence: null`. `expresses_concept` edges are read from `library/graph.json` by `adapt_library`; `derived_from` edges come only from the run that owns them | accepted | A unit's confidence is about the unit — no confidence about the edge exists in any canonical file, and copying one across would put a number on a claim nothing made. Splitting the two synthetic vocabularies by producer keeps a run indexable before `rebuild_library` has ever run, and stops the 45 `derived_from` edges being counted twice |
| D-026 | The API contract is frozen as OpenAPI 3.1 in [`schemas/api/v1/openapi.json`](../schemas/api/v1/README.md), `$ref`-ing `schemas/v1/` rather than restating it. Every response body is an adapter record inside an envelope carrying `api_version` and `schema_version`, and the version is the directory as in D-015 | accepted | The API is a reader, so a response shape of its own would only be a third place for the same fact to drift. `adapt_project(root).by_model()` is what an endpoint returns a page of, and the contract tests validate the endpoints against records the real adapters produce — so the document cannot agree with the schemas while disagreeing with the code |
| D-027 | Only the read-only surface is frozen in v1: eleven endpoints, all `GET`. The board endpoints of §15 stay reserved and unfrozen until Phase 3 gives boards a record schema | accepted | Freezing a contract for a shape that does not exist is inventing one, and `T-301` would rewrite it. The same restraint as D-023 — reserving a name costs nothing, guessing its shape costs a migration |
| D-028 | `/api/search` preserves the two result shapes `query.search_knowledge` already returns and adds `global_id`/`source_id` additively; a `transcript_caption` hit carries no `global_id` | accepted | Those shapes are the de-facto contract the CLI and the MCP tools ship today, and FTS5 is an implementation change, not a contract change. A caption has no global id because v1 emits no caption entities (D-023); minting one would create an address that resolves to nothing |
| D-029 | TypeScript declarations are generated by a stdlib-only script into a committed `types.d.ts`, drift-guarded by a byte-identity test rather than by an npm toolchain | accepted | `T-005` runs before `T-008`, so no `web/`, no `package.json`, and no Node in CI yet; putting the frontend's types behind a dependency the core package does not have cuts against ADR 0001 invariant 5. The generator refuses a construct it does not understand rather than emitting `unknown`, because a declaration that has quietly stopped describing the contract still compiles |
| D-030 | *(**extended by D-044**)* Error taxonomy: a rejected id is `400 invalid_id`, a well-formed id naming nothing is `404 not_found`, a record whose file is absent is `available: false` and `404 unavailable`, and an unbuilt index is `503 index_unavailable` | accepted | D-020 over HTTP: a malformed id is refused before anything is read and is never dressed up as absence. The `503` exists so the UI can tell an empty index from an absent one — otherwise 'no sources yet' is presented as a fact about the user's data |
| D-031 | The indexer ↔ API seam is `IndexRepository` in [`src/x2knwldg/repository/`](../src/x2knwldg/repository/README.md) ([ADR 0002](adr/0002-index-repository-seam.md)): ten methods serving the eleven frozen endpoints, returning **pages of v1 records** — the plain dicts `IndexRecords.by_model()` already produces. It sits beside `adapters/`, in neither track's exclusive directory | accepted | §8.2 of the tracker makes Tracks A and B concurrent only if they meet at one interface. A row type of the repository's own would be a third vocabulary for the same fact on top of the two identifier vocabularies R12 already tracks, and an interface living inside `index/` would be owned by one of the two tracks that share it. `/api/media` reuses `get_artifact` rather than adding a method: two ways to reach a file are two places to get path traversal wrong |
| D-032 | Every list is keyset-paged over a total order, with an **opaque** cursor whose encoding lives in `repository/base.py` and is bound to the query that issued it. Changing a filter refuses the cursor; changing only `limit` does not | accepted | An offset shifts every later page when a record is inserted before it, and silently skips one. Binding the cursor to its filters stops a cursor being re-anchored onto a different collection, which would return data for a question nobody asked. Sharing the encoding between implementations is what makes `T-104`'s rebuild-equivalence a page-for-page comparison rather than a second implementation of the comparison. Search keeps an offset cursor because a relevance rank is not a stable key — stated in the docstring, and changeable by `T-103` precisely because the cursor is opaque |
| D-033 | The repository raises D-030 as typed errors carrying `code` and `http_status` — `InvalidId` 400, `InvalidQuery` 400, `IndexUnavailable` 503 — and an absent record is `None` or an empty page, never an exception | accepted | The API renders the refusal it is handed rather than choosing a status for it, so D-030 becomes a test instead of a convention a route can forget. Absence is an ordinary answer about the user's data and a refusal is not: conflating them is how "no sources yet" comes to be presented as an error, and an error as absence. `404` is what a route makes of `None` |
| D-034 | A relation belongs to a source when that source produced it **or** when either endpoint is an entity of that source | accepted | The 17 `expresses_concept` edges carry `source_id: null` because `adapt_library` produces them and they are cross-source (D-025). They are still the edges linking a source to the concepts it expresses, and a Reader that filtered on `source_id` alone would hide the source's own links. Endpoint membership is read off the three-part global id (D-011) — no join, and no second rule |
| D-035 | *(**extended by D-041**, which settles which nodes)* A `/api/graph` page is a page of **nodes** with the edges among them, and an edge is included only when both endpoints pass the node filter and at least one is on the page | accepted | Paging over edges would silently drop an entity that has no relations, so a full walk would lose real records and the Map would never show them. Requiring *both* endpoints keeps a page renderable: an edge to a filtered-out node dangles, and a Map that draws a dangling edge asserts a node it will not show. An edge straddling two pages appears in both; clients dedupe by `id` |
| D-036 | `MemoryRepository` — the reference implementation over `adapters.adapt_project` — ships with the seam, and D-028's additive search fields move into it | accepted | Track B builds routes against it on day one while Track A builds SQLite behind the same interface, and `T-104` gets a cache-free oracle: where a rebuilt index, an incremental one, and the canonical files disagree, the index is stale (ADR 0001 invariant 3). It closes R18 — `global_id` and `source_id` were a test helper no server would call — and reads the source type from the indexed source rather than assuming `youtube`. It is not an index: it holds every record in memory and re-runs `query.search_knowledge`'s linear scan per search, which is the cost `T-103` exists to remove |
| D-037 | The `ui` extra is `fastapi` + `uvicorn`, each floor- **and** ceiling-bounded, and `x2knwldg ui` ships as a **refusing stub**: it enforces loopback-only binding (ADR 0001 invariant 9) and resolves the project root, then exits ~~`2`~~ **`6`** with `UI_NOT_IMPLEMENTED` naming `T-116` (renumbered by D-040). It never prints a URL, and `--port` defaults to unset rather than to a constant | accepted, amended by D-040 | A scaffolded command that exits `0` claims the project can serve a UI, and one that prints `http://127.0.0.1:8000` claims a socket nobody opened — the same class of dishonesty as coercing `PARTIAL` to `PASS`. The two checks that *are* real here are both refusals, and a refusal is worth having before the thing it guards exists: the host check runs before the dependency probe, so the invariant holds on machines without the extra installed. §8.3's rule that the port must not rest on a brittle constant is met by having no default at all |
| D-038 | `web/` gets **TypeScript and nothing else** — no Vite, no React, no router, no tokens; `T-109` chooses those. What `T-008` does add is CI: `tsc --noEmit` over `web/` with `skipLibCheck: false` and `schemas/api/v1/types.d.ts` as a *root file*, plus `web/src/api/contract.ts` as the single re-export of the generated declarations | accepted | Same restraint as D-029 — handing `T-109` a framework it did not choose is a cost it pays for the life of the project. `skipLibCheck` is load-bearing: TypeScript's default skips `.d.ts` files, so with it on the Node job would skip the only file it exists to check and pass without looking, leaving risk R17 closed on paper. Verified by breaking `types.d.ts` deliberately and watching `tsc` fail. One import path to the generated file means moving it breaks a test, not a build |
| D-039 | `pipeline.project_root(explicit=None)` is the single root-resolution rule — explicit path, then `X2KNWLDG_PROJECT_ROOT`, then the working directory. `mcp_server.PROJECT_ROOT` calls it rather than re-reading the env var | accepted | The `ui` command is the second consumer of 'where is the project', and a second implementation of a lookup rule is what D-020 was written about. Behaviour for the MCP server is unchanged — the same three-step fallback, one copy of it — and a test asserts the env var is no longer read in `mcp_server.py` so the duplication cannot quietly return |
| D-040 | Exit codes are a semantic contract: `0` `PASS`, `1` `ERROR`, `2` reserved for `argparse`, `3` `PARTIAL`, `4` `FAIL`, `5` `TRANSCRIPT_REQUIRED`, `6` ~~`UI_NOT_IMPLEMENTED`~~ **`UI_NOT_BUILT`** (renamed by D-064 when `T-116` landed the server), from the single `cli.VERDICT_EXIT_CODES` mapping and printed by `--help`. Completion may be claimed only on `0`. Amends D-037 (`ui` refusal `2` → `6`) | accepted, amended by D-064 | `PARTIAL` exited `0`, so no shell or CI check could distinguish it from `PASS`, and every refusal shared `1` with every real error. `2` returns to `argparse`, because a semantic code that collides with a typo'd flag cannot be tested for. D-037's reasoning stands — only its number moved |
| D-041 | Which nodes a source's graph is drawn over is `relation_belongs_to_source` (D-034) — the same rule `/api/sources/{id}/relations` uses. A node belongs when it is an entity of that source **or** when a relation of that source names it as an endpoint. The **edge** rule of D-035 is unchanged: both endpoints must be nodes of the graph. **Extends D-035** ([ADR 0004](adr/0004-graph-membership-and-search-corpus.md)) | accepted | `/api/graph?source_id=` used its own rule — both endpoints had to be entities *of that source* — and a canonical concept belongs to no source (D-016), so all 17 `expresses_concept` edges vanished from the graph while the relations endpoint returned them: 101 edges against 118 on the sample. Two answers to one question, and the lossy one was the one a user calls 'the graph'. Widening the **node set** is the opposite of the either-endpoint **edge** rule ADR 0002 rejected: the far endpoint becomes a node rather than a dangling reference. Both views now report 118 edges over 86 nodes |
| D-042 | `MemoryRepository`'s search corpus is built from the `canonical_dir` each **indexed** `Source` carries, once per instance on the first search, and never invalidated. A run outside the index is not searched; a source whose files will not read is *unreadable*, so `total` is `null` rather than a zero ([ADR 0004](adr/0004-graph-membership-and-search-corpus.md)) | accepted | Walking `output/` per call made paging cost the whole library **per page**, and made search a second, disagreeing view: a run added after construction returned hits carrying `source_id: null`, because no `Source` existed to resolve them against — renderable and unnavigable. Resolving through the record also means no id is joined onto a path, so no host path reaches an error body (D-030, ADR 0003). Built lazily because a repository that never searches must not pay for a corpus and `/api/status` must stay cheap. Narrows ADR 0002's promise of a cache-free `T-104` oracle to *cache-free per instance* |
| D-043 | `library.rebuild_library` invents no confidence and drops no run in silence. `expresses_concept` edges carry `confidence: null`; a `derived_from` edge carries the unit's **own** confidence verbatim, `null` when the unit states none. A run missing a canonical file is indexed from what it has, and `status.json` gains `runs_discovered`, `runs_indexed`, `runs_skipped`, `skipped_runs[]` and `incomplete_runs[]`, with every `videos.json` entry gaining `problems: []`. **Amends D-025** | accepted | D-025 forbade the index fabricating an edge confidence; `library.py` was doing exactly that in its own graph — `1.0` on every `expresses_concept` edge, which is a match on a normalised string key and not a measurement, and `0` (the *least* confident value) on a `derived_from` edge whose unit stated none. The same reasoning applies to both producers, so the parenthetical in D-025 that excused `library.py` as writing 'its own value for its own reasons' is withdrawn. Separately, `relationships.json` was a precondition for indexing at all, so a run with units but no relationships file disappeared from `graph.json`, `videos.json` and the `videos` count while `adapt_run` indexed it without complaint — a count that omits a run without saying so is a claim of completeness the library has not got |
| D-044 | D-030's taxonomy gains two codes for boundaries that are not HTTP: `invalid_request` — an argument refused before anything is read, where no identifier is involved — and `internal_error`. The four original codes keep their meanings and their HTTP statuses. **Extends D-030** | accepted | Two MCP tool parameters are *paths*, not ids, so `resolve_run_dir` is not their check even though its behaviour is (ADR 0003 invariant 5). Reporting a refused path as `invalid_id` would name a thing the request never contained, which is the kind of small lie D-030 exists to prevent — the taxonomy's whole point is that a refusal says what was actually refused. `internal_error` is the boundary's own catch: a tool must let out one error type carrying a known code, so an unexpected exception is converted rather than leaked with its message and paths intact. Narrowing the MCP surface to the four HTTP codes was the alternative and was rejected: it would force one of them to mean something it does not |
| D-045 | An adapter **states what it could not do** rather than dropping it silently, and `Source.adapter_metadata` carries two diagnostic channels for it: `unmappable_artifacts` (a generated `vault/` note whose filename cannot spell an id — skipped and named, not fatal) and `unreadable_files` (a canonical file present but damaged — named, so a missing count is not read as a zero). Both are free-form by schema and absent when there is nothing to report. The line is drawn at index integrity: a run whose `knowledge_units.json` is damaged while its `relationships.json` is intact is **refused** at adapt time, naming the dangling edge. **Qualifies D-022** | accepted | D-022 requires an `AdapterError` wherever a value would have to be guessed, and that is still right for canonical evidence. Nothing here is guessed either way; the choice is between refusing everything and stating the one omission, and the rule that actually matters is that the omission is never silent — the recurring finding across this audit. One `vault/` note whose filename cannot spell an id took down a whole project's index, and that note is a generated export beside the canonical files, so it is skipped and named. A damaged canonical file is different again: its counts were already omitted rather than zeroed, but 'this count is missing' does not say 'this file is broken', and only one of those is actionable. The refusal stays where integrity is at stake: stranded edges would make the graph and `/api/sources/{id}/relations` disagree about one fact, `check_index_integrity` would refuse the whole project later anyway, and the failure belongs on the run that causes it. `adapter_metadata` is the only place in the frozen `Source` record an adapter may say any of this |
| D-117 | Phase 2 starts on an exactly pinned Sigma v4 beta, with `T-202` as a real compatibility gate and stable v3 as the single fallback before implementation proceeds ([ADR 0005](adr/0005-knowledge-map-client.md)) | accepted | The v4 line is now documented as beta and its maintainer describes the API as full-featured and stable enough for new work, while still warning of possible feature-interaction bugs. This is a new Map, so building the provenance/kind renderer on v4's declarative primitives avoids a known later migration. Exact pins and the 86/118 MacBook gate contain the prerelease risk |
| D-118 | The Map is a progressive, explicitly bounded snapshot: pages accumulate by identity, cross-page edges wait for both endpoints, and `truncated` remains visible until the graph is whole ([ADR 0005](adr/0005-knowledge-map-client.md)) | accepted | D-059 allows a page edge to reach a node on another page and repeats the edge across those pages. Drawing a page directly would dangle, invent a node or silently drop connectivity; an unbounded prefetch would defeat overview-first loading |
| D-119 | `mapLink` is the one grammar for addressable Map selection/filters, and selection uses only an existing three-part `global_id` ([ADR 0005](adr/0005-knowledge-map-client.md)) | accepted | The Reader already demonstrated why link building and parsing must share one module. State must survive reload, while malformed values and search hits without a v1 entity address are ignored rather than coerced or minted |
| D-120 | No Map operation is WebGL- or pointer-only; a bounded semantic DOM companion exposes graph state, search, selection, neighbourhood, inspector and Reader navigation ([ADR 0005](adr/0005-knowledge-map-client.md)) | accepted | WebGL is the right overview renderer and the wrong accessibility tree. The companion preserves keyboard operation and text alternatives without putting a heavy HTML component on every graph node |

> **Ledger maintenance note.** Phase 1 implementation decisions D-046–D-116 are in
> `PROJECT_MANAGEMENT.md` §6, which remains their complete live ledger. Backfilling those
> already-accepted rows here is documentation consolidation work, not part of the Phase 2
> implementation and not a reason to renumber D-117–D-120.

## 20. Open questions

These do not block Phase 2 and must be answered at the appropriate later phase:

- Should boards enter Git by default, or only have a local backup?
- Should user notes stay limited to plain Markdown, or is rich text required?
- Are videos played only from YouTube, or will local files also be kept?
- At which phase do PDFs and documents genuinely enter the daily workflow?
- Can one entity have independent view state across multiple boards? Probably yes, but the schema must be fixed.
- Is a summary snapshot of a node inside a board needed to survive source deletion?
- How much recovery does the board and attachment deletion policy require?
- The final visual theme and design tokens are decided after wireframes.

An agent must not guess the answers to these if the decision would cause a noticeable change in the product or the schema.

## 21. Multi-session working protocol

### At the start of each session

1. Read `AGENTS.md`.
2. For any ingestion/extraction, follow `WORKFLOW.md` completely.
3. Read this document.
4. Check `git status` and existing changes; preserve the user's changes.
5. Review the "Execution status" and "Next step" sections.
6. Take on only one bounded, verifiable phase or subtask.

### While working

- Record any new architecture decision in the decision table.
- If a decision exceeds the accepted scope, ask the user.
- Do not modify canonical output or raw evidence.
- Do not report cache changes as data achievements.
- Write and run tests proportionate to the risk.

### At the end of each session

1. Run the relevant tests and validators.
2. Record the changed files.
3. Mark the acceptance criteria that were met.
4. Add any new decision and risk to this document.
5. Update "Execution status" and "Precise next step".
6. If something is incomplete, record it explicitly as `PARTIAL` or pending.

## 22. Execution status

### Completed

- [x] Review the current X2KNWLDG structure
- [x] Review the provenance and canonical output contracts
- [x] Multi-stage search of open-source options
- [x] Compare AFFiNE, BlockSuite, Logseq, TubeNotes, Kanvaz, and Excalidraw
- [x] Review React Flow, Sigma.js, perfect-freehand, SQLite FTS5, and the tldraw licence
- [x] Choose the base architecture
- [x] Record the multi-session plan in this document
- [x] Verify the real state of the canonical outputs and correct §4 (2026-08-31)
- [x] Create the execution tracker at `docs/PROJECT_MANAGEMENT.md` with a task breakdown and the agent parallelism model
- [x] Phase 0 / T-001: ADR convention and [ADR 0001](adr/0001-local-web-ui.md)
- [x] Phase 0 / T-002: v1 index model in [`schemas/v1/`](../schemas/v1/README.md) — Source, Artifact, Locator, EntityRef, IndexedRelation — with contract tests that project the real sample onto it
- [x] Phase 0 / T-003: three-part global id helper in [`src/x2knwldg/ids.py`](../src/x2knwldg/ids.py), additive to the library ids
- [x] Phase 0 / T-006: labelled test-only `PASS`/`PARTIAL`/`FAIL` run fixtures in [`tests/fixtures/runs/`](../tests/fixtures/runs/README.md)
- [x] Phase 0 / T-004: YouTube adapter in [`src/x2knwldg/adapters/`](../src/x2knwldg/adapters/README.md), mapping `output/<id>/` onto the v1 model and changing no canonical output
- [x] Phase 0 / T-005: frozen v1 HTTP contract in [`schemas/api/v1/`](../schemas/api/v1/README.md) — eleven `GET` endpoints `$ref`-ing `schemas/v1/`, with generated TypeScript types
- [x] Phase 0 / T-007: the indexer ↔ API seam in [`src/x2knwldg/repository/`](../src/x2knwldg/repository/README.md), with [ADR 0002](adr/0002-index-repository-seam.md) and a reference implementation over the adapters
- [x] Phase 0 / T-008: the [`web/`](../web/README.md) scaffold, the `ui` extra, the `ui` CLI stub, and the first Node job in CI (`tsc --noEmit`, closing risk R17)
- [x] Phase 0 / T-009: re-confirmed the zero-dependency install after the `ui` extra existed
- [x] **Phase 0 complete** — the exit gate in `docs/PROJECT_MANAGEMENT.md` §5 is met; Phase 1 may fan out
- [x] **Phase 1 complete** — SQLite/FTS5 index, all eleven HTTP endpoints, Library, Reader,
  honest status/provenance, real-API frontend integration and `x2knwldg ui`; end-to-end
  scenarios 1–3 and the cache half of scenario 7 walked on 2026-09-02
- [x] Phase 2 selected and approved as the `T-201` Knowledge Map epic
- [x] Phase 2 decomposed into claimable `T-202`–`T-209`, with [ADR 0005](adr/0005-knowledge-map-client.md)
  fixing the Sigma v4 gate, progressive graph truth, URL identity and accessible DOM boundary
- [x] Translate this document to English per D-014

### Planned / not started

- [ ] `T-202`: Sigma v4 compatibility and layout gate
- [ ] `T-203`–`T-209`: Knowledge Map implementation and phase gate
- [ ] Canvas
- [ ] Pen annotations
- [ ] Adapters for future sources

Live status, task breakdown, and track ownership are maintained in `docs/PROJECT_MANAGEMENT.md`. In case of conflict, that file is the authority on **status** and this document is the authority on **design**.

## 23. Precise next step

The next execution session claims **`T-202` only**, inside the approved `T-201` Knowledge Map
epic:

1. Read [ADR 0005](adr/0005-knowledge-map-client.md), `PROJECT_MANAGEMENT.md` §5 Phase 2,
   D-059 and D-117–D-120.
2. Check current official Sigma v4 beta and compatible Graphology package versions, then pin
   one exact set in `web/package.json` and the lockfile. Do not accept a moving prerelease
   range.
3. Build the smallest isolated Sigma v4 renderer over the real 86-node/118-edge sample. Use
   the existing `EntityRef` and `IndexedRelation` types; do not design a second API shape.
4. Seed deterministic non-zero `x`/`y` positions, exercise create/update/resize/selection/
   teardown, and record layout/render observations on the user's MacBook.
5. If v4 has a blocking defect, record the evidence and pin stable v3 before proceeding. Do
   not implement both majors. If it passes, mark `T-202` done and make `T-203` the only next
   claimable task.
6. Run the frontend checks and prove `git diff --stat -- output/` is empty.

Do not start Map routing, pagination state, styling or the inspector inside the spike; those
belong to `T-203`–`T-207`. Phase 3 Canvas and Phase 4 pen remain out of scope.

## 24. Research references

- AFFiNE: <https://github.com/toeverything/AFFiNE>
- BlockSuite Edgeless Editor: <https://blocksuite.io/components/editors/edgeless-editor>
- BlockSuite Edgeless Data Structure: <https://blocksuite.io/components/editors/edgeless-data-structure>
- Logseq: <https://github.com/logseq/logseq>
- Logseq tablet/whiteboard issue: <https://github.com/logseq/logseq/issues/12174>
- TubeNotes: <https://github.com/orgofjs/tubenotes-desktop>
- Kanvaz: <https://github.com/p4inz-code/kanvaz>
- Excalidraw: <https://github.com/excalidraw/excalidraw>
- React Flow performance: <https://reactflow.dev/learn/advanced-use/performance>
- React Flow attribution: <https://reactflow.dev/remove-attribution>
- Sigma.js: <https://github.com/jacomyal/sigma.js>
- Sigma v4 beta: <https://v4.sigmajs.org/>
- Sigma v4 quickstart: <https://v4.sigmajs.org/get-started/quickstart/>
- Sigma v3 → v4 migration: <https://v4.sigmajs.org/how-to/technical/migration-v3-v4/>
- Sigma v4 maturity discussion: <https://github.com/jacomyal/sigma.js/discussions/1539>
- Graphology `MultiDirectedGraph`: <https://graphology.github.io/instantiation.html>
- Graphology ForceAtlas2: <https://graphology.github.io/standard-library/layout-forceatlas2.html>
- W3C keyboard technique G202: <https://www.w3.org/WAI/WCAG22/Techniques/general/G202.html>
- W3C accessibility principles: <https://www.w3.org/WAI/fundamentals/accessibility-principles/>
- Playwright visual comparisons: <https://playwright.dev/docs/test-snapshots>
- perfect-freehand: <https://github.com/steveruizok/perfect-freehand>
- PointerEvent pressure: <https://developer.mozilla.org/en-US/docs/Web/API/PointerEvent/pressure>
- tldraw licence: <https://tldraw.dev/community/license>
- SQLite FTS5: <https://www.sqlite.org/fts5.html>
- SQLite WAL: <https://sqlite.org/wal.html>
- Vite: <https://vite.dev/guide/>
- FastAPI: <https://fastapi.tiangolo.com/>

## 25. Document change history

### 2026-09-02 — Phase 2 planning

- Recorded Phases 0 and 1 as complete and selected `T-201` as the approved Knowledge Map epic.
- Decomposed Phase 2 into claimable `T-202`–`T-209` in `PROJECT_MANAGEMENT.md`.
- Accepted [ADR 0005](adr/0005-knowledge-map-client.md): exact Sigma v4 beta pin behind a
  real-device compatibility gate, progressive graph snapshots, one Map URL grammar and a
  semantic DOM companion to the WebGL view.
- Expanded Phase 2 deliverables, acceptance criteria, performance rules and the precise next
  step. Canvas transfer remains Phase 3 rather than a false Phase 2 dependency.

### 2026-08-31 — initial version

- First version of the document created.
- User requirements, research results, architecture decisions, data boundaries, and the roadmap recorded.
- Phase 0 identified as the next step.

### 2026-08-31 — second update

- §4 corrected: the `pqlWNihgdjI` sample has a complete, `PASS` extraction (69 units, 56 relationships, 17 concepts). The earlier "empty / `PARTIAL`" description was stale.
- The Phase 1 acceptance criterion that relied on the sample being `PARTIAL` was rewritten.
- Risk 7 marked resolved; the residual risk (no `PARTIAL`/`FAIL` fixture) recorded explicitly.
- Decisions D-011 (three-part identifier, additive), D-012 (switchable UI language, English default), and D-013 (document correction) recorded.
- The open question about UI language removed, since it was decided.
- `docs/PROJECT_MANAGEMENT.md` added as the execution tracker.

### 2026-08-31 — third update

- Phase 0 / T-001 completed: ADR convention established in `docs/adr/README.md`, with the architecture decision recorded in ADR 0001. §19 and §23 cross-linked to it.
- **This document translated from Persian to English** per D-014. Content, structure, section numbering, decisions, and diagrams are unchanged; only the language differs.
- D-014 recorded: all project documentation in English; Persian reserved for the UI and for extracted knowledge content.
- §9.4 annotated with the verified SQLite version, resolving the open WAL caveat.
