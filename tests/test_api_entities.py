"""`T-107` — ``GET /api/entities/{id}`` and ``GET /api/artifacts/{id}``.

Two lookups by three-part global id (D-011), and one question underneath them:
**does a malformed id come back as malformed?** D-020 and
[ADR 0003](../docs/adr/0003-reject-unsafe-identifiers.md) say a lookup must fail
rather than quietly answer about something else, and D-030 says that failure is
``400 invalid_id`` — never a ``404``, never an empty result, never a ``500``.
Collapsing "refused" into "absent" is the whole defect this task exists to
avoid, so the traversal battery below asserts the *code*, not merely "not 200".

Every test whose answer *could* differ between the two implementations runs on
both, through ``both_clients``. `T-104` proved ``MemoryRepository`` and
``SqliteRepository`` answer identically page for page, so a route that behaves
differently on one of them has found a **route** bug rather than an
implementation difference. Tests about the route's own shaping — that it adds no
field, that it answers no verb but ``GET`` — run on the oracle alone, because
the repository is not what they are asking about.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import api_harness
from api_harness import (
    assert_contract,
    assert_error,
    both_clients,
    client,
    memory_repository,
    project,
    requires_fastapi,
    requires_fts5,
    sqlite_repository,
)

pytestmark = [requires_fastapi, requires_fts5]


# --------------------------------------------------------------------------
# One project, built once. Every test below is a reader.
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def root(tmp_path_factory: Any) -> Path:
    """The three committed run fixtures as a project root.

    Module-scoped because nothing here writes: copying the fixtures, rebuilding
    the library and building the index once is the same evidence for every test.
    """
    return project(tmp_path_factory.mktemp("t107"))


@pytest.fixture(scope="module")
def known(root: Path) -> dict[str, Any]:
    """Real ids, read out of the index rather than hard-coded.

    A hard-coded id is a second copy of what the fixtures contain, and the copy
    is what goes stale when a fixture is regenerated. The one thing asserted
    about the ids themselves is the shape D-016 promises: a canonical concept is
    addressed as ``library:concepts:<hash>``.
    """
    from x2knwldg.repository import EntityQuery, SourceQuery

    repo = memory_repository(root)
    entities = repo.list_entities(EntityQuery(limit=500)).items
    sources = repo.list_sources(SourceQuery(limit=500)).items
    artifacts = [
        artifact
        for source in sources
        for artifact in repo.get_source(source["id"]).artifacts
    ]
    concepts = [e for e in entities if e["source_type"] == "library"]
    units = [e for e in entities if e["entity_type"] == "knowledge_unit"]

    assert units, "the fixtures must hold at least one knowledge unit entity"
    assert concepts, "rebuild_library must have produced at least one canonical concept"
    assert artifacts, "the fixtures must hold artifacts"

    return {
        "entities": entities,
        "artifacts": artifacts,
        "unit": units[0],
        "concept": concepts[0],
        "artifact": artifacts[0],
    }


# --------------------------------------------------------------------------
# The happy path, validated against the frozen components
# --------------------------------------------------------------------------


def test_an_entity_round_trips_on_both_implementations(root: Path, known: dict[str, Any]) -> None:
    """``EntityResponse``, and ``data`` is the repository's record verbatim."""
    entity_id = known["unit"]["global_id"]
    seen = {}
    for label, http in both_clients(root):
        response = http.get(f"/api/entities/{entity_id}")
        assert response.status_code == 200, f"{label}: {response.text}"
        body = response.json()
        assert_contract("EntityResponse", body)
        assert body["api_version"] == "v1"
        assert body["schema_version"] == "1.0"
        assert body["data"]["global_id"] == entity_id
        assert body["data"] == known["unit"], f"{label} reshaped the record"
        seen[label] = body
    assert seen["memory"] == seen["sqlite"], "the two implementations disagreed about one entity"


def test_an_artifact_round_trips_on_both_implementations(root: Path, known: dict[str, Any]) -> None:
    """``ArtifactResponse`` — metadata about the file, never the file."""
    artifact_id = known["artifact"]["id"]
    seen = {}
    for label, http in both_clients(root):
        response = http.get(f"/api/artifacts/{artifact_id}")
        assert response.status_code == 200, f"{label}: {response.text}"
        body = response.json()
        assert_contract("ArtifactResponse", body)
        assert body["data"]["id"] == artifact_id
        assert body["data"] == known["artifact"], f"{label} reshaped the record"
        seen[label] = body
    assert seen["memory"] == seen["sqlite"], "the two implementations disagreed about one artifact"


