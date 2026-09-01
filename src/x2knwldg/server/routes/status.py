"""``GET /api/status`` — the one endpoint that answers in every state.

Every other route refuses with ``503 index_unavailable`` unless the index is
``ready``. This one must not, and that is why
:meth:`~x2knwldg.repository.base.IndexRepository.status` *returns* an
:class:`~x2knwldg.repository.base.IndexStatus` instead of raising: ``absent`` is
a **reported state**, not a failure. A UI that got a ``503`` for an unbuilt
project would have no way to tell "never indexed" from "the server is broken",
and the first of those is the ordinary state of a fresh checkout.

The ``503`` the frozen document lists for this path is therefore reachable only
through the generic handlers — a repository that raises while being asked what
it is. It is not something this route decides.

The payload is ``IndexStatus.payload()`` verbatim. In particular ``runs`` is
passed through exactly as the repository produced it (D-050): ``SqliteRepository``
scanned a filesystem and can name what it could not index, ``MemoryRepository``
did not and omits the key. Synthesising ``skipped: []`` here would turn "nobody
looked" into "we looked and found none", which is a claim about the user's disk
that this process never checked.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from ...repository.base import IndexRepository
from ..deps import repository
from ..envelope import envelope

router = APIRouter(tags=["status"])


@router.get("/status")
def get_status(repo: IndexRepository = Depends(repository)) -> dict[str, Any]:
    """``StatusResponse``: index state, counts, tallies, adapters, and runs."""
    return envelope(repo.status().payload())
