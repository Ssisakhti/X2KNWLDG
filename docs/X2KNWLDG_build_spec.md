# X2KNWLDG — Build Specification

## 0. Purpose

Build a reusable YouTube-to-knowledge system that does **knowledge extraction, not summarization**.

The system must ingest a YouTube video, preserve the full transcript with timing/provenance, extract structured knowledge units, build relationships/graph structure, clearly separate source-grounded knowledge from model-derived synthesis, and run an explicit coverage audit so important content is not silently missed.

This project should **not** be built from scratch if an existing base already covers most of the pipeline. Use the existing `youtube-to-knowledge` project as the base/fork and extend it. Do **not** use Fabric `extract_wisdom` as the core extraction layer because its design prioritizes selecting the most interesting insights rather than preserving all meaningful knowledge.

### 0.1 Current implementation status — 2026-08-31

The current implementation is an operational first version built from `velmighty/youtube-to-knowledge`.

Implemented:

- timestamp-preserving import for `SRT`, `VTT`, structured `JSON`, and timestamped `TXT/MD`
- native YouTube caption acquisition through `youtube-transcript-api` with `yt-dlp` caption fallback
- explicit `TRANSCRIPT_REQUIRED` inbox flow when captions cannot be acquired
- immutable-by-policy raw transcript storage, transcript hash, and no silent output overwrite
- transcript integrity checks and time-aware segmentation with overlap
- canonical knowledge-unit, relationship, coverage, and extraction-bundle schemas
- explicit source-vs-derived validation and evidence/provenance checks
- typed per-video graph and cumulative cross-video knowledge library
- coverage windows, omission labels, PASS/PARTIAL/FAIL validation, and capped repair instructions
- canonical JSON, Markdown report, Obsidian, graph, search, CLI, and MCP interfaces
- shared agent workflow for ChatGPT/Codex and Claude Desktop
- 37 passing automated tests
- successful end-to-end acceptance run on `pqlWNihgdjI`
- 509 native captions, 7 extraction segments, 69 knowledge units, and 56 typed relationships
- 5/5 coverage windows and 21/21 semantic checkpoints passing

Pending hardening/follow-up work:

- add the acceptance video or an equivalent licensed transcript as a portable full regression fixture
- validate the ready MCP configuration inside Claude Desktop and repeat the same workflow from both desktop apps
- implement versioned reprocessing instead of only refusing silent overwrite
- add a multi-video contradiction/support acceptance fixture
- optionally add the executive summary view after coverage passes

Whisper and WhisperX are intentionally deferred. They are not installed or invoked by the current workflow.

---

## 1. Core product principle

**Do not summarize first. Extract first, compress later.**

A summary may be generated as an optional final view, but it must never replace the structured extracted knowledge or the source traceability.

The system should optimize for:

- completeness of meaningful knowledge
- traceability back to source
- distinction between observed/source content and model inference
- structured reuse of extracted knowledge
- multi-video accumulation and connection
- auditable omissions

---

## 2. Base project

Use this as the starting point:

- `velmighty/youtube-to-knowledge`

Retain useful capabilities from the base where practical:

- YouTube ingestion
- subtitle/transcript acquisition
- user-provided timestamped transcript fallback when native captions are unavailable
- optional Whisper/WhisperX adapter in a later phase
- deep analysis mode
- knowledge graph generation
- entity/relation extraction
- Obsidian-compatible outputs
- multi-video knowledge accumulation
- specialist querying over ingested videos

Do not reimplement these capabilities unless the existing implementation blocks reliability or provenance.

---

## 3. Why Fabric is not the core

Fabric's `extract_wisdom` can still be useful as an optional secondary view, but not as source-of-truth extraction.

Reasons:

- it intentionally selects surprising/interesting/insightful items
- it can omit meaningful but non-salient content
- it does not provide a coverage guarantee
- it is not designed around transcript-wide preservation
- it does not cleanly separate source knowledge from derived synthesis

Optional use later:

- “best insights” view
- executive takeaway view
- highlight generation

But the canonical knowledge store must come from the X2KNWLDG extraction pipeline described below.

---

## 4. End-to-end pipeline