def test_every_entity_and_artifact_in_the_index_is_addressable(root: Path, known: dict[str, Any]) -> None:
    """Not a sample of one: every record the index holds resolves by its own id.

    A route that happened to work for the first knowledge unit and failed for a
    vault note whose id carries dots would pass a single-record test.
    """
    with client(memory_repository(root)) as http:
        for entity in known["entities"]:
            response = http.get(f"/api/entities/{entity['global_id']}")
            assert response.status_code == 200, f"{entity['global_id']}: {response.text}"
            assert_contract("EntityResponse", response.json())
            assert response.json()["data"] == entity
        for artifact in known["artifacts"]:
            response = http.get(f"/api/artifacts/{artifact['id']}")
            assert response.status_code == 200, f"{artifact['id']}: {response.text}"
            assert_contract("ArtifactResponse", response.json())
            assert response.json()["data"] == artifact


def test_a_canonical_concept_resolves_though_it_belongs_to_no_source(
    root: Path, known: dict[str, Any]
) -> None:
    """D-016: a concept has no ``source_id`` and is still an addressable entity.

    The failure this guards is a lookup that resolves an entity *through* its
    source — which would 404 all 17 concepts in the real library while
    ``/api/sources/{id}/relations`` went on returning the edges that name them.
    """
    concept_id = known["concept"]["global_id"]
    assert concept_id.startswith("library:concepts:"), "D-016 fixes the concept id shape"
    assert known["concept"]["source_id"] is None

    for label, http in both_clients(root):
        response = http.get(f"/api/entities/{concept_id}")
        assert response.status_code == 200, f"{label}: a concept 404'd: {response.text}"
        body = response.json()
        assert_contract("EntityResponse", body)
        assert body["data"]["source_id"] is None
        assert body["data"]["entity_type"] == "concept"


def test_an_artifact_absent_at_index_time_is_a_200_saying_so(tmp_path: Path) -> None:
    """``available: false`` is a fact about the file, not about the id.

    The frozen description says so in as many words: the record exists, and the
    honest answer is that the file does not. ``/api/media`` is where missing
    bytes become a refusal, because that is the endpoint that promised bytes.

    Every artifact in the committed fixtures is present, so the state is reached
    by deleting one **generated** file from a throwaway copy — never from
    ``raw/``, which is immutable evidence, and never from the committed fixtures
    themselves.
    """
    damaged = project(tmp_path, "pass-run")
    (damaged / "output" / "pass-run" / "report.md").unlink()

    for label, http in both_clients(damaged):
        response = http.get("/api/artifacts/youtube:fixture-pass:report")
        assert response.status_code == 200, f"{label}: an absent file 404'd: {response.text}"
        body = response.json()
        assert_contract("ArtifactResponse", body)
        assert body["data"]["available"] is False, label
        assert body["data"]["path"] == "output/pass-run/report.md", label


# --------------------------------------------------------------------------
# Malformed is not absent — the traversal battery (D-020, ADR 0003)
# --------------------------------------------------------------------------

#: ``(label, path_segment)`` — hostile ids that occupy **one** path segment, so
#: the router matches and the route is asked about them. Every one must be
#: ``400 invalid_id``. The segment is written as it travels on the wire:
#: percent-encoded where a literal would be resolved or rejected by the HTTP
#: client before the server ever saw it. ``%2e`` is a dot, ``%00`` a NUL,
#: ``%5c`` a backslash, ``%20`` a space, ``%0a`` a newline.
HOSTILE_IDS: tuple[tuple[str, str], ...] = (
    ("dot-dot as the external id", "youtube:..:KU-000001"),
    ("dot-dot as the local id", "youtube:fixture-pass:.."),
    ("percent-encoded dot-dot", "youtube:fixture-pass:%2e%2e"),
    ("single dot as the local id", "youtube:fixture-pass:."),
    ("windows path with backslashes", "youtube:..%5c..%5cwindows%5csystem32:x"),
    ("NUL byte in the local id", "youtube:fixture-pass:KU%00"),
    ("NUL byte in the external id", "youtube:fixture-pass%00:KU-000001"),
    ("NUL-truncated real id", "youtube:fixture-pass:KU-000001%00.json"),
    ("over-long local id", "youtube:fixture-pass:" + "a" * 600),
    ("over-long whole id", "a" * 900),
    ("two parts, not three", "youtube:fixture-pass"),
    ("four parts", "youtube:fixture-pass:KU-000001:extra"),
    ("empty external id", "youtube::KU-000001"),
    ("uppercase source type", "YOUTUBE:fixture-pass:KU-000001"),
    ("space in the local id", "youtube:fixture-pass:KU%20000001"),
    ("newline in the local id", "youtube:fixture-pass:KU-000001%0a"),
    ("leading dot in the local id", "youtube:fixture-pass:.hidden"),
    ("home-directory shorthand", "youtube:~:x"),
    ("shell expansion", "youtube:%24HOME:x"),
    ("wildcard", "youtube:*:x"),
)

