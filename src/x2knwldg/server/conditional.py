"""Validators and the conditional comparisons RFC 9110 actually defines.

Two routes revalidate: ``/api/openapi.json``, which has served an ``ETag`` since
D-084, and ``/api/media/{artifact_id}``, which had no validator of any kind. The
comparisons live here rather than in either of them because they are *rules*,
not code — "``W/"x"`` and ``"x"`` are the same representation for
``If-None-Match`` and different ones for ``If-Range``" is a sentence from the
specification, and a second copy of it is the copy that gets the weak/strong
distinction backwards.

D-101 is the standing reason: the project keeps one statement of a rule and
imports it. This module is stdlib-only and imports nothing from the app, so
``routes/media.py`` can use it without the import cycle that reaching into
``app.py`` would create.

What was wrong before
---------------------

``app.frozen_spec`` compared ``If-None-Match`` with ``==`` against the strong
tag. Measured against a 71,186-byte document:

* ``If-None-Match: "a8dd…"``    -> ``304``
* ``If-None-Match: W/"a8dd…"``  -> ``200``, the whole document
* ``If-None-Match: "a8dd…", "x"`` -> ``200``
* ``If-None-Match: *``          -> ``200``

RFC 9110 §13.1.2 requires the **weak** comparison function for
``If-None-Match``, defines the field as a *list*, and gives ``*`` the meaning
"any current representation". Any cache that stored the tag as weak — which a
cache is free to do — or any client that sent two tags re-downloaded the whole
document on every poll: exactly the cost the ``ETag`` was added to remove.

``routes/media.py`` had no ``ETag``, ``Last-Modified``, ``Cache-Control`` or
``If-Range`` at all, so every ``<video>`` seek and every re-open of the Reader
re-read the artifact in full and a ``304`` was not expressible.
"""

from __future__ import annotations

import hashlib
import os
from email.utils import formatdate, parsedate_to_datetime


def entity_tag(stat: os.stat_result) -> str:
    """A **strong** entity tag for the file *stat* describes, quoted and ready to send.

    Derived from ``(st_dev, st_ino, st_size, st_mtime_ns)`` and hashed. Each
    part earns its place:

    * ``st_size`` and ``st_mtime_ns`` are the usual pair, and on their own they
      are not enough. Some filesystems report ``st_mtime_ns`` at one-second
      resolution, so a canonical file rewritten inside the same second at the
      same length would keep its tag — and a client would splice new bytes onto
      a cached range. That is precisely the failure a *strong* validator is
      defined to exclude, and ``If-Range`` accepts nothing weaker (§13.1.5).
    * ``st_ino`` closes it: this project writes canonical files by atomic
      replace (D-170), and a replace installs a **new inode**. A same-size,
      same-second rewrite therefore still changes the tag.
    * ``st_dev`` keeps two inodes of the same number on different filesystems
      from colliding.

    Hashed rather than concatenated, so the header carries no fact about the
    host filesystem — ADR 0003 forbids leaking layout, and an inode number is
    such a fact even though it is not a path.
    """
    material = f"{stat.st_dev}:{stat.st_ino}:{stat.st_size}:{stat.st_mtime_ns}"
    digest = hashlib.blake2b(material.encode("ascii"), digest_size=16).hexdigest()
    return f'"{digest}"'


def http_date(timestamp: float) -> str:
    """*timestamp* as an IMF-fixdate, which is the only format a server may send.

    One-second resolution, which is why this is a *supplementary* validator:
    :func:`entity_tag` is the one ``If-Range`` is checked against.
    """
    return formatdate(timestamp, usegmt=True)


def _tags(header: str) -> list[str]:
    """The entity tags of a list-valued precondition header, in order.

    Split on commas rather than parsed: an entity tag is a quoted string, and
    the only characters the grammar allows inside one are ``etagc``, which
    excludes both the comma and the quote. So no legal tag can contain a
    separator, and a splitter is a parser here.
    """
    return [candidate.strip() for candidate in header.split(",") if candidate.strip()]


def _weak_equal(candidate: str, etag: str) -> bool:
    """The weak comparison function (§13.1.2): opaque tags equal, prefixes ignored."""
    return _opaque(candidate) == _opaque(etag)


def _opaque(tag: str) -> str:
    return tag[2:].strip() if tag.startswith("W/") else tag


def if_none_match(header: str | None, etag: str) -> bool:
    """Whether *header* says the client already holds this representation.

    ``True`` means the precondition evaluated to false and the answer is
    ``304`` — which is the direction the RFC states it in and the direction that
    reads backwards in code, so it is named for what a caller wants to know.

    Weak comparison, a list, and ``*``: all three are §13.1.2, and all three
    were missing.
    """
    if not header:
        return False
    return any(
        candidate == "*" or _weak_equal(candidate, etag) for candidate in _tags(header)
    )


def if_modified_since(header: str | None, mtime: float) -> bool:
    """Whether *header* says the client's copy is still current.

    Evaluated only when there is no ``If-None-Match`` (§13.2.2 gives the entity
    tag precedence), and only to a second, because that is all an HTTP-date
    carries. An unparseable date is ignored rather than refused: the RFC says a
    recipient that cannot understand a date treats the field as absent, and a
    ``400`` here would refuse a request the client is entitled to make.
    """
    if not header:
        return False
    try:
        since = parsedate_to_datetime(header)
    except (TypeError, ValueError):
        return False
    if since is None or since.tzinfo is None:  # pragma: no cover - defensive
        return False
    return int(mtime) <= int(since.timestamp())


def if_range_matches(header: str | None, etag: str, last_modified: str) -> bool:
    """Whether a ``Range`` guarded by *header* may still be applied (§13.1.5).

    ``True`` when there is no ``If-Range`` at all, because then the range is
    unconditional. When there is one and it does not match, the range is
    **ignored** — the whole representation is sent with ``200`` — rather than
    refused: the client asked for "this range of the thing I already have", and
    the honest answer to a changed thing is all of it, not a ``416``.

    Strong comparison for a tag, exact equality for a date. Both are the
    specification's: a weak validator says two representations are equivalent,
    not identical, and splicing a byte range onto an equivalent-but-different
    representation is how a cache builds a file that never existed.
    """
    if not header:
        return True
    candidate = header.strip()
    if candidate.startswith("W/"):
        return False
    if candidate.startswith('"'):
        return candidate == etag
    return candidate == last_modified