```text
YouTube URL
  ↓
Metadata fetch
  ↓
Transcript acquisition
  ├─ Native YouTube captions preferred
  ├─ Preserve start time + duration + text
  ├─ User-provided SRT/VTT/JSON when captions are unavailable
  └─ WhisperX adapter deferred; never invoked automatically
  ↓
Transcript integrity checks
  ↓
Semantic segmentation
  ↓
Knowledge extraction per segment
  ↓
Knowledge-unit normalization
  ↓
Cross-segment deduplication / merge
  ↓
Source-vs-derived separation
  ↓
Relationship extraction
  ↓
Knowledge graph generation
  ↓
Coverage audit
  ↓
Validation / QA
  ↓
Outputs
  ├─ Canonical structured knowledge file
  ├─ Human-readable markdown
  ├─ Knowledge graph
  ├─ Obsidian vault files
  ├─ Coverage report
  └─ Optional executive summary
```

---

## 5. Transcript requirements

### 5.1 Preferred source

Use native YouTube captions when available.

Do **not** collapse them into plain text while discarding timing metadata.

Preserve at minimum:

```yaml
segment_id: cap_000123
start_sec: 312.42
end_sec: 318.91
duration_sec: 6.49
text: "..."
source: youtube_caption
language: en
```

If `duration` is provided instead of end time:

```text
end_sec = start_sec + duration
```

`original_id` and `speaker` are added when the source supplies them, and omitted when it
does not.

#### Non-speech cues

A cue whose text cleans away to nothing is **kept**, not dropped. That means a cue that was
blank or whitespace-only to begin with, and one whose whole body was WebVTT markup —
`<v Speaker>`, `<c.yellow>`, a karaoke timestamp tag such as `<00:00:01.000>` — with no words
between the tags. (A literal sound label like `[music]` is ordinary text and is **not**
affected: it survives cleaning, so it is a normal caption.) A non-speech caption carries:

```yaml
text: ""
non_speech: true
```

and its `start_sec`, `end_sec`, and `duration_sec` unchanged. The key is present only on such
captions; a caption with speech carries no `non_speech` key at all, rather than `false`.

**This is a timing-integrity mechanism, not a formatting nicety.** `duration_sec` in
`metadata.json` comes from `transcripts.transcript_integrity`, which reads it off the caption
timings, so dropping a cue moves the clock. A ten-minute VTT whose last cue (09:55–10:00) held
only whitespace reported `duration_sec: 5.0` — the length of the one surviving caption. The
coverage audit then built its windows over 0–5s, found them covered, and declared `PASS` over
under 1% of the video. Keeping the cue keeps the clock. `tests/test_transcripts_hardening.py::SilentCueTests`
is that exact case, held down.

Consequences for every reader — the segmenter, the coverage audit, the UI, and any adapter:

- An empty `text` on a `non_speech` caption is **data, not missing data.** Never treat it as
  a gap, a parse failure, or something to repair.
- Never quote one as evidence, and never build a knowledge unit from one.
- Never drop them when computing duration, window boundaries, or caption counts.
- A cue with neither text nor a usable start time is a different thing and *is* discarded;
  it is not a cue.

Verified against `transcripts._canonical_caption`, which is the single place a canonical
caption is built, for every input format.

### 5.2 Fallback

Current-version behavior:

- if native captions are unavailable or unusable, create `inbox/<video-id>/`
- request a timestamped `SRT`, `VTT`, or structured `JSON` transcript from the user
- accept `TXT/MD` only when every block has an explicit start and end timestamp
- never silently continue with untimed text
- never automatically invoke Whisper or WhisperX

Future optional behavior:

- WhisperX may be added as an explicit opt-in adapter
- its output must be normalized to the same canonical schema
- enabling it must not change the user-provided transcript path or provenance rules

### 5.3 Transcript preservation

Store the raw transcript as an immutable source artifact.

Never overwrite it with cleaned or summarized text.

Recommended files:

```text
raw/transcript.json
raw/transcript.md
```

### 5.4 Integrity checks

Before extraction, verify:

- transcript is non-empty
- timing is monotonic
- no obviously missing multi-minute ranges unless source lacks data
- language detection is plausible
- transcript length is plausible for video duration — non-speech cues are retained (§5.1),
  so a trailing stretch of music cannot shorten the reported duration
- duplicate caption blocks are detected

Flag uncertainty instead of silently proceeding.

---

## 6. Semantic segmentation

Do not process the whole transcript as a single blob if the video is long.

Create semantic segments with overlap.

Recommended starting strategy:

- target: 2–6 minutes per segment
- overlap: 10–20 seconds or 1–2 caption blocks
- break on topic transitions when detectable
- preserve exact source span for each segment

