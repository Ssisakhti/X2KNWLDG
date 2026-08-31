"""Backward-compatible native-caption entry point.

Unlike the upstream script, this wrapper preserves caption timing and never
falls back to Whisper. New integrations should use the ``x2knwldg`` command.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from x2knwldg.pipeline import PipelineError, extract_video_id, prepare_inbox
from x2knwldg.youtube import process_youtube_url


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch native YouTube captions with provenance")
    parser.add_argument("url")
    parser.add_argument("--output", type=Path, default=Path("output"))
    parser.add_argument("--inbox", type=Path, default=Path("inbox"))
    parser.add_argument("--lang", action="append", default=[])
    args = parser.parse_args()
    try:
        run_dir = process_youtube_url(
            args.url, args.output, preferred_languages=args.lang or None
        )
    except PipelineError as exc:
        video_id = extract_video_id(args.url) or "unknown-video"
        inbox = prepare_inbox(args.inbox, video_id, args.url)
        print(f"Error: {exc}", file=sys.stderr)
        print(f"TRANSCRIPT_REQUIRED:{inbox}")
        print("WHISPER_FALLBACK:false")
        return 1
    metadata_path = run_dir / "metadata.json"
    print(f"OUTPUT_DIR:{run_dir}")
    print(f"METADATA_FILE:{metadata_path}")
    print(f"TRANSCRIPT_FILE:{run_dir / 'transcript.json'}")
    print("WHISPER_FALLBACK:false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

