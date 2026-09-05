# X2KNWLDG instructions for Claude

X2KNWLDG is a model-neutral, evidence-first knowledge pipeline derived from
`velmighty/youtube-to-knowledge`. Read and follow `WORKFLOW.md` for every acquisition,
ingestion, extraction, validation, or finalization task. Canonical files under
`output/<run-id>/` are the source of truth; do not infer support from roadmap text.

## Source support

- **YouTube is supported.** Prefer native captions; otherwise ask for `SRT`, `VTT`,
  timestamped `JSON`, or timestamped `TXT/MD`.
- **Public X/Twitter posts and same-author self-threads are supported through the
  CLI.** For a thread, ask for its last post. The current MCP tools remain
  YouTube-oriented; do not pretend they expose the X acquisition path.
- **Medium, arbitrary websites, books, PDF, and EPUB are planned, not implemented.**
  Do not create a new canonical shape ad hoc or route them through the YouTube path.

## Evidence and extraction rules

- Extract before summarizing.
- Never install, invoke, or silently fall back to Whisper or WhisperX.
- Never accept untimed plain text as strict YouTube provenance.
- Treat every file under `output/<run-id>/raw/` as immutable evidence.
- Preserve YouTube timing. Retain cleaned non-speech cues for duration and coverage,
  but never quote or extract knowledge from them.
- Preserve X/Twitter `items[].text.canonical` byte for byte. A source claim must cite
  its actual post id and an exact character span whose excerpt re-slices verbatim.
  Never normalize that text, never expand a `t.co` link inside it — the expansion is not
  in the authored text and pairing the two is not safe on this route (D-218) — and never
  substitute seconds for a character span.
- Keep source-grounded units separate from derived synthesis, and never treat a derived
  unit as evidence.
- Never invent timestamps, spans, excerpts, quotes, evidence, coverage, completeness,
  or source support.

## Permanent output-language policy

- Write narrative knowledge in Persian: `content`, `normalized_statement`, summaries,
  analysis, `derivation_note`, and human-readable coverage notes.
- Use Persian technical terminology, adding the English term in parentheses when it
  helps precision or recognition.
- Keep `evidence_excerpt` verbatim in the source language; never translate or normalize it.
- Keep source titles and acquisition metadata in their original form.
- Do not translate schema keys, IDs, enum values, relation types, omission codes, or statuses.
- Two of these fields are machine-checked and the rest are not: `validators` refuses a
  source brief's `content` and a source relation's `rationale` when they carry no
  Perso-Arabic character, and checks nothing else on this list. Hold to the policy anyway —
  the primary extraction output is the part no exit code covers. `WORKFLOW.md` states the
  boundary in full.

## Workflow and completion

- Use the medium-specific prompt sequence in `WORKFLOW.md`; store intermediate work in
  `output/<run-id>/work/`.
- Run no more than three total coverage-audit attempts.
- Submit the final extraction through `apply-bundle`; do not bypass its validation gate.
- Run validation before finalization and before reporting success.
- Claim completion only on exit code `0`, when validation and coverage both report
  `PASS`. Report `PARTIAL` and `FAIL` honestly.
- Keep the canonical format portable between Claude, Codex, the CLI, the local UI, and
  Obsidian. Obsidian compatibility does not authorize writing into a separate personal
  vault unless the user explicitly asks.

## Output boundaries

- Do not overwrite an existing run or mutate preserved raw evidence.
- Keep acquisition facts in the canonical capture and metadata files, and model-derived
  content in the extraction outputs. One file does not hold both.
- `finalize` may generate `report.md`, `graph.json`, the cumulative library, and the
  run-local `vault/` — and nothing else. Obsidian compatibility means Markdown, YAML
  frontmatter, and wikilinks, which is a file format, not a synchronization step.
- **The local UI and API are read-only. Do not add a write path as an ingestion
  shortcut.**

## Tool boundary

The optional MCP server exposes the current YouTube-oriented workflow and read/search
tools. Use the local CLI for the implemented X/Twitter capture path. Do not reinterpret
missing MCP functionality as missing canonical evidence, and do not invent a tool call
for a source the project does not support.
