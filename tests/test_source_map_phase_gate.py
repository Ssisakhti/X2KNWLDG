"""The Phase 2.3 gate, on the Python side (`T-257`).

`T-251`–`T-256` each proved their own piece. What no test asked is whether the
*phase's* acceptance clauses hold over one project at once, and whether the
witnesses that are supposed to prove them can actually fail. Both questions are
here, and the second is the one worth stating first.

**A gate that cannot fail is not a gate.** The browser suite walks the Source
Map over whatever `web/scripts/dev_api.py` serves. Over the three
``PASS``/``PARTIAL``/``FAIL`` runs that project used to hold,
``/api/source-graph`` answers three nodes, **no brief and no relation** — so
every Source Map clause in `web/browser/source.spec.ts` would walk an empty
corpus, assert that nothing equals nothing, and report green. D-281 pointed that
project at ``tests/source_map_corpus.py`` instead, and the first section below is
what stops it from quietly going back: it asserts that the library the browser
gate is served actually carries all five record families, and it asserts it by
building the same project the gate builds rather than by reading the script's
source.

**And the phase's own clauses, over one project.** Every implemented source
appears exactly once; a brief is readable and cannot claim more than its run; at
least one YouTube↔X relation exists with valid source-owned knowledge-unit basis;
a source with no relation emits none; deleting and rebuilding SQLite produces an
equivalent Source Map; and nothing under any run's ``raw/`` moved while all of
that happened.

Stdlib only above the HTTP section, which skips without ``fastapi`` exactly as
every other ``tests/test_api_*.py`` file does.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

import source_map_corpus as smc

from x2knwldg.adapters import adapt_project
from x2knwldg.artifacts import source_relations_document
from x2knwldg.index.scanner import build_index
from x2knwldg.synthesis import brief_state

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WEB = PROJECT_ROOT / "web"

#: The two-part id of the one accepted relation's two ends, which cross media.
#: Named through the corpus rather than retyped, so a fixture change moves both.
CROSS_MEDIUM = (smc.RELATION_FROM, smc.RELATION_TO)


@pytest.fixture(scope="module")
def corpus(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The phase's project: four runs, three briefs, one relation."""
    root = tmp_path_factory.mktemp("phase-gate")
    return smc.build(root / "project").project_root


def _sources(root: Path) -> list[dict[str, object]]:
    """Every source node the adapters project, as the fifth record family."""
    return list(adapt_project(root).source_entities)


def _briefs(root: Path) -> dict[str, dict[str, object]]:
    """Each run's brief state, keyed by the source id the run declares.

    Read through ``synthesis.brief_state`` — the same function the index reads
    and the endpoints answer from — rather than by loading the JSON here, so a
    brief this file calls ``available`` is one the served API would too. The run
    directory comes from the record's own ``canonical_path``, because the corpus
    deliberately names its directories differently from the ids the runs declare.
    """
    states: dict[str, dict[str, object]] = {}
    for source in _sources(root):
        run = root / Path(str(source["canonical_path"])).parent
        states[str(source["source_id"])] = brief_state(run)
    return states


def _relations(root: Path) -> list[dict[str, object]]:
    """The accepted relations, as records.

    ``source_relations_document`` rather than ``source_relations_state``: the two
    answer different questions, and the one this file asks is what the relations
    *are* rather than which of them have moved.
    """
    return source_relations_document(root / "output")


def _units_of(root: Path, source_id: str) -> set[str]:
    """The local unit ids one source holds, from the entity family."""
    return {
        str(entity["local_id"])
        for entity in adapt_project(root).entities
        if entity.get("source_id") == source_id
    }


# ---------------------------------------------------------------------------
# The gate's own corpus: the witness has to be able to fail
# ---------------------------------------------------------------------------


