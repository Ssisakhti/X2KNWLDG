# Upstream scripts (unmaintained)

These files come from `velmighty/youtube-to-knowledge`, the project X2KNWLDG
extends. They are kept for attribution and history — see
[`THIRD_PARTY_NOTICES.md`](../../THIRD_PARTY_NOTICES.md) — and are **not** part of
the `x2knwldg` package: nothing under `src/x2knwldg/` imports them, and `pip
install` does not ship them.

They live here rather than in `src/` so that `src/` contains the package and
nothing else. Previously they sat beside it and were importable only because an
editable install happened to put `src/` on `sys.path`.

## Do not run the Whisper scripts

`transcribe.py`, `transcribe_whisper.py`, `transcribe_whisperx.py`, and
`requirements-whisperx.txt` contradict a standing project constraint:
**never install or invoke Whisper or WhisperX** (`CLAUDE.md`, `AGENTS.md`,
`WORKFLOW.md`). When native captions are unavailable, ask for a timestamped
`SRT`, `VTT`, or `JSON` file instead. The files are retained as upstream history
only.

## Still covered by tests

`generate_video_db.py`, `obsidian_exporter.py`, and `graph_extractor.py` have
tests in `tests/`, which reach them through the `pythonpath` entry in
`pyproject.toml`. Note that `obsidian_exporter.py` is *not* what the pipeline
uses — the live export is `artifacts._export_obsidian`.
