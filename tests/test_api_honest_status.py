"""`T-115` — the `PARTIAL` and `FAIL` fixtures, over HTTP.

`T-006` gave `PARTIAL` and `FAIL` an on-disk existence for the first time
(D-013, D-019, risk R11), and `tests/test_repository.py` proved the repository
serves them. Nothing asked the same question of the **HTTP surface**, which is
what the honest-status UI actually consumes. `tests/test_api_status.py` checks
the `/api/status` tally and `tests/test_api_sources.py` checks the `status`
filter; between them sits the thing neither owns — whether a whole run that did
not pass survives the trip to a client intact.

Four properties, and each one is a way a status is lost rather than reported:

* **The served status is the status the validator wrote.** `pipeline.validate_run`
  is the only legitimate source (§10) and the API must copy it, not derive
  something near it. Checked against a fresh `validate_run` as well as against
  the canonical files, so a route that recomputed would have to recompute the
  same answer to pass.
* **Nothing coerces toward `PASS`** (ADR 0001 invariant 2). Asserted over a
  project holding *only* the failed run, so the pass run is not sitting there
  making a `"PASS"` in a body look explicable.
* **A failed run is served, not hidden.** The opposite dishonesty, and the
  easier one to ship by accident: dropping a `FAIL` run from the library reports
  a project that is smaller than it is, and a Reader that cannot open the run
  cannot show the evidence that failed.
* **The awkward shape holds.** `fail-run` has a `report.md`, a `graph.json` and
  a full Obsidian export, all served and all `available`, while its verdict is
  `FAIL`. A UI that infers status from "the files are there" passes against
  `pass-run` and lies about this one — that is what the fixture is for.

Every test runs over both implementations. D-052 is why: the oracle answered
correctly while `SqliteRepository` `503`'d on every request.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import api_harness as h
import pytest

pytestmark = h.requires_fastapi

#: Run directory to the ``Source.id`` its ``metadata.json`` spells. Stated
#: rather than derived: the directory name and the ``video_id`` inside it differ
#: on purpose, so a test that built one from the other would be checking its own
#: arithmetic. The link is re-asserted from the served `canonical_dir` in
#: :func:`test_the_served_status_is_the_status_the_validator_wrote`.
RUN_SOURCES = {
    "pass-run": "youtube:fixture-pass",
    "partial-run": "youtube:fixture-partial",
    "fail-run": "youtube:fixture-fail",
}

FAIL_RUN, FAIL_SOURCE = "fail-run", RUN_SOURCES["fail-run"]
PARTIAL_RUN, PARTIAL_SOURCE = "partial-run", RUN_SOURCES["partial-run"]

#: A term that appears in every fixture run's knowledge units, so a search that
#: returns nothing is a finding rather than a badly chosen query.
SEARCH_TERM = "evidence"

#: Enough to hold everything the fixtures produce in one page.
ALL = 200


# --------------------------------------------------------------------------
# Reading the canonical files, which is the only authority on a status
# --------------------------------------------------------------------------


def canonical_status(run_dir: Path) -> dict[str, Any]:
    """The status object the adapter is supposed to have copied, read off disk.

    Built from the two canonical validator files and nothing else — no
    recomputation, no inference, no default. `UNKNOWN` for a file that is not
    there or will not read, which is what `common.schema.json`'s `runStatus`
    says the value means.
    """
    from x2knwldg.adapters import RUN_STATUSES, UNKNOWN_STATUS
    from x2knwldg.io import read_json_or_reason

    def stated(name: str) -> tuple[Any, str]:
        document, _ = read_json_or_reason(run_dir / name)
        if not isinstance(document, dict):
            return None, UNKNOWN_STATUS
        status = document.get("status")
        return document, status if status in RUN_STATUSES else UNKNOWN_STATUS

    validation, validation_status = stated("validation.json")
    coverage, coverage_status = stated("coverage.json")
    return {
        "validation": validation_status,
        "coverage": coverage_status,
        # `overall` is the top-level status of validation.json, copied. It
        # already aggregates coverage; deriving it here would be the very
        # recomputation the invariant forbids.
        "overall": validation_status,
        "audit_attempts": coverage.get("audit_attempts") if isinstance(coverage, dict) else None,
    }


def with_paths(status: dict[str, Any], run: str) -> dict[str, Any]:
    """*status* plus the project-relative paths the record must name."""
    return {
        **status,
        "validation_path": f"output/{run}/validation.json",
        "coverage_path": f"output/{run}/coverage.json",
    }


def status_objects(node: Any) -> Iterator[dict[str, Any]]:
    """Every ``Source.status`` object anywhere in a decoded body.

    Found structurally rather than by path, because the point is that *no*
    route reshapes one — including a route added after this test was written.
    """
    if isinstance(node, dict):
        if {"validation", "coverage", "overall"} <= set(node):
            yield node
        for value in node.values():
            yield from status_objects(value)
    elif isinstance(node, list):
        for item in node:
            yield from status_objects(item)


# --------------------------------------------------------------------------
# Projects and clients
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """One project of all three committed fixtures, copied, shared here."""
    return h.project(tmp_path_factory.mktemp("honest-status"))


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


def ok(test_client: Any, component: str, path: str, **params: Any) -> dict[str, Any]:
    """The contract-checked body of a ``200``."""
    response = test_client.get(path, params=params)
    assert response.status_code == 200, f"{path} answered {response.status_code}: {response.text}"
    body = response.json()
    h.assert_contract(component, body)
    return body


# --------------------------------------------------------------------------
# 1. The served status is the status the validator wrote
# --------------------------------------------------------------------------


@pytest.mark.parametrize("run", sorted(RUN_SOURCES))
def test_the_served_status_is_the_status_the_validator_wrote(
    api: Any, root: Path, run: str
) -> None:
    """Copied from the canonical files, whole, including the paths it read."""
    source = ok(api, "SourceDetailResponse", f"/api/sources/{RUN_SOURCES[run]}")["data"]["source"]
    assert source["canonical_dir"] == f"output/{run}", (
        "the record must name the directory it was read from"
    )
    assert source["status"] == with_paths(canonical_status(root / "output" / run), run)


@pytest.mark.parametrize("run", sorted(RUN_SOURCES))
def test_the_api_agrees_with_a_fresh_run_of_the_validator(
    api: Any, tmp_path_factory: pytest.TempPathFactory, run: str
) -> None:
    """`pipeline.validate_run` is the only legitimate source; the API matches it.

    Run against a **separate** copy, because `validate_run` writes
    `validation.json` — asking the authority is a mutation, and the project the
    clients are serving must not be the one it is asked about.
    """
    from x2knwldg import pipeline

    output = tmp_path_factory.mktemp(f"revalidate-{run}") / "output"
    output.mkdir(parents=True)
    shutil.copytree(h.FIXTURE_RUNS / run, output / run)

    served = ok(api, "SourceDetailResponse", f"/api/sources/{RUN_SOURCES[run]}")["data"]["source"]
    verdict = pipeline.validate_run(pipeline.resolve_run_dir(output, run))["status"]

    assert served["status"]["overall"] == verdict
    assert served["status"]["validation"] == verdict


def test_the_repair_cap_is_reported_rather_than_the_run_being_called_finished(api: Any) -> None:
    """`partial-run` exhausted the audit budget and is still `PARTIAL`.

    The cap is `constants.MAX_AUDIT_ATTEMPTS`, never a literal (§10). Reaching
    it is the honest end of coverage repair, not a licence to round the verdict
    up — so the number and the verdict are asserted together.
    """
    from x2knwldg.constants import MAX_AUDIT_ATTEMPTS

    source = ok(api, "SourceDetailResponse", f"/api/sources/{PARTIAL_SOURCE}")["data"]["source"]
    assert source["status"]["audit_attempts"] == MAX_AUDIT_ATTEMPTS
    assert source["status"]["overall"] == "PARTIAL"


def test_both_implementations_serve_the_same_status_for_every_run(root: Path) -> None:
    """A status that differed between the oracle and the index would be a bug in one."""
    answers: dict[str, dict[str, Any]] = {}
    for label, test_client in h.both_clients(root):
        answers[label] = {
            source_id: ok(
                test_client, "SourceDetailResponse", f"/api/sources/{source_id}"
            )["data"]["source"]["status"]
            for source_id in RUN_SOURCES.values()
        }
    assert answers["memory"] == answers["sqlite"]


# --------------------------------------------------------------------------
# 2. Nothing coerces toward PASS
# --------------------------------------------------------------------------


@pytest.mark.parametrize("run", [FAIL_RUN, PARTIAL_RUN])
def test_no_endpoint_reports_a_pass_for_a_run_that_did_not_pass(
    tmp_path: Path, run: str
) -> None:
    """The whole surface, over a project holding only the run that did not pass.

    Alone on purpose: with `pass-run` in the project a stray `"PASS"` in a body
    has an innocent explanation, and this test is about the case where it has
    none. Every status object any route emits — found structurally, so a route
    that nests one somewhere new is still checked — must equal the one the
    canonical files state, in both directions. Coercion upward is the invariant;
    coercion downward would be just as much of an invention.
    """
    root = h.project(tmp_path, run)
    expected = with_paths(canonical_status(root / "output" / run), run)
    source_id = RUN_SOURCES[run]

    for label, test_client in h.both_clients(root):
        seen = 0
        for response in _every_body(test_client, source_id):
            for status in status_objects(response):
                assert status == expected, f"{label} reshaped a status: {status}"
                seen += 1
        assert seen, f"{label} served no status object at all"

        tally = ok(test_client, "StatusResponse", "/api/status")["data"]["sources_by_status"]
        assert tally == {**dict.fromkeys(tally, 0), expected["overall"]: 1}


def _every_body(test_client: Any, source_id: str) -> Iterator[Any]:
    """Every ``200`` body a client can obtain for *source_id*, decoded."""
    paths = [
        "/api/status",
        "/api/sources",
        f"/api/sources/{source_id}",
        f"/api/sources/{source_id}/entities",
        f"/api/sources/{source_id}/relations",
        "/api/graph",
        "/api/search",
    ]
    for path in paths:
        params = {"limit": ALL}
        if path == "/api/search":
            params["q"] = SEARCH_TERM
        response = test_client.get(path, params=params)
        assert response.status_code == 200, f"{path} answered {response.status_code}"
        yield response.json()


# --------------------------------------------------------------------------
# 3. A failed run is served, not hidden
# --------------------------------------------------------------------------


def test_a_failed_run_is_listed_beside_the_others(api: Any) -> None:
    """Dropping it would report a library smaller than the project, silently."""
    listed = ok(api, "SourceListResponse", "/api/sources", limit=ALL)
    assert {record["id"] for record in listed["data"]} == set(RUN_SOURCES.values())
    assert listed["page"]["total"] == len(RUN_SOURCES)


def test_every_reader_endpoint_answers_for_the_failed_run(api: Any) -> None:
    """A `FAIL` verdict is a fact about the run, not a reason to refuse to open it.

    The evidence a reader most needs is the evidence that failed, so each of the
    endpoints a Reader opens is asked for the failed run and must answer with
    the frozen shape rather than a refusal.
    """
    detail = ok(api, "SourceDetailResponse", f"/api/sources/{FAIL_SOURCE}")["data"]
    assert detail["artifacts"], "the failed run declares artifacts"

    entities = ok(api, "EntityListResponse", f"/api/sources/{FAIL_SOURCE}/entities", limit=ALL)
    assert entities["data"], "the failed run holds knowledge units"
    relations = ok(api, "RelationListResponse", f"/api/sources/{FAIL_SOURCE}/relations", limit=ALL)
    assert relations["data"], "the failed run holds relations"

    for entity in entities["data"]:
        global_id = entity["global_id"]
        assert ok(api, "EntityResponse", f"/api/entities/{global_id}")["data"]["global_id"] == (
            global_id
        )
        ok(api, "NeighborhoodResponse", f"/api/graph/neighborhood/{global_id}")

    graph = ok(api, "GraphResponse", "/api/graph", source_id=FAIL_SOURCE, limit=ALL)
    assert graph["data"]["nodes"], "the failed run is drawn on the map like any other"


def test_the_failed_run_is_searchable(api: Any) -> None:
    """Its content is indexed; only its verdict is bad."""
    hits = ok(api, "SearchResponse", "/api/search", q=SEARCH_TERM, source_id=FAIL_SOURCE, limit=ALL)
    assert hits["data"], "a run that did not pass is still knowledge that was extracted"
    assert all(hit["source_id"] == FAIL_SOURCE for hit in hits["data"])


# --------------------------------------------------------------------------
# 4. The awkward shape: finished-looking files, a FAIL verdict
# --------------------------------------------------------------------------


def test_the_finished_looking_artifacts_do_not_make_the_run_a_pass(api: Any) -> None:
    """R11's whole point, as an assertion.

    `fail-run` carries a report, a graph and a full Obsidian export, all present
    and all served. A UI that reads "the files are there" as completion passes
    against `pass-run` and lies about this one. The two halves are asserted in
    one test on purpose: separated, either half looks like a passing run.
    """
    detail = ok(api, "SourceDetailResponse", f"/api/sources/{FAIL_SOURCE}")["data"]
    kinds = {artifact["kind"] for artifact in detail["artifacts"]}
    assert {"report", "graph", "vault_note"} <= kinds, (
        "the fixture is only awkward while the finished-looking files are there"
    )
    assert detail["source"]["status"]["overall"] == "FAIL"


def test_the_report_of_a_failed_run_is_available_and_readable(api: Any) -> None:
    """`available: true` describes the bytes, not the verdict.

    Conflating the two is the same mistake in the other direction: a report that
    exists must not be reported as missing because the run failed, and reading
    it must not be refused.
    """
    artifact = ok(api, "ArtifactResponse", f"/api/artifacts/{FAIL_SOURCE}:report")["data"]
    assert artifact["available"] is True
    assert artifact["path"] == f"output/{FAIL_RUN}/report.md"

    response = api.get(f"/api/media/{FAIL_SOURCE}:report")
    assert response.status_code == 200, response.text
    assert response.content, "the report of a failed run is still bytes on disk"


# --------------------------------------------------------------------------
# 5. The tally and the filter describe the same library
# --------------------------------------------------------------------------


def test_the_status_tally_and_the_status_filter_agree(api: Any) -> None:
    """Two endpoints, one library.

    `/api/status` counts by status and `/api/sources?status=` selects by it.
    Each is already tested against the fixtures; neither is tested against the
    other, and a UI showing the tally as a filter chip needs them to agree.
    """
    from x2knwldg.repository.base import FILTERABLE_STATUSES

    tally = ok(api, "StatusResponse", "/api/status")["data"]["sources_by_status"]
    assert set(tally) == set(FILTERABLE_STATUSES)
    for status in FILTERABLE_STATUSES:
        filtered = ok(api, "SourceListResponse", "/api/sources", status=status, limit=ALL)
        assert len(filtered["data"]) == tally[status], status
        assert all(record["status"]["overall"] == status for record in filtered["data"])
    assert sum(tally.values()) == ok(api, "StatusResponse", "/api/status")["data"]["counts"][
        "sources"
    ]


# --------------------------------------------------------------------------
# 6. A missing or damaged validator file is UNKNOWN, never PASS
# --------------------------------------------------------------------------


@pytest.mark.parametrize("damage", ["missing", "malformed"])
def test_a_run_whose_verdict_cannot_be_read_is_unknown(tmp_path: Path, damage: str) -> None:
    """`UNKNOWN` is a status, and the one thing it must never be replaced with is `PASS`.

    Both damages are checked because they arrive by different paths — an absent
    file is an absence, a present unreadable one is damage (D-045) — and only
    the second one has anything to report.
    """
    from x2knwldg.adapters import UNKNOWN_STATUS

    root = h.project(tmp_path, FAIL_RUN)
    verdict = root / "output" / FAIL_RUN / "validation.json"
    if damage == "missing":
        verdict.unlink()
    else:
        verdict.write_text("{ not json", encoding="utf-8")

    for label, test_client in h.both_clients(root):
        source = ok(test_client, "SourceDetailResponse", f"/api/sources/{FAIL_SOURCE}")["data"][
            "source"
        ]
        assert source["status"]["validation"] == UNKNOWN_STATUS, label
        assert source["status"]["overall"] == UNKNOWN_STATUS, label
        # The file that *is* readable is still reported as itself.
        assert source["status"]["coverage"] == "PASS", label
        tally = ok(test_client, "StatusResponse", "/api/status")["data"]["sources_by_status"]
        assert tally == {**dict.fromkeys(tally, 0), UNKNOWN_STATUS: 1}, label


def test_a_damaged_file_is_reported_without_naming_the_host(tmp_path: Path) -> None:
    """ADR 0003, D-051: no host path reaches a body — an error body or any other.

    `test_api_hardening.test_no_response_body_names_a_host_path` sweeps every
    route over a *healthy* project, so it never reaches the one field that is
    populated only when a canonical file is broken.

    `YouTubeAdapter._read` sanitises the reason where it records it, which is
    where D-051 put the same rule for the skipped-run channel. Both
    implementations are checked because SQLite stores the record verbatim: a
    reason sanitised on the way *out* would pass on the oracle and leak here.
    """
    root = h.project(tmp_path, FAIL_RUN)
    (root / "output" / FAIL_RUN / "validation.json").write_text("{ not json", encoding="utf-8")

    for label, test_client in h.both_clients(root):
        source = ok(test_client, "SourceDetailResponse", f"/api/sources/{FAIL_SOURCE}")["data"][
            "source"
        ]
        damaged = source["adapter_metadata"]["unreadable_files"]
        assert [entry["path"] for entry in damaged] == [f"output/{FAIL_RUN}/validation.json"], label
        blob = json.dumps(damaged)
        assert str(root) not in blob, f"{label}: a 200 body named the project root: {blob}"
        assert "/Users/" not in blob and "/home/" not in blob, f"{label}: {blob}"
        # The reason must still *say* what is wrong. Sanitising by deleting the
        # sentence would pass the assertions above and destroy the channel.
        assert "Malformed JSON" in damaged[0]["reason"], label
        assert damaged[0]["path"] in damaged[0]["reason"], label
