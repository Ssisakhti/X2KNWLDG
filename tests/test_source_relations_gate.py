"""Automatic cross-source relations, end to end (`T-253`).

The phase's acceptance clause is that **a fixture-backed YouTube↔X relationship
is generated automatically and exposes valid source-owned KU basis, while a
no-relation fixture emits none**. That is what this file establishes, and it does
it over a corpus built by :mod:`source_corpus` in the test process — because no
committed corpus can produce a cross-medium candidate, and none should be edited
into producing one. The reasoning is in that module's docstring; the short
version is that every committed Twitter run emits ``quote`` units on purpose, and
``quote`` is not a concept kind.

Three properties carry the task, and each has a section:

* **The walk is bounded, and the bound is not self-reported.** The gate re-runs
  discovery and compares. A pass that walked every pair and then wrote a small
  ``considered`` is refused, which is what makes "no all-pairs walk" a check
  rather than a promise.
* **A relation is only as strong as its grounds.** Basis ownership, direction,
  and corroboration for an explicit reference are each refused by name, and
  mixed evidence survives.
* **A conclusion is about the runs as they are.** Endpoint digests are recorded,
  recomputed and compared; a pair whose runs have moved is refused at write time
  and reported ``stale`` at read time, per relation rather than per file.

Stdlib only apart from the package.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import source_corpus

from x2knwldg import ids, synthesis
from x2knwldg.artifacts import (
    apply_source_relations,
    source_relations_path,
    source_relations_state,
)
from x2knwldg.candidates import (
    ROUTE_EXPLICIT_REFERENCE,
    ROUTE_LOCAL_RETRIEVAL,
    ROUTE_SHARED_CONCEPT,
    discover,
)
from x2knwldg.constants import MAX_SOURCE_CANDIDATES
from x2knwldg.pipeline import PipelineError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = PROJECT_ROOT / "tests" / "fixtures" / "source-map"
GENERATED_AT = "2026-01-01T00:00:00+00:00"


@pytest.fixture(scope="module")
def corpus(tmp_path_factory: pytest.TempPathFactory) -> source_corpus.Corpus:
    """One YouTube run and one X run that genuinely share a canonical concept."""
    return source_corpus.build(tmp_path_factory.mktemp("corpus"))


@pytest.fixture
def workspace(corpus: source_corpus.Corpus, tmp_path: Path) -> Path:
    """A per-test copy of the corpus's output root.

    Building the corpus drives the real pipeline twice and is expensive, so it
    is module-scoped — and a module-scoped fixture that tests *write into* is a
    suite whose result depends on its order. It bit exactly that way here: one
    test asserted no synthesis file appears, and passed alone while failing
    after the test that writes one. Every test that writes takes a copy.
    """
    import shutil

    destination = tmp_path / "output"
    shutil.copytree(corpus.output, destination)
    return destination


def _report(corpus: source_corpus.Corpus):
    return discover(corpus.output)


def _relation(
    corpus: source_corpus.Corpus,
    *,
    relation_type: str = "critiques",
    scope: str = "partial",
    reverse: bool = False,
    basis: list[dict] | None = None,
    **changes,
) -> dict:
    """A relation over the corpus, with real ids, real units and real digests."""
    report = _report(corpus)
    from_source = corpus.twitter_source_id if not reverse else corpus.youtube_source_id
    to_source = corpus.youtube_source_id if not reverse else corpus.twitter_source_id
    relation = {
        "id": ids.source_relation_id(from_source, to_source, relation_type, scope),
        "from_source_id": from_source,
        "to_source_id": to_source,
        "relation_type": relation_type,
        "scope": scope,
        "provenance_class": "derived",
        "rationale": "این دو منبع دربارهٔ یک جملهٔ واحد سخن می‌گویند و ادعای یکدیگر را می‌سنجند.",
        "basis": basis
        if basis is not None
        else [
            {
                "from_ku_id": "KU-000001",
                "to_ku_id": "KU-000001",
                "relation_type": "contradicts",
            }
        ],
        "generated_from": {
            "from_run_digest": report.source(from_source).digest,
            "to_run_digest": report.source(to_source).digest,
        },
    }
    relation.update(changes)
    return relation


def _container(corpus: source_corpus.Corpus, relations: list[dict], **changes) -> dict:
    document = {
        "schema_version": synthesis.SCHEMA_VERSION,
        "generated_at": GENERATED_AT,
        "candidates": _report(corpus).counts,
        "relations": relations,
    }
    document.update(changes)
    return document


def _write(tmp_path: Path, document: dict, name: str = "relations.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# 1. Discovery: bounded, deterministic, and honest about what it cannot see
# --------------------------------------------------------------------------


def test_a_cross_medium_pair_is_discovered_automatically(corpus) -> None:
    """The acceptance clause, at the discovery end.

    Nothing here names the pair: it is found by reading the canonical concept
    registry that ``rebuild_library`` produced from two runs of different media.
    """
    report = _report(corpus)
    pairs = {candidate.pair for candidate in report.considered}
    assert (corpus.twitter_source_id, corpus.youtube_source_id) in pairs
    assert (corpus.youtube_source_id, corpus.twitter_source_id) in pairs


def test_the_shared_concept_route_names_the_concept_it_found(corpus) -> None:
    candidate = _report(corpus).candidate(
        corpus.twitter_source_id, corpus.youtube_source_id
    )
    assert candidate.routes == (ROUTE_SHARED_CONCEPT,)
    assert candidate.shared_concepts, "the concept that made this a candidate"
    assert all(c.startswith("library:concepts:") for c in candidate.shared_concepts)


def test_discovery_is_deterministic(corpus) -> None:
    """Two runs over one corpus agree, or the bound is not reproducible."""
    assert _report(corpus).as_dict() == _report(corpus).as_dict()


def test_discovery_counts_the_pairs_it_did_not_propose(corpus) -> None:
    """``pairs_in_corpus`` is what keeps a small result readable."""
    report = _report(corpus)
    assert report.counts["pairs_in_corpus"] == 2
    assert report.counts["considered"] == 2
    assert report.counts["bound"] == MAX_SOURCE_CANDIDATES


def test_discovery_states_that_local_retrieval_is_not_implemented(corpus) -> None:
    """An unbuilt route is named, so "no candidates" is never read as "unrelated"."""
    routes = _report(corpus).routes
    assert set(routes) == {
        ROUTE_EXPLICIT_REFERENCE,
        ROUTE_SHARED_CONCEPT,
        ROUTE_LOCAL_RETRIEVAL,
    }
    assert routes[ROUTE_LOCAL_RETRIEVAL].startswith("not implemented")


def test_the_bound_is_per_source_and_omissions_are_counted(corpus) -> None:
    """One heavily-connected source may not consume the whole budget."""
    report = discover(corpus.output, bound=1)
    assert report.counts["bound"] == 1
    assert report.counts["considered"] == 2, "one per from-source, not one in total"
    assert report.counts["omitted"] == 0
    tight = discover(corpus.output, bound=0)
    assert tight.counts["considered"] == 0
    assert tight.counts["omitted"] == 2, "the bound bound, and said so"


def test_an_unresolvable_reference_is_named_rather_than_dropped(tmp_path: Path) -> None:
    """The quote fixture cites a post no run in the corpus holds."""
    import shutil

    output = tmp_path / "output"
    output.mkdir(parents=True)
    shutil.copytree(
        PROJECT_ROOT / "tests" / "fixtures" / "twitter-runs" / "quote",
        output / "twitter-quote",
    )
    report = discover(output)
    assert any("name no acquired run" in note for note in report.notes)
    assert report.counts["considered"] == 0


def test_discovery_carries_no_score(corpus) -> None:
    """Rank orders the bound; it is never a fact about the sources (D-247)."""
    document = json.dumps(_report(corpus).as_dict())
    for word in ("score", "similarity", "rank", "confidence", "strength"):
        assert word not in document, word


# --------------------------------------------------------------------------
# 2. The gate accepts an honest relation over that pair
# --------------------------------------------------------------------------


def test_a_cross_medium_relation_is_accepted_and_stored(
    corpus, workspace: Path, tmp_path: Path
) -> None:
    """The acceptance clause, at the gate end: valid source-owned KU basis."""
    document = _container(corpus, [_relation(corpus)])
    result = apply_source_relations(_write(tmp_path, document), workspace)

    assert result["status"] == "PASS"
    assert result["relations"] == 1
    stored = json.loads(source_relations_path(workspace).read_text(encoding="utf-8"))
    assert stored == document
    relation = stored["relations"][0]
    assert relation["from_source_id"].startswith("twitter:")
    assert relation["to_source_id"].startswith("youtube:")
    assert relation["basis"][0]["from_ku_id"] in _report(corpus).source(
        relation["from_source_id"]
    ).unit_ids


def test_the_stored_file_sits_beside_the_runs_and_is_not_one(
    corpus, workspace: Path, tmp_path: Path
) -> None:
    """``output/synthesis/`` is never discovered as a run (``io.NOT_A_RUN``)."""
    apply_source_relations(
        _write(tmp_path, _container(corpus, [_relation(corpus)])), workspace
    )
    path = source_relations_path(workspace)
    assert path.parent.name == "synthesis"
    assert {s.source_id for s in discover(workspace).sources} == {
        corpus.youtube_source_id,
        corpus.twitter_source_id,
    }


def test_an_empty_relation_set_is_a_finding(corpus, workspace: Path, tmp_path: Path) -> None:
    """The no-relation case. Two pairs compared, nothing related, and it says so."""
    document = _container(corpus, [])
    result = apply_source_relations(_write(tmp_path, document), workspace)
    assert result["status"] == "PASS"
    assert result["relations"] == 0
    assert result["candidates"]["considered"] == 2
    assert result["candidates"]["pairs_in_corpus"] == 2


def test_two_relations_between_one_pair_coexist(
    corpus, workspace: Path, tmp_path: Path
) -> None:
    """When their supported semantics differ (`SOURCE_MAP_SPEC.md` §3.3)."""
    document = _container(
        corpus,
        [
            _relation(corpus, relation_type="critiques", scope="partial"),
            _relation(
                corpus,
                relation_type="overlaps_with",
                scope="broad",
                basis=[
                    {
                        "from_ku_id": "KU-000001",
                        "to_ku_id": "KU-000001",
                        "relation_type": "related_to",
                    }
                ],
            ),
        ],
    )
    assert apply_source_relations(_write(tmp_path, document), workspace)["relations"] == 2


def test_mixed_evidence_survives_the_gate(corpus, workspace: Path, tmp_path: Path) -> None:
    """A contrary ground beside agreeing ones is kept, not tidied away."""
    document = _container(
        corpus,
        [
            _relation(
                corpus,
                relation_type="supports",
                basis=[
                    {
                        "from_ku_id": "KU-000001",
                        "to_ku_id": "KU-000001",
                        "relation_type": "supports",
                    },
                    {
                        "from_ku_id": "KU-D-0001",
                        "to_ku_id": "KU-000001",
                        "relation_type": "contradicts",
                    },
                ],
            )
        ],
    )
    apply_source_relations(_write(tmp_path, document), workspace)
    stored = json.loads(source_relations_path(workspace).read_text(encoding="utf-8"))
    kinds = {g["relation_type"] for g in stored["relations"][0]["basis"]}
    assert kinds == {"supports", "contradicts"}


# --------------------------------------------------------------------------
# 3. The refusals
# --------------------------------------------------------------------------


def test_a_pair_discovery_never_proposed_is_refused(
    corpus, workspace: Path, tmp_path: Path
) -> None:
    """The "no all-pairs walk" exit condition, as a check.

    A third run is added that shares no concept with either of the others and
    references neither, so the pair is **real** — both endpoints exist and both
    hold the units named — and nothing proposed it. That is exactly the shape of
    a comparison pass that looked past its candidate list.

    The first version of this test bounded discovery to zero instead, which
    could never have worked: the *gate* re-discovers with the real bound, so the
    pair was a candidate there and only the counts disagreed. It would have
    passed for the wrong reason the moment the counts happened to line up.
    """
    import shutil

    from x2knwldg.library import rebuild_library

    shutil.copytree(
        PROJECT_ROOT / "tests" / "fixtures" / "runs" / "pass-run", workspace / "pass-run"
    )
    rebuild_library(workspace)
    report = discover(workspace)
    stranger = "youtube:fixture-pass"
    assert report.source(stranger) is not None, "the third run is in the corpus"
    assert not any(
        stranger in candidate.pair for candidate in report.considered
    ), "and nothing proposed it"

    relation = _relation(corpus)
    relation["from_source_id"] = stranger
    relation["to_source_id"] = corpus.youtube_source_id
    relation["id"] = ids.source_relation_id(
        stranger, corpus.youtube_source_id, "critiques", "partial"
    )
    relation["generated_from"] = {
        "from_run_digest": report.source(stranger).digest,
        "to_run_digest": report.source(corpus.youtube_source_id).digest,
    }
    document = _container(corpus, [relation])
    document["candidates"] = report.counts

    with pytest.raises(PipelineError, match="pair_was_not_a_candidate"):
        apply_source_relations(_write(tmp_path, document), workspace)


def test_self_reported_counts_are_not_taken_on_trust(
    corpus, workspace: Path, tmp_path: Path
) -> None:
    """A pass that walked everything and wrote a small number is refused."""
    document = _container(corpus, [])
    document["candidates"] = {"considered": 1, "omitted": 0, "bound": 25, "pairs_in_corpus": 2}
    with pytest.raises(PipelineError, match="candidate_counts_mismatch"):
        apply_source_relations(_write(tmp_path, document), workspace)


def test_a_basis_unit_of_the_wrong_endpoint_is_refused(corpus, workspace: Path, tmp_path: Path) -> None:
    """Both runs use ``KU-000001``; only holding both can see the ownership."""
    document = _container(
        corpus,
        [
            _relation(
                corpus,
                basis=[
                    {
                        "from_ku_id": "KU-999999",
                        "to_ku_id": "KU-000001",
                        "relation_type": "contradicts",
                    }
                ],
            )
        ],
    )
    with pytest.raises(PipelineError, match="basis_unit_not_owned_by_endpoint"):
        apply_source_relations(_write(tmp_path, document), workspace)


def test_an_uncorroborated_explicit_reference_is_refused(corpus, workspace: Path, tmp_path: Path) -> None:
    """Neither run in this corpus records a reference to the other."""
    document = _container(corpus, [_relation(corpus, relation_type="explicitly_references")])
    with pytest.raises(PipelineError, match="explicit_reference_without_evidence"):
        apply_source_relations(_write(tmp_path, document), workspace)


def test_an_inverted_relation_is_refused(corpus, workspace: Path, tmp_path: Path) -> None:
    """Every ground pointing the other way is an inversion, not a mixed basis."""
    document = _container(
        corpus,
        [
            _relation(
                corpus,
                relation_type="supports",
                basis=[
                    {
                        "from_ku_id": "KU-000001",
                        "to_ku_id": "KU-000001",
                        "relation_type": "contradicts",
                    }
                ],
            )
        ],
    )
    with pytest.raises(PipelineError, match="direction_incompatible_with_basis"):
        apply_source_relations(_write(tmp_path, document), workspace)


def test_an_invented_confidence_is_refused(corpus, workspace: Path, tmp_path: Path) -> None:
    document = _container(corpus, [_relation(corpus, confidence=0.9)])
    with pytest.raises(PipelineError, match="unknown_relation_field"):
        apply_source_relations(_write(tmp_path, document), workspace)


def test_an_english_rationale_is_refused(corpus, workspace: Path, tmp_path: Path) -> None:
    document = _container(
        corpus, [_relation(corpus, rationale="This thread critiques the video.")]
    )
    with pytest.raises(PipelineError, match="narrative_not_in_persian_script"):
        apply_source_relations(_write(tmp_path, document), workspace)


def test_a_refused_document_leaves_the_previous_synthesis_untouched(
    corpus, workspace: Path, tmp_path: Path
) -> None:
    """The gate's central promise, checked with something real to overwrite."""
    apply_source_relations(
        _write(tmp_path, _container(corpus, [_relation(corpus)])), workspace
    )
    accepted = source_relations_path(workspace).read_bytes()

    with pytest.raises(PipelineError):
        apply_source_relations(
            _write(tmp_path, _container(corpus, [_relation(corpus, confidence=0.9)]), "bad.json"),
            workspace,
        )
    assert source_relations_path(workspace).read_bytes() == accepted


