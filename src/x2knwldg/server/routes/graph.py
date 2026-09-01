"""``GET /api/graph`` and ``GET /api/graph/neighborhood/{entity_id}``.

The two views the Knowledge Map is drawn from: a bounded slice of the whole
graph, and a bounded walk out from one entity. They live in one module because
they answer the same question at two scales, and because splitting them is how
``/api/graph/neighborhood/{entity_id}`` ends up matched by a route that was
written for ``/api/graph``.

What this module does **not** do is as much of its job as what it does:

* It does not compute ``truncated``. The repository knows whether ``limit`` cut
  the result short; a route that recomputed it would be a second opinion on a
  fact the Map cannot afford two of (canvas plan: never present a partial graph
  as the whole one).
* It does not add, drop, or re-check edges. ``graph()`` already guarantees that
  every edge it returns runs between nodes it returned, and ``neighborhood()``
  the same. Filtering here would either duplicate that rule or contradict it.
* It does not catch :class:`~x2knwldg.repository.base.RepositoryError`. The
  repository decides what kind of refusal a refusal is and with what status
  (D-030); the global handler renders it. ``404`` is the one status the route
  makes itself, out of ``None``, because absence is a return value and not an
  exception.
* It does not validate ``entity_id``, ``source_id``, ``provenance_class`` or
  ``relation_vocabulary`` before handing them over.
  :class:`~x2knwldg.repository.base.NeighborhoodQuery` and
  :class:`~x2knwldg.repository.base.GraphQuery` refuse what the contract does
  not allow, and they distinguish a *malformed* id (``400 invalid_id``) from a
  *bad* filter value (``400 invalid_request``) — a distinction a ``pattern`` on
  the parameter would flatten into one code. A malformed id is rejected, never
  rewritten and never joined onto a path (ADR 0003 / D-020); a well-formed id
  naming nothing is the ``404``, and the two are never collapsed.

``depth`` is the one bound declared here as well as in the query object, for
the reason ``params`` gives for ``limit``: a value outside ``1..3`` is refused
before any work happens. It is never clamped — answering ``depth=4`` with
``depth=3`` would answer a question the client did not ask, and the response
echoes ``depth`` back, so the client would be told a bound it never set.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Path, Query

from ...repository import GraphQuery, IndexRepository, NeighborhoodQuery
from ..deps import repository
from ..envelope import envelope
from ..errors import NotFound
from ..params import MAX_DEPTH, MIN_DEPTH, cursor_param, limit_param

router = APIRouter(tags=["graph"])


def _source_id_param() -> Any:
    return Query(None, description="Restrict to one source.")


def _provenance_class_param() -> Any:
    return Query(
        None,
        description=(
            "Filter on origin: source evidence, recorded synthesis, or user "
            "content. One of `source`, `derived`, `user`."
        ),
    )


def _relation_vocabulary_param() -> Any:
    return Query(
        None,
        description=(
            "Filter on which of the three edge vocabularies an edge belongs to. "
            "One of `canonical`, `library_synthetic`, `user`."
        ),
    )


@router.get("/graph")
def get_graph(
    limit: int = limit_param(),
    cursor: str | None = cursor_param(),
    source_id: str | None = _source_id_param(),
    provenance_class: str | None = _provenance_class_param(),
    relation_vocabulary: str | None = _relation_vocabulary_param(),
    repo: IndexRepository = Depends(repository),
) -> dict[str, Any]:
    """A page of nodes with the edges that run between them.

    ``data`` is the whole ``GraphPayload`` object rather than an array, so this
    is :func:`~x2knwldg.server.envelope.envelope` with ``page`` beside it and
    not :func:`~x2knwldg.server.envelope.paged`. The difference matters: a graph
    page is a page of **nodes** (paging over edges would silently drop an entity
    that has no relations), and the edges travel with them rather than being the
    thing counted.

    A node need not belong to any source — a concept belongs to none (D-016) —
    so nothing here assumes ``source_id`` is present on a node.
    """
    page = repo.graph(
        GraphQuery(
            limit=limit,
            cursor=cursor,
            source_id=source_id,
            provenance_class=provenance_class,
            relation_vocabulary=relation_vocabulary,
        )
    )
    return envelope(page.payload(), page=page.page_info())


@router.get("/graph/neighborhood/{entity_id}")
def get_neighborhood(
    entity_id: str = Path(
        ...,
        description="Three-part global id, `<source_type>:<external_id>:<local_id>`.",
    ),
    depth: int = Query(
        MIN_DEPTH,
        ge=MIN_DEPTH,
        le=MAX_DEPTH,
        description="Hops from the centre.",
    ),
    limit: int = limit_param(),
    relation_vocabulary: str | None = _relation_vocabulary_param(),
    repo: IndexRepository = Depends(repository),
) -> dict[str, Any]:
    """The bounded neighborhood of one entity.

    No ``page``, and that asymmetry with ``/api/graph`` is the contract's:
    ``NeighborhoodResponse`` forbids the member outright. A neighborhood is
    bounded by ``depth`` and ``limit`` and says so with ``truncated``, rather
    than being walked page by page — so there is no cursor to carry and no
    position to resume from.

    Any entity is a legitimate centre, including a concept, which belongs to no
    source (D-016) and would be unreachable if a centre had to name one.

    The ``404`` message names no id. Echoing an unknown identifier back reflects
    the caller's input into the response body, and the caller already knows what
    it asked for.
    """
    result = repo.neighborhood(
        NeighborhoodQuery(
            entity_id=entity_id,
            depth=depth,
            limit=limit,
            relation_vocabulary=relation_vocabulary,
        )
    )
    if result is None:
        raise NotFound("No entity in the index has that id.")
    return envelope(result.payload())