Each segment should include:

```yaml
segment_id: seg_012
start_sec: 720.0
end_sec: 965.4
caption_ids:
  - yt_000311
  - yt_000312
  - yt_000313
text: "..."
```

---

## 7. Canonical knowledge-unit schema

Every extracted unit must follow a normalized structure.

```yaml
id: KU-000123
kind: claim
source_class: source
content: "The team observed that workflow redesign mattered more than tool access."
normalized_statement: "Workflow design can dominate tooling choice as a productivity factor."
importance: high
confidence: 0.95

source:
  video_id: pqlWNihgdjI
  segment_id: seg_012
  start_sec: 742.1
  end_sec: 781.0
  evidence_excerpt: "..."

attribution:
  speaker: "Clare Liguori"
  attribution_type: direct

relationships:
  supports: []
  contradicts: []
  causes: []
  depends_on: []
  exemplifies: []
  refines: []
  related_to: []

notes: null
```

---

## 8. Allowed knowledge-unit kinds

At minimum support:

### Source-grounded units

- `claim`
- `evidence`
- `fact`
- `statistic`
- `concept`
- `definition`
- `framework`
- `principle`
- `process`
- `instruction`
- `recommendation`
- `example`
- `case_study`
- `analogy`
- `caveat`
- `limitation`
- `assumption`
- `counterargument`
- `question`
- `open_problem`
- `reference`
- `quote`

### Derived/synthesized units

- `relationship`
- `implication`
- `generalized_rule`
- `mental_model`
- `diagnostic_model`
- `actionable_experiment`
- `hypothesis`
- `synthesis`

---

## 9. Source vs Derived separation

This is mandatory.

Every unit must have:

```yaml
source_class: source | derived
```

### 9.1 `source`

Use when the unit is directly supported by transcript content.

Requirements:

- source timestamp
- source excerpt or exact caption references
- attribution when relevant

### 9.2 `derived`

Use when the model infers or synthesizes across one or more source units.

Requirements:

- must reference supporting knowledge-unit IDs
- must never be phrased as if explicitly stated by the speaker
- include confidence
- include derivation note

Example:

```yaml
id: KU-D-0012
kind: diagnostic_model
source_class: derived
content: "An AI-native team can be diagnosed by explicit intent, persistent context, autonomous execution, and fast local feedback."
derived_from:
  - KU-0041
  - KU-0049
  - KU-0057
  - KU-0062
confidence: 0.88
```

---

## 10. Extraction behavior

The extractor must explicitly seek all meaningful knowledge, not just highlights.

For each semantic segment, ask for all applicable categories.

The extraction prompt/instructions should enforce:

- preserve boring-but-important details
- preserve qualifiers
- preserve limitations
- preserve numerical values with units/context
- distinguish examples from evidence
- distinguish speaker opinion from reported observations
- preserve disagreements and uncertainty
- avoid inventing missing rationale
- avoid merging separate claims prematurely
- preserve causal direction if stated
- preserve scope conditions

Never enforce arbitrary counts like “exactly 20 insights.”

---

## 11. Evidence rules

For every important claim, attach the best available supporting transcript evidence.

At minimum:

```yaml
claim_id: KU-0101
supported_by:
  - KU-0102
  - KU-0103
```

Where evidence units may be:

- experiment result
- statistic
- anecdote
- example
- comparison
- quoted observation

If a claim is asserted without evidence, mark:

```yaml
evidence_status: unsupported_in_video
```

Do not fabricate evidence.

---

## 12. Statistics and numbers

Numerical extraction must be lossless where practical.

Capture:

- value
- units
- range
- denominator/sample size
- comparison baseline
- timeframe
- conditions
- uncertainty

Example:

```yaml
kind: statistic
content: "Median productivity improvement was approximately 4.5× in the pilot."
value: 4.5
unit: "x"
stat_type: median
population: "pilot teams"
context: "Amazon Stores pilot"
```

Do not flatten distinct experiments into one number.

---

## 13. Relationship model

Support directed typed edges.

Recommended edge types:

- `supports`
- `contradicts`
- `causes`
- `contributes_to`
- `depends_on`
- `enables`
- `inhibits`
- `exemplifies`
- `is_example_of`
- `is_evidence_for`
- `refines`
- `qualifies`
- `is_part_of`
- `precedes`
- `results_in`
- `related_to`

Graph edges should reference knowledge-unit IDs, not free text only.