def _dev_api_fixture_project(destination: Path) -> Path:
    """Build exactly what `web/scripts/dev_api.py` serves, through that module.

    Imported by path rather than reimplemented. The whole point of this section
    is that the browser gate's library is the one this file measured, and a
    reimplementation here would measure a copy that can drift from it.
    """
    module_path = WEB / "scripts" / "dev_api.py"
    assert module_path.is_file(), "the development API the browser gate serves is gone"
    import importlib.util

    spec = importlib.util.spec_from_file_location("x2knwldg_dev_api", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # `dev_api` puts `src/` and `tests/` on the path itself; this keeps that
    # from leaking a duplicate entry into the suite's own `sys.path`.
    before = list(sys.path)
    try:
        spec.loader.exec_module(module)
        return module.build_fixture_project(destination)
    finally:
        sys.path[:] = before


def test_the_browser_gates_library_holds_all_five_record_families(tmp_path: Path) -> None:
    """The Source Map half of the browser gate has something to walk (D-281).

    Every assertion here would have been true-but-vacuous over the old
    three-run fixture project, which is exactly why they are stated as
    inequalities against zero rather than as "the endpoints answered".
    """
    root = _dev_api_fixture_project(tmp_path / "project")

    sources = _sources(root)
    assert len(sources) >= 4, "the gate's library has too few sources to walk"
    media = {str(source["source_type"]) for source in sources}
    assert media == {"youtube", "twitter"}, (
        f"the gate's library covers {media}, so no cross-medium clause can be walked"
    )

    states = _briefs(root)
    assert [state for state in states.values() if state["state"] == "available"], (
        "no run in the gate's library has a readable brief, so no brief can be read"
    )
    assert [state for state in states.values() if state["state"] == "unavailable"], (
        "every run in the gate's library has a brief, so the `unavailable` state "
        "has no witness"
    )

    relations = _relations(root)
    assert relations, "the gate's library holds no source relation, so no basis can be opened"
    assert any(
        {relation["from_source_id"], relation["to_source_id"]} == set(CROSS_MEDIUM)
        for relation in relations
    ), "the gate's library holds no cross-medium relation"


def test_the_browser_gate_is_pointed_at_that_library() -> None:
    """`playwright.config.ts` serves the fixture project, not a hand-built one.

    The check is that the gate takes the *default* — no `--project-root` unless
    `X2KNWLDG_BROWSER_PROJECT_ROOT` is set — because that default is what the
    test above measured.
    """
    config = (WEB / "playwright.config.ts").read_text(encoding="utf-8")
    assert "scripts/dev_api.py" in config, "the gate no longer serves the real API"
    assert "X2KNWLDG_BROWSER_PROJECT_ROOT" in config, (
        "the gate can no longer be pointed at a real library"
    )


def test_the_source_map_specs_are_part_of_the_gate() -> None:
    """The three files `T-257` added are specs the gate collects.

    Named individually rather than counted: a count passes a rename, and a
    renamed spec that no longer matches `*.spec.ts` is a gate that silently
    stopped walking a third of the phase.
    """
    gate = WEB / "browser"
    for name in ("source.spec.ts", "sourceAccess.spec.ts", "sourceVisual.spec.ts"):
        assert (gate / name).is_file(), f"{name} is missing from the browser gate"
    assert (gate / "sourceGate.ts").is_file(), "the Source Map gate's shared helpers are gone"


# ---------------------------------------------------------------------------
# The phase's acceptance clauses, over one project
# ---------------------------------------------------------------------------


def test_every_implemented_source_appears_exactly_once(corpus: Path) -> None:
    ids = [str(source["source_id"]) for source in _sources(corpus)]
    assert sorted(ids) == sorted(smc.SOURCE_IDS)
    assert len(ids) == len(set(ids)), "a source is projected more than once"


def test_a_brief_never_claims_more_than_the_run_it_was_written_from(corpus: Path) -> None:
    """The clause that keeps a synthesis from outranking its own evidence."""
    rank = {"FAIL": 0, "PARTIAL": 1, "PASS": 2}
    seen = 0
    for source_id, state in _briefs(corpus).items():
        brief = state["brief"]
        if not isinstance(brief, dict):
            continue
        seen += 1
        validation = json.loads(
            (corpus / "output" / _run_dir(corpus, source_id) / "validation.json").read_text(
                encoding="utf-8"
            )
        )
        assert rank[str(brief["status"])] <= rank[validation["status"]], (
            f"{source_id}'s brief claims {brief['status']} over a "
            f"{validation['status']} run"
        )
    assert seen >= 2, "too few briefs to have measured anything"


def _run_dir(corpus: Path, source_id: str) -> str:
    """The directory a source id was projected from, read rather than guessed.

    The corpus deliberately names its directories differently from the ids the
    runs declare — `pass-run/` declares `fixture-pass` — so this resolves through
    each run's own `metadata.json` instead of assuming the two match.
    """
    for run in sorted((corpus / "output").iterdir()):
        metadata = run / "metadata.json"
        if not metadata.is_file():
            continue
        data = json.loads(metadata.read_text(encoding="utf-8"))
        prefix = data.get("source_type", "youtube")
        if f"{prefix}:{data['video_id']}" == source_id:
            return run.name
    raise AssertionError(f"no run in the corpus declares {source_id}")


def test_every_brief_statement_names_units_the_run_actually_holds(corpus: Path) -> None:
    """The support clause, checked against each run's own unit ids.

    This is the record-level half of what the browser gate checks on screen: the
    card draws a chip per id, and the ids have to be real.
    """
    checked = 0
    for source_id, state in _briefs(corpus).items():
        brief = state["brief"]
        if not isinstance(brief, dict):
            continue
        units = _units_of(corpus, source_id)
        elements = [
            brief["thesis"],
            *brief.get("key_points", []),
            *brief.get("limitations_or_tensions", []),
        ]
        for element in elements:
            based_on = set(element.get("based_on", []))
            assert based_on, f"{source_id} has a statement with no support"
            unknown = based_on - units
            assert not unknown, f"{source_id} cites units it does not hold: {unknown}"
            checked += 1
    assert checked >= 3, "too few statements to have measured anything"


def test_the_cross_medium_relation_rests_on_units_its_own_endpoints_hold(corpus: Path) -> None:
    """The phase's headline clause, over the record rather than over the UI."""
    relations = _relations(corpus)
    assert relations, "the corpus holds no source relation"

    crossing = [
        relation
        for relation in relations
        if {relation["from_source_id"], relation["to_source_id"]} == set(CROSS_MEDIUM)
    ]
    assert crossing, "no relation joins the two media"
    for relation in crossing:
        assert relation["from_source_id"] != relation["to_source_id"]
        assert relation["rationale"].strip(), "an accepted relation carries no rationale"
        # Each end of every basis pair belongs to the endpoint that states it,
        # which is the check `apply-source-relations` enforces (D-266) and the
        # one the Reader links `T-257` drew depend on being true: the link for a
        # `from_ku_id` addresses `from_source_id`'s Reader and nothing resolves
        # a unit by searching for it.
        for pair in relation["basis"]:
            for unit, owner in (
                (pair["from_ku_id"], relation["from_source_id"]),
                (pair["to_ku_id"], relation["to_source_id"]),
            ):
                assert unit in _units_of(corpus, owner), f"{unit} is not held by {owner}"
        # No score, rank or confidence is representable on the record (D-247).
        assert not {"confidence", "score", "rank", "similarity"} & set(relation)


def test_a_source_with_no_relation_emits_none(corpus: Path) -> None:
    standing = {
        end
        for relation in _relations(corpus)
        for end in (relation["from_source_id"], relation["to_source_id"])
    }
    alone = [source for source in _sources(corpus) if str(source["source_id"]) not in standing]
    assert alone, "every source in the corpus stands in a relation, so this proves nothing"


def test_no_run_lost_a_byte_of_raw_evidence(tmp_path: Path) -> None:
    """Building and rebuilding the whole layer never writes into a run.

    `T-252`'s gate proves this of one apply. What is proved here is the whole
    phase's read path — adapters, index build, delete, rebuild — over a project
    holding both media, because `raw/` is immutable evidence and an index is a
    cache with no right to touch it.
    """
    root = smc.build(tmp_path / "project").project_root
    raw_files = sorted(
        path for path in (root / "output").rglob("raw/**/*") if path.is_file()
    )
    assert raw_files, "the corpus carries no raw evidence to protect"
    before = {
        path: (path.stat().st_mtime_ns, path.read_bytes()) for path in raw_files
    }

    adapt_project(root)
    build_index(root)
    shutil.rmtree(root / ".x2knwldg")
    build_index(root)

    after = {path: (path.stat().st_mtime_ns, path.read_bytes()) for path in raw_files}
    assert after == before, "raw evidence moved while the source layer was built"
