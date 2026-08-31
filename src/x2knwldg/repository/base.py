"""The indexer ↔ API seam (``T-007``).

Track A builds the SQLite index (``T-101``–``T-104``). Track B serves the frozen
HTTP contract in ``schemas/api/v1/openapi.json`` (``T-105``–``T-108``). They meet
here and nowhere else: Track B calls :class:`IndexRepository` and never opens a
database, a canonical file, or a run directory; Track A implements it and never
imports a route.

Six rules shape the seam, and each is enforced in this module rather than left
to an implementation:

**The repository owes pages of v1 records, not rows.** Every list method returns
a :class:`Page` of the plain dicts ``IndexRecords.by_model()`` already produces.
A row type of its own would be a third vocabulary for the same fact (D-026),
and there are already two identifier vocabularies to keep honest (risk R12).

**The cursor encoding belongs to the repository alone.** The contract declares
it opaque, so the API passes it through unparsed and the frontend cannot depend
on it. :func:`encode_cursor` and :func:`decode_cursor` are that encoding, and
:func:`page_from_window` is the arithmetic around it — shared so that two
implementations page identically, which is what lets ``T-104`` compare them page
for page. A token is authenticated with a key random to this process: the
position it names reaches real work, so it is proved to be one this repository
issued rather than merely parsed.

**The order every page walks is total.** :func:`order_key` appends a content
digest to the id in ``ORDER_KEYS``, and :func:`check_index_integrity` refuses a
record set in which an id repeats or an edge names an endpoint no entity record
has. A tie at a page boundary deletes a record from the paged output while
``total`` goes on counting it, and a dangling edge makes the graph and the
relations list disagree about one fact; neither is something a page can be
honest about after the fact.

**A cursor is bound to the query that issued it.** Presenting one against
different filters is refused, not silently re-anchored onto a different
collection.

**Absence is a return value; malformation is an exception.** A well-formed id
naming nothing returns ``None`` or an empty page — the API renders that as
``404``. An id that fails :mod:`x2knwldg.ids` raises :class:`InvalidId` before
anything is read, which is D-020 over HTTP: refused as malformed, never dressed
up as absence.

**The repository can say it cannot answer.** :meth:`IndexRepository.status`
always answers, with a state of ``absent``, ``building``, ``ready``, or
``error``; every other method raises :class:`IndexUnavailable` unless the state
is ``ready``. An empty index and an unbuilt one are different answers, and the
UI must be able to tell them apart (D-030).

The repository is a **reader**. It never writes a canonical file, never
recomputes a status, and never invents a value the canonical files do not carry.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Protocol, Sequence, runtime_checkable

from .. import ids
from ..adapters import RUN_STATUSES, UNKNOWN_STATUS
from ..constants import KNOWLEDGE_KINDS

#: Page size bounds, copied from ``schemas/api/v1/openapi.json``. The contract
#: is the authority; these exist so a query object cannot be constructed outside
#: it and reach an implementation.
DEFAULT_LIMIT = 50
MIN_LIMIT = 1
MAX_LIMIT = 500

#: ``PageInfo.next_cursor`` is capped at 512 characters by the contract.
MAX_CURSOR_LENGTH = 512

#: ``/api/search`` caps ``q`` at 512 characters.
MAX_QUERY_LENGTH = 512

#: ``/api/graph/neighborhood`` caps ``depth`` at 3.
MIN_DEPTH = 1
MAX_DEPTH = 3

#: What the index can answer with. ``absent`` and ``building`` are reported
#: plainly: a UI that cannot tell an empty index from an unbuilt one presents
#: "no sources" as a fact about the user's data.
INDEX_STATES = ("absent", "building", "ready", "error")

#: The state in which the repository answers questions. Every other state is an
#: :class:`IndexUnavailable`.
READY = "ready"

#: ``EntityRef.provenance_class`` / ``IndexedRelation.provenance_class``.
PROVENANCE_CLASSES = ("source", "derived", "user")

#: ``IndexedRelation.relation_vocabulary``.
RELATION_VOCABULARIES = ("canonical", "library_synthetic", "user")

#: Every status a source may be filtered by, ``UNKNOWN`` included — it is a real
#: answer about a run, not the absence of one.
FILTERABLE_STATUSES = tuple(sorted(RUN_STATUSES)) + (UNKNOWN_STATUS,)

#: ``EntityRef.kind``: the kinds of ``constants.py`` plus the concept kind
#: ``library.py`` emits. Built from ``constants`` rather than restated, so the
#: drift test that guards ``schemas/v1/common.schema.json`` guards this too.
ENTITY_KINDS = frozenset(KNOWLEDGE_KINDS | {"canonical_concept"})

#: The field each record family is identified and paged by. The order is
#: lexicographic over this field; it is *total* only because :func:`order_key`
#: appends a tiebreak to it, and because :func:`check_index_integrity` refuses
#: an index in which the field repeats.
ORDER_KEYS = {
    "source": "id",
    "artifact": "id",
    "entity_ref": "global_id",
    "indexed_relation": "id",
}

#: Separates an order key's identity from its tiebreak. NUL sorts below every
#: character an identifier may contain (``ids.ID_PART_PATTERN`` admits none
#: below ``-``), so appending it can never reorder two distinct ids.
ORDER_KEY_SEPARATOR = "\x00"

#: How much of an over-long order key a cursor carries verbatim. The rest is
#: represented by a digest of the whole key; see :class:`Cursor`.
CURSOR_PREFIX_LENGTH = 200


# --------------------------------------------------------------------------
# Errors — D-030, executable
# --------------------------------------------------------------------------


class RepositoryError(RuntimeError):
    """A request the repository refuses.

    ``code`` and ``http_status`` are the D-030 taxonomy made executable: the API
    renders the error it is handed and does not get to pick a different status
    for the same refusal.
    """

    #: A member of the frozen ``ErrorCode`` enum.
    code = "internal"
    http_status = 500


class InvalidId(RepositoryError):
    """An id is malformed, or its parts contradict the whole.

    Raised *before* anything is read. D-020: a lookup must fail rather than
    silently read something else, so a bad id is reported as bad.
    """

    code = "invalid_id"
    http_status = 400


class InvalidQuery(RepositoryError):
    """A parameter is outside the frozen contract, or a cursor does not belong.

    Covers a limit out of range, an unknown filter value, and a cursor presented
    against a query it was not issued for.
    """

    code = "invalid_request"
    http_status = 400


class IndexUnavailable(RepositoryError):
    """The index exists in a state that cannot answer questions.

    ``state`` is the :data:`INDEX_STATES` member that explains why, so the API
    can say *unbuilt* rather than *empty*.
    """

    code = "index_unavailable"
    http_status = 503

    def __init__(self, message: str, state: str = "absent") -> None:
        super().__init__(message)
        self.state = state


# --------------------------------------------------------------------------
# Cursors — opaque outside, deterministic inside
# --------------------------------------------------------------------------


#: The key every cursor this process issues is authenticated with.
#:
#: A cursor used to be an unkeyed hash: anything that could base64-encode a JSON
#: object could mint one, and a forged token handed the repository an arbitrary
#: position — for search, an arbitrary offset. The contract only says the token
#: is opaque and at most 512 characters, so a MAC fits inside it without
#: touching the wire format.
#:
#: The key is random per process and never leaves it. Two implementations in one
#: process therefore still mint identical tokens for identical positions, which
#: is what ``T-104``'s page-for-page comparison needs; a cursor does not survive
#: a restart, and is refused as ``invalid_request`` afterwards rather than
#: honoured. That is the right answer for a token that names a position in an
#: index the restart may have rebuilt.
_CURSOR_KEY = secrets.token_bytes(32)

#: Bytes of the MAC carried in a token. 128 bits is far past what forging a
#: local, per-process key is worth, and it costs 32 characters of the 512.
_CURSOR_MAC_BYTES = 16


def query_fingerprint(parts: Mapping[str, Any]) -> str:
    """A short, stable digest of the filters a query applies.

    ``limit`` and ``cursor`` are deliberately **not** part of it: keyset paging
    does not depend on the page size, so changing ``limit`` mid-iteration is
    legitimate and must not invalidate the cursor. Changing a *filter* must.
    """
    canonical = json.dumps(parts, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def key_digest(key: str) -> str:
    """The digest by which a cursor names an order key it cannot carry whole."""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _authenticate(payload: str) -> str:
    return hmac.new(_CURSOR_KEY, payload.encode("utf-8"), hashlib.sha256).hexdigest()[
        : _CURSOR_MAC_BYTES * 2
    ]


@dataclass(frozen=True)
class Cursor:
    """A position in the total order, in a form that always fits the contract.

    ``PageInfo.next_cursor`` is capped at 512 characters; an order key is not.
    ``IndexedRelation.id`` is a 1300-character field by schema — two 600-byte
    global ids and a relation name — so a record the schema permits used to
    raise ``500`` the moment it landed on a page boundary. A key that does not
    fit is therefore carried as a bounded *prefix* plus a digest of the whole.

    Resuming from the short form is exact, not approximate. Every key in
    ``(prefix, position]`` begins with ``prefix`` — a lexicographic fact: a key
    that differs from ``prefix`` before ``prefix`` ends is either below it or
    above every key that extends it. So the tail of the collection starts right
    after the single row whose key digests to :attr:`digest`, and no row is
    skipped or repeated.
    """

    #: The key itself when it fits, otherwise its first
    #: :data:`CURSOR_PREFIX_LENGTH` characters.
    prefix: str
    #: ``None`` when :attr:`prefix` is the whole key.
    digest: str | None = None

    @property
    def key(self) -> str | None:
        """The whole order key, or ``None`` when only a prefix was carried."""
        return self.prefix if self.digest is None else None

    @property
    def identity_bound(self) -> str:
        """The value a SQL backend seeks on: ``WHERE <id column> >= this``.

        An order key is ``<id><NUL><digest>`` (see :func:`order_key`) and the id
        is the part a database has an index on. Seeking ``>=`` this returns a
        superset of the tail — at most the rows sharing the boundary id, which
        is exactly one under a ``UNIQUE`` constraint — and :meth:`tail` trims it
        to the exact position.
        """
        return self.prefix.split(ORDER_KEY_SEPARATOR, 1)[0]

    def tail(self, ordered: Sequence[Any], key_of) -> list[Any]:
        """The part of *ordered* that follows this position."""
        after = [row for row in ordered if key_of(row) > self.prefix]
        if self.digest is None:
            return after
        for index, row in enumerate(after):
            if key_digest(key_of(row)) == self.digest:
                return after[index + 1 :]
        raise InvalidQuery(
            "the record this cursor names is no longer in the collection; "
            "start the collection again rather than resuming from a gap"
        )


def encode_cursor(fingerprint: str, key: str) -> str:
    """Encode the position *key*, bound to the query that produced it.

    The token is base64url of compact JSON, followed by a MAC over it. It is
    opaque by contract, not by obfuscation: the API must not parse it, and the
    encoding may change without a contract change — which is precisely why it
    lives here and not in a route.
    """
    token = _token({"f": fingerprint, "k": key})
    if len(token) <= MAX_CURSOR_LENGTH:
        return token
    # Too long to carry whole. A key that long is legal — the schema allows a
    # 1300-character relation id — so it is paged, not refused.
    token = _token(
        {
            "f": fingerprint,
            "p": key[:CURSOR_PREFIX_LENGTH],
            "d": key_digest(key),
        }
    )
    if len(token) > MAX_CURSOR_LENGTH:  # pragma: no cover - the budget is fixed
        raise RepositoryError(
            f"cursor is {len(token)} characters, over the {MAX_CURSOR_LENGTH} "
            "the contract allows"
        )
    return token


def _token(body: Mapping[str, Any]) -> str:
    payload = json.dumps(body, sort_keys=True, separators=(",", ":"))
    encoded = base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii").rstrip("=")
    return f"{encoded}.{_authenticate(payload)}"


def decode_cursor(token: str, fingerprint: str) -> Cursor:
    """The position *token* names, or a refusal.

    Three ways to be refused, and they are different refusals of the same kind.
    A token this process did not sign was not issued here. A token issued for
    different filters is refused rather than re-anchored: re-anchoring would
    return a page of a collection the client never asked for, and it would look
    like data rather than like an error. A token naming a position the
    collection no longer holds is refused by :meth:`Cursor.tail`.
    """
    if not isinstance(token, str) or not token:
        raise InvalidQuery("cursor must be a non-empty string")
    if len(token) > MAX_CURSOR_LENGTH:
        raise InvalidQuery(f"cursor is longer than {MAX_CURSOR_LENGTH} characters")
    encoded, _, mac = token.rpartition(".")
    if not encoded or not mac:
        raise InvalidQuery("cursor is not a cursor this repository issued")
    padding = "=" * (-len(encoded) % 4)
    try:
        raw = base64.urlsafe_b64decode(encoded + padding).decode("utf-8")
        payload = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise InvalidQuery("cursor is not a cursor this repository issued") from exc
    if not hmac.compare_digest(mac, _authenticate(raw)):
        # Unsigned or tampered with. The offset a search cursor carries reaches
        # real work, so it is authenticated rather than merely parsed.
        raise InvalidQuery("cursor is not a cursor this repository issued")
    if not isinstance(payload, dict):
        raise InvalidQuery("cursor is not a cursor this repository issued")
    if payload.get("f") != fingerprint:
        raise InvalidQuery(
            "cursor was issued for a different query; start the collection again "
            "rather than paging one collection with another's cursor"
        )
    if isinstance(payload.get("k"), str):
        return Cursor(prefix=payload["k"])
    if isinstance(payload.get("p"), str) and isinstance(payload.get("d"), str):
        return Cursor(prefix=payload["p"], digest=payload["d"])
    raise InvalidQuery("cursor is not a cursor this repository issued")


# --------------------------------------------------------------------------
# Validation helpers — every one of them refuses rather than corrects
# --------------------------------------------------------------------------


def _check_limit(limit: int) -> int:
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise InvalidQuery(f"limit must be an integer, got {type(limit).__name__}")
    if not MIN_LIMIT <= limit <= MAX_LIMIT:
        raise InvalidQuery(f"limit must be between {MIN_LIMIT} and {MAX_LIMIT}, got {limit}")
    return limit


def _check_choice(value: Any, allowed: Sequence[str], label: str) -> str | None:
    if value is None:
        return None
    if value not in allowed:
        raise InvalidQuery(f"{label} must be one of {', '.join(sorted(allowed))}, got {value!r}")
    return value


def _check_source_id(value: Any, label: str = "source_id") -> str | None:
    """Parse a two-part source id, or refuse it. Never joined onto a path."""
    if value is None:
        return None
    try:
        return ids.parse_source_id(value).value
    except ids.IdError as exc:
        raise InvalidId(f"{label}: {exc}") from exc


def _check_global_id(value: Any, label: str) -> str:
    try:
        return ids.parse_global_id(value).value
    except ids.IdError as exc:
        raise InvalidId(f"{label}: {exc}") from exc


def _check_source_type(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return ids.validate_source_type(value)
    except ids.IdError as exc:
        raise InvalidQuery(f"source_type: {exc}") from exc


def _check_confidence(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidQuery(f"min_confidence must be a number, got {type(value).__name__}")
    if not 0 <= value <= 1:
        raise InvalidQuery(f"min_confidence must be between 0 and 1, got {value}")
    return float(value)


# --------------------------------------------------------------------------
# Queries — an invalid one cannot be constructed
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class PagedQuery:
    """Shared paging parameters. Validated on construction.

    Validating in ``__post_init__`` puts the ``400`` where the request is
    translated, not where the records are read — so no implementation has to
    re-check what the contract already bounds, and none can forget to.
    """

    limit: int = DEFAULT_LIMIT
    cursor: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "limit", _check_limit(self.limit))
        if self.cursor is not None and not isinstance(self.cursor, str):
            raise InvalidQuery("cursor must be a string")

    def filters(self) -> dict[str, Any]:
        """The filter fields a cursor is bound to. Excludes limit and cursor."""
        return {}

    @property
    def fingerprint(self) -> str:
        return query_fingerprint({"query": type(self).__name__, **self.filters()})

    def start(self) -> Cursor | None:
        """The position this page starts after, or ``None`` for the first page."""
        if self.cursor is None:
            return None
        return decode_cursor(self.cursor, self.fingerprint)


@dataclass(frozen=True)
class SourceQuery(PagedQuery):
    """``GET /api/sources``."""

    source_type: str | None = None
    status: str | None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        object.__setattr__(self, "source_type", _check_source_type(self.source_type))
        object.__setattr__(
            self, "status", _check_choice(self.status, FILTERABLE_STATUSES, "status")
        )

    def filters(self) -> dict[str, Any]:
        return {"source_type": self.source_type, "status": self.status}


@dataclass(frozen=True)
class EntityQuery(PagedQuery):
    """``GET /api/sources/{source_id}/entities``.

    ``source_id`` is optional here although the frozen endpoint always supplies
    one: leaving it out is how ``/api/graph`` asks for nodes across the library,
    and a concept — which belongs to no source (D-016) — is reachable only that
    way.
    """

    source_id: str | None = None
    provenance_class: str | None = None
    kind: str | None = None
    min_confidence: float | None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        object.__setattr__(self, "source_id", _check_source_id(self.source_id))
        object.__setattr__(
            self,
            "provenance_class",
            _check_choice(self.provenance_class, PROVENANCE_CLASSES, "provenance_class"),
        )
        object.__setattr__(
            self, "kind", _check_choice(self.kind, sorted(ENTITY_KINDS), "kind")
        )
        object.__setattr__(self, "min_confidence", _check_confidence(self.min_confidence))

    def filters(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "provenance_class": self.provenance_class,
            "kind": self.kind,
            "min_confidence": self.min_confidence,
        }


@dataclass(frozen=True)
class RelationQuery(PagedQuery):
    """``GET /api/sources/{source_id}/relations``."""

    source_id: str | None = None
    relation_vocabulary: str | None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        object.__setattr__(self, "source_id", _check_source_id(self.source_id))
        object.__setattr__(
            self,
            "relation_vocabulary",
            _check_choice(
                self.relation_vocabulary, RELATION_VOCABULARIES, "relation_vocabulary"
            ),
        )

    def filters(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "relation_vocabulary": self.relation_vocabulary,
        }


@dataclass(frozen=True)
class SearchQuery(PagedQuery):
    """``GET /api/search``.

    ``q`` has no default: a search without a query string is a bad request, not
    an empty result.
    """

    q: str = ""
    source_id: str | None = None
    include_transcript: bool = True

    def __post_init__(self) -> None:
        super().__post_init__()
        if not isinstance(self.q, str) or not self.q.strip():
            raise InvalidQuery("q must be a non-empty query string")
        if len(self.q) > MAX_QUERY_LENGTH:
            raise InvalidQuery(f"q must be at most {MAX_QUERY_LENGTH} characters")
        object.__setattr__(self, "source_id", _check_source_id(self.source_id))
        if not isinstance(self.include_transcript, bool):
            raise InvalidQuery("include_transcript must be a boolean")

    def filters(self) -> dict[str, Any]:
        return {
            "q": self.q,
            "source_id": self.source_id,
            "include_transcript": self.include_transcript,
        }


@dataclass(frozen=True)
class GraphQuery(PagedQuery):
    """``GET /api/graph``."""

    source_id: str | None = None
    provenance_class: str | None = None
    relation_vocabulary: str | None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        object.__setattr__(self, "source_id", _check_source_id(self.source_id))
        object.__setattr__(
            self,
            "provenance_class",
            _check_choice(self.provenance_class, PROVENANCE_CLASSES, "provenance_class"),
        )
        object.__setattr__(
            self,
            "relation_vocabulary",
            _check_choice(
                self.relation_vocabulary, RELATION_VOCABULARIES, "relation_vocabulary"
            ),
        )

    def filters(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "provenance_class": self.provenance_class,
            "relation_vocabulary": self.relation_vocabulary,
        }

    def node_filter(self) -> EntityQuery:
        """The non-membership node filters, as an :class:`EntityQuery`.

        Membership is *not* in here. Which entities a source's graph is drawn
        over is decided by :func:`graph_nodes`, because it is the same question
        ``/api/sources/{id}/relations`` answers and there is one rule for it.
        """
        return EntityQuery(
            limit=self.limit,
            cursor=None,
            provenance_class=self.provenance_class,
        )


@dataclass(frozen=True)
class NeighborhoodQuery:
    """``GET /api/graph/neighborhood/{entity_id}``.

    Not a :class:`PagedQuery`: ``NeighborhoodResponse`` carries no ``page``. A
    neighborhood is bounded by ``depth`` and ``limit`` and says so with
    ``truncated``, rather than being walked page by page.
    """

    entity_id: str = ""
    depth: int = MIN_DEPTH
    limit: int = DEFAULT_LIMIT
    relation_vocabulary: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "entity_id", _check_global_id(self.entity_id, "entity_id")
        )
        if isinstance(self.depth, bool) or not isinstance(self.depth, int):
            raise InvalidQuery(f"depth must be an integer, got {type(self.depth).__name__}")
        if not MIN_DEPTH <= self.depth <= MAX_DEPTH:
            raise InvalidQuery(
                f"depth must be between {MIN_DEPTH} and {MAX_DEPTH}, got {self.depth}"
            )
        object.__setattr__(self, "limit", _check_limit(self.limit))
        object.__setattr__(
            self,
            "relation_vocabulary",
            _check_choice(
                self.relation_vocabulary, RELATION_VOCABULARIES, "relation_vocabulary"
            ),
        )


# --------------------------------------------------------------------------
# Results — the payloads of the frozen contract, without its envelope
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Page:
    """One page of v1 records.

    ``items`` are the plain dicts the adapters produce; nothing translates them
    on the way out. ``total`` is ``None`` when the implementation did not count
    — which the contract says means *unknown*, never *zero*.
    """

    items: list[dict[str, Any]] = field(default_factory=list)
    limit: int = DEFAULT_LIMIT
    next_cursor: str | None = None
    total: int | None = None

    def page_info(self) -> dict[str, Any]:
        """Exactly the frozen ``PageInfo`` object. The API adds the envelope."""
        return {"limit": self.limit, "next_cursor": self.next_cursor, "total": self.total}


@dataclass(frozen=True)
class SourceDetail:
    """``GET /api/sources/{source_id}`` — a source and the artifacts it owns."""

    source: dict[str, Any]
    artifacts: list[dict[str, Any]] = field(default_factory=list)

    def payload(self) -> dict[str, Any]:
        return {"source": self.source, "artifacts": list(self.artifacts)}


@dataclass(frozen=True)
class GraphPage:
    """``GET /api/graph`` — a page of nodes with the edges that connect them.

    ``truncated`` is stated rather than implied, so the Map never presents a
    partial graph as the whole one.
    """

    nodes: list[dict[str, Any]] = field(default_factory=list)
    edges: list[dict[str, Any]] = field(default_factory=list)
    truncated: bool = False
    limit: int = DEFAULT_LIMIT
    next_cursor: str | None = None
    total: int | None = None

    def payload(self) -> dict[str, Any]:
        return {
            "nodes": list(self.nodes),
            "edges": list(self.edges),
            "truncated": self.truncated,
        }

    def page_info(self) -> dict[str, Any]:
        return {"limit": self.limit, "next_cursor": self.next_cursor, "total": self.total}


@dataclass(frozen=True)
class Neighborhood:
    """``GET /api/graph/neighborhood/{entity_id}`` — a bounded walk from a center."""

    center_id: str
    depth: int
    nodes: list[dict[str, Any]] = field(default_factory=list)
    edges: list[dict[str, Any]] = field(default_factory=list)
    truncated: bool = False

    def payload(self) -> dict[str, Any]:
        return {
            "center_id": self.center_id,
            "depth": self.depth,
            "nodes": list(self.nodes),
            "edges": list(self.edges),
            "truncated": self.truncated,
        }


@dataclass(frozen=True)
class IndexStatus:
    """``GET /api/status`` — what the index is, not what a source says.

    ``counts`` is a cache convenience reproducible from the canonical files. A
    stale count is a bug, never a data achievement (canvas plan §2).
    """

    state: str = "absent"
    built_at: str | None = None
    index_version: int | None = None
    counts: Mapping[str, int] = field(default_factory=dict)
    sources_by_status: Mapping[str, int] = field(default_factory=dict)
    adapters: Sequence[Mapping[str, str]] = ()

    def __post_init__(self) -> None:
        if self.state not in INDEX_STATES:
            raise RepositoryError(
                f"index state must be one of {', '.join(INDEX_STATES)}, got {self.state!r}"
            )

    def payload(self) -> dict[str, Any]:
        """Exactly the frozen ``StatusPayload`` object."""
        return {
            "index": {
                "state": self.state,
                "built_at": self.built_at,
                "index_version": self.index_version,
            },
            "counts": {
                "sources": int(self.counts.get("sources", 0)),
                "artifacts": int(self.counts.get("artifacts", 0)),
                "entities": int(self.counts.get("entities", 0)),
                "relations": int(self.counts.get("relations", 0)),
            },
            "sources_by_status": {
                status: int(self.sources_by_status.get(status, 0))
                for status in (*sorted(RUN_STATUSES), UNKNOWN_STATUS)
            },
            "adapters": [dict(adapter) for adapter in self.adapters],
        }


# --------------------------------------------------------------------------
# Membership and paging — shared so two implementations cannot disagree
# --------------------------------------------------------------------------


def entity_belongs_to_source(entity: Mapping[str, Any], source_id: str) -> bool:
    """Whether *entity* is one of *source_id*'s.

    A canonical concept carries ``source_id: null`` because it belongs to no
    single source (D-016), so it is nobody's entity and appears only in the
    library-wide views.
    """
    return entity.get("source_id") == source_id


def relation_belongs_to_source(relation: Mapping[str, Any], source_id: str) -> bool:
    """Whether *relation* is one of *source_id*'s.

    Two ways to belong, and the second is not redundant. A relation names the
    run that produced it in ``source_id`` — but the 17 ``expresses_concept``
    edges of the current library name **no** run, because ``adapt_library``
    produces them and they are cross-source (D-025). They are still the edges
    that connect a source to the concepts it expresses, and a Reader that showed
    a source's relations without them would be hiding the source's own links.

    So: a relation belongs to a source when the source produced it, **or** when
    either endpoint is an entity of that source. Endpoint membership is read off
    the global id itself (D-011) — no join, and no second rule.
    """
    if relation.get("source_id") == source_id:
        return True
    prefix = f"{source_id}:"
    return any(
        isinstance(endpoint, str) and endpoint.startswith(prefix)
        for endpoint in (relation.get("from_id"), relation.get("to_id"))
    )


def matches_entity(entity: Mapping[str, Any], query: EntityQuery) -> bool:
    """Every ``EntityRef`` filter the frozen contract exposes, in one place."""
    if query.source_id is not None and not entity_belongs_to_source(entity, query.source_id):
        return False
    if query.provenance_class is not None and entity.get("provenance_class") != query.provenance_class:
        return False
    if query.kind is not None and entity.get("kind") != query.kind:
        return False
    if query.min_confidence is not None:
        confidence = entity.get("confidence")
        # A unit that states no confidence is not "confident enough". Treating a
        # missing value as passing would invent one (ADR 0001 invariant 2).
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
            return False
        if confidence < query.min_confidence:
            return False
    return True


def matches_relation(relation: Mapping[str, Any], query: RelationQuery | GraphQuery) -> bool:
    """Every ``IndexedRelation`` filter the frozen contract exposes."""
    if query.source_id is not None and not relation_belongs_to_source(relation, query.source_id):
        return False
    vocabulary = getattr(query, "relation_vocabulary", None)
    if vocabulary is not None and relation.get("relation_vocabulary") != vocabulary:
        return False
    return True


def graph_nodes(
    entities: Iterable[Mapping[str, Any]],
    relations: Iterable[Mapping[str, Any]],
    query: GraphQuery,
) -> list[Mapping[str, Any]]:
    """Every entity this graph is drawn over, in the order it was given.

    One fact, one home. ``/api/sources/{id}/relations`` answers "which relations
    are this source's" with :func:`relation_belongs_to_source`, and that rule
    counts the ``expresses_concept`` edges a source makes to the cross-source
    concepts it expresses even though those edges name no run (D-025, D-034).
    ``/api/graph?source_id=…`` used to answer the same question with a different
    rule — an edge counted only if *both* endpoints were entities **of that
    source** — and a concept belongs to no source (D-016). So the graph dropped
    every one of those edges, and the two views disagreed about one fact: over
    the sample, 101 edges against 118, with none of the 17 ``expresses_concept``
    edges in the graph at all.

    The graph now takes the relations rule as given and draws the nodes those
    relations need. A node belongs to a source's graph when it is an entity of
    that source, **or** when a relation of that source names it as an endpoint.
    Nothing dangles — ADR 0002 is emphatic that an edge to a node the page will
    not show asserts a node that does not exist — because the far endpoint is
    now a node of the graph rather than an excluded one.

    The other filters are unchanged and still apply to every node, membership or
    not: a client that asks for ``provenance_class=source`` gets the graph it
    asked for, and the edges to what it excluded go with it.
    """
    relations = list(relations)
    reachable: set[str] = set()
    if query.source_id is not None:
        for relation in relations:
            if not matches_relation(relation, query):
                continue
            for endpoint in (relation.get("from_id"), relation.get("to_id")):
                if isinstance(endpoint, str):
                    reachable.add(endpoint)

    node_filter = query.node_filter()
    selected: list[Mapping[str, Any]] = []
    for entity in entities:
        if not matches_entity(entity, node_filter):
            continue
        if query.source_id is not None and not (
            entity_belongs_to_source(entity, query.source_id)
            or entity.get("global_id") in reachable
        ):
            continue
        selected.append(entity)
    return selected


def matches_source(source: Mapping[str, Any], query: SourceQuery) -> bool:
    """Every ``Source`` filter the frozen contract exposes.

    ``status`` filters on the **overall** status the adapter copied out of the
    validator files — the one the Library list displays.
    """
    if query.source_type is not None and source.get("source_type") != query.source_type:
        return False
    if query.status is not None:
        status = source.get("status")
        overall = status.get("overall") if isinstance(status, Mapping) else None
        if overall != query.status:
            return False
    return True


def record_copy(record: Mapping[str, Any]) -> dict[str, Any]:
    """An independent copy of *record*, safe to hand outside the repository.

    Deep, not shallow. ``dict(record)`` duplicates only the top level, so
    ``status``, ``artifact_ids``, ``locator`` and ``derived_from`` stayed shared
    references into the index — and a caller that edited one edited the stored
    record. That defeated two invariants at once: ADR 0002 invariant 6 (records
    handed out are copies) and, worse, ADR 0001 invariant 2, because writing
    ``status["overall"] = "PASS"`` on a returned ``FAIL`` source coerced the
    index and every later status tally with it.

    Every hand-out boundary goes through here so there is one place to get this
    right, and so ``T-101``'s SQLite implementation — which will build fresh
    dicts per row and needs no copy at all — has a named seam to opt out of.
    """
    return copy.deepcopy(dict(record))


def content_digest(record: Mapping[str, Any]) -> str:
    """A short, stable digest of everything *record* says."""
    canonical = json.dumps(record, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def identity(record: Mapping[str, Any], model: str) -> str:
    """The id *record* is addressed by — ``ORDER_KEYS[model]``, and nothing else."""
    return str(record.get(ORDER_KEYS[model], ""))


def order_key(record: Mapping[str, Any], model: str) -> str:
    """The **total** order key *record* pages by.

    ``ORDER_KEYS`` names the id each family is ordered by, and the seam calls
    that order total and lexicographic. It was total only while the id was
    unique, and nothing enforced that: two records sharing an id sort equal, and
    a tie that straddles a page boundary is a record silently *deleted* from the
    paged output while ``total`` goes on counting it.

    So the key carries a second component — a digest of the record's own content
    — behind a separator that sorts below every character an id may contain. Two
    records that differ at all now sort in a defined, implementation-independent
    order and both survive a full walk. Two that differ in nothing are one
    record filed twice, which :func:`check_index_integrity` refuses at
    construction rather than letting a page swallow it.

    A SQL implementation reproduces this with a stored digest column, or omits
    it entirely under a ``UNIQUE`` constraint on the id, which buys the same
    guarantee a different way.
    """
    return f"{identity(record, model)}{ORDER_KEY_SEPARATOR}{content_digest(record)}"


def sort_records(records: Iterable[Mapping[str, Any]], model: str) -> list[dict[str, Any]]:
    """*records* in the one order every implementation must page in."""
    return sorted(
        (record_copy(record) for record in records), key=lambda item: order_key(item, model)
    )


def check_index_integrity(by_model: Mapping[str, Sequence[Mapping[str, Any]]]) -> None:
    """Refuse a record set that cannot be paged or drawn honestly.

    Two conditions, and both were previously invisible until they had already
    corrupted an answer:

    **No two records may claim the same id.** A duplicate makes the order
    non-total, and a tie across a page boundary drops a record from the paged
    output while ``total`` keeps counting it — a silent deletion, which is worse
    than a refusal. Artifacts and entities share one global-id namespace, so
    they are checked together.

    **No edge may name an endpoint no entity record has.** A dangling edge
    cannot be drawn — the graph excludes it, because an edge to a node the page
    will not show asserts a node that does not exist — while
    ``/api/sources/{id}/relations`` still lists it. The two views then disagree
    about one fact, which is precisely what the graph rule exists to prevent.

    Raised as :class:`RepositoryError` (``internal``, ``500``): the request is
    fine, the index is not. ``adapters.check_records`` should refuse the same
    two conditions where the records are *produced*; this is the seam's own
    guard, so that no implementation can hand the API a set it cannot page.
    """
    problems: list[str] = []

    claimed: dict[str, str] = {}
    for model in ("source", "artifact", "entity_ref", "indexed_relation"):
        # Artifacts and entities are addressed out of one namespace, so they
        # cannot be checked separately; sources and relations have their own.
        namespace = claimed if model in ("artifact", "entity_ref") else {}
        for record in by_model.get(model, ()):
            key = identity(record, model)
            previous = namespace.get(key)
            if previous is not None:
                problems.append(
                    f"{model} {key!r} is claimed twice (also by {previous}); "
                    "one record, one id"
                )
            namespace[key] = model

    entities = {identity(entity, "entity_ref") for entity in by_model.get("entity_ref", ())}
    for relation in by_model.get("indexed_relation", ()):
        for side in ("from_id", "to_id"):
            endpoint = relation.get(side)
            if endpoint not in entities:
                problems.append(
                    f"relation {identity(relation, 'indexed_relation')!r} names "
                    f"{side} {endpoint!r}, which no entity record has"
                )

    if problems:
        shown = problems[:10]
        if len(problems) > len(shown):
            shown.append(f"… and {len(problems) - len(shown)} more")
        raise RepositoryError(
            "the index cannot be served: " + "; ".join(shown)
        )


def page_from_window(
    window: Sequence[Mapping[str, Any]],
    query: PagedQuery,
    model: str,
    *,
    total: int | None = None,
) -> Page:
    """Assemble a page from at most ``limit + 1`` rows already in key order.

    This is the half of paging two implementations have to share, and the reason
    it takes a *window* rather than a whole collection. ``T-101``'s SQL does the
    seek itself — ``WHERE key > :prefix ORDER BY key LIMIT :limit + 1``, the
    bound coming from :attr:`Cursor.prefix` — and hands the rows here. The extra
    row is the probe that decides whether a next cursor exists; it is never
    returned. So the cursor arithmetic is one piece of code rather than two, and
    ``T-104``'s rebuild-equivalence test compares pages instead of comparing a
    re-implementation with the thing it re-implements.
    """
    rows = [record_copy(row) for row in window[: query.limit]]
    exhausted = len(window) <= query.limit
    next_cursor = (
        None
        if exhausted or not rows
        else encode_cursor(query.fingerprint, order_key(rows[-1], model))
    )
    return Page(items=rows, limit=query.limit, next_cursor=next_cursor, total=total)


def keyset_page(
    ordered: Sequence[Mapping[str, Any]],
    query: PagedQuery,
    model: str,
    *,
    total: int | None = None,
) -> Page:
    """One page of an already-filtered, already-sorted, materialised sequence.

    A keyset page, not an offset one: the cursor names the last key returned, so
    a record inserted before it cannot shift a later page and cause a record to
    be skipped. The seek is the part an in-memory sequence and a ``SELECT`` do
    differently; :func:`page_from_window` is the part they must do identically.
    """
    start = query.start()
    remaining = (
        list(ordered)
        if start is None
        else start.tail(ordered, lambda row: order_key(row, model))
    )
    return page_from_window(
        remaining[: query.limit + 1],
        query,
        model,
        total=len(ordered) if total is None else total,
    )


# --------------------------------------------------------------------------
# The contract
# --------------------------------------------------------------------------


@runtime_checkable
class IndexRepository(Protocol):
    """What the API may ask the index for. Ten methods, eleven endpoints.

    ``GET /api/media/{artifact_id}`` reuses :meth:`get_artifact`: the record
    carries ``path`` — project-relative, produced by ``adapters.project_relative``
    — and ``available``. Serving bytes, range requests, and the loopback binding
    are ``T-108``'s, not the repository's; a repository that streamed files would
    put path safety in two places.

    An implementation is a **reader**. Every method here is a question.
    """

    def status(self) -> IndexStatus:
        """What the index is. Answers in every state, including ``error``."""

    def list_sources(self, query: SourceQuery) -> Page:
        """``GET /api/sources`` — a page of ``Source`` records."""

    def get_source(self, source_id: str) -> SourceDetail | None:
        """``GET /api/sources/{source_id}``, or ``None`` when nothing has that id.

        Raises :class:`InvalidId` when *source_id* is not a source id.
        """

    def list_entities(self, query: EntityQuery) -> Page:
        """``GET /api/sources/{source_id}/entities`` — a page of ``EntityRef``.

        An unknown ``source_id`` yields an **empty page**; distinguishing "no
        such source" from "a source with no entities" is :meth:`get_source`'s
        job, so the route checks existence once and the repository does not
        answer the same question twice.
        """

    def list_relations(self, query: RelationQuery) -> Page:
        """``GET /api/sources/{source_id}/relations`` — a page of ``IndexedRelation``."""

    def get_entity(self, entity_id: str) -> dict[str, Any] | None:
        """``GET /api/entities/{entity_id}``, or ``None``."""

    def get_artifact(self, artifact_id: str) -> dict[str, Any] | None:
        """``GET /api/artifacts/{artifact_id}`` and ``/api/media``, or ``None``."""

    def search(self, query: SearchQuery) -> Page:
        """``GET /api/search`` — a page of the two hit shapes of D-028."""

    def graph(self, query: GraphQuery) -> GraphPage:
        """``GET /api/graph`` — a page of nodes with the edges among them."""

    def neighborhood(self, query: NeighborhoodQuery) -> Neighborhood | None:
        """``GET /api/graph/neighborhood/{entity_id}``, or ``None`` for an unknown center."""
