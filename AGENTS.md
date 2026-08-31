# X2KNWLDG agent instructions

Read and follow `WORKFLOW.md` for every ingestion or extraction task.

- Extract before summarizing.
- Prefer native YouTube captions; otherwise request a timestamped transcript from the user.
- Never invoke, install, or silently fall back to Whisper or WhisperX.
- Never accept untimed plain text as strict provenance.
- Treat files under `output/<video-id>/raw/` as immutable evidence.
- Keep source-grounded and derived knowledge separate.
- Never invent timestamps, quotes, evidence, or coverage.
- Run the validators before claiming success.
- Coverage may be `PARTIAL` or `FAIL`; never force `PASS`.
- Use the canonical files so results remain portable between ChatGPT/Codex and Claude.