def test_a_refused_document_writes_nothing_at_all(
    corpus, workspace: Path, tmp_path: Path
) -> None:
    """And on a corpus that has no synthesis yet, no file appears."""
    document = _container(corpus, [_relation(corpus, confidence=0.9)])
    with pytest.raises(PipelineError):
        apply_source_relations(_write(tmp_path, document, "bad2.json"), workspace)
    assert not source_relations_path(workspace).exists()


# --------------------------------------------------------------------------
# 4. Staleness — a conclusion is about the runs as they are
# --------------------------------------------------------------------------


def test_a_stale_pair_is_refused_at_write_time(corpus, workspace: Path, tmp_path: Path) -> None:
    relation = _relation(corpus)
    relation["generated_from"]["from_run_digest"] = "0" * 64
    with pytest.raises(PipelineError, match="stale_endpoint_digest"):
        apply_source_relations(_write(tmp_path, _container(corpus, [relation])), workspace)


def test_a_relation_goes_stale_when_an_endpoint_is_re_extracted(
    corpus, tmp_path: Path
) -> None:
    """Reported per relation, not per file.

    A corpus of twenty relations in which one endpoint moved has nineteen that
    are still current, and discarding them all would be the coarse answer this
    phase exists to avoid.
    """
    import shutil

    working = tmp_path / "working"
    shutil.copytree(corpus.output, working / "output")
    output = working / "output"
    apply_source_relations(
        _write(tmp_path, _container(corpus, [_relation(corpus)]), "stale-in.json"), output
    )
    assert source_relations_state(output)["state"] == "available"

    run = output / corpus.youtube_source_id.split(":", 1)[1]
    units = json.loads((run / "knowledge_units.json").read_text(encoding="utf-8"))
    units["units"][0]["confidence"] = 0.5
    (run / "knowledge_units.json").write_text(
        json.dumps(units, ensure_ascii=False), encoding="utf-8"
    )

    state = source_relations_state(output)
    assert state["state"] == "stale"
    assert [r["state"] for r in state["relations"]] == ["stale"]
    assert "to_run_digest" in state["relations"][0]["reason"]


