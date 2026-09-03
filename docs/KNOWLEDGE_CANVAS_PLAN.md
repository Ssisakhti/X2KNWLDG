# X2KNWLDG Knowledge Canvas — Product and Architecture Plan

---

**Document status:** active; the design authority for continuing this work
**Current stage:** Phases 0, 1, 2 and 2.1 are complete. The user has chosen Twitter/X as the next product phase, ahead of Canvas. **Phase 2.2 / `T-220` is active; `T-221` and `T-222` are complete. `T-222` measured a `GO` (D-205) and `T-223` is next, gated on three user answers in [the spike report](spikes/T-222/REPORT.md) §11 — one of which changes the phase MVP (D-206).** The accepted acquisition boundary qualifies `x-cli` first on the user's real Iran environment, keeps FxTwitter/FxEmbed explicit opt-in, uses official oEmbed only for corroboration, limits Firefox to passive credential-free capture, and excludes Treasury/twscrape account-pool and evasion patterns (D-204; [ADR 0007](adr/0007-twitter-acquisition-boundary.md)). Phase 3 remains technically unblocked after the accepted Map gate (D-202) but is deliberately deferred until the Twitter phase closes.
**Last updated:** 2026-09-03
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

- Implemented first source: YouTube.
- Next source phase: Twitter/X, before Canvas, under the qualification-first boundary in
  [ADR 0007](adr/0007-twitter-acquisition-boundary.md).
- Later: Medium, web pages, PDFs, and other content types.
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
- The exact visual language is approved in `T-211`'s high-fidelity mockups, but distinguishing these three categories is mandatory:
  - source-grounded
  - derived
  - user-authored
- Coverage and validation status must always be available, but must not interfere with reading.
- Layout and typography must handle bidirectional text correctly for both Persian and English content.

### 7.1 Approved Knowledge Map browsing model

The Map is a read-only **content browser**, not a diagram that makes the user guess what a
circle contains. Its progressive journey is:

```text
Search  ->  Preview / Peek  ->  Focus  ->  Quick Read  ->  full Reader when needed
```

- **Search** opens a collapsible rail of result cards. Each card shows only returned content,
  kind, provenance, confidence and real source/locator cues; it never generates a summary.
- **Peek** is one transient, compact card for a loaded node under pointer hover or keyboard
  focus. It provides information scent but writes neither selection nor browser history.
- **Focus** keeps the user in `#/map`. The selected entity becomes one primary Knowledge Card
  with a visibly bounded statement preview, active connections name their real relation/
  direction, and compact neighbour previews form a bounded focus constellation. Unrelated
  structure may be de-emphasised, never represented as absent.
- **Quick Read** is the collapsible inspector ordered for reading: full stored statement,
  recorded evidence/locator, active relation, recorded derivation, provenance/source, then
  technical metadata. The Reader remains the destination for the complete source.
- A focus selection pushes `mapLink` history. Browser Back restores the previous focus without
  leaving or rebuilding the Map; Peek never pollutes that history.

The visual references approved by the user contribute four ideas: card-shaped focus nodes and
labelled active paths; visible interaction/history trails; a clear radial centre with related
material around it; and editorial hierarchy with restrained translucent group regions. They
do **not** authorise an invented radar value, importance score, cluster or relation. Visual
grouping uses only fields the API states: relation, direction, vocabulary, provenance, source
and identity.

```text
┌─────────────────────────────────────────────────────────────────────┐
│ Search: memory          path: result / selected          [filters] │
├─────────────────────────────────────────────────────────────────────┤
│  ┌──────────────────┐       supports       ┌──────────────────┐    │
│  │ neighbour preview├──────────────────────┤ neighbour preview│    │
│  │ relation + label │                      │ relation + label │    │
│  └──────────────────┘                      └──────────────────┘    │
│              ╲                                  ╱                   │
│               ╲  ┌──────────────────────────┐  ╱                    │
│                ──┤ SELECTED KNOWLEDGE CARD  ├──                     │
│                  │ bounded statement preview│                       │
│                  │ provenance · kind · time │                       │
│                  │ [Quick Read] [Reader]    │                       │
│                  └──────────────────────────┘                       │
│                                                                     │
│ Related: every returned neighbour remains in the semantic list     │
└─────────────────────────────────────────────────────────────────────┘
```

The stage does not become an HTML renderer. It carries one primary selected card, at most one
transient Peek and only density-budgeted neighbour previews. Sigma/WebGL retains every loaded
graph mark; every neighbour returned by the bounded API is also present in the semantic
related list even when its card cannot fit on stage.

### 7.2 Approved visual-quality direction

The Phase 2 journey and content rules are correct, but the first implementation does not meet
the visual bar of the references: the stage is pushed down by document-flow controls, the
selected item has no commanding centre, and ForceAtlas labels, cards and edges compete in one
layer. Phase 2.1 changes the composition, not the data model.

The Map has two modes over the same snapshot and selection identity:

- **Explore** is a quiet topology overview. Marks and structure dominate; text appears through
  semantic zoom, hover, keyboard focus or selection. No large card field covers the graph.
- **Focus** is a content-reading composition called **Directional Orbit**. The selected card is
  fixed at the visual centre. Incoming relations occupy the left side, outgoing relations the
  right, and actual hop count determines radial distance. Relation names are horizontal pills
  on readable paths. Unrelated topology remains present but faint.

Explore composition:

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ Knowledge Canvas   [Library] [Map: Explore]      [Search] [Filters] [EN/FA] │
├──────────────────────────────────────────────────────────────────────────────┤
│ ┌ Search drawer (closed) ┐                         86 nodes · 118 relations │
│ └────────────────────────┘                         [Legend] [−] [fit] [+]   │
│                                                                              │
│          ·───◇                 ○                                              │
│        ╱       ╲             ╱   ╲       quiet full-graph topology           │
│      ○           ·─────────□       ·      labels on zoom / hover / focus      │
│       ╲         ╱            ╲   ╱                                           │
│        ·───────·               ○                                             │
│                                                                              │
│  status stays available but compact; no panel pushes this stage downward     │
└──────────────────────────────────────────────────────────────────────────────┘
```

Focus / Directional Orbit composition:

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ [← Explore]  Focus · 2 hops                         [Search] [Quick Read ▸]  │
├──────────────────────────────────────────────────────────────────────────────┤
│                 hop 2             hop 1             hop 1          hop 2     │
│                                                                              │
│ ┌ related preview ┐   ┌ related preview ┐   ┌ related preview ┐   ┌ preview┐│
│ │ verbatim text…  │───┤ verbatim text…  │   │ verbatim text…  ├───│ text…  ││
│ └───────●─────────┘   └───────●─────────┘   └─────────●───────┘   └──●─────┘│
│          ╲             [supports →]       [← derived from]          ╱        │
│           ╲                    ╲           ╱                       ╱         │
│ incoming   ╲          ┌─────────●─────────┐             outgoing  ╱          │
│  LEFT       ──────────┤ SELECTED KNOWLEDGE├────────────────────── RIGHT       │
│                       │ complete readable │                                 │
│                       │ statement preview │   ┌ Quick Read drawer ────────┐ │
│                       │ source · kind · at │   │ full statement             │ │
│                       └─────────●─────────┘   │ evidence + locator          │ │
│                                               │ active relations            │ │
│   unrelated graph remains as low-contrast context                           │ │
│                                               └────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────┘
```

These diagrams specify hierarchy and geometry, not final styling. `T-211` must replace them
with screenshot-level mockups and obtain explicit user approval before implementation.

Visual language:

- neutral charcoal field and neutral cards; one strong accent for the active reading path;
- provenance remains a shape/border/badge distinction, with hue only as reinforcement;
- kind colour is a small cue, not a competing full-card fill;
- card content follows D-131 and the existing formatter: verbatim, visibly truncated where
  bounded, with the complete text in Quick Read;
- readable card content has an exclusion zone: no graph label or edge may pass through it;
- drawers are bounded overlays, with one primary drawer competing with the stage at a time;
- the semantic DOM order, keyboard route, bidi rules and honest states remain primary even
  when the visual layout uses floating surfaces.

The four references contribute mood, hierarchy, paths, ports, a definite centre and editorial
radial composition. They do not justify copying their domain-specific workflow semantics or
inventing radar values, community clusters, importance, strength or similarity.

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

Only the YouTube adapter is currently implemented. Phase 2.2 adds Twitter through the same
generic boundary; it does not make a provider response part of the adapter contract.

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

### 11.2 Twitter/X acquisition boundary

Acquisition and adaptation are separate seams. A Twitter provider may return a command result,
JSON, HTML or an observed browser response, but extraction and the adapter consume only one
provider-neutral canonical capture. The capture preserves the raw response as immutable
evidence and records its SHA-256, acquisition time, provider and provider version, request
surface, post/thread ordering, omissions and failure state. X ids are strings throughout.

