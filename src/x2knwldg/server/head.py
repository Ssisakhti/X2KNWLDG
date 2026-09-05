"""``HEAD`` wherever ``GET`` is answered, without a second declared operation.

FastAPI's ``APIRoute`` does not add ``HEAD`` alongside ``GET``, so every route
answered ``405`` to it — including ``HEAD /api/media/{artifact_id}``, which is
the standard way a player discovers ``Content-Length`` and ``Accept-Ranges``
before it asks for a range, and ``405`` is a status the frozen document declares
on no path.

Adding ``"HEAD"`` to each route's ``methods`` would have worked and would also
have made FastAPI *generate* thirteen new ``head`` operations, which the frozen
contract does not declare and ``types.d.ts`` does not carry. RFC 9110 defines
``HEAD`` as ``GET`` without the body, so it needs no declaration of its own: the
published surface is unchanged and the server simply honours the method the
specification already defines over it. Doing that in one ASGI middleware also
means the rule cannot be forgotten on the fourteenth route.
"""

from __future__ import annotations

from typing import Any

#: Set on the ASGI scope for a request that arrived as ``HEAD``. A route reads
#: it where knowing costs less than producing a body nobody will receive —
#: ``routes/media.py`` answers the length without opening the file.
#:
#: **It is not a licence to answer a different question.** ``routes/media.py``
#: read this key *before* computing the requested byte range and then answered
#: ``200`` with the whole file's length, so ``HEAD`` with ``Range: bytes=0-9``
#: reported ``200``/``508`` where ``GET`` reported ``206``/``bytes 0-9/508``.
#: RFC 9110 §9.3.2 requires the header fields a ``GET`` would have sent, and a
#: player probing with ``HEAD Range: bytes=0-1`` — the discovery named three
#: paragraphs above — read that as "ranges unsupported" and downloaded the
#: whole artifact. The branch is below the range arithmetic now: what this key
#: may skip is the body, and only the body.
HEAD_SCOPE_KEY = "x2knwldg.head_request"


class HeadAsGet:
    """Route a ``HEAD`` as its ``GET`` and send the headers without the body.

    Pure ASGI rather than ``BaseHTTPMiddleware`` because it has to change the
    scope *before* routing and suppress body messages *after* the response is
    produced, and because a streaming response must not be buffered here just
    to be discarded.
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope.get("type") != "http" or scope.get("method") != "HEAD":
            await self.app(scope, receive, send)
            return

        scope = dict(scope)
        scope["method"] = "GET"
        scope[HEAD_SCOPE_KEY] = True

        finished = False

        async def send_headers_only(message: Any) -> None:
            nonlocal finished
            if message.get("type") != "http.response.body":
                await send(message)
                return
            # One empty terminal body message, whatever the response sent.
            # `Content-Length` is left as the ``GET`` would have stated it,
            # which is the whole point of the method: RFC 9110 requires the
            # headers a ``GET`` would carry.
            if finished:
                return
            finished = True
            await send({"type": "http.response.body", "body": b"", "more_body": False})

        await self.app(scope, receive, send_headers_only)
