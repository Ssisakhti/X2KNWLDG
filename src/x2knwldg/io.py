from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any


class JsonReadError(ValueError):
    """A JSON file that could not be read as a JSON document.

    One error type for every way a read can fail — absent, unreadable, malformed,
    or carrying a constant no other language's JSON parser accepts — so that
    every caller has one thing to catch and one decision to make. There used to
    be three readers for this one job (``io.read_json``, ``artifacts._read`` and
    an inline ``json.loads`` in ``library.py``) and three different failures for
    the same damaged file: a ``PipelineError``, a bare ``FileNotFoundError``, and
    an uncaught traceback out of the middle of a library rebuild.

    A ``ValueError`` subclass because that is what ``json`` itself raises, so
    existing ``except ValueError`` callers keep working.
    """


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _reject_non_finite(constant: str) -> Any:
    """Refuse ``NaN``/``Infinity``: canonical JSON must be readable everywhere."""
    raise ValueError(f"Canonical JSON must not contain {constant}")


def dumps_json(value: Any) -> str:
    """Serialise *value* as canonical JSON text, exactly as it is written to disk.

    Separated from :func:`write_json` so a caller writing several files together
    can serialise all of them *before* touching any of them: a value that cannot
    be represented then fails with nothing on disk changed, rather than half way
    through a sequence of writes.
    """
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def write_bytes(path: Path, data: bytes) -> None:
    """Write *data* to *path* atomically and without leaving a stray temp file.

    The replace is atomic per file: a reader sees either the old file or the new
    one, never a half-written one. Atomicity *across* files is a separate problem
    and belongs to the caller — see ``artifacts._write_group``.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with NamedTemporaryFile("wb", dir=path.parent, delete=False, suffix=".tmp") as handle:
            temporary = Path(handle.name)
            handle.write(data)
        os.replace(temporary, path)
    except BaseException:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


def write_text(path: Path, text: str) -> None:
    """Write *text* to *path* as UTF-8, atomically. See :func:`write_bytes`.

    Encoded here rather than written through a text-mode handle so the bytes on
    disk are the bytes given: a canonical file ends every line with ``\\n`` on
    every platform, not with whatever the host's line separator happens to be.
    """
    write_bytes(path, text.encode("utf-8"))


def write_json(path: Path, value: Any) -> None:
    """Write ``value`` as canonical JSON, atomically and without a stray temp file.

    ``allow_nan=False`` keeps NaN/Infinity — which no other language's JSON
    parser accepts — out of the canonical outputs, and a failed write removes its
    own ``.tmp`` instead of leaving it in the output directory.
    """
    write_text(path, dumps_json(value))


def read_json(path: Path) -> Any:
    """The JSON document at *path*, or a :class:`JsonReadError` naming what is wrong.

    The single strict reader. Use it wherever a missing or damaged file means the
    caller must stop; use :func:`read_json_or_reason` wherever it means the caller
    must carry on and report the damage.
    """
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle, parse_constant=_reject_non_finite)
    except FileNotFoundError as exc:
        raise JsonReadError(f"Missing JSON file: {path}") from exc
    except IsADirectoryError as exc:
        raise JsonReadError(f"Not a JSON file: {path}") from exc
    except OSError as exc:
        raise JsonReadError(f"Unreadable JSON file: {path} ({exc})") from exc
    except UnicodeDecodeError as exc:
        raise JsonReadError(f"JSON file is not valid UTF-8: {path} ({exc})") from exc
    except ValueError as exc:
        raise JsonReadError(f"Malformed JSON in {path} ({exc})") from exc


def read_json_or_reason(path: Path) -> tuple[Any, str | None]:
    """``(document, None)``, or ``(None, reason)`` when *path* cannot be read.

    The tolerant half of :func:`read_json`, for the callers whose job is to keep
    going: a damaged run must still be indexable, and what is wrong with it must
    still be *stated* rather than silently dropped. The reason is returned rather
    than logged so the caller can put it somewhere a reader will find it.
    """
    try:
        return read_json(path), None
    except JsonReadError as exc:
        return None, str(exc)


def format_timestamp(seconds: float) -> str:
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def timestamp_url(video_id: str, seconds: float) -> str:
    return f"https://www.youtube.com/watch?v={video_id}&t={max(0, int(seconds))}s"
