Process a YouTube URL or timestamped transcript using the vendor-neutral X2KNWLDG workflow.

**Arguments:** $ARGUMENTS

1. Read `WORKFLOW.md` completely.
2. If the argument is a URL, run `x2knwldg process "<url>"` — **always double-quoted.**
   A real watch URL carries `&list=...&index=...`; unquoted, the shell splits at the first `&`,
   backgrounds a truncated command, and tries to run the rest as further commands.
3. If native captions are unavailable, report the created inbox path and ask the user for `SRT`, `VTT`, or timestamped `JSON`. Do not invoke Whisper or WhisperX.
4. If the argument is a file, import it with its video ID and URL, quoting the path and the URL
   for the same reason: `x2knwldg import-transcript "<file>" --video-id "<id>" --video-url "<url>"`.
5. Run the five prompt passes in `prompts/`.
6. Apply the extraction bundle, finalize outputs, and run validation.
7. Report `PASS`, `PARTIAL`, or `FAIL` exactly as produced. Never force a pass.