Example:

```yaml
from: KU-040
relation: enables
to: KU-055
confidence: 0.92
source_class: derived
```

---

## 14. Coverage audit

This is the main extension missing from existing tools.

### 14.1 Goal

Prove that the extractor inspected the entire transcript and account for what was kept, merged, or intentionally omitted.

### 14.2 Coverage windows

Split the full transcript into audit windows, for example 2–5 minutes each.

For each window record:

```yaml
window_id: CW-007
start_sec: 900
end_sec: 1200
status: covered
knowledge_units:
  - KU-088
  - KU-089
  - KU-090
omitted_items:
  - type: repetition
    note: "Repeated prior explanation of workflow redesign."
unresolved_items: []
```

### 14.3 Allowed omission reasons

Use explicit labels only:

- `intro_noninformational`
- `sponsor`
- `small_talk`
- `transition`
- `repetition`
- `housekeeping`
- `audience_reaction`
- `unintelligible`
- `off_topic`
- `other_explained`

If `other_explained`, require a note.

### 14.4 Coverage pass criteria

Coverage can only be `PASS` when:

- every transcript span belongs to an audit window
- every window is `covered` or has explicit omission accounting
- unresolved important content is zero or clearly surfaced
- all high-importance source units have provenance

Otherwise:

```text
Coverage: FAIL
```

or

```text
Coverage: PARTIAL
```

Never claim complete coverage without this audit.

---

## 15. Deduplication and merging

Repeated content should not create noisy duplicate units.

But deduplication must preserve provenance.

If the same claim appears multiple times:

```yaml
id: KU-101
kind: claim
source_class: source
content: "..."
source_occurrences:
  - start_sec: 310
    end_sec: 340
  - start_sec: 1280
    end_sec: 1310
```

Do not erase repeated emphasis; optionally record recurrence count.

---

## 16. Confidence

Use confidence values carefully.

Recommended interpretation:

- `0.95–1.00`: directly and clearly stated
- `0.80–0.94`: well-supported inference/normalization
- `0.60–0.79`: plausible but some ambiguity
- `<0.60`: include only if useful and clearly mark uncertain

Confidence is not a substitute for provenance.

---

## 17. Human-readable output

Generate a canonical Markdown report with sections like:

```markdown
# <Video title>

## Metadata

## Core Thesis

## Knowledge Map

## Claims

## Evidence

## Concepts & Definitions

## Frameworks & Mental Models

## Processes / How-To

## Examples & Case Studies

## Facts & Statistics

## Recommendations

## Caveats & Limitations

## Open Questions

## Source Knowledge

## Derived Knowledge

## Relationships

## Actionable Experiments

## Coverage Audit

## Optional Executive Summary
```

Every important item should include a timestamp link when possible.

Example:

```markdown
### KU-0042 — Claim
**Statement:** ...
**Source:** 12:21–13:08
**Evidence:** ...
**Confidence:** 0.97
```

---

## 18. Timestamp links

Prefer clickable links back to the source video.

Format:

```text
https://www.youtube.com/watch?v=<VIDEO_ID>&t=<SECONDS>s
```

Use the start time of the relevant source span.

---

## 19. Obsidian output

Retain Obsidian compatibility from the base project.

Recommended structure:

```text
vault/
  videos/
    <video-id>.md
  concepts/
    <concept-slug>.md
  claims/
    <claim-id>.md
  people/
    <person>.md
  organizations/
    <organization>.md
  frameworks/
    <framework>.md
  reports/
    <video-id>-coverage.md
```

Use wikilinks where appropriate.

Example:

```markdown
[[AI-native development]] enables [[Agent autonomy]] through [[Fast local feedback]].
```

Avoid creating duplicate concept pages for synonyms; maintain aliases.

---

## 20. Canonical machine-readable outputs

At minimum produce:

```text
output/<video-id>/
  metadata.json
  transcript.json
  segments.json
  knowledge_units.json
  relationships.json
  coverage.json
  report.md
  graph.json
```

Optional:

```text
  graph.graphml
  graph.csv
  report.html
```

---

## 21. Optional executive summary

Only after extraction + audit succeeds.

The summary must be generated **from the canonical knowledge store**, not directly from the raw transcript.

This ensures the summary is a view over preserved knowledge rather than a lossy first-pass transformation.

---

## 22. Querying an ingested video

Retain or implement a “video specialist” mode.

