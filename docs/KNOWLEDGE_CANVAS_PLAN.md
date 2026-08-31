# X2KNWLDG Knowledge Canvas — Product and Architecture Plan

---

**Document status:** active; the reference for continuing this work
**Current stage:** research and architecture decisions complete; execution plan recorded in `docs/PROJECT_MANAGEMENT.md`; implementation not yet started
**Last updated:** 2026-08-31
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

The current sample `pqlWNihgdjI` has a complete extraction. State measured on 2026-08-31:

- `validation.json` is `PASS` (all five sections `PASS`).
- `coverage.json` is `PASS` (5 of 5 windows, `audit_attempts: 1`).
- `knowledge_units.json` contains 69 units (61 `source`, 8 `derived`).
- `relationships.json` contains 56 relationships.
- `graph.json` contains 69 nodes and 56 edges.
- `output/library/` contains 1 video, 69 knowledge nodes, 17 canonical concepts, and 118 edges.

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

## 15. Proposed API

Names are provisional and are fixed during the API contract phase.

```text
GET  /api/status
GET  /api/sources
GET  /api/sources/{source_id}
GET  /api/entities/{entity_id}
GET  /api/search?q=...
GET  /api/graph
GET  /api/graph/neighborhood/{entity_id}
GET  /api/artifacts/{artifact_id}
GET  /api/media/{artifact_id}

GET  /api/boards
POST /api/boards
GET  /api/boards/{board_id}
PUT  /api/boards/{board_id}
```

API rules:

- IDs must be opaque and URL-safe.
- Responses must carry a schema version.
- Canonical status must be read from the validator files.
- A missing artifact must not be masked with a placeholder or fabricated data.
- Mutations must be atomic: write to a temp file, then replace safely.

## 16. Execution phases

### Phase 0 — Contracts and scaffolding

**Goal:** fix the boundaries before any heavy UI work.

Deliverables:

- A short ADR for the architecture choice
- Version 1 schemas for Source/Artifact/Locator/EntityRef
- The YouTube adapter contract
- The `web/` structure and the optional backend
- A defined development command
- Valid fixtures for `PASS`, `PARTIAL`, and `FAIL` states

Acceptance criteria:

- No canonical file is modified.
- Schemas are versioned and validate.
- One existing source converts to the generic model with no guessing.
- The Python project still installs and tests without the UI extra.

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

- Sigma.js view
- Node/edge styles based on provenance and kind
- Search/focus/filter
- Neighbourhood view
- Inspector integration
- Link from Map to Reader

Acceptance criteria:

- An empty graph is displayed honestly.
- Canonical and derived relationships are distinguishable.
- Selecting a node shows real details and evidence.
- The graph is fed from `output/library/graph.json` or an equivalent index.

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
| D-020 | Run directories are resolved by `pipeline.resolve_run_dir`, which rejects an unsafe id instead of sanitising it | accepted | Sanitising is correct when creating a run and wrong when looking one up: a lookup must fail rather than silently read a different run |
| D-021 | `src/` holds the package only; unmaintained upstream scripts live in `legacy/upstream/` | accepted | They were importable only by accident of an editable install, and two of them are Whisper transcribers the project forbids running |

## 20. Open questions

These do not block the start of Phases 0 and 1, and must be answered at the appropriate time:

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
- [x] Translate this document to English per D-014

### Not started

- [ ] Phase 0: remaining contracts (T-003 ID helper, T-005 API freeze, T-006 fixtures, T-007 repository seam, T-008 scaffolding)
- [ ] YouTube adapter (T-004)
- [ ] SQLite index
- [ ] FastAPI local API
- [ ] React/Vite scaffolding
- [ ] Library/Reader
- [ ] Knowledge Map
- [ ] Canvas
- [ ] Pen annotations
- [ ] Adapters for future sources

Live status, task breakdown, and track ownership are maintained in `docs/PROJECT_MANAGEMENT.md`. In case of conflict, that file is the authority on **status** and this document is the authority on **design**.

## 23. Precise next step

The next execution session must start Phase 0 only:

1. Review the current schemas and the real knowledge unit/source IDs.
2. ~~Write the architecture ADR in `docs/adr/`.~~ Done — [ADR 0001](adr/0001-local-web-ui.md), with the ADR convention in `docs/adr/README.md`.
3. ~~Define version 1 schemas for Source, Artifact, Locator, EntityRef, and IndexedRelation.~~
   Done — [`schemas/v1/`](../schemas/v1/README.md), validated by `tests/test_index_schemas.py`.
   Three invariants are beyond JSON Schema and remain the adapter's obligation: a global id equals
   its three parts, a source id equals its two, and a `time_range` locator has
   `end_sec >= start_sec`.
4. Define the YouTube adapter contract without changing any existing canonical output. The shape
   probe in `tests/test_index_schemas.py::_project_sample` shows the mapping and should be replaced
   by a call into the real adapter.
5. Build valid, clearly labelled test-only fixtures for the `PARTIAL` and `FAIL` states. A real, complete graph is already available from the existing `PASS` sample and does not need to be constructed.
6. Run the existing tests and add schema/adapter tests.

Until these contracts are validated, work on the Canvas or on production UI design must not begin.

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
- perfect-freehand: <https://github.com/steveruizok/perfect-freehand>
- PointerEvent pressure: <https://developer.mozilla.org/en-US/docs/Web/API/PointerEvent/pressure>
- tldraw licence: <https://tldraw.dev/community/license>
- SQLite FTS5: <https://www.sqlite.org/fts5.html>
- SQLite WAL: <https://sqlite.org/wal.html>
- Vite: <https://vite.dev/guide/>
- FastAPI: <https://fastapi.tiangolo.com/>

## 25. Document change history

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