def test_an_absent_synthesis_is_unavailable_rather_than_empty(tmp_path: Path) -> None:
    output = tmp_path / "output"
    output.mkdir()
    state = source_relations_state(output)
    assert state["state"] == "unavailable"
    assert state["relations"] == []


def test_a_damaged_synthesis_does_not_raise(tmp_path: Path) -> None:
    output = tmp_path / "output"
    (output / "synthesis").mkdir(parents=True)
    source_relations_path(output).write_text("{ not json", encoding="utf-8")
    state = source_relations_state(output)
    assert state["state"] == "unavailable"
    assert str(tmp_path) not in (state["reason"] or "")


# --------------------------------------------------------------------------
# 5. The committed `gate`-filed relation fixtures really are refused
# --------------------------------------------------------------------------
#
# `T-251` committed them and asserted the *facts* they state; `T-252` showed the
# pattern for the brief. These are theirs: each is fed to the validator with a
# corpus that makes everything else about it valid, so the one code that fires is
# the one its note names.


def _gate_fixture(name: str) -> dict:
    return json.loads((FIXTURE_DIR / "invalid" / name).read_text(encoding="utf-8"))


_FIXTURE_UNITS = {
    "twitter:2094039408081068233": frozenset({"KU-000001", "KU-D-0001"}),
    "youtube:fixture-pass": frozenset({"KU-000001", "KU-D-0001"}),
}


