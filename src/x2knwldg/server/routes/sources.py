"""The four ``/api/sources`` endpoints: the list, one source, its entities, its relations.

Each one is the same three steps — translate the request into a repository
query, ask, envelope the answer — and everything interesting is in what is
*not* done here:

* **No id is repaired.** ``source_id`` arrives from outside the process, so it
  is handed to the repository, which parses it with ``ids.py`` and raises
  ``InvalidId`` (``400``) when it is not a source id. Nothing in this module
  joins it onto a path, trims it, or replaces a character in it — ADR 0003
  decision 2, and the reason ``_safe_identifier`` is not importable here.
* **No refusal is re-labelled.** ``InvalidId``, ``InvalidQuery`` and
  ``IndexUnavailable`` carry their own status (D-030) and propagate to the
  handler registered in ``errors.install``. A route that caught one and chose a
  different status would put the taxonomy in thirteen places.
* **No record is reshaped.** ``Page.page_info()`` and ``SourceDetail.payload()``
  are already the frozen objects; the envelope is added around them and nothing
  is added inside them.

**Absence and malformation are different answers.** A well-formed id naming
nothing is ``404 not_found``; an id that is not an id at all is ``400
invalid_id``. Collapsing them would hide a traversal attempt behind an ordinary
"no such source" (ADR 0003 invariant 3).

**The sub-collections check existence first.** ``list_entities`` and
``list_relations`` answer an unknown source with an empty page, by design — the
repository does not answer the same question twice. But an empty page *asserts*
that the source exists and has nothing, so these two routes ask
:meth:`~x2knwldg.repository.base.IndexRepository.get_source` first and raise
:class:`~x2knwldg.server.errors.NotFound` when it is ``None``. The frozen
document lists ``404`` on both paths; this is what produces it.

The closed-vocabulary filters (``status``, ``provenance_class``, ``kind``,
``relation_vocabulary``) are declared as plain strings and validated by the
query dataclasses rather than re-stated as framework enums. Those vocabularies
are ``constants.py``'s — ``kind`` alone is thirty-one values — and a second copy
in a route is the copy that goes stale. The refusal is identical either way:
``InvalidQuery`` renders as ``400 invalid_request``.

``source_type`` is **not** one of them, and this paragraph used to list it as
though it were. ``common.schema.json#/$defs/sourceType`` is an open pattern,
``^[a-z][a-z0-9_]*$``, and says so in its own words: "open by design: adding a
source type must not require a schema change". An adapter namespace arrives by
adding an adapter — ``twitter`` did, on a surface frozen when only ``youtube``
existed — so ``?source_type=nonexistent_type`` is a well-formed filter matching
nothing, and ``200`` with an empty page is the true answer to it, not a
refusal. Reading the old sentence, the ``200`` looked like a missing check.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Path, Query

from ...repository.base import (
    EntityQuery,
    IndexRepository,
    RelationQuery,
    SourceQuery,
)
from ..deps import repository
from ..envelope import envelope, paged
from ..errors import NotFound
from ..params import cursor_param, limit_param

router = APIRouter(tags=["sources"])

#: ``SourceIdPath``. Declared without a pattern on purpose: the grammar lives in
#: ``ids.py`` (ADR 0003 invariant 4), and a regex here would be a second
#: definition of what a source id is — one that would answer a malformed id with
#: ``invalid_request`` where the contract says ``invalid_id``.
_SOURCE_ID = Path(
    ...,
    description="Two-part source id, `<source_type>:<external_id>`.",
)


def _empty_page_or_404(repo: IndexRepository, source_id: str) -> None:
    """Decide, **after** the page was read, whether an empty page is a ``404``.

    This used to run *before* the real query, as ``_require_source``: a
    ``get_source`` whose only job was to turn an empty page into a ``404``,
    followed by the query that actually answers. Two round trips for the
    common, non-empty case — and a window between them. If the source vanished
    in that window the route answered ``200`` with an empty page, which
    *asserts* that the source exists and holds nothing: exactly the claim the
    helper was written to prevent.

    Asked only when the page came back empty, so a source with entities costs
    one read, and the existence question is decided after the data rather than
    before it. The remaining window runs the other way — a source that
    disappears between the query and this check answers ``404`` for something
    that was there a moment ago — which is a true statement about now.

    ``InvalidId`` (``400``) for an id that is not a source id, and
    ``IndexUnavailable`` (``503``) when the index cannot answer at all, both
    still come from the repository and are rendered by the shared handler.
    """
    if repo.get_source(source_id) is None:
        raise NotFound(f"no source has the id {source_id!r}")


@router.get("/sources")
def list_sources(
    repo: IndexRepository = Depends(repository),
    limit: int = limit_param(),
    cursor: str | None = cursor_param(),
    source_type: str | None = Query(None, description="Restrict to one adapter namespace."),
    status: str | None = Query(None, description="Filter on the copied validation status."),
) -> dict[str, Any]:
    """``SourceListResponse``: one page of ``Source`` records."""
    page = repo.list_sources(
        SourceQuery(limit=limit, cursor=cursor, source_type=source_type, status=status)
    )
    return paged(page.items, page.page_info())


@router.get("/sources/{source_id}")
def get_source(
    source_id: str = _SOURCE_ID,
    repo: IndexRepository = Depends(repository),
) -> dict[str, Any]:
    """``SourceDetailResponse``: the source and the artifacts it names."""
    detail = repo.get_source(source_id)
    if detail is None:
        raise NotFound(f"no source has the id {source_id!r}")
    return envelope(detail.payload())


@router.get("/sources/{source_id}/entities")
def list_source_entities(
    source_id: str = _SOURCE_ID,
    repo: IndexRepository = Depends(repository),
    limit: int = limit_param(),
    cursor: str | None = cursor_param(),
    provenance_class: str | None = Query(
        None, description="Filter on origin: source evidence, recorded synthesis, or user content."
    ),
    kind: str | None = Query(None, description="Filter on knowledge kind."),
    min_confidence: float | None = Query(
        None,
        description=(
            "Keep only entities whose copied confidence is at least this value. "
            "An entity with a null confidence is excluded."
        ),
    ),
) -> dict[str, Any]:
    """``EntityListResponse``: one page of the source's ``EntityRef`` records."""
    page = repo.list_entities(
        EntityQuery(
            limit=limit,
            cursor=cursor,
            source_id=source_id,
            provenance_class=provenance_class,
            kind=kind,
            min_confidence=min_confidence,
        )
    )
    if not page.items:
        _empty_page_or_404(repo, source_id)
    return paged(page.items, page.page_info())


@router.get("/sources/{source_id}/relations")
def list_source_relations(
    source_id: str = _SOURCE_ID,
    repo: IndexRepository = Depends(repository),
    limit: int = limit_param(),
    cursor: str | None = cursor_param(),
    relation_vocabulary: str | None = Query(
        None, description="Filter on which of the three edge vocabularies an edge belongs to."
    ),
) -> dict[str, Any]:
    """``RelationListResponse``: one page of the source's ``IndexedRelation`` records."""
    page = repo.list_relations(
        RelationQuery(
            limit=limit,
            cursor=cursor,
            source_id=source_id,
            relation_vocabulary=relation_vocabulary,
        )
    )
    if not page.items:
        _empty_page_or_404(repo, source_id)
    return paged(page.items, page.page_info())