When answering questions about an ingested video:

1. search canonical knowledge units first
2. follow relations if useful
3. inspect raw transcript when exact wording or missing detail matters
4. cite timestamps
5. distinguish source answer from derived synthesis
6. do not answer from the summary alone

---

## 23. Cross-video knowledge accumulation

When ingesting new videos:

- identify existing concepts
- reuse canonical concept nodes
- add new evidence/claims to existing nodes
- create cross-video contradiction/support relations
- track source provenance per video

Do not overwrite prior knowledge with newer content unless explicitly versioned.

---

## 24. Contradiction handling

If two videos disagree:

```yaml
relation: contradicts
```

Keep both claims.

Store:

- source video
- speaker
- date
- evidence
- scope conditions

Never collapse disagreement into one “correct” statement unless a separate fact-checking process is run.

---

## 25. Fact-checking

Fact-checking is a separate optional stage.

Do not mix:

```text
What the speaker said
```

with:

```text
Whether the statement is externally true
```

Optional future stage:

```text
source claim
  ↓
external verification
  ↓
verified / disputed / uncertain
```

Keep the original source claim intact.

---

## 26. Extraction quality rules

The model/instructions must explicitly enforce:

- no hallucinated facts
- no invented timestamps
- no invented quotes
- no collapsing separate experiments
- no dropping caveats because they are less interesting
- no arbitrary top-N truncation
- no replacement of exact statistics with vague paraphrase
- no pretending derived synthesis was spoken by the source
- no claiming coverage pass without audit data

---

## 27. Validation checks

Implement automated validators where practical.

### 27.1 Transcript validator

Check:

- monotonic timestamps
- non-empty text
- valid video ID
- expected duration coverage

### 27.2 Knowledge-unit validator

Check:

- required fields
- allowed `kind`
- valid `source_class`
- source units have provenance
- derived units have `derived_from`
- confidence in [0,1]

### 27.3 Relationship validator

Check:

- both node IDs exist
- relation type is allowed
- no malformed self-loop unless intentional

### 27.4 Coverage validator

Check:

- audit windows cover full transcript timeline
- each window has status
- omitted items have allowed reasons
- unresolved high-importance items prevent PASS

---

## 28. Test strategy

Use the previously discussed YouTube video as the primary acceptance test:

```text
https://www.youtube.com/watch?v=pqlWNihgdjI
```

The expected extraction should preserve, at minimum, distinct knowledge around:

- multiple Amazon experiments rather than flattening them together
- Bedrock greenfield case
- Prime Video legacy case
- approximately 50-team pilot
- median ~4.5× and top >10× results where supported by source transcript
- similar tooling vs different workflow behavior
- the five habits
- agent context
- context pruning as models improve
- initial productivity slowdown
- infrastructure changes to make environments agent-friendly
- feed agents vs babysit agents
- async / parallel agent execution
- explicit intent and specs
- fast/local/deterministic testing
- self-correction loops
- burnout / FOMO / cognitive load caveat
- organizational bottleneck shift toward decisions/review/intent

The test should not hardcode these as “truth” if the transcript differs; instead use them as expected semantic checkpoints to verify completeness.

---

## 29. Acceptance criteria

The build is acceptable only if all of the following are true.

### Transcript

- [x] Native YouTube caption timestamps are preserved by the acquisition/import pipeline.
- [x] Raw transcript, timestamped Markdown, and transcript hash are stored without silent overwrite.
- [x] User-provided timestamped transcripts are the current fallback.
- [x] WhisperX is disabled and deferred rather than used automatically.
- [x] Native caption acquisition passed end-to-end on the provided YouTube acceptance video.

### Extraction

- [x] Knowledge units are structured and validated.
- [x] Claims, evidence, examples, caveats, stats, frameworks, recommendations, etc. are distinct types.
- [x] No arbitrary top-N insight selection is used in the extraction prompts.
- [x] The complete extraction pass produced 69 validated knowledge units on the acceptance video.

### Provenance

- [x] Source units require valid timestamp/source spans and transcript evidence.
- [x] Derived knowledge must reference valid source-unit IDs and include a derivation note.
- [x] Source and derived knowledge are clearly separated and validated.

### Coverage

- [x] Contiguous transcript audit windows are generated and validated.
- [x] Omitted content is restricted to explicit allowed reasons.
- [x] Coverage can report PASS, PARTIAL, or FAIL and cannot be forced to pass structurally.
- [x] All five semantic coverage windows passed with zero unresolved important items.