def _validate_fixture(document: dict) -> set[str]:
    from x2knwldg.validators import validate_source_relations

    relation = document["relations"][0]
    pair = (relation["from_source_id"], relation["to_source_id"])
    digests = {
        relation["from_source_id"]: relation["generated_from"]["from_run_digest"],
        relation["to_source_id"]: relation["generated_from"]["to_run_digest"],
    }
    result = validate_source_relations(
        document,
        units_by_source=_FIXTURE_UNITS,
        digests_by_source=digests,
        considered_pairs=frozenset({pair}),
        explicit_reference_pairs=frozenset(),
        candidate_counts=document["candidates"],
    )
    return {error["code"] for error in result["errors"]}


@pytest.mark.parametrize(
    "name,code",
    [
        ("relation-basis-unit-belongs-to-the-other-endpoint.json", "basis_unit_not_owned_by_endpoint"),
        ("relation-joins-a-source-to-itself.json", "self_relation"),
        ("relation-id-does-not-match-its-parts.json", "relation_id_mismatch"),
        ("container-duplicates-a-relation-id.json", "duplicate_relation_id"),
    ],
)
def test_a_committed_gate_fixture_is_refused_by_the_code_that_names_it(
    name: str, code: str
) -> None:
    assert code in _validate_fixture(_gate_fixture(name))