Provider success cannot imply conversation completeness. The capture and coverage model must
distinguish a single post, a provably complete same-author self-thread, an observed subset,
tombstones/unavailable items and a provider outage. Each expected or included post is covered,
omitted with a reason or unresolved. Only the first two can become `PASS`, and only when the
provider supplies evidence for the relevant boundary.

The approved provider order is qualification-dependent, not an unconditional fallback chain:

1. `x-cli`, if `T-222` proves the pinned public/credential-free path in Iran;
2. FxTwitter/FxEmbed, only after explicit per-use consent to third-party disclosure;
3. passive Firefox capture of responses already loaded through user-driven browsing;
4. official oEmbed as corroboration for a public anchor, never as thread acquisition.

There is no silent provider switch. Treasury/twscrape account pools, X passwords or cookies,
multi-account/proxy rotation, automated browsing and stealth/evasion are outside the product.
The full decision and rejected alternatives are in [ADR 0007](adr/0007-twitter-acquisition-boundary.md).

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
- Focus, filtering and neighbourhood visualization; a cluster/region only when an explicit
  API field defines it, never from a client inference presented as evidence
- In-memory graph algorithms

The Map must not place heavy HTML components on each node. D-132 permits only a bounded focus
overlay — one primary selected card, one transient Peek and density-budgeted neighbour previews —
paired with the complete semantic related list and Quick Read.

Phase 2 starts with an exactly pinned Sigma v4 beta, subject to the real-graph and real-device
compatibility gate in `T-202` ([ADR 0005](adr/0005-knowledge-map-client.md), D-117). The
official v4 site now describes this line as beta and documents `4.0.0-beta.5`; it began as an
alpha and remains prerelease, so a moving semver range is forbidden. If `T-202` finds a
blocking v4 defect, it records that evidence and selects stable v3 before any later Map task
begins. The phase carries one renderer API, never a compatibility layer for both.

`T-202` ran on 2026-09-02 and **kept the v4 line**: `sigma@4.0.0-beta.5` drew the real
86-node/118-edge graph, survived 21 create/teardown cycles releasing every WebGL context, and
raised no uncaught error, so stable v3 was not needed. Two consequences belong here rather
than in the task record. The layout stays **synchronous** — 200 ForceAtlas2 iterations over
that graph cost 2.7–9.0 ms, so §13.1's conditionally permitted worker is not adopted (D-121) — and the Map
must **not draw the raw `label`**, because a knowledge unit's label is its whole
`normalized_statement` and 86 of them overlap into an unreadable pile (D-122). Positions come
from a deterministic seed hashed from each node's `global_id`, never from its index in a page,
so a node keeps its start as later pages arrive.

`T-203` then built what the renderer draws from, in `web/src/map/`: a typed projection whose
node and edge attributes are the API's record verbatim plus that seed (D-124), and a snapshot
that accumulates pages, holds a D-059 edge until both of its endpoints have arrived, and
refuses a repeated identity that disagrees with one already drawn (D-125). Walking the real
86-node/118-edge graph at 1, 10, 50 and 500 nodes per page reaches the identical graph every
time — page size does not change it — holding up to 54 edges at once on the way and none at
the end.

`T-204` then put it on screen at `#/map`, with one renderer lifecycle in `MapSession` reached
through an injected factory (D-126) and Sigma loaded on demand rather than statically, because
its module body reads a WebGL global that jsdom does not define (D-127). The Map states nodes
loaded, edges drawn, edges held, pages applied and whether the graph is whole — before the
canvas, since that text is the only honest account available when the picture cannot be read
(D-129) — and a further page re-settles the layout of the graph already drawn rather than
pinning what is placed, which the graph has no attribute to record (D-128). Nothing is styled
yet: that is `T-205`'s, in reducers.

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
- "Complete" is a measured claim, not a guess: the walk has finished, no edge is still waiting
  for an endpoint, and either the API said nothing was cut short or the loaded node count
  reached the stated total — an uncounted total leaves the question open (D-123).
- Cross-page edges wait until both endpoints have arrived and dedupe by their canonical edge
  `id`; placeholder nodes are never invented.
- Search, selection, neighbourhood and inspector also exist in a bounded semantic DOM surface;
  no operation is WebGL- or pointer-only (D-120).
- The card overlay is bounded and measured: one selected card, one Peek and only neighbour
  previews that fit the stated density policy. Every returned neighbour remains in WebGL and
  the semantic list, so performance culling is never silent data omission (D-132, R20).
- Phase 2.1 qualifies the placement, not the bound: Explore remains the WebGL overview, while
  Focus may assign deterministic Directional Orbit presentation positions to the bounded
  neighbourhood. Those positions never become `GraphSnapshot` attributes or stored graph data
  (D-152, R10).
- Card content is copied from the API; visible preview truncation is permitted, client-authored
  summaries and inferred importance/cluster/quantitative axes are not (D-131, D-133).
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
- No X password, cookie, token, browser profile or session export may enter project data,
  fixtures, logs or errors.
- A third-party Twitter provider requires explicit opt-in, a fixed reviewed HTTPS origin and
  a visible disclosure that the requested post id and ordinary network metadata leave the
  machine. Redirects to unapproved origins are refused.
- Passive browser capture observes only responses already received during ordinary user-driven
  browsing; it makes no additional X request and performs no automated interaction.

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

**Goal:** search, read and browse related knowledge while keeping graph context and avoiding
blind node clicks or repeated Map ↔ Reader backtracking.

Deliverables:

- Exactly pinned Sigma v4 beta after the `T-202` real-graph/real-device gate
- Typed `MultiDirectedGraph` projection preserving node/edge identity, direction, parallel
  edges and intentional self-loops
- Progressive graph pages that dedupe D-059 straddling edges and state partiality
- Sigma.js/WebGL view with deterministic initial positions and measured layout
- Node/edge styles based on provenance and kind, with explicit normal/hovered/selected/
  neighbour states and a zoom/density/focus label policy
- Server-backed source/provenance/relation-vocabulary filters
- A collapsible search rail with verbatim result preview cards and one transient Peek card
- Search/focus with one addressable `mapLink` URL grammar and focus history that stays in Map
- Bounded neighbourhood view (depth 1–3), with truncation stated
- Bounded Focus Constellation: one primary selected Knowledge Card, active relation labels,
  density-budgeted neighbour previews and a complete semantic related list
- Collapsible Quick Read over `/api/entities/{entity_id}`, ordered around statement and
  evidence rather than technical metadata
- Link from Map to Reader through the existing `readerLink` grammar
- Keyboard-operable semantic DOM companion and honest WebGL-unavailable fallback

Acceptance criteria:

- An empty graph is displayed honestly.
- A partial graph is never presented as whole, even on the last page of a paged walk.
- Canonical and derived relationships are distinguishable.
- A search result and a related-node preview show enough returned statement/relation context
  for the user to choose before opening the node; no generated summary fills a gap.
- Selecting a node shows its complete stored statement and real evidence without leaving Map.
- At most one primary selected card and one transient Peek are overlaid on stage; any neighbour
  whose compact card cannot fit remains present in both WebGL and the semantic related list.
- Browser Back returns to the preceding focus without leaving or rebuilding `#/map`; Peek
  creates no history entry.
- Pointer and keyboard selection resolve the same existing `global_id`, and selection/filter
  state survives reload without inventing a default for malformed URL state.
- The same Search → Preview/Peek → Focus → Quick Read → Reader journey works with pointer,
  keyboard and touch; hover is never required.
- The real 86-node/118-edge sample has no lost or duplicated identities after accumulation.
- Sigma and any layout worker release their resources on replacement/unmount.
- The graph is fed from `output/library/graph.json` or an equivalent index.
- Raw and canonical files remain unchanged.

Moving a selected node or subgraph to the Canvas is deliberately not an acceptance criterion
for this phase: the board schema and write API do not exist until Phase 3. Phase 2 may expose
selection in a form Phase 3 can consume, but it must not guess that contract.

### Phase 2.1 — Map visual-quality remediation

**Goal:** bring the already-correct Map journey to the visual and interaction quality of the
approved references before building another major surface on top of it.

Deliverables:

- User-approved high-fidelity Explore and Focus mockups before production implementation
- Full-viewport Map workspace with compact floating status/controls and bounded drawers
- Quiet Explore overview with semantic label reveal rather than persistent label noise
- Directional Orbit Focus layout using only real direction and hop count
- Selected Knowledge Card as the definite centre, with readable neighbouring previews,
  visible ports and horizontal active-relation pills
- Editorial dark/light visual system with restrained colour, explicit type/spacing hierarchy
  and provenance distinguishable without colour
- Screenshot-backed real-browser QA at the review viewport and existing tested breakpoints,
  in English/Persian and normal/reduced motion

Acceptance criteria:

- The user approves both high-fidelity mockups before production UI changes begin.
- At 2852×1688, the graph is above the fold and Search → Focus → Quick Read requires no
  document scrolling.
- Focus is unmistakably central; incoming relations are left, outgoing relations right, and
  ring/distance means only the returned hop count.
