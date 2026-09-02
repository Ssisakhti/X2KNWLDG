# X2KNWLDG Agent Workflow

This workflow is vendor-neutral. ChatGPT/Codex, Claude, or any MCP-capable agent must use the same canonical files and validators.

## 1. Acquire the transcript

Preferred order:

1. Native YouTube captions with timestamps.
2. User-provided `VTT`, `SRT`, or timestamped `JSON`.
3. Timestamped `TXT/MD` using `[HH:MM:SS - HH:MM:SS]` headers.

Whisper and WhisperX are disabled. Never silently fall back to audio transcription.

Run either:

```bash
x2knwldg process "<youtube-url>"
x2knwldg import-transcript "<file>" --video-id "<id>" --video-url "<url>"
```

If native captions are unavailable, `process` creates `inbox/<video-id>/README.md` and exits `5` (`TRANSCRIPT_REQUIRED`). Ask the user to put a timestamped transcript there.

## 2. Inspect canonical inputs

Use only these files as extraction inputs:

- `output/<video-id>/metadata.json`
- `output/<video-id>/transcript.json`
- `output/<video-id>/segments.json`

Some captions in `transcript.json` carry `"non_speech": true` with `"text": ""` — a cue
like `[music]` whose text cleaned away. They keep their timing on purpose, because dropping
them shortens the run's reported duration and the coverage windows with it. Treat them as
data, not as a gap: never quote one, never extract from one, and never leave one out when
counting captions or computing a duration.

The file under `raw/` is immutable evidence. Never edit it.

## 3. Run the model passes

Follow the prompt files in this order:

1. `prompts/01_segment_extraction.md`
2. `prompts/02_normalize_deduplicate.md`
3. `prompts/03_relationships.md`
4. `prompts/04_derived_synthesis.md`
5. `prompts/05_coverage_audit.md`

Do not summarize before these passes finish. Store intermediate results under `output/<video-id>/work/`.

## 4. Coverage repair

When the coverage audit finds missing meaningful content:

1. Create the missing source-grounded units.
2. Normalize and deduplicate again.
3. Re-audit only the affected windows.
4. Stop after three total audit attempts. `MAX_AUDIT_ATTEMPTS` in `src/x2knwldg/constants.py` is the number, and the coverage document must report how many it took: `audit_attempts` is **required**, an integer, and never above the cap. The validator accepts `0` only while the document does not claim `PASS`, which is the honest state of a scaffolded, never-audited run.
5. If important content remains unresolved, use `PARTIAL`, never `PASS`.

## 5. Apply and finalize

Assemble `extraction_bundle.json` using `schemas/extraction_bundle.schema.json`. It has
exactly three required keys, and the schema sets `additionalProperties: false`, so no other
top-level key is accepted:

| Bundle key | Comes from | Note |
|---|---|---|
| `knowledge_units` | passes 1, 2 and 4 | The **bundle** key is `knowledge_units`. The canonical `knowledge_units.json` file writes the same list under `units`; do not carry that spelling into the bundle (D-073) |
| `relationships` | pass 3 | |
| `coverage` | pass 5 | `audit_attempts` is required; `0` is the honest never-audited state and may not accompany a `PASS` (§4.4) |

Then run:

```bash
x2knwldg apply-bundle output/<video-id> extraction_bundle.json
x2knwldg finalize output/<video-id>
```

Completion may be claimed only when validation and coverage both report `PASS` — which is
exactly **exit code `0`**. `PARTIAL` exits `3` and `FAIL` exits `4`: both are real results to
report, and neither is completion. The full table is in
[`README.md` § Exit codes](README.md#exit-codes), and `x2knwldg --help` prints it.