def test_the_valid_committed_container_is_shape_valid_but_not_gate_applicable() -> None:
    """An honest distinction, stated rather than left to be discovered.

    ``tests/fixtures/source-map/valid/synthesis/source_relations.json`` is a
    **schema** contract fixture: its pair is `pass-run`↔`quote`, which share no
    concept and carry no resolvable reference, so no corpus proposes it. The gate
    therefore refuses it — for the right reason, and only that one.
    """
    document = json.loads(
        (FIXTURE_DIR / "valid" / "synthesis" / "source_relations.json").read_text(
            encoding="utf-8"
        )
    )
    from x2knwldg.validators import validate_source_relations

    result = validate_source_relations(
        document,
        units_by_source=_FIXTURE_UNITS,
        digests_by_source={
            document["relations"][0]["from_source_id"]: document["relations"][0][
                "generated_from"
            ]["from_run_digest"],
            document["relations"][0]["to_source_id"]: document["relations"][0][
                "generated_from"
            ]["to_run_digest"],
        },
        considered_pairs=frozenset(),
        explicit_reference_pairs=frozenset(),
        candidate_counts=document["candidates"],
    )
    assert {e["code"] for e in result["errors"]} == {"pair_was_not_a_candidate"}


# --------------------------------------------------------------------------
# 6. Through the commands
# --------------------------------------------------------------------------


