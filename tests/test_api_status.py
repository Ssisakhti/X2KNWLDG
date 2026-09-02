"""``GET /api/status`` (`T-105`) — the endpoint that answers when nothing else can.

Every other route refuses with ``503 index_unavailable`` unless the index is
``ready``. This one must not, and these tests are what stops a later refactor
from making it look like its neighbours: an unbuilt project is the ordinary
state of a fresh checkout, and a UI that got a ``503`` for it could not tell
"never indexed" from "the server is broken".

Three facts no other file can assert:

* **``absent`` is a 200.** Not a ``503``, not an empty body, not a guess. That
  is why ``IndexRepository.status`` returns rather than raises.
* **``runs`` is passed through, never synthesised** (D-050). ``SqliteRepository``
  scanned a filesystem and can name what it could not index;
  ``MemoryRepository`` scanned none and omits the key. A route that filled in
  ``skipped: []`` would turn "nobody looked" into a measurement.
* **No body names a host path** (ADR 0003, D-051) — including the one field
  that is a path by nature, a skipped run's location.

Both implementations answer every test that both can reach. ``T-104`` proved
they agree, so a divergence found here is a bug in the route.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import api_harness as h
import pytest

pytestmark = h.requires_fastapi

#: The three committed run fixtures, one of each validator outcome. Asserted as
#: a whole rather than key by key: the point of the tally is that `PARTIAL` and
#: `FAIL` survive to the API as themselves (ADR 0001 invariant 2).
FIXTURE_STATUSES = {"PASS": 1, "PARTIAL": 1, "FAIL": 1, "UNKNOWN": 0}


# --------------------------------------------------------------------------
# A client per implementation
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """One project of the committed fixtures, copied, shared by every test here."""
    return h.project(tmp_path_factory.mktemp("status-project"))


@pytest.fixture(
    scope="module",
    params=[
        pytest.param("memory", id="memory"),
        pytest.param("sqlite", id="sqlite", marks=h.requires_fts5),
    ],
)
def api(request: pytest.FixtureRequest, root: Path) -> Any:
    """A ``TestClient`` over each implementation in turn."""
    build = h.memory_repository if request.param == "memory" else h.sqlite_repository
    with h.client(build(root)) as test_client:
        yield test_client


def status(test_client: Any) -> dict[str, Any]:
    """The ``data`` of a checked ``200``. Every caller validates the envelope."""
    response = test_client.get("/api/status")
    assert response.status_code == 200, response.text
    body = response.json()
    h.assert_contract("StatusResponse", body)
    return body["data"]


def both(root: Path) -> dict[str, dict[str, Any]]:
    """The payload of each implementation, keyed by name.

    Used only by the tests that compare the two *against each other*; everything
    else takes the parametrized ``api`` fixture and is run once per arm.
    """
    return {label: status(test_client) for label, test_client in h.both_clients(root)}


# --------------------------------------------------------------------------
# 1. What the index is
# --------------------------------------------------------------------------


def test_a_built_index_reports_ready(api: Any) -> None:
    assert status(api)["index"]["state"] == "ready"


def test_the_payload_carries_exactly_the_frozen_keys(api: Any) -> None:
    """``additionalProperties: false`` catches a stray key; this catches a missing one."""
    data = status(api)
    assert {"index", "counts", "sources_by_status", "adapters"} <= set(data)
    assert set(data["counts"]) == {"sources", "artifacts", "entities", "relations"}
    assert set(data["index"]) == {"state", "built_at", "index_version"}


def test_the_statuses_are_copied_and_none_is_coerced(api: Any) -> None:
    """`PARTIAL` and `FAIL` reach the API as themselves (ADR 0001 invariant 2)."""
    assert status(api)["sources_by_status"] == FIXTURE_STATUSES


def test_the_adapters_that_wrote_the_records_are_named(api: Any) -> None:
    adapters = status(api)["adapters"]
    assert adapters
    assert "youtube" in {adapter["name"] for adapter in adapters}


def test_the_counts_agree_with_what_the_list_endpoints_serve(api: Any) -> None:
    """A count is a cache convenience; a stale one is a bug, never an achievement."""
    counted = status(api)["counts"]["sources"]
    listed = api.get("/api/sources", params={"limit": 500}).json()["data"]
    assert counted == len(listed) == 3


def test_both_implementations_count_the_same_records(root: Path) -> None:
    answers = both(root)
    assert answers["memory"]["counts"] == answers["sqlite"]["counts"]
    assert answers["memory"]["sources_by_status"] == answers["sqlite"]["sources_by_status"]


def test_only_a_persisted_index_claims_a_migration_version(root: Path) -> None:
    """`MemoryRepository` reports null rather than claiming a durable artifact."""
    answers = both(root)
    assert answers["memory"]["index"]["index_version"] is None
    assert isinstance(answers["sqlite"]["index"]["index_version"], int)


# --------------------------------------------------------------------------
# 2. D-050 — `runs` is reported, or omitted, but never invented
# --------------------------------------------------------------------------


def test_memory_omits_runs_and_sqlite_reports_them(root: Path) -> None:
    answers = both(root)

    assert "runs" not in answers["memory"], (
        "MemoryRepository scans no filesystem; a `runs` object would claim it looked"
    )

    runs = answers["sqlite"]["runs"]
    assert set(runs) == {"discovered", "indexed", "skipped"}
    assert runs["indexed"] == 3
    assert runs["skipped"] == []
    assert runs["discovered"] == runs["indexed"] + len(runs["skipped"])


@h.requires_fts5
def test_a_run_the_index_could_not_take_is_named(tmp_path: Path) -> None:
    """A library smaller than the filesystem says why, rather than being smaller."""
    root = h.project(tmp_path, "pass-run")
    broken = root / "output" / "not-a-run"
    broken.mkdir()
    (broken / "metadata.json").write_text("{ this is not json", encoding="utf-8")

    with h.client(h.sqlite_repository(root)) as test_client:
        runs = status(test_client)["runs"]
        assert [run["relative_path"] for run in runs["skipped"]] == ["output/not-a-run"]
        assert runs["discovered"] == runs["indexed"] + len(runs["skipped"])
        # D-051: the reason locates the run in the project, never on the host.
        blob = json.dumps(runs)
        assert str(h.PROJECT_ROOT) not in blob
        assert "/Users/" not in blob and "/home/" not in blob


# --------------------------------------------------------------------------
# 3. The states that are not `ready`
# --------------------------------------------------------------------------


@h.requires_fts5
def test_an_unbuilt_index_is_a_200_reporting_absent(tmp_path: Path) -> None:
    """`absent` is a reported state, not a failure. It must never become a 503."""
    root = h.project(tmp_path, "pass-run")
    with h.client(h.sqlite_repository(root, build=False)) as test_client:
        data = status(test_client)
        assert data["index"]["state"] == "absent"
        assert data["index"]["built_at"] is None
        assert data["index"]["index_version"] is None
        assert data["counts"] == {"sources": 0, "artifacts": 0, "entities": 0, "relations": 0}
        assert data["sources_by_status"] == dict.fromkeys(FIXTURE_STATUSES, 0)


def test_the_oracle_reports_absent_the_same_way() -> None:
    from x2knwldg.repository import MemoryRepository

    with h.client(MemoryRepository.unavailable("absent")) as test_client:
        assert status(test_client)["index"]["state"] == "absent"


def test_status_still_answers_in_the_error_state() -> None:
    """The reason `status()` returns rather than raises: `error` is answerable."""
    from x2knwldg.repository import MemoryRepository

    repository = MemoryRepository.unavailable("error", message="the index is damaged")
    with h.client(repository) as test_client:
        assert status(test_client)["index"]["state"] == "error"


@h.requires_fts5
def test_status_answers_where_the_list_endpoints_refuse(tmp_path: Path) -> None:
    """The asymmetry *is* the decision: this one answers, the rest say why they cannot."""
    root = h.project(tmp_path, "pass-run")
    with h.client(h.sqlite_repository(root, build=False)) as test_client:
        assert test_client.get("/api/status").status_code == 200
        h.assert_error(test_client.get("/api/sources"), 503, "index_unavailable")


def test_an_unbuilt_index_is_not_reported_as_an_empty_one(tmp_path: Path) -> None:
    """Same zero counts, different states. A UI that conflates them states a fact."""
    from x2knwldg.repository import MemoryRepository

    # A project with no runs at all. `h.project` always copies at least one
    # fixture, and the whole point here is a library that is genuinely empty.
    (tmp_path / "output").mkdir()
    with h.client(h.memory_repository(tmp_path)) as indexed:
        with h.client(MemoryRepository.unavailable("absent")) as unbuilt:
            indexed_data, unbuilt_data = status(indexed), status(unbuilt)

    assert indexed_data["counts"] == unbuilt_data["counts"] == {
        "sources": 0,
        "artifacts": 0,
        "entities": 0,
        "relations": 0,
    }
    assert indexed_data["index"]["state"] == "ready"
    assert unbuilt_data["index"]["state"] == "absent"


# --------------------------------------------------------------------------
# 4. ADR 0003 — nothing in a body names the host
# --------------------------------------------------------------------------


def test_no_status_body_names_a_host_path(api: Any) -> None:
    blob = json.dumps(status(api))
    assert str(h.PROJECT_ROOT) not in blob
    assert "/Users/" not in blob and "/home/" not in blob
