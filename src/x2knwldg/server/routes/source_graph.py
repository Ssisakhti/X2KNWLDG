"""``GET /api/source-graph`` and ``GET /api/source-graph/neighborhood/{source_id}``.

The Source Map's two reads (`T-254`), and the first thing in the project that
lets anything *read* a source node, a source brief or a cross-source relation.
The records they serve have existed and been gated since `T-251`–`T-253`; the
response shapes have been frozen as components with no paths since `T-251`
(D-254), and these two operations are what those components were frozen for.

They live in one module for the reason ``routes/graph.py``'s two do: they answer
the same question at two scales, and separating them is how the neighbourhood
path ends up matched by a route written for the collection.

What this module does not do, and each omission is the point:

* It does not decide which relations a source has, how they are bounded, or
  which of them were left out. The repository does, and both implementations do
  it with one set of shared functions — a route that re-derived any of it would
  be a second opinion on a fact the Map cannot afford two of.
* It does not read a canonical file. The brief is a repository method
  (``source_knowledge``), not a path this module joins onto an id — ADR 0002's
  seam, and D-042's rule that no id reaches a path.
* It does not compute ``truncated``, ``counts`` or ``basis_returned``. Those
  come out of the payload the repository built, because the bound is the
  repository's and reporting it is what makes it honest.
* It does not catch :class:`~x2knwldg.repository.base.RepositoryError`. The
  repository decides what kind of refusal a refusal is and with what status
  (D-030); the global handler renders it. ``404`` is the one status this module
  makes itself, out of ``None``, because absence is a return value.

The path parameter is a **two-part source id**, not the three-part global id of
the source node. That is what the frozen ``SourceIdPath`` parameter declares and
what the Reader, ``/api/sources/{source_id}`` and every board file already
address a source by; the node's global id comes back as ``center_id``, so a
client that batches requests can attribute the answer without constructing an id
of its own.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Path

from ...repository import IndexRepository, SourceGraphQuery, SourceNeighborhoodQuery
from ..deps import repository
from ..envelope import envelope
from ..errors import NotFound
from ..params import cursor_param, limit_param

router = APIRouter(tags=["source-graph"])


@router.get("/source-graph")
def get_source_graph(
    limit: int = limit_param(),
    cursor: str | None = cursor_param(),
    repo: IndexRepository = Depends(repository),
) -> dict[str, Any]:
    """One node per acquired source, with the relations among them.

    ``data`` is the whole ``SourceGraphPayload`` with ``page`` beside it, so
    this is :func:`~x2knwldg.server.envelope.envelope` and not
    :func:`~x2knwldg.server.envelope.paged` — the same shape ``/api/graph``
    uses, and for the same reason: the page is a page of **nodes**, and the
    relations travel with them rather than being the thing counted.

    Every acquired source appears exactly once across a full walk, whatever its
    status. A ``FAIL`` run is a source that exists, and a Map that omitted it
    would report a smaller library than the one on disk.
    """
    page = repo.source_graph(SourceGraphQuery(limit=limit, cursor=cursor))
    return envelope(page.payload(), page=page.page_info())


@router.get("/source-graph/neighborhood/{source_id}")
def get_source_neighborhood(
    source_id: str = Path(
        ...,
        description="Two-part source id, `<source_type>:<external_id>`.",
    ),
    limit: int = limit_param(),
    repo: IndexRepository = Depends(repository),
) -> dict[str, Any]:
    """One selected source, its readable brief, and its qualified relations.

    No ``page``, and the asymmetry with ``/api/source-graph`` is the contract's:
    ``SourceNeighborhoodResponse`` forbids the member outright. The body is
    bounded by ``limit`` and says so with ``truncated``, and each relation's
    basis is bounded separately and states both counts, so neither cut is
    silent.

    The ``404`` names no id. Echoing an unknown identifier back reflects the
    caller's input into the response body, and the caller already knows what it
    asked for.
    """
    found = repo.source_neighborhood(
        SourceNeighborhoodQuery(source_id=source_id, limit=limit)
    )
    if found is None:
        raise NotFound("No source in the index has that id.")
    return envelope(found.payload())