- No two readable cards overlap; no card, relation pill or important text is clipped; no graph
  label or active edge runs through card content.
- Unrelated topology remains available as low-contrast context and never competes with the
  active reading path.
- Explore and Focus use the same `GraphSnapshot`, selected `global_id`, neighbourhood,
  formatter and URL history. The visual layout creates no second data truth.
- Dark/light and English/Persian preserve the same hierarchy; keyboard, touch, reduced-motion,
  no-WebGL and partial/refused-data journeys remain honest and usable.
- All Phase 2 behavioural, accessibility and renderer-lifecycle gates remain green, and raw,
  canonical and workspace files remain unchanged.

**These criteria passed on 2026-09-03 (D-202) and Phase 3 is unblocked.** The implementation
units and their serial order were `T-211`–`T-216` in `PROJECT_MANAGEMENT.md` §5 — six rather
than the five first planned, because `T-215`'s gate was green and its captures were refused
(D-196), which is ADR 0006 clause 5 behaving as designed. What the phase leaves standing is an
approved reference set regenerable from committed sources, sixteen browser scenarios whose
recorded numbers are a regression surface, a per-tier bound on the share of the field floating
chrome may cover, and four measured differences recorded in `docs/mockups/T-211/SPEC.md` §17 (which D-203 later added two more to, items 5 and 6)
rather than remembered.

### Phase 2.2 — Twitter/X source foundation

**Goal:** add useful public Twitter/X sources without a paid API, without storing an account
session, and without coupling the knowledge pipeline to one brittle provider.

This phase deliberately precedes Canvas by the user's 2026-09-03 roadmap decision (D-204;
[ADR 0007](adr/0007-twitter-acquisition-boundary.md)). Its first act is an empirical spike on
the user's real Iran environment. `x-cli` is the primary candidate, not an assumed dependency.

MVP scope:

- public single posts;
- provable same-author self-threads, root-first even when acquisition starts from a middle post;
- Persian/RTL text, replies and quotes represented without merging distinct authors;
- post text/entities, author and created time when stated, media metadata/alt text, poll
  snapshot, edit/tombstone/unavailable state and long-form content only where acquisition
  proves them;
- exact post-id and text-span/excerpt locators, with item-based coverage.

Explicitly out of scope: private/bookmarked/account-only content, third-party reply trees as
one authored thread, engagement history, recursive fetching of linked pages, credentials,
account/proxy rotation, browser automation, stealth/evasion and any payment or regional-access
circumvention.

Deliverables:

1. A reproducible acquisition capability matrix from the target environment, testing a pinned
   `x-cli` first and the same cases through FxTwitter/FxEmbed and official oEmbed.
2. A provider-neutral canonical Twitter capture with immutable raw evidence, digests, provider
   provenance, explicit omissions and schema-valid `PASS`/`PARTIAL`/`FAIL` fixtures.
3. At least one qualified acquisition provider. `x-cli` is used only if the spike passes; the
   separately installed/external-tool boundary is preferred until its AGPL and maintenance
   implications are deliberately revisited.
4. Explicit opt-in FxTwitter fallback and official oEmbed corroboration if retained by the
   spike; no silent network fallback.
5. Passive Firefox capture/import if needed: user-initiated observation of responses already
   loaded by ordinary browsing, with no extra requests or session material.
6. Twitter extraction, segmentation, precise provenance, item-based coverage and validators.
7. Source adapter, index/API/Library/Reader/Search/Map coexistence and an end-to-end failure
   rehearsal beside the existing YouTube source.

Acceptance criteria:

- At least one no-payment route passes the declared MVP on the user's actual environment; a
  successful request with incomplete content is recorded `PARTIAL`, not promoted to success.
- The entire acquisition can be revalidated from immutable raw bytes and recorded SHA-256;
  the acquisition provider/version/time and every omission are visible.
- No password, cookie, token, browser profile or session export is read, stored or logged.
- Every included or expected post is covered, omitted with a reason or unresolved. Deleted,
  private, suspended, withheld and unavailable items cannot disappear silently.
- A provider can be replaced without changing extraction, adapter, index or UI contracts.
- YouTube and Twitter coexist through the generic model; existing ids, raw evidence, outputs
  and Map visual regression surface remain unchanged.
- `WORKFLOW.md` is updated only after the behaviour and validators exist, and promises only
  matrix capabilities that passed.

The exact executable tasks and dependencies are `T-221`–`T-229` in
`PROJECT_MANAGEMENT.md` §5. `T-222` is currently the only claimable task.

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

### Phase 6 — Additional sources

**Goal:** adding Medium, web pages and later approved source types without changing the UI core.

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

### Risk 9: functional completion is mistaken for visual acceptance

Status: **closed 2026-09-03 (D-202) — all six children done, and closed on the only evidence
that could have closed it: a person accepting two sets of pictures.** The Map passed its
behavioural browser gate and the reviewed composition still did not meet the user's reference
bar, which is the whole of this risk. `T-211`'s replacement compositions were approved (D-191),
`T-212`–`T-214` built and dressed them (D-192–D-194), and `T-215`'s gate then demonstrated the
risk from the other side: **everything it asserts went green and the pictures still differed
from the approved ones in three ways no assertion fired on** (`SPEC.md` §16), so the captures
were refused (D-196) and `T-216` was opened. `T-216` demonstrated it once more and at a higher
level — the decision D-196 had reasoned out for it was wrong about the library in both halves,
and only reading the renderer's own sizing code and re-running the captures found that. The
acceptance came against `T-216`'s captures, judged by `T-215`'s gate unchanged.

Mitigation: Phase 2.1 separates visual acceptance from Phase 2 history. `T-211` required
approved Explore and Focus mockups before implementation — delivered — and `T-215` requires
final browser captures plus geometry assertions against them. A green behavioural suite alone
cannot close the risk, and every task in Phase 2.1 demonstrated it. The mockups'
own in-page geometry checks caught four defects a passing component suite would not have
seen, including an RTL drawer covering the focused card. `T-212`'s 605-test jsdom suite then
went green while the *browser* found three more: a focused card 5 px over the field's edge
because the drawer had been subtracted from a field too narrow to hold it, the counts surface
and the drawer laid out as one rectangle at 1440×900, and a screenshot comparison that had
quietly become a test of a focus ring. jsdom has no layout; every rectangle in it is zero.
`T-213`'s 607-test suite said nothing about five more, each of which a reader would have seen
at once — including every card on the wrong half of the field, because direction was read from
the neighbour's end of the relation. `T-214` closed a clause that had been *stated* since
ADR 0006 and had shipped broken through two tasks, because no test asserted it. And `T-215`
proved the thesis from the other side: sixteen green scenarios, and three visible differences
none of them fired on.

What the closed risk leaves behind is machinery rather than a warning: an approved reference
set regenerable from committed sources, sixteen browser scenarios whose recorded numbers are a
regression surface, a per-tier bound on the share of the field floating chrome may cover — read
off the reference by the instrument that measures the build — and four measured differences (D-203 added two more, §17 items 5 and 6)
standing in `SPEC.md` §17. A later surface that repeats this mistake is caught by those.

### Risk 10: Focus becomes a second graph or invents meaning

Mitigation: Directional Orbit is presentation derived from the existing snapshot, selection
and bounded neighbourhood. It may use returned direction and hop count only; it cannot mint an
identity, infer importance/clusters, merge neighbourhood data into the snapshot or persist its
positions as graph truth. Explore restores deterministically.

### Risk 11: a public Twitter provider is unavailable from Iran or changes abruptly

Mitigation: qualify the exact pinned candidate from the target environment before integration;
save provider version, raw evidence and failure results; keep acquisition behind a replaceable
canonical boundary. Documentation alone cannot close this risk.

### Risk 12: a successful acquisition is mistaken for a complete thread

Mitigation: provider success and completeness are separate. Model post order, omissions,
tombstones and unresolved items explicitly; use item-based coverage; make passive observation
`PARTIAL` unless a checkable boundary proves it complete.

### Risk 13: credentials, third-party disclosure, terms or licence obligations are hidden

