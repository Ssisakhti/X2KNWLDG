"""One entity, one artifact — both addressed by a three-part global id (D-011).

``GET /api/entities/{entity_id}`` and ``GET /api/artifacts/{artifact_id}``. Two
endpoints, two repository methods, and no logic of their own: the record the
repository returns is the record that goes on the wire. ``EntityResponse.data``
and ``ArtifactResponse.data`` ``$ref`` ``schemas/v1/entity_ref.schema.json`` and
``schemas/v1/artifact.schema.json`` directly (D-026), so reshaping, filtering or
enriching here would put a second shape in front of the frozen one.

``GET /api/media/{artifact_id}`` reuses ``get_artifact`` for the *bytes*; that is
``T-108``'s and lives in ``routes/media.py``. This module answers with the
**record** — what the file is, where it sits, and whether it was there at index
time. An artifact that was absent at index time is a ``200`` carrying
``available: false``: its record exists, and "the file is gone" is a fact about
the file, not about the id.

What this module is really about
--------------------------------

The path parameter is untrusted input, and this is the boundary ADR 0003 is
written about. Three rules follow, and all three are enforced by *not* doing
something:

1. **The id is never rewritten.** No ``strip``, no ``basename``, no substitution.
   ``pipeline._safe_identifier`` is not imported here and must not be: it guards
   the id a run is *created* at, and a lookup that rewrites returns a different
   record than the one asked for while reporting no traversal at all (D-020).
2. **The id is never joined onto a path.** These two endpoints resolve an id
   against the index and touch no filesystem, so there is nothing here for a
   ``..`` to traverse *into*. Containment is ``/api/media``'s problem precisely
   because ``/api/media`` is the only one of the three that opens a file.
3. **The grammar has one implementation.** ``ids.parse_global_id`` — reached
   through the repository — decides what a global id is (ADR 0003 invariant 4).
   The route does not pre-validate with a regex of its own, because a second
   copy of the rule is a rule that can disagree with the first.

So a malformed id becomes ``InvalidId`` inside the repository, before anything
is read, and the global handler renders it as ``400 invalid_id`` with the status
the repository chose (D-030). A **well-formed** id naming nothing is a different
answer: the repository returns ``None`` and the route raises
:class:`~x2knwldg.server.errors.NotFound`. Collapsing those two into one status
is the failure D-020 exists to prevent — it hides a traversal attempt behind an
ordinary "no such thing".

An id the router cannot match
-----------------------------

A path parameter matches one segment, so an id containing a slash —
``../../etc/passwd``, ``%2e%2e%2f..``, ``/etc/passwd`` — does not match
``/entities/{entity_id}`` and never reaches this module: the router declines it
and the ``404`` handler in ``errors.py`` renders the frozen ``ErrorResponse``.
That is the answer ``T-108`` fixed for every id-taking route, and it is not the
``400`` the *segment* cases get.

Making it a ``400`` would mean declaring a second, ``:path`` route per endpoint.
That was tried and reverted: the served surface is exactly the eleven frozen
paths — ``test_api_hardening.test_the_served_surface_is_exactly_the_frozen_one``
says "not ten, and not twelve" — and a route the contract does not declare is a
contract change, which this task is not. Nothing is lost that matters: no
``globalId`` contains a slash (``common.schema.json#/$defs/idPart`` excludes one
so ids split unambiguously), so such a request cannot name an entity; nothing is
read, nothing is rewritten, and no record is returned. The distinction D-020
actually protects — a **well-formed** id refused versus a well-formed id
absent — is decided inside a single segment, and that is where the ``400`` is.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from ...repository.base import IndexRepository
from ..deps import repository
from ..envelope import envelope
from ..errors import NotFound

router = APIRouter()


def _entity(entity_id: str, repo: IndexRepository) -> dict[str, Any]:
    """The one implementation, shared by the contract path and its catch-all.

    ``repo.get_entity`` raises ``InvalidId`` for a malformed id and returns
    ``None`` for a well-formed one that names nothing. Neither is caught here:
    the first is rendered by the global handler with the repository's own status
    (D-030), and the second is the route's ``404`` to make.
    """
    record = repo.get_entity(entity_id)
    if record is None:
        raise NotFound("No entity has that id.")
    return envelope(record)


def _artifact(artifact_id: str, repo: IndexRepository) -> dict[str, Any]:
    """As :func:`_entity`, for the ``Artifact`` record.

    ``available: false`` is **not** a ``404`` here. The record exists and states
    that the file did not at index time; ``/api/media`` is where that becomes a
    refusal, because that is the endpoint that promised bytes.
    """
    record = repo.get_artifact(artifact_id)
    if record is None:
        raise NotFound("No artifact has that id.")
    return envelope(record)


@router.get(
    "/entities/{entity_id}",
    tags=["entities"],
    response_model=None,
    summary="One entity by global id",
)
def get_entity(
    entity_id: str,
    repo: IndexRepository = Depends(repository),
) -> dict[str, Any]:
    """``EntityResponse`` — one ``EntityRef``, verbatim.

    A canonical concept is reachable here like any other entity. It carries
    ``source_id: null`` because a concept belongs to no source (D-016), and it
    is addressed as ``library:concepts:<hash>``; a lookup that required a source
    would make the 17 concepts in the library unaddressable by the id the index
    itself gives them.
    """
    return _entity(entity_id, repo)


@router.get(
    "/artifacts/{artifact_id}",
    tags=["artifacts"],
    response_model=None,
    summary="One artifact record",
)
def get_artifact(
    artifact_id: str,
    repo: IndexRepository = Depends(repository),
) -> dict[str, Any]:
    """``ArtifactResponse`` — metadata about the file, never the file."""
    return _artifact(artifact_id, repo)
