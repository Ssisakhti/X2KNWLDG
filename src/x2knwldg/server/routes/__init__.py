"""One module per group of endpoints; this file only lists them.

The order here is the order they are matched in. ``sources`` must come before
nothing in particular — FastAPI matches on the full path template, so
``/api/sources/{source_id}`` and ``/api/sources/{source_id}/entities`` do not
compete — but ``graph`` declares ``/api/graph/neighborhood/{entity_id}``
alongside ``/api/graph``, and keeping them in one module is what stops a later
edit from separating them.
"""

from __future__ import annotations

from .entities import router as entities_router
from .graph import router as graph_router
from .media import router as media_router
from .search import router as search_router
from .sources import router as sources_router
from .status import router as status_router

#: Included by :func:`x2knwldg.server.app.create_app`, all under ``/api``.
ROUTERS = (
    status_router,
    sources_router,
    entities_router,
    media_router,
    search_router,
    graph_router,
)