Mitigation: accept no X password/cookie/token/session export; make FxTwitter explicit opt-in;
exclude account pools, automation and evasion; state that unofficial access is not represented
as X-approved; keep `x-cli` outside the runtime dependency graph until the qualification and
AGPL boundary are recorded. See [ADR 0007](adr/0007-twitter-acquisition-boundary.md).

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
| D-121 | ForceAtlas2 runs synchronously in the Map; no layout worker until a measurement demands one | accepted | 200 iterations over the real 86/118 graph measured 2.7–9.0 ms on the target machine, against a 16.7 ms frame. A worker adds a second lifecycle to kill and a layout that can outlive its renderer, to hide a pass that does not block |
| D-122 | The Map draws a truncated label under a stated density policy, never the raw `label` field; the full statement stays in the inspector | accepted | A knowledge unit's label is its whole `normalized_statement`. The gate drew 86 of them and they overlap into a pile that hides the graph. Truncating for display invents nothing as long as the inspector shows the statement in full |
| D-123 | A Map snapshot is whole only when the walk has finished, nothing is pending, and either the API said `truncated: false` or the loaded node count reached the stated `total` ([ADR 0005](adr/0005-knowledge-map-client.md)) | accepted | `truncated` describes a page, and the last page of a paged walk reports it as well, so it cannot be read as sticky partiality; a null cursor cannot be read as completion either (invariant 4). The count is the fact that settles it, and an uncounted `total` leaves the question open rather than answered |
| D-124 | Map node and edge attributes are the API's record verbatim plus a seeded position; styling lives in the renderer's reducers, never in the graph ([ADR 0005](adr/0005-knowledge-map-client.md)) | accepted | A stored label or colour would put presentation — including D-122's truncation — inside the data the inspector reads back, and a flattened record cannot support D-125's field-by-field refusal. A restyle then costs a reducer, not a re-projection |
| D-125 | A repeated identity must match in every field, with absent and `null` read as the same statement; anything else is a refusal naming the field, and the page is refused whole ([ADR 0005](adr/0005-knowledge-map-client.md)) | accepted | D-059 makes repeats normal, so a repeat is not an error; a disagreement is, because merging would draw a record no request returned. The contract's optional fields are `field?: T | null`, so the two spellings of *not stated* must not be a conflict |
| D-126 | The Map has one renderer lifecycle, owned by a framework-free `MapSession` reached through an injected factory; React decides only when to attach and when to kill ([ADR 0005](adr/0005-knowledge-map-client.md)) | accepted | Killing a renderer on unmount *and on replacement* is a sequence property, and jsdom has no WebGL, so it is only assertable against a fake. `StrictMode` double-invokes effects, so an attach that did not kill first would leak a WebGL context per mount — and a browser answers an excess by losing the oldest context, far from the cause |
| D-127 | Sigma is loaded through a dynamic `import` from the Map route only, never statically ([ADR 0005](adr/0005-knowledge-map-client.md)) | accepted | `sigma`'s default primitives read `WebGL2RenderingContext` off the global while the module body evaluates, so a static import anywhere in the application's module graph fails to load under jsdom and takes unrelated suites with it. Loading it where it is used also keeps a 362 kB chunk out of the routes that draw no graph |
| D-128 | A continuation page re-settles the whole layout; nodes already placed are not pinned ([ADR 0005](adr/0005-knowledge-map-client.md)) | accepted | New nodes arrive on their identity seeds, which say nothing about the structure the layout has found, so drawing them unrelaxed scatters dots over a settled graph. Pinning needs a third node attribute, and D-124 lets the graph carry `x`, `y` and the record only. The picture moving when the graph grows is the accepted cost |
| D-129 | A Map that cannot draw still reports the graph: the renderer's refusal is a stated state, the counts beside it stay true, and they precede the canvas ([ADR 0005](adr/0005-knowledge-map-client.md)) | accepted | `allowInvalidContainer: false` is kept because a graph drawn into a zero-sized box is an unexplainable failure — which makes an unsized container and a browser without WebGL2 states the Map must render. Those counts were also the only text account until `T-208` built the companion list beside them (D-142), so an account placed after the picture would read as complete to anyone who never reaches it |
| D-130 | The Map is a content browser with one progressive Search → Preview/Peek → Focus → Quick Read journey; preview and reading stay in `#/map`, while the Reader is the full-source destination ([ADR 0005](adr/0005-knowledge-map-client.md)) | accepted | A topology-only graph does not reveal what a node contains, and routing every selection away from the graph produces blind clicks and repeated backtracking. Progressive disclosure keeps overview, information scent and reading context together without turning every node into a card |
| D-131 | Search, Peek, selected and related cards use only verbatim API records; on-stage previews may visibly truncate, while Quick Read exposes the complete stored statement and recorded evidence; no client-generated summary is allowed ([ADR 0005](adr/0005-knowledge-map-client.md)) | accepted | `EntityRef.label` is already the pipeline's selected `normalized_statement`/content and its locator may state an excerpt and time. Summarising again would introduce an unproven claim between canonical evidence and the user |
| D-132 | Focus is a bounded card constellation over the same graph: one primary selected card, at most one transient Peek, active relation labels and density-budgeted neighbour previews; every returned neighbour is also present in the complete semantic related list ([ADR 0005](adr/0005-knowledge-map-client.md)) | accepted | Permanent HTML for every node defeats WebGL and creates overlap, while circles alone recreate the blind-click problem. Sigma's graph-to-viewport overlay pattern supports a bounded focus layer, and the semantic list prevents a viewport budget from becoming silent data loss |
| D-133 | Focus selection pushes `mapLink` history so Back restores prior focus without leaving Map; Peek is history-free. Grouping/ordering use only stated relation, direction, vocabulary, provenance, source and identity, never inferred importance or decorative quantities ([ADR 0005](adr/0005-knowledge-map-client.md)) | accepted | A navigation trail preserves context; hover entries would pollute it. The approved radial and infographic references justify visual hierarchy and labelled paths, not a radar metric or cluster the project does not hold |
| D-134 | A bounded neighbourhood is a transient projected structure and is never merged into the filtered `GraphSnapshot` ([ADR 0005](adr/0005-knowledge-map-client.md)) | accepted | It answers a different question from the filtered graph; merging it would make nodes, totals and completion disagree |
| D-135 | Edge events stay disabled; relations, direction, vocabulary and provenance are named in the DOM ([ADR 0005](adr/0005-knowledge-map-client.md)) | accepted | Selection addresses entities, not relations, and active-edge styling derives from endpoints without another hit-test path |
| D-136 | Neighbourhood depth is a bounded view control, not `mapLink` URL state ([ADR 0005](adr/0005-knowledge-map-client.md)) | accepted | It changes a transient request rather than graph scope or selected identity; invalid values are ignored rather than clamped |
| D-137 | The on-stage card overlay is presentation-only, pointer-free and hidden from accessibility APIs; its actions live in the semantic DOM ([ADR 0005](adr/0005-knowledge-map-client.md)) | accepted | This avoids a second interaction/accessibility tree and keeps the renderer from destroying owned React content |
| D-138 | On-stage cards are placed only when the camera settles and are hidden while it moves ([ADR 0005](adr/0005-knowledge-map-client.md)) | accepted | Per-frame HTML placement would repeatedly re-render reading surfaces and their omission accounting |
| D-139 | Map honesty is expressed by two total state functions that preserve unasked ≠ empty, partial ≠ whole, refused ≠ empty and undrawn ≠ absent ([ADR 0005](adr/0005-knowledge-map-client.md)) | accepted | Distributed render-site conditions had no single statement of these required distinctions |
| D-140 | A renderer module that never loads and a renderer that refuses its current container are separate states with separate messages ([ADR 0005](adr/0005-knowledge-map-client.md)) | accepted | The first is a permanent capability absence; the second normally recovers after layout |
| D-141 | The canvas is described as drawn, and receives `role="img"`, only while a live renderer holds the current graph ([ADR 0005](adr/0005-knowledge-map-client.md)) | accepted | React renders before its effects attach the renderer; claiming a picture earlier is false |
| D-142 | A non-windowed semantic DOM companion lists every drawn entity in API order, initially bounded at 25 with the remainder counted ([ADR 0005](adr/0005-knowledge-map-client.md)) | accepted | The graph must remain reachable without pointer, WebGL or an initial search, and degree ordering would invent importance |
| D-143 | Map panels share one `Disclosure`; its summary states its count and its open state is synchronized without fighting the asynchronous `toggle` event ([ADR 0005](adr/0005-knowledge-map-client.md)) | accepted | Multiple independent disclosures compete, while a controlled `<details>` can revert a later programmatic state |
| D-144 | Reduced motion is handled in CSS and at the JavaScript camera boundary; touch targets are at least 44 px and narrow screens retain a usable stage ([ADR 0005](adr/0005-knowledge-map-client.md)) | accepted | CSS cannot reach Sigma's camera animation, and zero/near-zero stages create misleading renderer states |
| D-145 | Card placement tests measured footprints in four orientations, includes the pointed mark in its exclusion rectangle, counts `no_room`, and forces at most four neighbour labels ([ADR 0005](adr/0005-knowledge-map-client.md)) | accepted | The browser showed the former fixed grid both rejecting cards that fit and accepting severe overlaps |
| D-146 | A new focus frames itself and its drawn neighbours once, with the shared reduced-motion argument ([ADR 0005](adr/0005-knowledge-map-client.md)) | accepted | Selection and camera were disconnected, leaving the focus small or off-stage and preventing usable card placement |
| D-147 | A renderer that refuses its container explicitly releases its WebGL context; CSS stage minimums are load-bearing for readability ([ADR 0005](adr/0005-knowledge-map-client.md)) | accepted | Browser testing found each refusal leaking a live context, while Sigma accepts any non-zero container even when unreadable |
| D-148 | Escape is read on `window`, and only while a Peek is open ([ADR 0005](adr/0005-knowledge-map-client.md)) | accepted | A canvas does not focus the route element, so an element-local handler could not dismiss pointer-created Peek state |
| D-149 | `interpolate` supports the English singular/plural form `{count|singular|plural}` chosen at one; Persian does not use it ([ADR 0005](adr/0005-knowledge-map-client.md)) | accepted | The real-browser walk exposed three English singular errors; Persian follows a different rule and needs no such branch |
| D-150 | Phase 2 remains functionally complete; Phase 2.1 (`T-210`) is a visual-quality gate that blocks Phase 3 ([ADR 0006](adr/0006-map-visual-quality.md)) | accepted | The behavioural gate passed, but the user rejected the current composition against the approved references |
| D-151 | High-fidelity Explore and Focus screenshots require explicit user approval before production UI work starts ([ADR 0006](adr/0006-map-visual-quality.md)) | accepted | Visual hierarchy and geometry must be agreed before refactoring shared Map surfaces |
| D-152 | Explore and Focus are different presentations of the same graph; Focus uses a Directional Orbit with centre, side and radius derived only from selection, direction and hop ([ADR 0006](adr/0006-map-visual-quality.md)) | accepted | Global topology and local reading need different compositions, while invented importance, clusters and metrics remain forbidden |
| D-153 | The Map is a viewport workspace with compact floating controls and bounded Search/related/Quick Read drawers, while truthful DOM order and keyboard access remain intact ([ADR 0006](adr/0006-map-visual-quality.md)) | accepted | Document-flow panels currently push the core graph and reading journey below the fold |
| D-154 | An editorial visual system plus screenshot-based browser QA is mandatory: no clipping, card overlap or labels beneath cards; relation pills stay horizontal; light/dark and English/Persian are verified ([ADR 0006](adr/0006-map-visual-quality.md)) | accepted | Behavioural tests alone did not reveal the visual hierarchy, collision and polish failures seen in the reviewed screenshot |
| D-191 | `T-211`'s Explore and Focus compositions are approved; implementation runs `T-212` → `T-213` → `T-214` → `T-215` and the committed sources in `docs/mockups/T-211/` are `T-215`'s reference, regenerated on demand ([ADR 0006](adr/0006-map-visual-quality.md)) | accepted | The gate ADR 0006 clause 2 opened is closed. It settles three things for the implementation: the Map is a viewport workspace whose document does not scroll; Focus is a Directional Orbit whose radius is `hops` and whose sides are relation direction; and below the orbit's minimum width the answer is fewer cards with counted omissions, never smaller text |
| D-192 | `T-212` composes the Map as a viewport workspace: `Shell` gives `/map` a `var(--bar-height) 1fr` frame, the stage is the field rather than a band on a page, every control is a bounded floating surface, and `placeConstellation` refuses a card that would be drawn under one ([ADR 0006](adr/0006-map-visual-quality.md)) | accepted | D-153 asked for the graph to occupy the usable route viewport, and the measurement is what makes this a decision rather than a restyle: at 2852×1688 the focused document was 5795 px and is now 1688 px, the viewport itself, and the stage moved from 790 px down a document to 56 px down a workspace. Four things are settled by it. **The route names the composition, not the view**: `Shell` holds the workspace path, because how tall the bar is and whether the document scrolls are facts about the frame, and a child that reported them upwards would have to do it in an effect — one render of the Map in the document composition first, which on this route means a renderer created against the wrong box. **The chrome is measured, never stated as insets**: the composition mirrors under `dir="rtl"`, and an inset per edge is the defect D-191 carries forward — so the surfaces marked `data-map-chrome` are read back with `getBoundingClientRect` in the stage's own coordinates and handed to the policy as rectangles, which is the same overlap test the crowding clause already ran. A card refused for one is `no_room`: the mark *is* on the stage, so `off_stage` would send a reader panning a camera that is not the problem. **The drawer's width comes out of the field only at SPEC §5's `full` tier**, because subtracting 560 px from a 1280 px viewport leaves a field too narrow to place the 416 px primary card beside its own centred mark — 452 px needed on one side, 344 available on either — and the card D-132 guarantees then hangs over the edge; the browser gate measured exactly that, at 5 px. **Below 48rem the route keeps its document composition**, which is a scope boundary rather than a compromise: SPEC §5's third tier is the orbit's narrowest and belongs to `T-213`. The four departures from the approved `SPEC.md` are recorded in its §13, the largest being that the camera's controls share the inline-end rail with the drawer instead of being painted over by it — a *Focus Not Obscured* failure in the approved capture itself |
| D-193 | `T-213` makes Focus a Directional Orbit: `placeOrbit` replaces `placeConstellation` in the one module that answers "where may a card go", the composition reads no camera, direction is taken from the **focus's** end of each relation, and a mark further out is drawn from the card it is actually joined to ([ADR 0006](adr/0006-map-visual-quality.md)) | accepted | ADR 0006 clause 3 asked for it and the browser is what makes it a decision rather than a restyle: at 2852×1688 it places 7 of the 8 neighbours returned and counts 1, against 4 and 4, with zero clipped cards, zero card/card overlaps, zero cards or pills under a floating control and zero pills without a clear seat. The camera stops being an input to placement, so the per-frame subscription, the settle timer and the two refusal reasons that were facts about a camera (`not_loaded`, `off_stage`) all go, and `unanchored` replaces them. `projectNeighbourhood` records `parentId`/`toParent` deterministically, so a hop-2 edge leaves the card it is joined to rather than a phantom point on a ring. The five departures from the approved `SPEC.md` are in its §14 |
| D-194 | `T-214` puts the editorial visual system on the composition and closes the last clause of ADR 0006 clause 5 that was still open: a node the orbit has carded loses its canvas label, and an edge whose both endpoints are carded loses its relation label ([ADR 0006](adr/0006-map-visual-quality.md)) | accepted | Until now the focused node's label and up to four neighbour labels were drawn underneath the very cards carrying the same statements, in less text and without the cut marked. `MapViewState.cardedNodes` is a set of ids rather than a flag, so a neighbour the orbit only *counted* keeps its label and is still named. Kind hue becomes a stated cue — an 8 px `KIND_FAMILY_COLOUR` swatch beside the record's own kind token, never a card fill — and the focused card is the centre by four means at once while its rail stays provenance's. The clauses are asserted as stylesheet rules, including that nothing keys a size, an opacity or a colour to a `confidence`, which is ADR 0006's rejected fourth alternative checked rather than remembered |
| D-195 | `T-215`'s real-browser visual gate asserts the geometry, accounting, direction and workspace clauses per scenario and leaves the acceptance of the pictures to the user, so the task is `PARTIAL` rather than done ([ADR 0006](adr/0006-map-visual-quality.md)) | accepted | The measurement moved into `browser/composition.ts`, so `measure_orbit.ts` and the gate are one implementation; sixteen scenarios hold the recorded numbers — 7 placed / 1 counted at 2852×1688 in dark, light and Persian, 2 / 6 at 1440×900 — with zero clipped, overlapping, chrome-covered or unseated marks and the document exactly the viewport. It walks the mockups' own entity when the library holds it, because a picture of another neighbourhood cannot answer whether this build reproduces these compositions. The one clause with no DOM node — a graph label under a card — stays where it is readable, in `labelPolicy` and its unit tests, and the gate holds the pill half; saying so is the point. The comparison then found three composition differences from the approved set, none of them a geometry violation, which is why the last word is a person's (`SPEC.md` §16) |
| D-196 | The `T-215` captures are not accepted as they stand; the three composition differences become `T-216`, a fifth child of `T-210`, and the sizing model that causes the largest of them is decided there rather than assumed ([ADR 0006](adr/0006-map-visual-quality.md)) | accepted | Explore's marks are sized in graph units and Sigma scales them with the camera, so the quiet field of the approved composition is quiet at 1440 and not at 2852, and the label grid then has room for roughly forty labels where the reference has eight. The fix is one decision, not two: `itemSizesReference: "screen"` freezes size under zoom and thereby retires D-122's `labelRenderedSizeThreshold` rule, so the sizing model and the zoom rule move together. `T-216` also carries the `compact` tier's collapsed chips, a recorded judgement on the drawer Explore mounts with nothing focused, and the re-run — and it is judged by `T-215`'s own gate, whose orbit numbers are a regression surface rather than a side effect |
| D-197 | A Map mark's size is screen pixels scaled by the field's width, and the camera is the only other thing that changes it; D-122's zoom rule is re-expressed rather than retired ([ADR 0006](adr/0006-map-visual-quality.md)) | accepted | The decision D-196 left open, and neither half of it was what D-196 assumed. `scaleSize` divides by `zoomToSizeRatioFunction(ratio)` and then, only under `"positions"`, multiplies by the framing — so clamping the ratio function could never have removed the viewport dependence, because that function never sees the field; and `"screen"` does not freeze size under zoom, because the division happens in both modes. So `labelRenderedSizeThreshold` survives as a camera rule and is re-derived at **6**, which must sit below the smallest mark any field draws at rest or it would silence a circle while a diamond in the same cell spoke — `NODE_PROVENANCE_MARK`'s four radii make four shapes read as one weight, not as a ranking. The ration moves to Sigma's grid at 560 px, measured at ten labels over 86 marks at 2852×1688 and five at 1440×900. The viewport scale itself is `SPEC.md` §3's own sentence, true of the shipped renderer for the first time |
| D-198 | Explore's edges are drawn at `MAP_QUIET_EDGE_OPACITY`, a third level between the dimmed and the active ([ADR 0006](adr/0006-map-visual-quality.md)) | accepted | §6's `--edge-faint` has no reader on a canvas (D-194), so the number lives in the one style table. Three levels rather than two, because "nothing is focused" and "something else is focused" are different sentences. The hue survives the quiet, so nothing ADR 0005 invariant 9 requires is traded for it, and the marks are deliberately left at full strength: quieting both would be a grey picture rather than a quiet one |
| D-199 | At the `compact` tier the Map's floating surfaces are chips — the search rail closed to its trigger, the filters and the account folded to theirs ([ADR 0006](adr/0006-map-visual-quality.md)) | accepted | The three surfaces the comparison named. The route decides the rail's preference now, because SPEC §5 gives that tier a search closed to its trigger and only the route measures the field — and an unmeasured field counts as wide, or D-130's opening step would be behind a click on every first paint. Disclosures rather than bounded scrollers, because a folded panel here states what it holds. D-129 is intact and checkable: the account precedes the stage, its counts are attributes on the section a fold never hides, and it opens itself whenever the picture is not being drawn. It moved no card |
| D-200 | Explore mounts no drawer; Quick Read and the related list appear with a focus and not before ([ADR 0006](adr/0006-map-visual-quality.md)) | accepted | The judgement D-196 asked to be recorded either way. ADR 0006 clause 4 opens the drawer *on demand*, SPEC §2 gives Explore four surfaces and none is a drawer, and the sentence the panels were kept for is already said by `MapSearchRail`'s focus row — on the one surface SPEC §2 does give Explore, and the step D-130's journey is on while nothing is selected. The share D-201 measures settled it: two collapsed panels are 4.5 % of an 844 px field against 10.3 % for the whole approved composition |
| D-201 | The browser gate bounds the share of the field floating chrome may cover, per tier, measured over both capture sets by one implementation — and at `compact` that bound is a ratchet rather than the reference's share ([ADR 0006](adr/0006-map-visual-quality.md)) | accepted | The failure it catches is four honest surfaces adding up rather than one oversized panel, which is what the comparison found and what no per-surface rule reports. `coveredShare` takes the union of the rectangles clipped to the field, and `capture_mockups.ts` calls it over the mockups' own surfaces, so the bound is read off the reference by the instrument that measures the build. `full` and `stack` are asserted at that measurement; `compact` is not, because the chrome's rectangles are what the orbit refuses cards against — bounding those surfaces to 14.4 % placed three cards at 1440×900 where D-193 recorded two. The gap is a finding in `SPEC.md` §17 and the trade is stated: the reference's 10.3 % costs the recorded 2 / 6 |