#: The other half: hostile ids that carry a **slash** once decoded. A path
#: parameter matches one segment, so the router never matches them and the
#: route is never asked — see the module docstring in ``routes/entities.py``.
#: They are still asserted, because "the router declined it" must be *proved*
#: to be what happens rather than assumed: no record, no crash, and the frozen
#: error body rather than Starlette's own.
UNROUTABLE_IDS: tuple[tuple[str, str], ...] = (
    ("encoded traversal, whole id", "%2e%2e%2f%2e%2e%2fetc%2fpasswd"),
    ("literal dots, encoded slashes", "..%2f..%2fetc%2fpasswd"),
    ("slash inside a segment", "youtube:fixture-pass%2f..%2f..%2fetc:KU-000001"),
    ("traversal after a real id", "youtube:fixture-pass:KU-000001%2f..%2f..%2fetc%2fpasswd"),
    ("absolute posix path", "%2fetc%2fpasswd"),
    ("absolute path wearing a source type", "file:%2fetc%2fpasswd:x"),
    ("ssh key by home shorthand", "youtube:~%2f.ssh%2fid_rsa:x"),
    ("overlong utf-8 encoding of a dot", "%c0%ae%c0%ae%2f"),
    ("empty id", ""),
)

#: Everything the two tables hold, for the sweeps that only care that no
#: response leaks and none crashes.
ALL_HOSTILE_IDS = HOSTILE_IDS + UNROUTABLE_IDS


def _refusals(http: Any, prefix: str) -> list[str]:
    """Run :data:`HOSTILE_IDS` against one endpoint. Returns failure descriptions."""
    problems: list[str] = []
    for label, segment in HOSTILE_IDS:
        response = http.get(f"{prefix}/{segment}")
        body = response.text
        if response.status_code == 200:
            problems.append(f"{label}: answered 200 with a record: {body[:200]}")
            continue
        if response.status_code == 404:
            problems.append(f"{label}: reported a malformed id as absent (404), not refused (400)")
            continue
        if response.status_code >= 500:
            problems.append(f"{label}: crashed with {response.status_code}: {body[:200]}")
            continue
        try:
            assert_error(response, 400, "invalid_id")
        except AssertionError as exc:
            problems.append(f"{label}: {exc}")
    return problems


def test_hostile_entity_ids_are_refused_as_malformed_never_as_absent(root: Path) -> None:
    """Every routable id in the battery is ``400 invalid_id``, on both implementations.

    Asserted as the *code*, not as "not 200": a ``404`` here would be D-020's
    failure — a refused id reported as an ordinary absence.
    """
    for impl, http in both_clients(root):
        problems = _refusals(http, "/api/entities")
        assert not problems, f"{impl}:\n  " + "\n  ".join(problems)


def test_hostile_artifact_ids_are_refused_as_malformed_never_as_absent(root: Path) -> None:
    """The same battery against ``/api/artifacts``. Two endpoints, one rule."""
    for impl, http in both_clients(root):
        problems = _refusals(http, "/api/artifacts")
        assert not problems, f"{impl}:\n  " + "\n  ".join(problems)


