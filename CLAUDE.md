# X2KNWLDG instructions for Claude

This project is a model-neutral extension of `velmighty/youtube-to-knowledge`.

Read and follow `WORKFLOW.md`. The canonical inputs and outputs under `output/<video-id>/` are the source of truth.

Important constraints:

- Do not summarize first.
- Do not install or run Whisper or WhisperX.
- If native captions are unavailable, ask for a timestamped `SRT`, `VTT`, or `JSON` file.
- Preserve raw transcript files and all timing metadata.
- Separate `source` knowledge from `derived` synthesis.
- Use the prompts in `prompts/` in numeric order.
- Run coverage repair no more than three total audit attempts.
- Apply the final bundle through the validator before generating final artifacts.
- Never claim completion unless validation and coverage both report `PASS`.