| D-202 | The `T-216` captures are accepted: `T-215`, `T-216` and `T-210` close, R21 closes, and Phase 3 is unblocked — and the `compact` tier's chrome bound is accepted as a ratchet rather than as the reference's own share ([ADR 0006](adr/0006-map-visual-quality.md)) | accepted | The decision the whole of Phase 2.1 existed to make possible, made the way ADR 0006 clause 5 says it must be: by a person looking at two sets of pictures. D-196 was the same clause exercised in the other direction, which is what makes this one worth recording — the gate was green both times and only one of the two answers was yes. What is accepted is the composition **and** the four differences `SPEC.md` §17 records as remaining. The first of them was a trade rather than an explanation and was taken deliberately: the chrome's rectangles are what the orbit refuses cards against, so bringing the `compact` share down to the reference's 10.3 % was measured to place three cards at 1440×900 where D-193 recorded two. The recorded numbers stand and the bound is a ratchet, so a later task may still take that trade — what it may not do is take it silently |
| D-203 | A green suite is evidence about what it looks at: seventy-one findings from a six-reader audit of a tree whose every gate was passing, closed with guards at the level the misses happened | accepted | The shape they share is the decision. Each guard that missed one was real and pointed at the known half of its problem: a stylesheet suite that never computed a contrast **number**; `validate_coverage` measuring a window against a bound the audited document supplied; the `ui` extra checked against the packages it declares, so an undeclared import was invisible to the job built to catch it; a drift guard asserted in prose and never written; six of sixteen visual scenarios whose numbers assert only on the machine holding the private library. So the remediation is 53 contrast assertions, a frontend lint gate and a type-check program for the capture scripts (both CI steps, and the second found a fault on its first run), a parameter-by-parameter served-versus-frozen comparison, one `PagedList` for the ladder five surfaces had copied, and guards that read every component through a glob rather than a list. **One finding's answer was found by measuring it rather than by reading it**: the card reservations were reported as never enforced, and enforcing them was tried and reverted — over all 86 centres of the real library, 63 lay a card out taller than its reservation and *none* of them overlaps, so the box is a seating input and the sentence calling it an upper bound over the drawn card was the actual defect. True upper bounds cost a recorded card (7 / 1 becomes 6 / 2) to buy nothing a reader sees, so the numbers stand, the claim is corrected where it was written, and the gate asserts the invariant a reader would notice — no two cards over the same pixels — over ten centres rather than two. Two further defects were found by the new tests rather than by the audit. What is not fixed is named rather than closed |
| D-204 | Insert Phase 2.2 / `T-220` before Canvas and qualify a no-payment Twitter/X acquisition route from the user's real Iran environment before integration ([ADR 0007](adr/0007-twitter-acquisition-boundary.md)) | accepted | `x-cli` is the primary candidate but not yet a dependency; `T-222` measures its exact pinned public/credential-free route before a schema or adapter is frozen. FxTwitter/FxEmbed is explicit opt-in fallback because the requested id leaves the machine, official oEmbed is corroboration only, and Firefox fallback passively imports responses ordinary browsing already received. Treasury/twscrape account pools, credentials, rotation, automation and evasion are excluded. Every accepted route ends at one provider-neutral immutable capture with honest item-based completeness; Canvas remains technically ready but deliberately deferred |
| D-205 | `T-222` qualifies a credential-free Twitter/X acquisition path from the user's real Iran environment: **`GO`**, `tamnd/x-cli` v0.5.0 pinned as an externally installed AGPL-3.0 binary ([spike report](spikes/T-222/REPORT.md)) | accepted | 52 measured cells across four routes, 0 `FAIL`, every Tier 0 surface reachable without payment from the user's real environment — Iran through his always-on tunnel, now a named phase dependency (D-209), with a stable egress and budgets consistent with a dedicated one; sanitized fixtures, digests and a reproducible harness committed. The measurement contradicted the candidate's own field table in four places, so `T-223` freezes on observation, not documentation. No adapter, schema or UI was written |
| D-206 | A same-author self-thread is complete **only when anchored at its deepest post**. Ingestion therefore **asks for the thread's last post** and records completeness as *complete to root from a user-asserted terminal anchor*; a root anchor warns rather than being accepted | accepted (user, 2026-09-03) | Upward is provable: `reply_to` terminates at a parent-less root, single-author, over a real 10-post thread at Tier 0. Downward is not: `x thread`/`x replies` return the anchor alone at every credential-free tier, the whole reply tree is Tier 2, and a 250-post author archive held 3 of 10 members. The user chose asking for the last post over making `PARTIAL` the normal state, and left `T-226` optional. The residual risk is permanent and explicit: a terminal anchor is a human judgement the system cannot verify |
| D-212 | The Twitter capture contract lives in `schemas/capture/v1/`, is self-contained, and makes every dishonest record unrepresentable rather than discouraged | accepted | A pipeline contract upstream of extraction, so it does not reference `schemas/v1/` — the index layer is derived *from* captures and the dependency would run backwards. Constraints were chosen against specific lies T-222 measured: no tier 2, no `complete` downward, no `observed` terminal claim, no `[]`/`{}` standing in for an observation of absence, `observed_at` required on metrics, and `additionalProperties: false` throughout so no provider shape leaks into extraction or UI. Its rejection catalogue is the real test |
| D-211 | The **canonical capture text is the authored form** (`t.co` links intact); expanded targets live in text entities beside the span | accepted (user, 2026-09-03) | Spans are offsets into the canonical text, so the choice binds every locator. The authored form is what raw evidence holds, the default route returns it without a third party, and expansion is a provider opinion that can lengthen text and shift stored spans without the post changing (D-210) |
| D-210 | Persian/RTL text survives every qualified route intact, and the routes agree byte-for-byte on the **authored** text; entity spans are **codepoint** offsets from the provider's facets | accepted (supersedes this row's first version) | ZWNJ, Persian ye, keheh and Persian digits identical across routes on four Persian posts; ZWNJ present in 53 of 60 sampled posts. The first version claimed the routes disagreed over `t.co` expansion — a field-selection error: FxTwitter's `tweet.text` is rendered, its `raw_text.text` is authored, and on the authored field the routes match exactly including media- and link-bearing posts. Entities come from `raw_text.facets` (`indices`/`original`/`replacement`), since x-cli's `entities.urls` holds expanded URLs absent from the text. Span basis is codepoints, proven against astral emoji; the UTF-16 reading corrupts every span after the first one |
| D-207 | Prefer x-cli **Tier 1 (anonymous guest token)** over Tier 0 as the default capture read | accepted (user, 2026-09-03) | Tier 0 silently truncated a real 2967-character post to 280 — 9% of the content, cut mid-sentence — with no in-band signal; Tier 1 passed 13 of 13 MVP cells and agreed with FxTwitter character-for-character. A guest token is bound to no account and is not a credential, session or account, but ADR 0007 did not name it, so it is ratified rather than assumed |