def test_a_slash_bearing_id_is_declined_by_the_router_and_reads_nothing(root: Path) -> None:
    """:data:`UNROUTABLE_IDS`: no record, no crash, and the frozen error shape.

    A slash-bearing id cannot name an entity — ``idPart`` excludes a slash — so
    there is no answer being withheld here. What must hold is that the request
    dies at the router rather than reaching anything: never a ``200``, never a
    ``5xx``, and never Starlette's own ``{"detail": ...}`` body, which would
    teach a client that the envelope is optional.
    """
    for impl, http in both_clients(root):
        for label, segment in UNROUTABLE_IDS:
            for prefix in ("/api/entities", "/api/artifacts"):
                response = http.get(f"{prefix}/{segment}")
                where = f"{impl} {prefix} {label}"
                assert response.status_code != 200, f"{where}: returned a record: {response.text[:200]}"
                assert response.status_code < 500, f"{where}: crashed {response.status_code}"
                assert_error(response, response.status_code, response.json()["error"]["code"])
                assert response.json()["error"]["code"] in ("not_found", "invalid_id"), where


def test_a_hostile_id_is_never_rewritten_into_a_real_one(root: Path, known: dict[str, Any]) -> None:
    """The sanitiser failure mode, asserted directly (D-020, ADR 0003 invariant 2).

    ``_safe_identifier`` used to turn ``../other`` into ``_other``. Pointed at a
    lookup, that answers *about a different record* and reports no traversal at
    all. So: ids a rewriting sanitiser would collapse onto a **real** id must
    never return that record.
    """
    real = known["unit"]["global_id"]
    source_type, external_id, local_id = real.split(":", 2)
    refused = (
        f"{source_type}:{external_id}:%2e%2e{local_id}",
        f"{source_type}:{external_id}%00:{local_id}",
        f"{source_type}:{external_id}:{local_id}%00",
        f"{source_type}:{external_id}:{local_id}%20",
        f"{source_type}:{external_id}:%20{local_id}",
        f"{source_type.upper()}:{external_id}:{local_id}",
    )
    declined = (
        f"{source_type}:..%2f{external_id}:{local_id}",
        f"{source_type}:{external_id}%2f..%2f{external_id}:{local_id}",
        f"{source_type}:.%2f{external_id}:{local_id}",
        f"{source_type}:{external_id}:%2e%2e%2f{local_id}",
    )
    with client(memory_repository(root)) as http:
        for disguise in refused:
            response = http.get(f"/api/entities/{disguise}")
            assert response.status_code != 200, (
                f"{disguise!r} was rewritten into a record: {response.text[:200]}"
            )
            assert_error(response, 400, "invalid_id")
        for disguise in declined:
            response = http.get(f"/api/entities/{disguise}")
            assert response.status_code != 200, (
                f"{disguise!r} was rewritten into a record: {response.text[:200]}"
            )
            assert response.status_code < 500


def test_a_client_resolved_dot_segment_never_reaches_a_record(root: Path) -> None:
    """A literal ``../..`` in the URL is resolved by the *client*, not the server.

    ``httpx`` collapses dot segments while building the request, so
    ``/api/entities/../../etc/passwd`` is sent as ``/etc/passwd`` and the server
    is never asked about an entity at all. Recorded so the encoded tables above
    are not mistaken for the whole story: ``%2e%2e%2f…`` is the form that
    arrives at the server intact.
    """
    with client(memory_repository(root)) as http:
        for path in ("/api/entities/../../etc/passwd", "/api/artifacts/../../../etc/passwd"):
            response = http.get(path)
            assert response.status_code != 200, f"{path} returned a body: {response.text[:200]}"
            assert response.status_code < 500
            assert_contract("ErrorResponse", response.json())


def test_a_well_formed_unknown_entity_id_is_404_not_found(root: Path) -> None:
    """The other half of D-020: well formed, naming nothing, is absence."""
    for label, http in both_clients(root):
        for unknown in (
            "youtube:fixture-pass:KU-999999",
            "youtube:no-such-run:KU-000001",
            "library:concepts:ffffffffffff",
            "podcast:whatever:thing",
            # Well formed and *contains* dots: `idPart` allows a dot anywhere but
            # first, so this is absence, not refusal. The line D-020 draws runs
            # between this id and `youtube:fixture-pass:..`, which is a 400.
            "youtube:fixture-pass:KU-000001..",
        ):
            response = http.get(f"/api/entities/{unknown}")
            body = assert_error(response, 404, "not_found")
            assert body["error"]["code"] == "not_found", label


