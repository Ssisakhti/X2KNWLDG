"""What the SQLite index refuses, in the taxonomy the seam already speaks.

Track A adds no error *codes*. D-030 fixed four (``invalid_id``,
``invalid_request``, ``not_found``, ``index_unavailable``) and D-044 extended it
by two more; every one of those decisions is recorded in the ledger under
``docs/``, which no track agent owns. So a new code here would be a taxonomy
change made in the wrong place, and these classes deliberately inherit their
``code`` and ``http_status`` from :mod:`x2knwldg.repository` instead.

That is not a workaround. The API contract is frozen and Track B routes on
``code``/``http_status`` alone: a store failure that presented a seventh code
would reach a route that has no branch for it. What the index needs to say is
already sayable —

* a request arrived for an index that is absent, mid-build or broken →
  :class:`~x2knwldg.repository.IndexUnavailable` (``index_unavailable``, 503),
  which is exactly the state machine ``INDEX_STATES`` describes;
* the store itself cannot do its job → :class:`StoreError` below, which is
  ``internal``/500, because the request was fine and the index is not.

If a future need genuinely cannot be expressed this way, the fix is a ledger
entry and an ``openapi.json`` change first, and a subclass here second.
"""

from __future__ import annotations

from ..repository import RepositoryError

__all__ = [
    "StoreError",
    "Fts5Unavailable",
    "SchemaTooNew",
    "IndexCorrupt",
]


class StoreError(RepositoryError):
    """The index cannot do its job. ``internal``/500, inherited deliberately.

    The request that provoked this was well formed; the store is the part that
    failed. That is the distinction ``RepositoryError`` already draws, so this
    adds a name and a docstring rather than a code.
    """


class Fts5Unavailable(StoreError):
    """This SQLite build has no FTS5, so the search index cannot exist.

    Refused rather than worked around. A fallback to a second ranking function
    would make search a different answer on different machines while both
    reported success — the "two disagreeing views of one dataset" defect ADR
    0004 was raised to fix, and the reason ``T-104``'s equivalence proof exists
    at all. A machine that cannot build the index says so.
    """


class SchemaTooNew(StoreError):
    """The database on disk was written by a newer schema than this code knows.

    Refused, never truncated or "upgraded" downward. A forward-only migration
    list can say what version 4 did to version 3; it cannot say what version 5
    did, so code at version 4 opening a version 5 file would be answering from a
    schema it does not understand. The index is a rebuildable cache (ADR 0001
    invariant 3) — deleting it is always safe, and is the fix.
    """


class IndexCorrupt(StoreError):
    """The stored records cannot be paged or drawn honestly.

    The same two conditions ``repository.check_index_integrity`` refuses — a
    duplicate id, and an edge naming an endpoint no entity record has — reaching
    the store rather than the seam. Refusing beats serving a page that silently
    drops a record while ``total`` goes on counting it.
    """