> **Ledger maintenance note.** Phase 1 implementation decisions D-046–D-116 are in
> `PROJECT_MANAGEMENT.md` §6, which remains their complete live ledger. Backfilling those
> already-accepted rows here is documentation consolidation work, not part of the Phase 2
> implementation and not a reason to renumber D-117–D-154.

## 20. Open questions

The Twitter questions below block contracts but are answered by `T-222`'s evidence, not by
guessing or by asking the user to choose a library name:

- Does the pinned credential-free `x-cli` path work from the target Iran environment for a
  public single post and a same-author self-thread?
- Which long-post, Article, edit, poll, media/alt-text and tombstone fields are actually
  available and stable enough to enter the canonical contract?
- Can the tested route prove a self-thread boundary from root and middle anchors, or must the
  capture remain `PARTIAL`?
- If `x-cli` does not qualify, is explicit opt-in FxTwitter sufficient, or is passive Firefox
  capture required for the approved MVP?

These board/media questions remain deferred to their appropriate later phase:

- Should boards enter Git by default, or only have a local backup?
- Should user notes stay limited to plain Markdown, or is rich text required?
- Are videos played only from YouTube, or will local files also be kept?
- At which phase do PDFs and documents genuinely enter the daily workflow?
- Can one entity have independent view state across multiple boards? Probably yes, but the schema must be fixed.
- Is a summary snapshot of a node inside a board needed to survive source deletion?
- How much recovery does the board and attachment deletion policy require?

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
- [x] Phase 2 / T-202: the Sigma v4 beta line pinned exactly and proved on the real 86/118 graph
  and on the user's MacBook; kept, with no worker (D-121) and no raw label (D-122)
