"""Digests of the canonical inputs a source synthesis record was derived from.

``T-251``. Two derived record families state what they were generated from —
``source_knowledge.json`` names three canonical files of its own run, and a
``SourceRelation`` names one digest per endpoint run — and both exist so that a
reader can tell a current account from a stale one. That only works if every
producer and every checker computes the digest the same way, so the rule lives
here rather than being spelled out again in the apply gate, the fixture
generator and the validator (D-158's lesson, one layer up).

**Content only.** ``index.scanner`` already digests a run, and that digest is
deliberately unsuitable here: it covers the whole subtree, folds in mtime and
size as a cheap prefilter, and is truncated to sixteen hex digits. It answers
"has anything under this directory been touched", which is the right question
for an incremental re-index and the wrong one for staleness of a derived
account. A brief goes stale when the knowledge it summarises changes — not when
``report.md`` is regenerated, and not when the run is copied to another machine
and every mtime moves.

**The three files, and only those.** A brief is generated after extraction,
normalization, relationship extraction and the coverage audit, from
``knowledge_units.json``, ``relationships.json`` and ``coverage.json``. Those
are its inputs, so those are what its digests cover. ``metadata.json`` is not:
re-running ``finalize`` rewrites ``extracted_at`` without a single unit
changing, and a brief that went stale on that would cry wolf until nobody read
the warning.

**A missing file is a value, not an error.** A run that has not been extracted
has no ``knowledge_units.json``, and this returns the digest of nothing rather
than raising: the absence is a fact about the run, it is stable, and a synthesis
record generated against it correctly goes stale the moment the file appears.
The alternative — an exception — would make an unextracted run unrepresentable
in a record whose whole job is to describe what it was derived from.

Stdlib only, and read-only: it opens files, hashes them, and returns.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

#: The record model version, matching ``schemas/synthesis/v1/``. The version is
#: the directory there and the constant here, and they move together.
SCHEMA_VERSION = "1.0"

#: The canonical files a source brief is derived from, keyed by the
#: ``generated_from`` field that carries each one's digest. Ordered, because
#: :func:`run_digest` hashes them in this order and a reordering would change
#: every digest in the project for no reason anyone could see.
CANONICAL_INPUTS: tuple[tuple[str, str], ...] = (
    ("knowledge_units_sha256", "knowledge_units.json"),
    ("relationships_sha256", "relationships.json"),
    ("coverage_sha256", "coverage.json"),
)

#: The digest of a file that is not there. ``sha256`` of the empty byte string —
#: a real, stable value rather than a sentinel, so nothing downstream has to
#: special-case it and no reader can mistake it for a hash of some content.
ABSENT_DIGEST = hashlib.sha256(b"").hexdigest()


def file_digest(path: Path) -> str:
    """The SHA-256 of *path*'s bytes, or :data:`ABSENT_DIGEST` when it is absent.

    An unreadable file that *is* there raises. That is the one case where
    silence would be wrong: absence is a fact about the run, but a file that
    exists and cannot be read is damage, and answering "as if it were empty"
    would let a synthesis record be generated against evidence nobody could see.

    The test is ``exists``, not ``is_file``. A *directory* named
    ``knowledge_units.json`` is pathological, and it is present — reading it as
    absence would report the honest digest of a run with no extraction for a run
    whose extraction is unreachable, which are not the same thing. ``open``
    raises for it, which is the correct answer. A broken symlink does not exist
    and is an absence, as it should be.
    """
    if not path.exists():
        return ABSENT_DIGEST
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_input_digests(run_dir: Path) -> dict[str, str]:
    """The ``generated_from`` block of a ``source_knowledge.json`` for *run_dir*."""
    run_dir = Path(run_dir)
    return {field: file_digest(run_dir / name) for field, name in CANONICAL_INPUTS}


#: The canonical filename of a run's readable brief.
BRIEF_FILENAME = "source_knowledge.json"

#: The three states a brief can be in when a reader asks for one, and the
#: vocabulary ``SourceKnowledgeAvailability`` publishes (`T-251`). ``stale`` is
#: its own state rather than an error: the document exists and describes inputs
#: whose digests have since moved, so it is shown with that said out loud rather
#: than withheld or silently trusted.
BRIEF_STATES = ("available", "unavailable", "stale")


def brief_state(run_dir: Path) -> dict[str, Any]:
    """``{"state", "reason", "brief"}`` for *run_dir*'s ``source_knowledge.json``.

    The **read** side of the gate, and deliberately much smaller than it. The
    gate in ``artifacts.apply_source_knowledge`` refuses a document that is not
    fully valid, so anything on disk was valid when it was written; what can
    change afterwards is the run underneath it, and that is the one thing this
    re-checks. Re-running the whole validator here would be a second opinion
    about a document the gate already judged, and the two could disagree.

    ``unavailable`` covers three different absences on purpose — no file, an
    unreadable one, and one that is not an object — because a reader needs the
    same thing from all three: the honest statement that there is no brief to
    show. The *reason* distinguishes them for anyone debugging, and it never
    carries a host path (D-030, D-051), because this string reaches an HTTP
    response body.

    Never raises. A damaged brief must not be able to take down the source it
    belongs to; that source's evidence, units and status are all still readable
    and are the more important thing on the page.
    """
    path = Path(run_dir) / BRIEF_FILENAME
    if not path.exists():
        return {"state": "unavailable", "reason": "no source_knowledge.json", "brief": None}
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {
            "state": "unavailable",
            "reason": f"source_knowledge.json cannot be read ({type(exc).__name__})",
            "brief": None,
        }
    if not isinstance(document, dict):
        return {
            "state": "unavailable",
            "reason": "source_knowledge.json does not hold an object",
            "brief": None,
        }
    recorded = document.get("generated_from")
    current = canonical_input_digests(run_dir)
    if not isinstance(recorded, dict) or any(
        recorded.get(field) != current[field] for field, _ in CANONICAL_INPUTS
    ):
        moved = sorted(
            field
            for field, _ in CANONICAL_INPUTS
            if not isinstance(recorded, dict) or recorded.get(field) != current[field]
        )
        return {
            "state": "stale",
            "reason": (
                "generated from inputs that have since changed: " + ", ".join(moved)
            ),
            "brief": document,
        }
    return {"state": "available", "reason": None, "brief": document}


def run_digest(run_dir: Path) -> str:
    """One digest standing for a run's extracted knowledge, for a ``SourceRelation``.

    A relation names two runs and cannot carry three digests for each without
    saying twice what one number says once, so this folds
    :func:`canonical_input_digests` into a single SHA-256 over the field names
    and their digests in :data:`CANONICAL_INPUTS` order. The field names are in
    the hashed text on purpose: without them, adding a fourth input later would
    produce a digest indistinguishable from one computed over a different three.
    """
    digests = canonical_input_digests(run_dir)
    payload = "\n".join(f"{field}={digests[field]}" for field, _ in CANONICAL_INPUTS)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
