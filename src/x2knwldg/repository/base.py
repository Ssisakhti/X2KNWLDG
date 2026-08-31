"""The indexer ↔ API seam (``T-007``).

Track A builds the SQLite index (``T-101``–``T-104``). Track B serves the frozen
HTTP contract in ``schemas/api/v1/openapi.json`` (``T-105``–``T-108``). They meet
here and nowhere else: Track B calls :class:`IndexRepository` and never opens a
database, a canonical file, or a run directory; Track A implements it and never
imports a route.

Five rules shape the seam, and each is enforced in this module rather than left
to an implementation:

**The repository owes pages of v1 records, not rows.** Every list method returns
a :class:`Page` of the plain dicts ``IndexRecords.by_model()`` already produces.
A row type of its own would be a third vocabulary for the same fact (D-026),
and there are already two identifier vocabularies to keep honest (risk R12).

**The cursor encoding belongs to the repository alone.** The contract declares
it opaque, so the API passes it through unparsed and the frontend cannot depend
on it. :func:`encode_cursor` and :func:`decode_cursor` are that encoding —
shared so that two implementations page identically, which is what lets
``T-104`` compare them page for page.

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
import hashlib
import json
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

#: The field each record family is ordered and paged by. The order is total and
#: lexicographic, so a keyset cursor is a record id and nothing else.
ORDER_KEYS = {
    "source": "id",
    "artifact": "id",
    "entity_ref": "global_id",
    "indexed_relation": "id",
}


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


def query_fingerprint(parts: Mapping[str, Any]) -> str:
    """A short, stable digest of the filters a query applies.

    ``limit`` and ``cursor`` are deliberately **not** part of it: keyset paging
    does not depend on the page size, so changing ``limit`` mid-iteration is
    legitimate and must not invalidate the cursor. Changing a *filter* must.
    """
    canonical = json.dumps(parts, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def encode_cursor(fingerprint: str, key: str) -> str:
    """Encode the position *key*, bound to the query that produced it.

    The token is base64url of compact JSON. It is opaque by contract, not by
    obfuscation: the API must not parse it, and the encoding may change without
    a contract change — which is precisely why it lives here and not in a route.
    """
    payload = json.dumps({"f": fingerprint, "k": key}, separators=(",", ":"))
    token = base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii").rstrip("=")
    if len(token) > MAX_CURSOR_LENGTH:
        raise RepositoryError(
            f"cursor for key {key!r} is {len(token)} characters, over the "
            f"{MAX_CURSOR_LENGTH} the contract allows"
        )
    return token


def decode_cursor(token: str, fingerprint: str) -> str:
    """The position key *token* carries, or a refusal.

    A cursor issued for different filters is refused rather than re-anchored:
    re-anchoring would return a page of a collection the client never asked
    for, and it would look like data rather than like an error.
    """
    if not isinstance(token, str) or not token:
        raise InvalidQuery("cursor must be a non-empty string")
    if len(token) > MAX_CURSOR_LENGTH:
        raise InvalidQuery(f"cursor is longer than {MAX_CURSOR_LENGTH} characters")
    padding = "=" * (-len(token) % 4)
    try:
        payload = json.loads(base64.urlsafe_b64decode(token + padding).decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise InvalidQuery("cursor is not a cursor this repository issued") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("k"), str):
        raise InvalidQuery("cursor is not a cursor this repository issued")
    if payload.get("f") != fingerprint:
        raise InvalidQuery(
            "cursor was issued for a different query; start the collection again "
            "rather than paging one collection with another's cursor"
        )
    return payload["k"]


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

    def start_key(self) -> str | None:
        """The exclusive lower bound this page starts after, or ``None``."""
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

    def node_query(self) -> EntityQuery:
        """The node page this graph page is built on. One filter rule, one place."""
        return EntityQuery(
            limit=self.limit,
            cursor=None,
            source_id=self.source_id,
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


def order_key(record: Mapping[str, Any], model: str) -> str:
    """The total-order key *record* pages by."""
    return str(record.get(ORDER_KEYS[model], ""))


def sort_records(records: Iterable[Mapping[str, Any]], model: str) -> list[dict[str, Any]]:
    """*records* in the one order every implementation must page in."""
    return sorted((dict(record) for record in records), key=lambda item: order_key(item, model))


def keyset_page(
    ordered: Sequence[Mapping[str, Any]],
    query: PagedQuery,
    model: str,
    *,
    total: int | None = None,
) -> Page:
    """One page of an already-filtered, already-sorted sequence.

    A keyset page, not an offset one: the cursor is the last key returned, so a
    record inserted before the cursor cannot shift a later page and cause a
    record to be skipped. ``T-101``'s SQL does the same with ``WHERE id > ?``,
    and because both use :func:`encode_cursor` the two produce the same tokens
    for the same position — which is what makes ``T-104``'s rebuild-equivalence
    test a page-for-page comparison rather than a re-implementation.
    """
    start = query.start_key()
    if start is not None:
        remaining = [row for row in ordered if order_key(row, model) > start]
    else:
        remaining = list(ordered)
    window = [dict(row) for row in remaining[: query.limit]]
    exhausted = len(remaining) <= query.limit
    next_cursor = (
        None
        if exhausted or not window
        else encode_cursor(query.fingerprint, order_key(window[-1], model))
    )
    return Page(
        items=window,
        limit=query.limit,
        next_cursor=next_cursor,
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