- [x] Phase 2 / T-203: the typed projection and the progressive snapshot in
  [`web/src/map/`](../web/src/map/README.md) — pages accumulate, D-059 edges wait for their
  endpoints, conflicts are refused whole, and a walk at 1, 10, 50 or 500 nodes per page reaches
  the identical 86/118 graph (D-123–D-125)
- [x] Phase 2 / T-204: the addressable Map shell — `#/map`, the navigation entry, one renderer
  lifecycle through an injected factory, container sizing and resize, zoom/reset, deliberate
  progressive loading, and the snapshot's own counts stated before the canvas (D-126–D-129)
- [x] Phase 2 / T-207: the reading itself — the bounded neighbourhood over the last two
  uncalled endpoints, projected through `T-203` and never merged into the drawn graph
  (D-134); the stated on-stage density policy with a counted reason for every card it
  cannot place, and a related list that holds every returned neighbour regardless (R20);
  Quick Read over the complete stored statement, the recorded evidence and the derivation
  in D-131's order; and the canvas's event and coordinate adapters as a *third* caller of
  one selection identity (D-135–D-138)
- [x] Phase 2 / T-208: usable by everyone — two honest-state functions and the four pairs
  they keep apart (D-139–D-141), the DOM companion that lists every entity the canvas draws
  and is deliberately not windowed (D-142), one collapsible panel whose summary keeps
  stating what it holds (D-143), and the motion, touch and bidi rules including a
  reduced-motion answer for the camera the stylesheet cannot reach (D-144)
- [x] Translate this document to English per D-014

### Planned / not started

- [x] Phase 2 / T-209: the real-browser anti-pogo phase gate over everything `T-202`–`T-208`
  built — [`web/browser/`](../web/browser/gate.ts), 31 specs over the production bundle and
  the real API in Google Chrome on the target machine, plus the same walk on a software
  rasteriser; the WebGL context leak on a refused container, the camera that had never been
  told about selection, the density grid that answered the wrong question and the Escape key
  the canvas could not reach (D-145–D-149)
- [x] **Phase 2 complete** — every clause of the Phase 2 gate in `docs/PROJECT_MANAGEMENT.md`
  §5 is met, and met in a browser
- [x] **Phase 2.1 / T-210 — Map Visual Quality Pass** — the corrective epic, complete: Phase 2's
  functionality preserved while the weak shared composition was replaced by distinct Explore
  and Focus presentations, and the captures accepted on 2026-09-03 (D-150–D-154, D-191–D-202;
  [ADR 0006](adr/0006-map-visual-quality.md))
- [x] `T-211` high-fidelity Explore and Focus mockups at the review viewport, approved before
  any production UI work (D-191)
- [x] `T-212` viewport workspace shell (D-192)
- [x] `T-213` Directional Orbit Focus composition (D-193)
- [x] `T-214` editorial visual system (D-194)
- [x] `T-215` real-browser visual-quality gate — sixteen scenarios, green, and its captures
  refused (D-195, D-196), which is the gate working rather than failing
- [x] `T-216` the six remediations that refusal produced: a mark sized by its field rather than
  by the camera, a re-derived label ration, a quiet Explore field, chips at the `compact` tier,
  no drawer in Explore, and a per-tier chrome-share bound (D-197–D-201)
- [x] Phase 2.2 / `T-221`: acquisition, privacy and risk boundary accepted in
  [ADR 0007](adr/0007-twitter-acquisition-boundary.md) (D-204)
- [x] Phase 2.2 / `T-222` — pinned `x-cli` v0.5.0 and the approved alternatives qualified from
  the user's real Iran environment: `GO`, 52 cells, 0 `FAIL`, self-threads provable only from a
  deep anchor and Tier 0 shown to truncate long posts silently (D-205, D-206;
  [spike report](spikes/T-222/REPORT.md))
- [x] Phase 2.2 / `T-223` — provider-neutral capture contract frozen in `schemas/capture/v1/` on
  the spike report's measurements, with eight fixtures covering `PASS`/`PARTIAL`/`FAIL` and 97
  tests including a twelve-entry catalogue of captures that must be refused (D-210–D-212)
- [ ] **Phase 2.2 / `T-224`: claimed and in progress** — the qualified local provider seam over
  the digest-verified `x-cli` pin, reading at Tier 1 by default. `T-225` (opt-in network
  fallback) and `T-226` (passive browser capture, optional) stay claimable alongside it
- [ ] Phase 2.2 / `T-227`–`T-229`: extraction and coverage, adapter/product coexistence and the
  full phase gate
- [ ] Canvas — Phase 3 / `T-301`: technically unblocked by `T-210`, deliberately deferred
  until the Twitter phase gate closes (D-204)
- [ ] Pen annotations
- [ ] Additional adapters for Medium, web pages and future approved sources

Live status, task breakdown, and track ownership are maintained in `docs/PROJECT_MANAGEMENT.md`. In case of conflict, that file is the authority on **status** and this document is the authority on **design**.

## 23. Precise next step

**`T-224` is claimed: build the qualified local provider seam.** The acquisition boundary was
accepted as D-204, the qualification it demanded returned a `GO` (D-205), and the capture
contract it demanded is frozen in `schemas/capture/v1/` (D-212). Provider work is no longer
gated, and `T-224` is the default path — `T-225` and `T-226` are fallbacks to this seam.

What the measurement changed, and why the sequencing was right: the phase MVP promised "provable
same-author self-threads", and that is true in one direction only. Following `reply_to` upward
terminates at a parent-less root and *is* a completeness proof, credential-free. Enumerating
descendants is impossible at every credential-free tier, and the author archive that looks like a
substitute held 3 of 10 posts of a real thread. A contract frozen on the candidate's
documentation would have reported whole threads while silently dropping seven posts in ten. The
seam therefore ingests a thread from its **last** post (D-206) and cannot express a downward
completeness claim, because the contract has no field for one.

The three answers that shaped the contract now constrain the seam directly:

1. **Self-thread ingestion (D-206)** — ask for the thread's last post, walk upward to a root and
   report `PASS`; a root anchor warns and yields `PARTIAL` with descendants named unresolved.
   `T-226` passive Firefox capture stays optional as a result.
2. **Tier 1 (anonymous guest token) is the default read (D-207)** — Tier 0 returned 280 of a real
   post's 2967 characters with no field announcing the loss, so the seam does not default to it.
