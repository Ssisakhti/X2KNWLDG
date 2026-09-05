"""One YouTube run and one Twitter run, through every read surface (``T-228``).

``T-227`` made a Twitter run canonical and ``T-228`` projects it. The acceptance
clause is coexistence rather than correctness in isolation, and that is what
this file measures: the two media in **one** project, through the adapter, the
SQLite index, the repository seam, search and the graph the Map draws — with
the YouTube sample's own numbers unmoved, because a second source type that
renumbers the first is a migration, and the row forbids one.

Two things are asserted here that no per-adapter test can see:

* **The locator resolves.** ``check_records`` refuses an *edge* naming an
  endpoint no entity has, but nothing refuses a **locator** naming an artifact
  no record carries — a text_span into a missing artifact is a claim whose
  evidence cannot be opened, and the Reader would 404 on it. D-233 mints one
  artifact per post precisely so this holds, so it is checked rather than
  assumed.
* **Rebuilding the cache is equivalent.** ADR 0001 invariant: SQLite is a
  rebuildable cache and deleting it must lose nothing. A second source type is
  the first real chance for that to stop being true.

Stdlib only apart from the one schema test, which skips without ``jsonschema``
the way ``tests/test_index_schemas.py`` does, so the file runs in the
zero-dependency job (ADR 0001 invariant 5).
"""

from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path

import pytest

from x2knwldg.adapters import adapt_project
from x2knwldg.index.scanner import refresh_index

PROJECT_ROOT = Path(__file__).resolve().parents[1]
YOUTUBE_RUNS = PROJECT_ROOT / "tests" / "fixtures" / "runs"
TWITTER_RUNS = PROJECT_ROOT / "tests" / "fixtures" / "twitter-runs"

#: The YouTube sample's projection, measured before this task and unchanged by
#: it. A number that moves here is a legacy-id migration, which the T-228 row
#: rules out in as many words.
YOUTUBE_ALONE = {"sources": 1, "artifacts": 18, "entities": 2, "relations": 2}


def _project(tmp_path: Path, *, youtube: str = "pass-run", twitter: str = "quote") -> Path:
    """A project root holding one run of each medium.

    The Twitter fixture's ``capture.json`` records its raw evidence relative to
    the *output root*, which for a committed fixture is ``tests/fixtures/``
    (D-231). Nothing here re-reads that path — the adapter maps the directory
    it is given — so the copy needs no rewriting.
    """
    shutil.copytree(YOUTUBE_RUNS / youtube, tmp_path / "output" / youtube)
    shutil.copytree(TWITTER_RUNS / twitter, tmp_path / "output" / f"twitter-{twitter}")
    return tmp_path


def _source_id(project: Path, case: str) -> str:
    """The run's own source id, read from the run.

    Hard-coding one is how a test starts asserting against the fixture it was
    written beside rather than the one it is given: three of these fixtures
    anchor at different posts, and a self-thread anchors at its **last**.
    """
    metadata = json.loads(
        (project / "output" / f"twitter-{case}" / "metadata.json").read_text(encoding="utf-8")
    )
    return f"twitter:{metadata['video_id']}"


# --------------------------------------------------------------------------
# 1. The adapter: two media, one record set
# --------------------------------------------------------------------------


def test_the_two_media_coexist_in_one_projection(tmp_path: Path) -> None:
    records = adapt_project(_project(tmp_path))
    by_type = sorted(source["source_type"] for source in records.sources)
    assert by_type == ["twitter", "youtube"]
    # Every record carries the source type in its own id, so the two sets are
    # separable without a lookup and cannot collide by construction.
    for record in records.artifacts + records.entities:
        key = record.get("id") or record["global_id"]
        assert key.startswith(("youtube:", "twitter:"))


def test_the_youtube_projection_is_not_moved_by_the_twitter_one(tmp_path: Path) -> None:
    """The regression the acceptance clause is really about."""
    alone = adapt_project(_project(tmp_path))
    youtube_only = {
        "sources": [s for s in alone.sources if s["source_type"] == "youtube"],
        "artifacts": [a for a in alone.artifacts if a["id"].startswith("youtube:")],
        "entities": [e for e in alone.entities if e["global_id"].startswith("youtube:")],
        "relations": [r for r in alone.relations if r["from_id"].startswith("youtube:")],
    }
    assert {name: len(rows) for name, rows in youtube_only.items()} == YOUTUBE_ALONE

    solo = tmp_path / "solo"
    (solo / "output").mkdir(parents=True)
    shutil.copytree(YOUTUBE_RUNS / "pass-run", solo / "output" / "pass-run")
    baseline = adapt_project(solo)
    assert youtube_only["entities"] == baseline.entities
    assert youtube_only["relations"] == baseline.relations
    assert youtube_only["artifacts"] == baseline.artifacts


