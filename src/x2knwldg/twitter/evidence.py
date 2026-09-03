"""Raw acquisition evidence: preserved bytes, two digests, and a redaction record.

``output/<id>/raw/`` is immutable evidence (AGENTS.md, ADR 0007). This module is
the only thing in the acquisition path that writes there, and it writes each
file **once**: re-acquiring the same post either finds byte-identical evidence
already on disk and reuses it, or refuses. A provider that could overwrite an
earlier capture's evidence would make every digest in that capture a claim about
bytes that are no longer there.

Two digests per file, because the schema asks for both and for a reason
(``sha256_raw`` beside ``sha256_sanitized``): the raw digest is of what the
acquisition actually received, the sanitized digest is of what is on disk, and
keeping them apart is what stops a redacted body being passed off as the
original bytes. When redaction removed nothing the two are equal, which is
itself a checkable claim rather than a coincidence.

The patterns come from the ``T-222`` harness, and one of them is here because it
was wrong first. The syndication surface's ``token`` parameter survived the
first version of the stripper: x-cli's JSON escapes the ampersand as ``\\u0026``,
so a ``[?&]``-only separator class walked straight past it. That near-miss is
the reason :func:`scan_for_credentials` runs *after* :func:`sanitize` and is a
hard stop rather than a warning — a redactor is not evidence that redaction
worked.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

#: Anything matching these must never reach a preserved file. The guest token is
#: not an account credential — X mints it anonymously against no account — but it
#: is minted material, so it is redacted rather than argued about.
CREDENTIAL_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r'"guest_token"\s*:\s*"[^"]+"'), '"guest_token":"<REDACTED>"'),
    (re.compile(r"(auth_token|ct0|kdt|twid)=[^&\s\"';]+"), r"\1=<REDACTED>"),
    (re.compile(r"[Bb]earer\s+[A-Za-z0-9%_\-.]{20,}"), "Bearer <REDACTED>"),
]

#: The syndication request token. Not a credential — it is derived from the post
#: id and x-cli recomputes it — but no preserved file carries a request token of
#: any kind. The separator class must accept the escaped ampersand; see the
#: module docstring.
TOKEN_IN_URL = re.compile(r"((?:[?&]|\\u0026)token=)[^&\"'\s\\]+")

TOKEN_LABEL = "syndication request token in url"


class EvidenceConflict(Exception):
    """Preserved bytes already exist at this path and differ from these.

    Never repaired, because which of the two readings of the same post is the
    real evidence is not this module's to decide, and overwriting is exactly the
    behaviour that would lose the earlier one.
    """


class CredentialLeak(Exception):
    """Sanitization ran and something credential-shaped survived it.

    A hard stop: nothing is written, no capture is produced. The alternative is
    a preserved file that a later scan finds material in, which is the one
    failure ADR 0007 invariant 1 exists to make impossible.
    """


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sanitize(text: str) -> tuple[str, list[str]]:
    """Redact credential-shaped material. Returns the text and what was hit."""
    removed: list[str] = []
    for pattern, replacement in CREDENTIAL_PATTERNS:
        text, hits = pattern.subn(replacement, text)
        if hits:
            removed.append(f"{pattern.pattern} x{hits}")
    text, hits = TOKEN_IN_URL.subn(r"\1<STRIPPED>", text)
    if hits:
        removed.append(f"{TOKEN_LABEL} x{hits}")
    return text, removed


def scan_for_credentials(text: str) -> list[str]:
    """The second pass. Anything this returns is a refusal, not a warning."""
    hits: list[str] = []
    for pattern, _ in CREDENTIAL_PATTERNS:
        for match in pattern.finditer(text):
            if "<REDACTED>" not in match.group(0):
                hits.append(match.group(0)[:40])
    for match in TOKEN_IN_URL.finditer(text):
        if "<STRIPPED>" not in match.group(0):
            hits.append(match.group(0)[:40])
    return hits


@dataclass(frozen=True)
class PreservedEvidence:
    """One file's worth of evidence: where it goes, its bytes, and its record.

    Nothing is on disk yet. The text is handed to :func:`x2knwldg.io.write_group`
    with the capture itself, so a run either lands whole or leaves the directory
    exactly as it was — the same all-or-nothing rule ``import_transcript`` uses
    for the nine files that are a YouTube run (D-090).
    """

    path: Path
    text: str
    record: dict[str, object]


def prepare(
    *,
    raw: bytes,
    destination: Path,
    relative_to: Path,
    route: str,
) -> PreservedEvidence:
    """Sanitize *raw*, and build the contract's ``raw_evidence`` entry for it.

    *destination* is the absolute path the bytes will occupy; *relative_to* is
    the directory the recorded path is expressed against — the output root's
    parent, which in the standard layout is the project root. One rule, so a
    validator resolving the path later does not need a second one.

    Raises :class:`EvidenceConflict` if different bytes already occupy the path,
    :class:`CredentialLeak` if redaction left something behind, and
    ``UnicodeDecodeError`` if the provider's output was not UTF-8 — which is a
    provider fault, and is refused upstream rather than preserved as though a
    capture could be built from it.
    """
    sanitized, removed = sanitize(raw.decode("utf-8"))
    leaks = scan_for_credentials(sanitized)
    if leaks:
        raise CredentialLeak(
            "Sanitization left credential-shaped material in the acquisition output, so "
            f"nothing was written: {leaks}"
        )

    # Written exactly as sanitized, with nothing appended or trimmed. That is
    # what makes the clean case checkable: redaction removed nothing if and only
    # if the two digests are equal, and ``sanitization_removed`` has to agree.
    text = sanitized
    if destination.exists():
        existing = destination.read_text(encoding="utf-8")
        if existing != text:
            raise EvidenceConflict(
                f"{destination} already holds different preserved bytes. Raw evidence is "
                "immutable: move or version the existing run rather than overwriting it."
            )

    relative = destination.relative_to(relative_to)
    return PreservedEvidence(
        path=destination,
        text=text,
        record={
            "route": route,
            "path": relative.as_posix(),
            # The digest of what arrived, and of what is on disk. Equal when
            # redaction removed nothing, and that equality is a claim the
            # `sanitization_removed` list has to agree with.
            "sha256_raw": sha256_bytes(raw),
            "sha256_sanitized": sha256_bytes(text.encode("utf-8")),
            "sanitization_removed": removed,
        },
    )