### Graph

- [x] Knowledge units can be connected with typed relations.
- [x] A cumulative namespaced cross-video graph and concept registry exist.
- [x] Contradictory claims can coexist through typed `contradicts` edges.
- [ ] Cross-video contradiction/support behavior needs a multi-video acceptance fixture.

### Outputs

- [x] Machine-readable JSON outputs exist.
- [x] Human-readable Markdown report generation exists.
- [x] Obsidian-compatible output exists.
- [ ] Optional executive summary generation is deferred; when added, it must read canonical knowledge only.

---

## 30. Suggested implementation phases

### Phase 1 — Fork and inspect base — COMPLETE

- fork `youtube-to-knowledge`
- map current transcript pipeline
- map current deep-analysis prompt
- map current graph schema
- map current Obsidian output

### Phase 2 — Fix transcript provenance — COMPLETE IN CODE

- preserve native YouTube `start` and `duration`
- normalize transcript schema
- retain raw immutable transcript

### Phase 3 — Add knowledge-unit layer — COMPLETE

- define schema
- implement per-segment extraction
- normalize and deduplicate
- attach provenance

### Phase 4 — Add source-vs-derived logic — COMPLETE

- extraction writes source units
- synthesis pass writes derived units
- derived units reference source IDs

### Phase 5 — Add relationship graph — COMPLETE

- map existing graph functionality onto canonical knowledge-unit IDs
- add typed edges

### Phase 6 — Add coverage audit — COMPLETE

- create timeline windows
- map extracted units back to windows
- classify omissions
- produce PASS/PARTIAL/FAIL

### Phase 7 — Outputs — COMPLETE

- canonical JSON
- report.md
- coverage.md
- Obsidian notes

### Phase 8 — Testing — PRIMARY ACCEPTANCE COMPLETE, MULTI-VIDEO FIXTURE PENDING

- run on the provided Clare Liguori video
- manually compare against transcript
- verify important details are not silently omitted
- add regression fixtures

Current result: `37 passed` automated tests. The Clare Liguori acceptance video also passed transcript integrity, provenance, knowledge-unit, relationship, and coverage validation. It produced 509 captions, 7 segments, 69 knowledge units, 56 relationships, 71 Obsidian files, and matched 21/21 specified semantic checkpoints.

---

## 31. Prompting strategy

Use multiple passes instead of one giant prompt.

Recommended:

```text
Pass 1: segment extraction
Pass 2: normalization/deduplication
Pass 3: relationships
Pass 4: derived synthesis
Pass 5: coverage audit
Pass 6: optional summary
```

This is preferable to one prompt because it improves:

- auditability
- recoverability
- provenance
- partial reruns
- testing
- cost control

---

## 32. Segment extraction prompt requirements

The segment extractor should receive:

- video metadata
- segment transcript
- segment start/end
- recent adjacent context if needed
- knowledge-unit schema

It should return only structured data.

Instruction intent:

```text
Extract every meaningful knowledge unit in this segment.
Do not optimize for novelty or brevity.
Preserve claims, evidence, numbers, examples, caveats, assumptions,
processes, definitions, frameworks, recommendations, and open questions.
Do not infer beyond the transcript in this pass.
Every unit must include the best supporting source span.
```

---

## 33. Derived synthesis prompt requirements

This pass may infer across source units.

Instruction intent:

```text
Using only the supplied source-grounded knowledge units, derive useful
relationships, implications, generalized rules, mental models, diagnostic
models, and actionable experiments.

Every derived item must cite the source-unit IDs it depends on.
Never attribute a derived statement directly to the speaker unless it was
explicitly stated in the source.
```

---

## 34. Coverage-audit prompt/logic

Prefer deterministic mapping plus LLM review.

For each audit window:

- list caption IDs
- list mapped knowledge units
- compare transcript text to represented knowledge
- identify meaningful uncovered content
- classify intentional omissions

Instruction intent:

```text
Audit this transcript window for semantic coverage.
Do not create new knowledge unless needed to repair a missed item.
If meaningful content is absent from the knowledge store, mark the window
uncovered and return the missing knowledge candidates.
If content is intentionally omitted, classify the omission reason.
```

If missed items are found:

1. create missing source units
2. rerun coverage for that window

---

## 35. Repair loop

Coverage should support automatic repair.