def test_every_locator_addresses_an_artifact_the_index_carries(tmp_path: Path) -> None:
    """The check `check_records` does for edges, done for locators.

    A `text_span` into an artifact no record carries is evidence the Reader
    cannot open, and D-233's per-item artifact is what makes it resolve. It is
    asserted over *both* media, because the rule is not Twitter's.
    """
    records = adapt_project(_project(tmp_path))
    artifacts = {artifact["id"] for artifact in records.artifacts}
    addressed = 0
    for entity in records.entities:
        locator = entity.get("locator")
        if not locator or "artifact_id" not in locator:
            continue
        addressed += 1
        assert locator["artifact_id"] in artifacts, (
            f"{entity['global_id']} cites {locator['artifact_id']}, which no artifact record has"
        )
    assert addressed, "no locator addressed an artifact, so this proved nothing"


@pytest.mark.parametrize(
    # By the file that makes a directory a run, the way
    # `test_twitter_run_fixtures.test_every_planned_case_is_present` already
    # discovers them. Filtering on the *name* instead swept in whatever else
    # lived beside the cases: `__pycache__` was excluded by hand, and `inputs/`
    # — the two constructed responses the `facets` case is built from — was
    # picked up as a ninth run with no capture in it.
    "case", sorted(path.parent.name for path in TWITTER_RUNS.glob("*/capture.json"))
)
def test_every_twitter_fixture_projects_and_resolves(tmp_path: Path, case: str) -> None:
    """All eight run fixtures, not just the convenient one — the tombstone
    (no claims at all), the ten-post thread, and both Persian cases included."""
    records = adapt_project(_project(tmp_path, twitter=case))
    artifacts = {artifact["id"] for artifact in records.artifacts}
    posts = [a for a in records.artifacts if a["kind"] == "post"]
    assert posts, f"{case} projected no post artifact"
    for entity in records.entities:
        locator = entity.get("locator") or {}
        if locator.get("type") == "text_span":
            assert locator["artifact_id"] in artifacts


def test_a_tombstone_projects_an_unavailable_post_and_no_claims(tmp_path: Path) -> None:
    """An item with no author, timestamp or text is still a real item of the
    run. Dropping it would put the artifact set at odds with the item coverage
    that counts it; inventing `available: true` is the class of claim the
    capture contract exists to make unrepresentable."""
    records = adapt_project(_project(tmp_path, twitter="tombstone"))
    posts = [a for a in records.artifacts if a["kind"] == "post"]
    assert len(posts) == 1 and posts[0]["available"] is False
    assert posts[0]["path"] is None and posts[0]["url"].endswith("/999999999999999999")
    assert [e for e in records.entities if e["global_id"].startswith("twitter:")] == []


def test_the_thread_mints_one_artifact_per_post_in_order(tmp_path: Path) -> None:
    records = adapt_project(_project(tmp_path, twitter="self-thread"))
    posts = [a for a in records.artifacts if a["kind"] == "post"]
    assert len(posts) == 10
    assert len({a["id"] for a in posts}) == 10
    capture = json.loads(
        (tmp_path / "output" / "twitter-self-thread" / "capture.json").read_text(encoding="utf-8")
    )
    # Root-first, from the capture's own order — never re-sorted here.
    assert [a["id"].rsplit(":post-", 1)[1] for a in posts] == [
        item["post_id"] for item in capture["items"]
    ]


# --------------------------------------------------------------------------
# 2. The index: built, rebuilt, and equivalent
# --------------------------------------------------------------------------


def _counts(project: Path) -> dict[str, int]:
    with sqlite3.connect(project / ".x2knwldg" / "index.sqlite") as db:
        return {
            table: db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]  # noqa: S608
            for table in ("sources", "artifacts", "entities", "relations")
        }


def test_the_index_carries_both_runs(tmp_path: Path) -> None:
    project = _project(tmp_path)
    report = refresh_index(project, strict=True)
    assert report.runs_indexed == 2 and not report.skipped_runs
    records = adapt_project(project)
    assert _counts(project) == {
        "sources": len(records.sources),
        "artifacts": len(records.artifacts),
        "entities": len(records.entities),
        "relations": len(records.relations),
    }


def test_deleting_and_rebuilding_the_cache_loses_nothing(tmp_path: Path) -> None:
    """ADR 0001: the index is a rebuildable cache. A second source type is the
    first real chance for that to quietly stop holding."""
    project = _project(tmp_path)
    refresh_index(project, strict=True)
    before = _counts(project)

    (project / ".x2knwldg" / "index.sqlite").unlink()
    refresh_index(project, strict=True)
    assert _counts(project) == before