3. **The pin (D-208)** — v0.5.0, AGPL-3.0, an external binary at `~/.local/bin/x` invoked as a
   subprocess, with its recorded SHA-256 checked **before** it is run: a version or digest
   mismatch is a refusal, not a fallback to whatever `x` is on `PATH`.

One environment obligation rides along (D-209): the target environment is the user's always-on
tunnel, so the seam must distinguish a transport failure from a change in the provider's output.
A dropped tunnel that reads as provider drift would discard a good capture.

The Phase 2.2 gate is not met: `T-222` and `T-223` produced evidence and a contract, not a
pipeline, and `WORKFLOW.md` still correctly describes only the implemented YouTube workflow.


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
- Sigma v4 interaction events: <https://v4.sigmajs.org/reference/events/>
- Sigma v4 graph-coordinate HTML/SVG overlays:
  <https://v4.sigmajs.org/how-to/layers/sync-html-svg/>
- Graphology `MultiDirectedGraph`: <https://graphology.github.io/instantiation.html>
- Graphology ForceAtlas2: <https://graphology.github.io/standard-library/layout-forceatlas2.html>
- Shneiderman, *The Eyes Have It* — overview, zoom/filter, details on demand:
  <https://hci.stanford.edu/courses/cs448b/papers/shneiderman96eyes.pdf>
- Li et al., *Knowledge Graphs in Practice* — contextual knowledge cards, digestibility and
  discoverability: <https://www.cs.tufts.edu/~remco/publications/2023/TVCG2023-KnowledgeGraph.pdf>
- Nielsen Norman Group, information scent and pogo-sticking:
  <https://www.nngroup.com/articles/information-scent/>
  <https://www.nngroup.com/articles/pogo-sticking/>
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
- `x-cli`: <https://github.com/tamnd/x-cli>
- `x-cli` reading guide: <https://x-cli.tamnd.com/guides/reading-tweets/>
- `x-cli` account tiers: <https://x-cli.tamnd.com/guides/your-account/>
- `x-cli` CLI reference and releases:
  <https://x-cli.tamnd.com/reference/cli/>
  <https://github.com/tamnd/x-cli/releases>
- FxTwitter/FxEmbed API and service version:
  <https://docs.fxembed.com/api/introduction/>
  <https://fxtwitter.com/version>
- FxTwitter thread and conversation endpoints:
  <https://docs.fxembed.com/api/twitter/operations/2threadid/>
  <https://docs.fxembed.com/api/twitter/operations/2conversationid/>
- FxTwitter FAQ and source:
  <https://docs.fxembed.com/guide/faq/>
  <https://github.com/FxEmbed/FxEmbed>
- Official X oEmbed: <https://docs.x.com/x-for-websites/oembed-api>
- Official X id, conversation, edit, expansion and error semantics:
  <https://docs.x.com/fundamentals/x-ids>
  <https://docs.x.com/x-api/fundamentals/conversation-id>
  <https://docs.x.com/x-api/fundamentals/edit-posts>
  <https://docs.x.com/x-api/fundamentals/expansions>
  <https://docs.x.com/x-api/fundamentals/response-codes-and-errors>
- X Terms, developer policy and purchaser terms:
  <https://x.com/en/tos>
  <https://docs.x.com/developer-terms/policy>
  <https://legal.x.com/en/purchaser-terms.html>
- `twscrape` and a current breakage example:
  <https://github.com/vladkens/twscrape>
  <https://github.com/vladkens/twscrape/issues/327>
- `xTap` passive-capture reference: <https://github.com/mkubicek/xTap>
- XCancel legal-notice shutdown context: <https://github.com/dgw/sopel-cancelx>

## 25. Document change history

### 2026-09-03 — Twitter/X source foundation moved before Canvas

- Inserted Phase 2.2 / `T-220` before Canvas by user decision; Phase 3 remains technically
  unblocked but is deliberately deferred.
- Accepted [ADR 0007](adr/0007-twitter-acquisition-boundary.md) and D-204: qualify `x-cli`
  first from the real Iran environment; keep FxTwitter explicit opt-in, oEmbed corroborative
  and Firefox capture passive; exclude credentials, account pools, rotation and evasion.
- Defined the public single-post and provable same-author self-thread MVP, provider-neutral
  immutable capture, item-based coverage and the `T-221`–`T-229` execution sequence.
- Marked `T-221` complete and `T-222` as the only claimable task. No production code,
  canonical output or operational workflow was changed by this planning session.

### 2026-09-03 — Map visual-quality remediation approved

- Preserved Phase 2 and `T-201` as functionally complete, but inserted Phase 2.1 / `T-210` as
  a visual release gate before Phase 3 after the user rejected the reviewed composition.
- Added §7.2's Explore and Directional Orbit Focus direction, including updated ASCII
  compositions derived from the four approved references without inventing graph meaning.
- Accepted [ADR 0006](adr/0006-map-visual-quality.md) and D-150–D-154: separate Explore/Focus
  presentations, viewport workspace, user-approved high-fidelity mockups before production
  work, and screenshot-backed browser QA.
- Decomposed execution into `T-211`–`T-215`; `T-211` is the only claimable task and Phase 3 is
  blocked until the final visual gate passes.
- Consolidated Phase 2 implementation decisions D-134–D-149 into the canonical §19 ledger;
  their detailed live rationale remains in `PROJECT_MANAGEMENT.md` §6 and ADR 0005.

### 2026-09-02 — Phase 2 planning

- Recorded Phases 0 and 1 as complete and selected `T-201` as the approved Knowledge Map epic.
- Decomposed Phase 2 into claimable `T-202`–`T-209` in `PROJECT_MANAGEMENT.md`.
- Accepted [ADR 0005](adr/0005-knowledge-map-client.md): exact Sigma v4 beta pin behind a
  real-device compatibility gate, progressive graph snapshots, one Map URL grammar and a
  semantic DOM companion to the WebGL view.
- Expanded Phase 2 deliverables, acceptance criteria, performance rules and the precise next
  step. Canvas transfer remains Phase 3 rather than a false Phase 2 dependency.

### 2026-09-02 — Phase 2 implementation begins

- `T-202` completed: one exactly pinned Sigma v4 beta line, proved on the real 86/118 graph in
  a browser on the user's MacBook. D-121 (no layout worker) and D-122 (no raw label) recorded
  from what it measured.
- `T-203` completed: the typed projection and the progressive snapshot. D-123 (what makes a
  snapshot whole), D-124 (records verbatim, styling in reducers) and D-125 (a repeat that
  disagrees is refused, naming the field) recorded from what it took to build.
- §22 and §23 updated: `T-204` is the only claimable task.

### 2026-09-02 — the Map is on screen

- `T-204` completed: `#/map`, its navigation entry, one renderer lifecycle in `MapSession`
  behind an injected factory, container sizing and resize, zoom/reset, and deliberate
  progressive loading. The snapshot's own counts — loaded, held, known total, pages,
  `truncated`, complete — are stated before the canvas.
- D-126 (one lifecycle, injected), D-127 (Sigma loaded dynamically, because its module body
  reads a WebGL global), D-128 (a merged page re-settles the whole layout) and D-129 (a Map
  that cannot draw still reports the graph) recorded from what it took to build.
- §22 and §23 updated: `T-205` and `T-206` may now run in parallel.

### 2026-09-02 — card-centred Map browsing approved

- §7.1 records the approved Search → Preview/Peek → Focus → Quick Read journey and its
  Focus Constellation wireframe, informed by the user's four visual references and research
  on information scent, details on demand and contextual knowledge cards.
- D-130–D-133 bind the remaining phase: the Map remains a content browser; card content is
  verbatim; overlays are bounded and backed by a complete semantic related list; focus has
  history while Peek does not; no decorative metric or inferred grouping is introduced.
- `T-205`–`T-209`, Phase 2 acceptance and §23 were refined without widening `T-204`, the
  frozen API, Phase 3 Canvas or canonical output.

### 2026-09-03 — the Map, opened in a browser

- `T-209` completed, and with it Phase 2. The gate is `web/browser/` on
  `@playwright/test@1.62.1`: the built bundle, the real API, Google Chrome 152 on the target
  machine through `ANGLE Metal`, and the same 31 specs green on Playwright's bundled Chromium
  over SwiftShader and on the committed fixtures.
- D-145 (the card policy tests measured footprints for overlap in four orientations, and the
  forced label budget is 4), D-146 (a new focus is framed with its drawn neighbours),
  D-147 (a refused container releases its WebGL context, and the stage's CSS minimum is
  load-bearing because the renderer accepts anything non-zero), D-148 (Escape is read on
  `window`) and D-149 (one plural form in `interpolate`) recorded from what the walk found.
- ADR 0005 § *Walk result* records where it ran, what it drew, the measurements that replaced
  the numbers chosen by argument, the anti-pogo baseline and the nine findings.
- §22 and §23 updated: Phase 3 is next and its first act is to decompose it.

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