def test_the_candidate_command_prints_the_report(
    corpus, capsys: pytest.CaptureFixture[str]
) -> None:
    from x2knwldg.cli import main

    assert main(["source-candidates", "--output", str(corpus.output)]) == 0
    body = json.loads(capsys.readouterr().out)
    assert body["counts"]["considered"] == 2
    assert body["candidates"][0]["routes"] == [ROUTE_SHARED_CONCEPT]


def test_the_apply_command_stores_and_reports(
    corpus, workspace: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from x2knwldg.cli import main

    document = _write(tmp_path, _container(corpus, [_relation(corpus)]), "cli.json")
    assert main(["apply-source-relations", str(document), "--output", str(workspace)]) == 0
    body = json.loads(capsys.readouterr().out)
    assert body["path"] == "synthesis/source_relations.json"
    assert body["relations"] == 1


def test_the_apply_command_reports_a_refusal_as_an_error(
    corpus, workspace: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from x2knwldg.cli import main

    document = _write(
        tmp_path, _container(corpus, [_relation(corpus, confidence=0.9)]), "cli-bad.json"
    )
    code = main(["apply-source-relations", str(document), "--output", str(workspace)])
    assert code == 1
    assert json.loads(capsys.readouterr().err)["status"] == "ERROR"


# --------------------------------------------------------------------------
# 7. The count the documentation quotes is the one in the source
# --------------------------------------------------------------------------


def test_the_relation_rejection_code_count_in_the_docs_is_the_one_in_the_source() -> None:
    """`T-251` and `T-252` each quoted a count wrong; this is the guard for `T-253`'s.

    Read out of the module between the section header and the next validator, so
    a branch added later moves the number and fails here rather than leaving the
    §3 and §5 rows describing a validator that has changed.
    """
    import re

    import x2knwldg.validators as module

    source = Path(module.__file__).read_text(encoding="utf-8")
    span = source[
        source.index("# Cross-source relations") : source.index("def validate_knowledge_units")
    ]
    codes = set(re.findall(r'"code": "([a-z_]+)"', span))
    row = (PROJECT_ROOT / "docs" / "PROJECT_MANAGEMENT.md").read_text(encoding="utf-8")
    assert f"emits **{len(codes)}** rejection codes" in row, (
        f"the relation validator emits {len(codes)} codes and the docs quote a different "
        f"number: {sorted(codes)}"
    )
