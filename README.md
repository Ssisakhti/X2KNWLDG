# X2KNWLDG

X2KNWLDG turns timestamped YouTube transcripts into auditable, reusable knowledge. It extracts structured knowledge first and only summarizes later.

## Origin and attribution

X2KNWLDG is an independent derivative of
[velmighty/youtube-to-knowledge](https://github.com/velmighty/youtube-to-knowledge).
It retains and modifies portions of the original MIT-licensed source, and adds
a canonical transcript, knowledge-unit, provenance, validation, and coverage
layer. X2KNWLDG is not affiliated with or endorsed by the upstream author.

The upstream copyright and MIT permission notice are preserved in
[`LICENSE`](LICENSE). See [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)
for provenance and attribution details.

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

When native captions are unavailable, the command creates `inbox/<video-id>/README.md` and exits **5** (`TRANSCRIPT_REQUIRED`) — its own code, so a wrapper can tell "this video needs a transcript from you" from a broken install. Put a transcript file there, then import it:

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

## Exit codes

Every command returns one of these. They are the only thing a shell or a CI job reads, so
they are the contract: **completion may be claimed only on `0`.**

| Code | Name | Meaning |
|---|---|---|
| `0` | `PASS` | The command succeeded. Any run it validated passed validation **and** coverage |
| `1` | `ERROR` | The command refused or failed — a bad argument, a missing or corrupt canonical file, an id that is not an id, a run directory already in use, a missing optional extra. A JSON object with `"status": "ERROR"` goes to stderr |
| `2` | usage error | Reserved by `argparse` for an unknown flag or a missing argument. Nothing semantic uses it |
| `3` | `PARTIAL` | Every validator passed and coverage is honestly incomplete (`WORKFLOW.md` §4). A real deliverable — and **not** a pass |
| `4` | `FAIL` | The run validated as failing |
| `5` | `TRANSCRIPT_REQUIRED` | No native captions. `inbox/<video-id>/` now holds instructions; supply a timestamped transcript. Whisper is never a fallback |
| `6` | `UI_NOT_BUILT` | `x2knwldg ui` accepted its arguments and the server is ready, but `web/dist` holds no built frontend. Run `cd web && npm ci && npm run build` |
| `7` | `PROVIDER_UNAVAILABLE` | An acquisition provider is not installed, or the binary at its pinned path is not the pinned build. Nothing was run and nothing was written |
| `8` | `PROVIDER_UNREACHABLE` | The read could not be completed and **nothing was learned** — the network failed, the request timed out, or it was rate limited. The stderr envelope names which; retry later |
| `9` | `PROVIDER_DRIFT` | A provider answered and the answer was unusable. Deliberately not `8`: a network failure must never read as a provider having changed |

`PARTIAL` used to exit `0`, so no check could tell an honestly incomplete run from a passing
one, and the `ui` command's refusal shared `1` with every real error. Splitting them
out is what makes `if x2knwldg finalize ...` a meaningful check: `0` is a pass, `3` and `4`
are verdicts to act on, `1` is something broken, and `5` and `6` are "do this next".

`7`, `8` and `9` are the same argument one layer out, for a command that depends on an external
tool and a network: install-or-re-pin, wait-and-retry, and the provider's output moved. `8` and
`9` are separate codes because a caller that cannot tell them apart will either retry a real
drift forever or blame the provider for the network.

`x2knwldg --help` prints the same table, and `cli.VERDICT_EXIT_CODES` is the single mapping
from a verdict to its code, so `validate`, `apply-bundle`, and `finalize` cannot disagree.

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

A template ships with the repo at [`config/claude_desktop_config.example.json`](config/claude_desktop_config.example.json). Copy it, replace both `/absolute/path/to/X2KNWLDG` placeholders with this checkout's real path, then paste the `x2knwldg` entry into Claude Desktop's MCP configuration and restart Claude Desktop:

```bash
cp config/claude_desktop_config.example.json config/claude_desktop_config.local.json
# then edit config/claude_desktop_config.local.json and set both paths to:
pwd
```

`config/*.local.json` is gitignored on purpose — the filled-in copy holds machine-local
absolute paths and is never committed, so only the `.example.json` exists in a fresh clone.

## Local web UI

A local-first Knowledge Canvas over the canonical outputs. Phase 2 — the **Library**, the
**Reader** and the **Knowledge Map** — is built and served; the board is a later phase. The design
is in [`docs/KNOWLEDGE_CANVAS_PLAN.md`](docs/KNOWLEDGE_CANVAS_PLAN.md) and
[ADR 0001](docs/adr/0001-local-web-ui.md); status and task breakdown are in
[`docs/PROJECT_MANAGEMENT.md`](docs/PROJECT_MANAGEMENT.md).

It is **optional.** The core package stays zero-dependency: nothing below is installed by
`pip install x2knwldg`, and the UI's Python dependencies are imported only by
`x2knwldg.server`.

```bash
.venv/bin/pip install -e '.[ui]'      # fastapi + uvicorn
(cd web && npm ci && npm run build)   # the frontend; without it, ui exits 6 UI_NOT_BUILT

.venv/bin/x2knwldg ui                 # serves on 127.0.0.1 and opens a browser
```

`x2knwldg ui` refuses any non-loopback bind address **before** anything else (ADR 0001
invariant 9), resolves the project root, refreshes the index — incrementally, so an unchanged
project pays a directory walk — then binds, prints the URL it actually reached, and opens a
browser. Nothing else in the CLI builds an index, so this is where one comes from.

| Flag | Meaning |
|---|---|
| `--root` | Project root. Defaults to `$X2KNWLDG_PROJECT_ROOT`, then the working directory |
| `--host` | Loopback address to bind. Only `127.0.0.1`, `::1` and `localhost` are accepted |
| `--port` | Omit to let the OS choose a free one — the URL is printed after the bind, never before |
| `--no-open` | Do not open a browser |

The frontend lives in [`web/`](web/README.md); the TypeScript types for the frozen HTTP
contract are generated into [`schemas/api/v1/`](schemas/api/v1/README.md).

## Tests

Core tests require only Python's standard library:

```bash
PYTHONPATH=src python -m unittest tests.test_core_pipeline -v
```

For the whole suite, install the development extras and run `pytest`:

```bash
.venv/bin/pip install -e '.[dev,legacy]'
.venv/bin/pytest -q
```

`dev` brings pytest and the schema validators; `legacy` brings networkx and pyvis, without
which the `legacy/upstream/` tests skip rather than run.

CI runs the suite on Python **3.10, 3.12, 3.13 and 3.14**, separately proves the core package
installs and passes with **no** extras at all, and installs each of the five declared extras
(`youtube`, `mcp`, `ui`, `legacy`, `dev`) on its own to prove it is still resolvable and
importable. See [`.github/workflows/ci.yml`](.github/workflows/ci.yml).

## Whisper status

The upstream project contained Whisper and WhisperX scripts. They are retained only as upstream legacy code and are not installed, invoked, or used by the X2KNWLDG workflow.
