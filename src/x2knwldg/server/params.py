"""The query parameters the frozen document declares, declared once.

Six endpoints take ``limit`` and ``cursor`` with identical bounds. Writing them
out per route is how the ``maximum`` drifts on one of them: the contract says
``1..500`` with a default of ``50``, and these constants are that sentence.

The bounds are enforced **twice**, and that is deliberate rather than
redundant: here, so a bad value is a ``400`` before any work happens and the
generated OpenAPI reflects the real limits; and again in
``PagedQuery.__post_init__``, so an implementation reached by any other caller
cannot skip the check. Neither can drift silently:
``test_api_hardening.test_every_query_parameter_bound_matches_the_frozen_document``
compares the *generated* document, parameter by parameter and bound by bound,
against the frozen one, and
``test_the_page_limit_the_document_publishes_is_the_one_enforced`` walks the
same number through this module, ``constants``, ``PageInfo`` and a live request.

This paragraph used to name ``tests/test_api_contract`` for that comparison and
no such comparison existed — the only check was on path *names*. Editing
``"maximum": 500`` to ``1000`` in the frozen document left the whole suite green
while the server went on refusing ``limit=501``: a published contract and an
enforced one that disagreed, with a docstring asserting they could not.
"""

from __future__ import annotations

from typing import Any

from fastapi import Query

from ..constants import MAX_PAGE_LIMIT

MIN_LIMIT = 1
#: D-101: stated once, in `constants`, so the MCP surface cannot disagree.
MAX_LIMIT = MAX_PAGE_LIMIT
DEFAULT_LIMIT = 50
MAX_CURSOR_LENGTH = 512
MAX_QUERY_LENGTH = 512
MIN_DEPTH = 1
MAX_DEPTH = 3


def limit_param(default: int = DEFAULT_LIMIT) -> Any:
    return Query(
        default,
        ge=MIN_LIMIT,
        le=MAX_LIMIT,
        description="Records per page.",
    )


def cursor_param() -> Any:
    return Query(
        None,
        min_length=1,
        max_length=MAX_CURSOR_LENGTH,
        description=(
            "Opaque continuation token from a previous page's `page.next_cursor`. "
            "Bound to the query that issued it, and to this process: a token does "
            "not survive a restart and is refused as `invalid_request` afterwards. "
            "Treat that as 'start again', not as an error."
        ),
    )
