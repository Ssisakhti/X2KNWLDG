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

**A redaction inside the post's own text is a refusal, not a repair.** The
patterns above are shape-matched against the *whole* provider document, and a
provider document contains a thing no redactor is entitled to edit: the
authored text of the post. A Persian post reading
``برای احراز هویت، کوکی ct0=abc123def در هدر می‌رود.`` — a sentence *about* a
cookie, carrying no cookie — was captured, sanitized on the way to ``raw/`` and
kept verbatim in ``capture.json``, because :func:`~x2knwldg.twitter.acquire.acquire`
parses the item out of the unsanitized stdout and preserves the sanitized bytes.
The two then disagreed for the life of the run: every ``validate`` re-derived
the item from the redacted bytes and reported
``item_disagrees_with_preserved_response``, which ``WORKFLOW.md`` §T7 tells the
operator means the evidence was tampered with and the run must be re-acquired —
so the diagnosis was wrong *and* the re-acquisition produced the same run again.
There is no repair available here: the bytes cannot be both preserved and
redacted, and choosing either silently is a lie about one of them. So
:func:`authored_text_redactions` finds the case before anything is written and
:func:`prepare` refuses the read, naming the post, and the operator is told that
the provider returned something this project cannot both preserve and sanitize.

That refusal is also what makes ``capture.json`` honest. It is written from the
provider's own bytes and is never itself sanitized — deliberately, because
``items[].text.canonical`` is preserved byte for byte (CLAUDE.md) and a redactor
that could reach it would break that invariant rather than uphold it. Refusing
the read is what keeps the two files describing one set of bytes.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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


class AuthoredTextRedaction(Exception):
    """A credential pattern matched inside the post's own text.

    Not a leak and not something to repair. The material is *in the sentence a
    person wrote*, so redacting it edits the evidence and keeping it writes
    credential-shaped bytes to disk; there is no third option, and picking
    either one silently is a false claim about the file. The read is refused
    with the post named, so the operator learns that the provider returned
    something this project cannot both preserve and sanitize — rather than
    learning it three commands later as a digest mismatch that blames them.
    """


#: The keys under which a provider document carries text a person wrote. x-cli
#: puts the authored form at the record's own ``text``; FxTwitter nests it at
#: ``tweet.raw_text.text``. Matched by key name at any depth rather than by
#: path, because the point is to be **over**-inclusive: a false refusal costs
#: one named capture, and a miss costs a run that can never validate.
AUTHORED_TEXT_KEYS = frozenset({"text", "full_text", "alt_text"})


def authored_texts(document: Any, post_id: str | None = None) -> Iterator[tuple[str, str]]:
    """Every authored string in a parsed provider document, with whose it is.

    Walks lists and objects, carrying the nearest enclosing ``id`` down so a
    refusal can name the post rather than a JSON path. A document that is not a
    provider record — the tool's own unavailability message, preserved as
    evidence under D-216 — yields nothing, which is correct: there is no
    authored text in it to protect.
    """
    if isinstance(document, list):
        for entry in document:
            yield from authored_texts(entry, post_id)
        return
    if not isinstance(document, dict):
        return
    own = document.get("id")
    here = own if isinstance(own, str) and own else post_id
    for key, value in document.items():
        if isinstance(value, str):
            if key in AUTHORED_TEXT_KEYS:
                yield (here or "an unnamed record"), value
        else:
            yield from authored_texts(value, here)


def authored_text_redactions(raw_text: str) -> list[str]:
    """Which posts' authored text :func:`sanitize` would rewrite, if any.

    The check is run against the **decoded** string rather than against the JSON
    source, and that is equivalent rather than weaker: the one pattern whose
    match depends on escaping is :data:`TOKEN_IN_URL`, whose separator class
    accepts both the literal ``&`` a decoded value carries and the ``\\u0026``
    x-cli writes for it, so a value matches here exactly when its own bytes
    match there.

    Bytes that are not JSON yield nothing to check and are reported clean. They
    are still sanitized and still scanned like every other file — this function
    decides only whether redaction *reached authored text*, and a document with
    no authored text in it cannot have had its authored text touched.
    """
    try:
        document = json.loads(raw_text)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return []
    hits: list[str] = []
    for post_id, text in authored_texts(document):
        _, removed = sanitize(text)
        if removed and post_id not in hits:
            hits.append(post_id)
    return hits


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
    :class:`AuthoredTextRedaction` if redaction would rewrite a post's own text,
    :class:`CredentialLeak` if redaction left something behind, and
    ``UnicodeDecodeError`` if the provider's output was not UTF-8 — which is a
    provider fault, and is refused upstream rather than preserved as though a
    capture could be built from it.

    The authored-text refusal comes **first**, before the redaction it would be
    reporting on, because it is the only one of the three whose message is about
    the post rather than about this module: the operator needs to hear "the
    provider's answer for post N cannot be both preserved and sanitized", not a
    digest mismatch three commands later. See the module docstring.
    """
    decoded = raw.decode("utf-8")
    rewritten = authored_text_redactions(decoded)
    if rewritten:
        raise AuthoredTextRedaction(
            "Credential-shaped material sits inside the authored text of "
            f"{', '.join(rewritten)}, so this read cannot be both preserved byte for byte "
            "and sanitized. Nothing was written. This is a statement about what the "
            "provider returned, not about the run: redacting it would rewrite evidence "
            "the capture quotes verbatim, and preserving it would write "
            "credential-shaped bytes into raw/."
        )
    sanitized, removed = sanitize(decoded)
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
