"""``GET /api/search`` — the one endpoint that answers a question, not an id.

Two things make this route different from the other five paged ones, and both
are contract, not preference:

* **The hits are not v1 records.** Every other endpoint pages over ``Source``,
  ``EntityRef``, ``Artifact`` or ``IndexedRelation``. A search hit is
  ``query.search_knowledge``'s own shape, field for field, plus D-028's two
  additive fields — ``video_id`` stays ``video_id`` and ``id`` stays the
  canonical unit id (ADR 0001 invariant 6). The repository hands them over
  already shaped; this module passes them through verbatim. Renaming one here
  would create a third vocabulary for a fact the CLI and the MCP tools already
  name.
* **The response echoes the query.** ``SearchResponse`` carries a ``query``
  member the other list responses do not, so a client firing several searches
  at once cannot attribute one response to another's question.

What this route does **not** do: rank. Ranking is ``query.rank_documents``
(D-046); FTS5 is candidate retrieval feeding it. Sorting, re-scoring or
trimming the page here would be a second ranking rule, and the two would
disagree the day one of them changed.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from ...repository.base import IndexRepository, SearchQuery
from ..deps import repository
from ..envelope import paged
from ..params import MAX_QUERY_LENGTH, cursor_param, limit_param

router = APIRouter(tags=["search"])


def query_param() -> Any:
    """``q``, required and bounded exactly as the frozen document declares it.

    Required at the framework level so a request with no ``q`` is refused
    before any work happens; ``handle_validation_error`` renders that as
    ``400 invalid_request`` rather than FastAPI's ``422``, which the contract
    does not list. ``SearchQuery.__post_init__`` refuses it a second time, and
    also refuses the case a length bound cannot see — a whitespace-only query,
    which is a bad request rather than a search that matches nothing.
    """
    return Query(
        ...,
        min_length=1,
        max_length=MAX_QUERY_LENGTH,
        description="The query. Empty or whitespace-only is `400 invalid_request`.",
    )


@router.get("/search")
def search(
    q: str = query_param(),
    limit: int = limit_param(),
    cursor: str | None = cursor_param(),
    source_id: str | None = Query(None, description="Restrict to one source."),
    include_transcript: bool = Query(
        True,
        description=(
            "Whether transcript captions are searched as well as knowledge units. "
            "Mirrors `include_transcript_fallback`."
        ),
    ),
    repo: IndexRepository = Depends(repository),
) -> dict[str, Any]:
    """A page of hits, most relevant first.

    Every refusal below is the repository's: a malformed ``source_id`` is
    ``invalid_id``, an empty ``q`` or a cursor that does not belong to this
    query is ``invalid_request``, and an index that is not ready is
    ``index_unavailable`` — each with the status the repository chose (D-030).
    None of them is caught here, because a route that re-raised one would be a
    second place the taxonomy lives.

    ``page.total`` is passed through as the repository states it, including
    ``null``: unknown, never zero. A source whose canonical files could not be
    read makes the count unknowable, and reporting it as a number would be an
    invented fact.
    """
    query = SearchQuery(
        q=q,
        limit=limit,
        cursor=cursor,
        source_id=source_id,
        include_transcript=include_transcript,
    )
    page = repo.search(query)
    # `query.q`, not the raw parameter: the echo names the query as *executed*,
    # which is what a client matching responses to requests needs.
    return paged(page.items, page.page_info(), query=query.q)
