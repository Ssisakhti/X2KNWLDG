# X2KNWLDG agent instructions

Read and follow `WORKFLOW.md` for every acquisition, ingestion, extraction,
validation, or finalization task. Canonical files under `output/<run-id>/` are the
source of truth; do not infer support from roadmap text.

## Supported source paths

- **YouTube:** prefer native captions. Otherwise request `SRT`, `VTT`, timestamped
  `JSON`, or timestamped `TXT/MD` from the user.
- **X/Twitter:** use the `capture` CLI path for public posts and same-author
  self-threads. For a thread, request its last post. Preserve authored text exactly;
  provenance is a post id plus an exact character span.
- **Medium, arbitrary websites, books, PDF, and EPUB:** not implemented. Do not claim
  they were ingested, adapt them as YouTube, or invent an ad hoc canonical format.

## Non-negotiable evidence rules

- Extract before summarizing.
- Never invoke, install, or silently fall back to Whisper or WhisperX.
- Never accept untimed plain text as strict YouTube provenance.
- Treat every file under `output/<run-id>/raw/` as immutable evidence.
- For YouTube, do not quote or extract from cleaned non-speech cues, but retain their
  timing when calculating duration and coverage.
- For X/Twitter, never normalize `items[].text.canonical`, expand `t.co` inside that
  text, substitute seconds for character spans, or treat a derived unit as evidence.
- Keep source-grounded knowledge separate from derived synthesis.
- Never invent timestamps, character spans, excerpts, quotes, evidence, coverage,
  source completeness, or support for a source type.

## Permanent output-language policy

- Write narrative knowledge in Persian: `content`, `normalized_statement`, summaries,
  analysis, `derivation_note`, and human-readable coverage notes.
- Use Persian technical terminology, adding the English term in parentheses when it
  helps precision or recognition.
- Keep `evidence_excerpt` verbatim in the source language; never translate or normalize it.
- Keep source titles and acquisition metadata in their original form.
- Do not translate schema keys, IDs, enum values, relation types, omission codes, or statuses.

## Required completion discipline

- Use the medium-specific prompt sequence in `WORKFLOW.md` and keep intermediate work
  under `output/<run-id>/work/`.
- Run no more than three total coverage-audit attempts.
- Apply model output through `apply-bundle`; do not write canonical extraction files
  around the gate.
- Run the validators before claiming success.
- Completion requires exit code `0`, with validation and coverage both `PASS`.
- `PARTIAL` and `FAIL` are valid reported outcomes. Never coerce either to `PASS`.
- Use the shared canonical files and commands so the result remains portable between
  Codex, Claude, the CLI, the local UI, and an Obsidian vault.

## Output boundaries

- Do not overwrite an existing run or mutate preserved raw evidence.
- Keep acquisition facts in canonical capture/metadata files and model-derived content
  in the extraction outputs.
- `finalize` may generate `report.md`, `graph.json`, the cumulative library, and the
  run-local `vault/`. Obsidian compatibility means Markdown, YAML frontmatter, and
  wikilinks; it does not authorize editing a user's separate vault.
- The local UI and API are read-only. Do not add a write path as an ingestion shortcut.
