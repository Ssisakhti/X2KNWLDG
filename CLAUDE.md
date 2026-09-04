# X2KNWLDG instructions for Claude

X2KNWLDG is a model-neutral, evidence-first knowledge pipeline derived from
`velmighty/youtube-to-knowledge`. Read and follow `WORKFLOW.md` for every acquisition,
ingestion, extraction, validation, or finalization task. Canonical files under
`output/<run-id>/` are the source of truth.

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
- Keep source-grounded units separate from derived synthesis.
- Never invent timestamps, spans, excerpts, quotes, evidence, coverage, completeness,
  or source support.

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

## Tool boundary

The optional MCP server exposes the current YouTube-oriented workflow and read/search
tools. Use the local CLI for the implemented X/Twitter capture path. Do not reinterpret
missing MCP functionality as missing canonical evidence, and do not invent a tool call
for a source the project does not support.