def test_a_well_formed_unknown_artifact_id_is_404_not_found(root: Path) -> None:
    for label, http in both_clients(root):
        for unknown in ("youtube:fixture-pass:no-such-artifact", "youtube:no-such-run:transcript"):
            response = http.get(f"/api/artifacts/{unknown}")
            body = assert_error(response, 404, "not_found")
            assert body["error"]["code"] == "not_found", label


def test_an_unbuilt_index_is_503_index_unavailable(tmp_path: Path, known: dict[str, Any]) -> None:
    """D-030: an unbuilt index is not an empty one, and must not read as ``404``.

    ``build=False`` reaches the ``absent`` state deliberately. The state travels
    in ``detail`` so a UI can say *unbuilt* rather than presenting "no such
    entity" as a fact about the user's data.
    """
    unbuilt = project(tmp_path, "pass-run")
    with client(sqlite_repository(unbuilt, build=False)) as http:
        for path in (
            f"/api/entities/{known['unit']['global_id']}",
            f"/api/artifacts/{known['artifact']['id']}",
        ):
            response = http.get(path)
            body = assert_error(response, 503, "index_unavailable")
            assert body["error"].get("detail", {}).get("state") == "absent"


# --------------------------------------------------------------------------
# No host path, anywhere (ADR 0003, D-030, D-051)
# --------------------------------------------------------------------------


def test_no_response_names_a_host_path(root: Path, known: dict[str, Any]) -> None:
    """Success bodies and refusals alike. ``Artifact.path`` is project-relative.

    ``assert_error`` already checks every refusal this file makes; this covers
    the ``200`` side, where the leak would be an absolute ``path`` on an
    artifact record rather than a message.
    """
    forbidden = (str(root), str(api_harness.PROJECT_ROOT), "/Users/", "/home/", "/var/folders/")
    with client(memory_repository(root)) as http:
        bodies = [http.get(f"/api/entities/{e['global_id']}").text for e in known["entities"]]
        bodies += [http.get(f"/api/artifacts/{a['id']}").text for a in known["artifacts"]]
        bodies += [http.get(f"/api/entities/{segment}").text for _, segment in ALL_HOSTILE_IDS]
        bodies += [http.get(f"/api/artifacts/{segment}").text for _, segment in ALL_HOSTILE_IDS]
        bodies.append(http.get("/api/entities/youtube:fixture-pass:KU-999999").text)

    for body in bodies:
        for needle in forbidden:
            assert needle not in body, f"a response named a host path ({needle}): {body[:300]}"


def test_an_artifact_path_stays_project_relative(root: Path, known: dict[str, Any]) -> None:
    """The record's own ``path`` is what a leak would ride out on."""
    with client(memory_repository(root)) as http:
        for artifact in known["artifacts"]:
            path = http.get(f"/api/artifacts/{artifact['id']}").json()["data"]["path"]
            if path is None:
                continue
            assert not path.startswith("/"), f"{artifact['id']} carries an absolute path: {path}"
            assert ".." not in Path(path).parts, f"{artifact['id']} carries a traversal: {path}"


# --------------------------------------------------------------------------
# The route adds nothing of its own
# --------------------------------------------------------------------------


def test_the_route_returns_the_repository_record_unchanged(root: Path, known: dict[str, Any]) -> None:
    """No reshaping, no filtering, no added field — ``data`` is the record.

    ``EntityResponse.data`` ``$ref``s ``schemas/v1/entity_ref.schema.json``
    directly (D-026), so any enrichment here would be a second shape in front of
    the frozen one and the contract would have to grow to describe it.
    """
    repo = memory_repository(root)
    with client(repo) as http:
        entity_id = known["concept"]["global_id"]
        from_route = http.get(f"/api/entities/{entity_id}").json()["data"]
    assert json.loads(json.dumps(from_route)) == known["concept"]
    assert set(from_route) == set(known["concept"]), "the route added or dropped a field"


def test_only_get_is_answered(root: Path, known: dict[str, Any]) -> None:
    """The v1 surface is read-only (D-026): 11 endpoints, all ``GET``."""
    entity_id = known["unit"]["global_id"]
    with client(memory_repository(root)) as http:
        for method in ("post", "put", "patch", "delete"):
            response = getattr(http, method)(f"/api/entities/{entity_id}")
            assert response.status_code == 405, f"{method.upper()} was answered {response.status_code}"