def test_an_incremental_refresh_sees_the_twitter_run_change(tmp_path: Path) -> None:
    """The scanner digests whole subtrees, so a Twitter run must be no more
    invisible to change detection than a YouTube one."""
    project = _project(tmp_path)
    refresh_index(project, strict=True)
    # `runs_indexed` is every run whose records are in the index when the scan
    # finishes, carried-over ones included; `runs_unchanged` is the subset that
    # did no work, which is the number that says the incremental path saw
    # nothing to do.
    settled = refresh_index(project, strict=True)
    assert settled.runs_indexed == 2 and settled.runs_unchanged == 2

    run = project / "output" / "twitter-quote"
    document = json.loads((run / "metadata.json").read_text(encoding="utf-8"))
    document["title"] = f"{document['title']} (edited)"
    (run / "metadata.json").write_text(json.dumps(document), encoding="utf-8")
    changed = refresh_index(project, strict=True)
    assert changed.runs_indexed == 2 and changed.runs_unchanged == 1


# --------------------------------------------------------------------------
# 3. The frozen read surface
# --------------------------------------------------------------------------


def test_the_repository_serves_both_media_over_one_seam(tmp_path: Path) -> None:
    from x2knwldg.index.repository import SqliteRepository
    from x2knwldg.repository import SourceQuery

    project = _project(tmp_path)
    refresh_index(project, strict=True)
    repo = SqliteRepository.open(project)
    page = repo.list_sources(SourceQuery())
    assert {row["source_type"] for row in page.items} == {"youtube", "twitter"}
    # No new endpoint, field or query parameter: the filter the contract
    # already exposes is the one that separates them.
    twitter = repo.list_sources(SourceQuery(source_type="twitter"))
    assert len(twitter.items) == 1
    assert twitter.items[0]["id"].startswith("twitter:")


def test_the_twitter_graph_is_drawable(tmp_path: Path) -> None:
    """What the Map asks for. A graph whose nodes are the run's entities and
    whose edges have both ends in it — the same rule `repository.graph_nodes`
    applies to a YouTube run (D-041, ADR 0004), reached by no new code."""
    from x2knwldg.index.repository import SqliteRepository
    from x2knwldg.repository import GraphQuery

    project = _project(tmp_path, twitter="self-thread")
    refresh_index(project, strict=True)
    repo = SqliteRepository.open(project)
    source = _source_id(project, "self-thread")
    graph = repo.graph(GraphQuery(source_id=source))
    ids = {node["global_id"] for node in graph.nodes}
    assert ids, "the Twitter run drew an empty graph"
    for edge in graph.edges:
        assert edge["from_id"] in ids and edge["to_id"] in ids


def test_persian_text_is_searchable_and_comes_back_unmangled(tmp_path: Path) -> None:
    """The bidi half of the acceptance clause, at the layer that can be
    measured without a browser: the ZWNJ and NBSP a Persian post is made of
    must survive the index, because the excerpt is compared verbatim upstream
    and a normalizing index would make that comparison a lie downstream."""
    from x2knwldg.index.repository import SqliteRepository

    project = _project(tmp_path, twitter="persian-rtl")
    refresh_index(project, strict=True)
    repo = SqliteRepository.open(project)

    units = json.loads(
        (project / "output" / "twitter-persian-rtl" / "knowledge_units.json").read_text(
            encoding="utf-8"
        )
    )["units"]
    excerpt = next(u["source"]["evidence_excerpt"] for u in units if u.get("source"))
    entity = repo.get_entity(f"{_source_id(project, 'persian-rtl')}:{units[0]['id']}")
    assert entity is not None
    assert entity["locator"]["excerpt"] == excerpt
    assert "‌" in excerpt or " " in excerpt, "this fixture no longer proves anything"


# --------------------------------------------------------------------------
# 4. The records the API serves are the records the schemas describe
# --------------------------------------------------------------------------


def test_the_twitter_projection_validates_against_the_v1_schemas(tmp_path: Path) -> None:
    jsonschema = pytest.importorskip(
        "jsonschema",
        reason="jsonschema is a dev-extra dependency; the core package stays zero-dependency",
    )
    from referencing import Registry, Resource

    schema_dir = PROJECT_ROOT / "schemas" / "v1"
    schemas = {
        path.name: json.loads(path.read_text(encoding="utf-8"))
        for path in schema_dir.glob("*.schema.json")
    }
    registry = Registry().with_resources(
        (schema["$id"], Resource.from_contents(schema)) for schema in schemas.values()
    )
    validator_for = {
        name.removesuffix(".schema.json"): jsonschema.Draft202012Validator(
            schema, registry=registry
        )
        for name, schema in schemas.items()
    }

    records = adapt_project(_project(tmp_path, twitter="self-thread"))
    checked = 0
    for model, rows in (
        ("source", records.sources),
        ("artifact", records.artifacts),
        ("entity_ref", records.entities),
        ("indexed_relation", records.relations),
    ):
        for row in rows:
            errors = [e.message for e in validator_for[model].iter_errors(row)]
            assert not errors, f"{model} {row.get('id') or row.get('global_id')}: {errors}"
            checked += 1
    assert checked > 30, "too few records validated for this to mean anything"
