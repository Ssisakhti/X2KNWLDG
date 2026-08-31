# X2KNWLDG

X2KNWLDG turns timestamped YouTube transcripts into auditable, reusable knowledge. It extracts structured knowledge first and only summarizes later.

The project is based on `velmighty/youtube-to-knowledge`, with a new canonical transcript, knowledge-unit, provenance, validation, and coverage layer.

## Current behavior

- Uses native YouTube captions when available.
- Accepts user-provided `SRT`, `VTT`, timestamped `JSON`, and timestamped `TXT/MD`.
- Preserves the raw transcript, exact timing, source, and transcript hash.
- Never falls back to Whisper or WhisperX.
- Rejects plain transcripts without timestamps in strict mode.
- Produces canonical JSON, Markdown, graph, validation, coverage, and Obsidian artifacts.
- Can be driven by ChatGPT/Codex, Claude, the small CLI, or the optional MCP server.

## Everyday use

You do not need to type commands when using ChatGPT/Codex or Claude. Give the app this project folder, attach or place a transcript, and ask it to follow `WORKFLOW.md`.

If you do use the command line:

```bash
python -m venv .venv
.venv/bin/pip install -e '.[youtube]'

.venv/bin/x2knwldg process "https://www.youtube.com/watch?v=VIDEO_ID"
```

When native captions are unavailable, the command creates `inbox/<video-id>/README.md`. Put a transcript file there, then import it:

```bash
.venv/bin/x2knwldg import-transcript inbox/<video-id>/transcript.vtt \
  --video-id <video-id> \
  --video-url "https://www.youtube.com/watch?v=<video-id>"
```

Plain text is accepted only in this form:

```text
[00:00:00 - 00:00:07] First timestamped caption.
[00:00:07 - 00:00:15] Second timestamped caption.
```

## Canonical outputs

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

Existing output is never silently overwritten.

## Extraction workflow

The desktop agent follows the model-neutral passes in `WORKFLOW.md` and `prompts/`. It then applies the validated bundle and generates final artifacts:

```bash
.venv/bin/x2knwldg apply-bundle output/<video-id> extraction_bundle.json
.venv/bin/x2knwldg finalize output/<video-id>
```

The build is complete for a video only when both validation and coverage report `PASS`.

## ChatGPT/Codex and Claude compatibility

The canonical data does not depend on either vendor. Codex can operate the local project and run the CLI directly. Claude Desktop can use the optional MCP server.

Install the optional MCP adapter:

```bash
.venv/bin/pip install -e '.[mcp]'
```

Then configure the desktop client to launch this command from the project directory:

```text
/absolute/path/to/X2KNWLDG/.venv/bin/x2knwldg-mcp
```

Set `X2KNWLDG_PROJECT_ROOT` to the absolute project directory in the MCP server environment.

For this checkout, a ready-to-copy Claude Desktop configuration is available at `config/claude_desktop_config.local.json`. Copy its `x2knwldg` entry into Claude Desktop's MCP configuration and restart Claude Desktop.

## Tests

Core tests require only Python's standard library:

```bash
PYTHONPATH=src python -m unittest tests.test_core_pipeline -v
```

Legacy graph tests require the `legacy` optional dependencies.

## Whisper status

The upstream project contained Whisper and WhisperX scripts. They are retained only as upstream legacy code and are not installed, invoked, or used by the X2KNWLDG workflow.