```text
extract
  ↓
audit
  ↓
missing knowledge?
  ├─ no → continue
  └─ yes
      ↓
    repair extraction
      ↓
    re-audit
```

Cap repair iterations to avoid infinite loops, e.g. 2–3 passes.

If unresolved after the cap:

```text
Coverage: PARTIAL
```

and surface the unresolved spans.

---

## 36. Storage/versioning

Recommended to store extraction metadata:

```yaml
pipeline_version: 0.1.0
extractor_model: "..."
extracted_at: "..."
transcript_source: youtube_caption
transcript_hash: "..."
```

This makes reprocessing and comparison possible.

---

## 37. Reprocessing behavior

If the same video is processed again:

- detect same transcript hash
- allow extraction rerun with newer pipeline/model
- do not delete prior run automatically
- version outputs by run or pipeline version

---

## 38. Error handling

Surface clear errors for:

- unavailable/private video
- age/region restrictions
- native captions unavailable and no user-provided timestamped transcript
- malformed captions
- unsupported language
- model output schema failure
- incomplete coverage

Never silently downgrade to summary-only mode.

---

## 39. Non-goals for initial version

Do not overbuild initially.

Not required in v1:

- local Whisper/WhisperX transcription
- full external fact-checking
- visual-frame understanding
- speaker diarization for complex podcasts unless needed
- web UI
- vector database if local files suffice
- autonomous topic ontology generation at large scale

Design interfaces so these can be added later.

---

## 40. Future extensions

Potential later features:

- frame/image understanding for slides and diagrams
- OCR of on-screen text
- external source verification
- citation graph across videos/articles/papers
- personalized knowledge ranking
- spaced-repetition cards
- study guide generation
- question bank generation
- “what changed vs my existing knowledge?” mode
- contradiction detection across creators
- claim confidence based on multiple sources

---

## 41. UX principle

A user should be able to provide:

```text
https://www.youtube.com/watch?v=...
```

and receive a durable knowledge artifact without needing to manually ask:

- “what were the claims?”
- “what evidence supported them?”
- “what caveats were mentioned?”
- “what did you miss?”

The pipeline must answer those systematically.

---

## 42. Minimal CLI and desktop-agent interface

Implemented CLI examples:

```bash
x2knwldg process "https://www.youtube.com/watch?v=..."
x2knwldg import-transcript transcript.vtt --video-id <video-id> --video-url <url>
```

Extraction and validation:

```bash
x2knwldg apply-bundle output/<video-id> extraction_bundle.json
x2knwldg finalize output/<video-id>
x2knwldg validate output/<video-id>
```

Query mode:

```bash
x2knwldg search "What evidence supports the main thesis?" --video-id <video-id>
```

Cross-video library:

```bash
x2knwldg rebuild-library
```

Daily use should not require the user to type CLI commands. ChatGPT/Codex can operate the local project directly, and Claude Desktop can use the local MCP server. The CLI remains the deterministic, testable execution boundary shared by both apps.

---

## 43. Final implementation instruction for Work

When implementing this project:

1. Start from `velmighty/youtube-to-knowledge` rather than a blank repo.
2. Inspect the current code before changing architecture.
3. Preserve useful existing functionality.
4. Make the smallest set of extensions needed to satisfy this spec.
5. Add tests for each new behavior.
6. Use the provided YouTube video as the primary end-to-end regression test.
7. Do not claim the build is complete until the acceptance criteria and coverage audit pass.
8. Keep canonical machine-readable knowledge separate from human-readable summaries.
9. Treat provenance and coverage as first-class data, not formatting extras.
10. Prefer explicit schemas and validators over prompt-only conventions where practical.

---

## 44. Definition of done

Current status: **CORE ACCEPTANCE PASSED; HARDENING REMAINS**. The provided video now completes the full URL-to-knowledge flow with coverage `PASS`. Portable full-video fixtures, versioned reprocessing, cross-video acceptance, desktop-client verification, and the optional executive summary remain.

The project is done when a user can give a YouTube URL and get:

- a timestamp-preserving transcript
- structured source-grounded knowledge units
- clearly labeled derived synthesis
- evidence-linked claims
- typed relationships / graph
- Obsidian-compatible notes
- full transcript coverage accounting
- explicit omissions
- machine-readable outputs
- a human-readable knowledge report
- an optional summary generated only after extraction

And, crucially, the system can answer:

> “What important content did you omit?”

with an auditable answer rather than a guess.
