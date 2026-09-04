"""Medium-dispatched finalize, and a vault a second medium can reach (`T-230`).

``finalize_run`` was YouTube-shaped in seven places, so a Twitter run stopped at
``validation.json``: no ``graph.json``, no ``report.md``, no vault note, and
nothing for ``rebuild_library`` to merge (D-234). The generalization is one
table — ``artifacts.MEDIUM_PROFILES`` — read by one implementation, and these
tests are about both halves of that: that a second medium now reaches the end of
the pipeline, and that the first one reaches exactly the same end it did.

Two of the seven places did not raise, which is why they are pinned hardest
here. ``_unit_markdown`` defaulted a missing ``start_sec`` to ``0`` and linked
``timestamp_url``, so a Twitter claim would have printed ``[00:00:00-00:00:00]``
against a YouTube watch URL built from a post id; and ``_coverage_markdown``
iterated ``windows``, which an item-based coverage document does not have, so the
audit rendered its header and stopped. A fabricated timestamp, a fabricated
source URL and an empty audit, all reached by defaulting rather than by failing
(§2: never invent a timestamp, a quote, an excerpt or a coverage value).

The third thing pinned here was found by trying to *check* the acceptance
clause rather than by reading the code: ``SECTION_ORDER``'s kind groups were
``set`` literals and ``finalize_run`` iterates them, so ``report.md``'s unit
order came from set iteration over interned strings and changed with
``PYTHONHASHSEED``. The committed YouTube fixtures never caught it because each
holds one unit per section; the 69-unit sample did, and it is gitignored.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from x2knwldg import artifacts, constants
from x2knwldg.adapters import adapt_project, get_adapter
from x2knwldg.artifacts import MEDIUM_PROFILES, SECTION_ORDER, finalize_run
from x2knwldg.ids import DEFAULT_SOURCE_TYPE
from x2knwldg.io import write_json
from x2knwldg.library import rebuild_library
from x2knwldg.pipeline import PipelineError, VerdictRefusal
from x2knwldg.twitter import extract

ROOT = Path(__file__).resolve().parents[1]
TWITTER_RUNS = ROOT / "tests" / "fixtures" / "twitter-runs"
YOUTUBE_RUNS = ROOT / "tests" / "fixtures" / "runs"

TWITTER_SOURCE_TYPE = extract.SOURCE_TYPE

#: The Twitter fixtures that earn final artifacts, and what they earn them as.
#: ``tombstone`` is absent on purpose: its capture is ``FAIL``, so it is the
#: refusal case and has a test of its own.
FINALIZES: dict[str, str] = {
    "single-post": "PASS",
    "persian-rtl": "PASS",
    "persian-rtl-ltr-run": "PASS",
    "self-thread": "PASS",
    "partial-thread": "PARTIAL",
    "edit": "PASS",
    "quote": "PASS",
}

_spec = importlib.util.spec_from_file_location(
    "t230_twitter_build_fixtures", TWITTER_RUNS / "build_fixtures.py"
)
assert _spec and _spec.loader
builder = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(builder)


def twitter_project(tmp_path: Path, *cases: str) -> Path:
    """The committed Twitter runs, copied into a project finalize can write to.

    Committed fixtures are never finalized where they sit: that would write
    ``report.md``, ``graph.json`` and a whole vault into ``tests/fixtures/``.

    The layout has to satisfy two different readers at once, which is why it is
    not a plain ``copytree``. ``adapt_project`` scans ``<root>/output/*`` for run
    directories, while ``twitter.extract.evidence_integrity`` resolves a
    capture's recorded ``raw_evidence`` paths against ``run_dir.parent.parent``
    — and those paths were recorded as ``twitter-runs/<case>/raw/...``, relative
    to ``tests/fixtures/`` (D-231). So each run is copied to
    ``<root>/output/<case>`` for the first reader and its ``raw/`` tree is
    *also* placed at ``<root>/twitter-runs/<case>/raw`` for the second. Get this
    wrong and every run fails validation with ``raw_evidence_missing``, which
    looks like a defect in the code under test and is an artefact of the copy.

    Returns the output root, so ``run_dir.parent`` is what ``rebuild_library``
    is handed and ``twitter_project(tmp_path).parent`` is the project root.

    Name *cases* to copy only those. Several fixtures were built from the same
    capture and therefore claim the same anchor post id, so a project holding
    all of them is a project with duplicate source ids — which the adapter
    refuses, correctly. Any test that *projects* the tree copies one run.
    """
    root = tmp_path / "project"
    output = root / "output"
    output.mkdir(parents=True)
    wanted = set(cases)
    for case in sorted(TWITTER_RUNS.iterdir()):
        if not (case / "metadata.json").is_file():
            continue
        if wanted and case.name not in wanted:
            continue
        shutil.copytree(case, output / case.name)
        shutil.copytree(case / "raw", root / "twitter-runs" / case.name / "raw")
    return output


def youtube_run(tmp_path: Path, name: str = "pass-run") -> Path:
    project = tmp_path / "youtube"
    project.mkdir(parents=True, exist_ok=True)
    run_dir = project / name
    shutil.copytree(YOUTUBE_RUNS / name, run_dir)
    return run_dir


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def units_of(run_dir: Path) -> list[dict[str, Any]]:
    return json.loads(read(run_dir / "knowledge_units.json"))["units"]


# ---------------------------------------------------------------------------
# The ordering defect: report.md has to be the same file twice.
# ---------------------------------------------------------------------------


def test_every_report_section_lists_its_kinds_in_a_fixed_order() -> None:
    """``SECTION_ORDER``'s groups are ordered containers, and must stay so.

    ``finalize_run`` iterates them to place units, so an unordered container
    here makes ``report.md`` unreproducible. A ``set`` literal is a one-character
    edit away and reads as harmless, which is how this got in.
    """
    for title, kinds in SECTION_ORDER:
        assert isinstance(kinds, tuple), (
            f"section {title!r} groups its kinds in a {type(kinds).__name__}, "
            "whose iteration order is not defined across processes. Use a tuple."
        )


def test_the_kind_vocabulary_and_the_report_sections_still_agree() -> None:
    covered: set[str] = set()
    for _, kinds in SECTION_ORDER:
        covered |= set(kinds)
    assert covered == constants.KNOWLEDGE_KINDS


def test_the_section_order_is_the_same_under_two_hash_seeds() -> None:
    """The flattened kind order, read in two processes seeded differently.

    This is the mechanism the defect was: ``PYTHONHASHSEED`` changes set
    iteration order over interned strings, and nothing else in this table
    varies. It fails on a ``SECTION_ORDER`` built from sets.
    """
    program = (
        "from x2knwldg.artifacts import SECTION_ORDER;"
        "print([k for _, kinds in SECTION_ORDER for k in kinds])"
    )
    seen = {
        seed: subprocess.run(
            [sys.executable, "-c", program],
            capture_output=True,
            text=True,
            check=True,
            env={**os.environ, "PYTHONHASHSEED": seed},
        ).stdout
        for seed in ("0", "1", "7", "99", "12345")
    }
    assert len(set(seen.values())) == 1, seen


def _mixed_kind_run(tmp_path: Path) -> Path:
    """A run whose units share a report section, built by driving the real gate.

    ``report.md``'s ordering only varies where one section holds more than one
    *kind*, and every committed fixture holds exactly one — which is why the
    suite was green while the file was nondeterministic. So this builds the
    shape the fixtures do not have: ten source units alternating between
    ``claim`` and ``principle``, which ``SECTION_ORDER`` collects into "Core
    Thesis" together.

    Through ``initialize_run`` and ``apply_extraction_bundle``, never by editing
    a canonical file: the apply gate is what makes the resulting run one the
    pipeline would accept, and a hand-edited one proves nothing about it.
    """
    runs = twitter_project(tmp_path, "self-thread")
    source = runs / "self-thread"
    run_dir = runs / "mixed-kinds"
    run_dir.mkdir()
    shutil.copy(source / "capture.json", run_dir / "capture.json")
    extract.initialize_run(run_dir)
    capture = json.loads(read(run_dir / "capture.json"))
    coverage = json.loads(read(run_dir / "coverage.json"))
    bundle = builder._bundle(capture, coverage)
    for index, unit in enumerate(bundle["knowledge_units"]):
        if unit["source_class"] == "source":
            unit["kind"] = "claim" if index % 2 == 0 else "principle"
    bundle_path = run_dir / "work" / "extraction_bundle.json"
    write_json(bundle_path, bundle)
    result = extract.apply_extraction_bundle(run_dir, bundle_path)
    assert result["status"] in {"PASS", "PARTIAL"}, result
    kinds = {unit["kind"] for unit in units_of(run_dir)}
    assert {"claim", "principle"} <= kinds, kinds
    return run_dir


def test_a_report_whose_section_holds_two_kinds_is_byte_identical_twice(
    tmp_path: Path,
) -> None:
    """The same run finalized in two differently seeded processes.

    The output-level statement of the defect above: not "the table is ordered"
    but "the file is the same file". ``report.md`` was two different files here.
    """
    built = _mixed_kind_run(tmp_path)
    reports: dict[str, bytes] = {}
    for seed in ("1", "2"):
        project = tmp_path / f"seed-{seed}"
        project.mkdir()
        shutil.copytree(built.parent, project / "twitter-runs")
        run_dir = project / "twitter-runs" / built.name
        subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys;from pathlib import Path;"
                "from x2knwldg.artifacts import finalize_run;"
                "finalize_run(Path(sys.argv[1]))",
                str(run_dir),
            ],
            check=True,
            capture_output=True,
            env={**os.environ, "PYTHONHASHSEED": seed},
        )
        reports[seed] = (run_dir / "report.md").read_bytes()
    assert reports["1"] == reports["2"]


# ---------------------------------------------------------------------------
# The first medium reaches exactly the end it did.
# ---------------------------------------------------------------------------


def test_a_youtube_run_finalizes_into_the_same_shape_it_always_did(
    tmp_path: Path,
) -> None:
    run_dir = youtube_run(tmp_path)
    result = finalize_run(run_dir)
    assert result["status"] == "PASS"
    video_id = json.loads(read(run_dir / "metadata.json"))["video_id"]
    note = run_dir / "vault" / "videos" / f"{video_id}.md"
    assert note.is_file()
    assert "type: video" in read(note)
    assert f"video_id: {video_id}" in read(note)
    report = read(run_dir / "report.md")
    assert "- Channel: " in report
    assert "- Transcript hash: `" in report
    assert "window-by-window audit" in report
    unit_note = next((run_dir / "vault" / "knowledge_units").rglob("*.md"))
    assert f"Source video: [[{video_id}]]" in read(unit_note)


def test_the_committed_youtube_fixtures_still_hold_what_finalize_writes(
    tmp_path: Path,
) -> None:
    """A re-finalize of each committed run reproduces its committed artifacts.

    ``tests/fixtures/runs/*`` commit ``report.md``, ``graph.json`` and a whole
    ``vault/`` — they *are* finalize output — so this is the byte-identity
    clause stated over the artifacts that are in version control. The real
    69-unit sample lives under gitignored ``output/``, so it cannot be the thing
    CI checks.
    """
    for name in ("pass-run", "partial-run"):
        run_dir = youtube_run(tmp_path / name, name)
        before = {
            path.relative_to(run_dir): path.read_bytes()
            for path in sorted(run_dir.rglob("*"))
            if path.is_file() and ("vault" in path.parts or path.name in {"report.md", "graph.json"})
        }
        assert before, "the fixture commits no final artifacts to compare against"
        finalize_run(run_dir)
        after = {
            path.relative_to(run_dir): path.read_bytes()
            for path in sorted(run_dir.rglob("*"))
            if path.is_file() and ("vault" in path.parts or path.name in {"report.md", "graph.json"})
        }
        assert after == before, f"{name} does not re-finalize to what it commits"


# ---------------------------------------------------------------------------
# The second medium reaches the end at all.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", sorted(FINALIZES))
def test_a_twitter_run_finalizes(tmp_path: Path, case: str) -> None:
    run_dir = twitter_project(tmp_path) / case
    result = finalize_run(run_dir)
    assert result["status"] == FINALIZES[case]
    assert (run_dir / "graph.json").is_file()
    assert (run_dir / "report.md").is_file()
    graph = json.loads(read(run_dir / "graph.json"))
    assert len(graph["nodes"]) == len(units_of(run_dir))


def test_a_partial_twitter_run_still_finalizes(tmp_path: Path) -> None:
    """An honestly incomplete run is a real deliverable, for this medium too."""
    run_dir = twitter_project(tmp_path) / "partial-thread"
    result = finalize_run(run_dir)
    assert result["status"] == "PARTIAL"
    assert (run_dir / "report.md").is_file()
    assert "**Coverage: PARTIAL**" in read(run_dir / "report.md")


@pytest.mark.parametrize("case", sorted(FINALIZES))
def test_the_note_frontmatter_names_the_medium_it_came_from(
    tmp_path: Path, case: str
) -> None:
    run_dir = twitter_project(tmp_path) / case
    finalize_run(run_dir)
    anchor = json.loads(read(run_dir / "metadata.json"))["video_id"]
    note = run_dir / "vault" / "posts" / f"{anchor}.md"
    assert note.is_file(), sorted(p.name for p in (run_dir / "vault").iterdir())
    text = read(note)
    assert "type: post" in text
    assert f"anchor_post_id: {anchor}" in text
    assert "type: video" not in text
    assert "video_id:" not in text
    assert not (run_dir / "vault" / "videos").exists()


@pytest.mark.parametrize("case", sorted(FINALIZES))
def test_every_source_claim_cites_its_own_post_and_its_own_span(
    tmp_path: Path, case: str
) -> None:
    """Not the anchor's post and not a time range — the claim's own coordinates.

    A claim taken from the seventh post of a ten-post thread cites the seventh
    post. The alternative a shared implementation invites is citing the run,
    which for a thread is a citation that points at the wrong text.
    """
    run_dir = twitter_project(tmp_path) / case
    finalize_run(run_dir)
    report = read(run_dir / "report.md")
    for unit in units_of(run_dir):
        if unit["source_class"] != "source":
            continue
        source = unit["source"]
        expected = (
            f"**Source:** [post `{source['post_id']}`, characters "
            f"{source['start_char']}–{source['end_char']}]"
            f"(https://x.com/i/status/{source['post_id']})"
        )
        assert expected in report, f"{unit['id']} in {case}"
        note = run_dir / "vault" / "knowledge_units" / "source" / f"{unit['id']}.md"
        assert note.is_file()


@pytest.mark.parametrize("case", sorted(FINALIZES))
def test_a_cited_post_is_an_artifact_the_adapter_actually_mints(
    tmp_path: Path, case: str
) -> None:
    """"Its own artifact" means an artifact that exists, not a plausible id.

    The vault cites a post by id and the index addresses it as
    ``twitter:<anchor>:post-<post_id>`` (D-233, D-237). Those are two spellings
    of one identity and nothing shares a constant between them, so this is the
    check that keeps them the same identity: every post a claim cites in the
    report resolves to an artifact record the adapter produced for that run.
    """
    runs = twitter_project(tmp_path, case)
    run_dir = runs / case
    finalize_run(run_dir)
    records = adapt_project(runs.parent)
    minted = {
        artifact["id"]
        for artifact in records.by_model()["artifact"]
        if artifact["kind"] == "post"
    }
    assert minted, "the adapter minted no post artifacts to address"
    adapter = get_adapter(TWITTER_SOURCE_TYPE, runs.parent)
    for entity in records.by_model()["entity_ref"]:
        locator = entity.get("locator")
        if not locator or locator.get("type") != "text_span":
            continue
        assert locator["artifact_id"] in minted
    assert adapter.source_type == TWITTER_SOURCE_TYPE


@pytest.mark.parametrize("case", sorted(FINALIZES))
def test_no_fabricated_timestamp_or_watch_url_reaches_a_twitter_artifact(
    tmp_path: Path, case: str
) -> None:
    """The two things the un-dispatched renderer would have invented.

    ``[00:00:00-00:00:00]`` from ``start_sec`` defaulting to ``0``, and a
    ``youtube.com/watch?v=<post id>`` link from ``timestamp_url``. Neither
    raised, so neither would have been noticed by a test that only asked whether
    finalize succeeded.
    """
    run_dir = twitter_project(tmp_path) / case
    finalize_run(run_dir)
    written = [run_dir / "report.md", *sorted((run_dir / "vault").rglob("*.md"))]
    for path in written:
        text = read(path)
        assert "youtube.com" not in text, path
        assert "00:00:00" not in text, path
        assert "&t=" not in text, path


@pytest.mark.parametrize("case", sorted(FINALIZES))
def test_the_coverage_report_audits_items_rather_than_windows(
    tmp_path: Path, case: str
) -> None:
    run_dir = twitter_project(tmp_path) / case
    finalize_run(run_dir)
    anchor = json.loads(read(run_dir / "metadata.json"))["video_id"]
    audit = read(run_dir / "vault" / "reports" / f"{anchor}-coverage.md")
    coverage = json.loads(read(run_dir / "coverage.json"))
    assert coverage["items"], "the fixture audits nothing, so this proves nothing"
    for item in coverage["items"]:
        assert f"## {item['item_id']}" in audit
        assert f"- Post: `{item['post_id']}`" in audit
    assert "- Span: " not in audit
    assert "post-by-post audit" in read(run_dir / "report.md")


def test_persian_text_survives_the_vault_with_its_joiners_intact(
    tmp_path: Path,
) -> None:
    """A ZWNJ is part of the word, so a note that loses it loses the quote."""
    run_dir = twitter_project(tmp_path) / "persian-rtl"
    finalize_run(run_dir)
    excerpts = [
        unit["source"]["evidence_excerpt"]
        for unit in units_of(run_dir)
        if unit["source_class"] == "source"
    ]
    assert any("‌" in excerpt for excerpt in excerpts), "fixture carries no ZWNJ"
    report = read(run_dir / "report.md")
    for excerpt in excerpts:
        assert excerpt in report


# ---------------------------------------------------------------------------
# The two refusals D-234 required be kept, and the ones the dispatch adds.
# ---------------------------------------------------------------------------


def test_a_failing_twitter_run_is_refused_before_the_first_write(
    tmp_path: Path,
) -> None:
    """``tombstone``'s capture is ``FAIL``, and nothing is written for it.

    "Before the first write" is the load-bearing half: ``graph.json`` and
    ``report.md`` are overwritten in place and ``rebuild_library`` merges the
    result, so a refusal that happened half way through would leave a run
    describing itself two ways.
    """
    run_dir = twitter_project(tmp_path) / "tombstone"
    before = sorted(path.name for path in run_dir.iterdir())
    with pytest.raises(VerdictRefusal) as raised:
        finalize_run(run_dir)
    assert raised.value.status == "FAIL"
    assert not (run_dir / "report.md").exists()
    assert not (run_dir / "graph.json").exists()
    assert not (run_dir / "vault").exists()
    assert sorted(path.name for path in run_dir.iterdir()) == before


def test_a_failing_youtube_run_is_still_refused(tmp_path: Path) -> None:
    run_dir = youtube_run(tmp_path, "fail-run")
    shutil.rmtree(run_dir / "vault")
    (run_dir / "report.md").unlink()
    (run_dir / "graph.json").unlink()
    with pytest.raises(VerdictRefusal):
        finalize_run(run_dir)
    assert not (run_dir / "vault").exists()
    assert not (run_dir / "report.md").exists()


def test_an_unknown_medium_is_refused_rather_than_finalized_as_a_video(
    tmp_path: Path,
) -> None:
    """``validate_provenance`` defaults an unknown medium to YouTube; this refuses.

    The difference is what each does next. That function goes on to *report*;
    this one goes on to write files whose names, frontmatter and provenance lines
    come from the answer, so guessing would put a ``type: video`` note with
    invented timestamps in a medium's vault.
    """
    run_dir = twitter_project(tmp_path) / "single-post"
    metadata = json.loads(read(run_dir / "metadata.json"))
    metadata["source_type"] = "medium-article"
    write_json(run_dir / "metadata.json", metadata)
    with pytest.raises(PipelineError) as raised:
        finalize_run(run_dir)
    message = str(raised.value)
    assert "medium-article" in message
    assert "MEDIUM_PROFILES" in message
    assert not (run_dir / "vault").exists()


def test_a_twitter_run_with_no_capture_digest_is_refused_before_writing(
    tmp_path: Path,
) -> None:
    """The integrity row ``report.md`` prints, and what happens when it is absent.

    ``transcript_hash`` has no counterpart for this medium and
    ``canonical_hashes`` is an object, so the string check in
    ``_checked_metadata`` cannot see it. It is checked by the renderer that reads
    it instead — and because every line is built before ``write_group`` is
    reached, that refusal still lands before the first write.
    """
    run_dir = twitter_project(tmp_path) / "single-post"
    metadata = json.loads(read(run_dir / "metadata.json"))
    metadata["canonical_hashes"] = {}
    write_json(run_dir / "metadata.json", metadata)
    with pytest.raises(PipelineError) as raised:
        finalize_run(run_dir)
    assert "capture.json" in str(raised.value)
    assert not (run_dir / "report.md").exists()
    assert not (run_dir / "vault").exists()


def test_a_missing_medium_field_names_the_medium_it_is_missing_for(
    tmp_path: Path,
) -> None:
    run_dir = twitter_project(tmp_path) / "single-post"
    metadata = json.loads(read(run_dir / "metadata.json"))
    del metadata["source_url"]
    write_json(run_dir / "metadata.json", metadata)
    with pytest.raises(PipelineError) as raised:
        finalize_run(run_dir)
    assert "source_url" in str(raised.value)
    assert "post" in str(raised.value)


def test_a_youtube_run_is_not_asked_for_a_twitter_field(tmp_path: Path) -> None:
    """The old check demanded all five fields of every medium at once.

    A YouTube run has no ``source_url`` and a Twitter run has no
    ``transcript_hash``: one list could only ever be satisfied by one medium.
    """
    assert "source_url" not in MEDIUM_PROFILES[DEFAULT_SOURCE_TYPE].required_metadata
    assert "transcript_hash" not in MEDIUM_PROFILES[TWITTER_SOURCE_TYPE].required_metadata
    run_dir = youtube_run(tmp_path)
    metadata = json.loads(read(run_dir / "metadata.json"))
    assert "source_url" not in metadata
    assert finalize_run(run_dir)["status"] == "PASS"


# ---------------------------------------------------------------------------
# One implementation, and one table that cannot drift from the adapters.
# ---------------------------------------------------------------------------


def test_there_is_one_finalize_path_and_a_table_it_dispatches_on() -> None:
    """A second ``finalize_run`` is what D-185 is about, so there is not one."""
    finalizers = [
        name
        for name in dir(artifacts)
        if name.startswith("finalize") and callable(getattr(artifacts, name))
    ]
    assert finalizers == ["finalize_run"], finalizers
    assert set(MEDIUM_PROFILES) == {DEFAULT_SOURCE_TYPE, TWITTER_SOURCE_TYPE}


def test_every_profile_answers_every_question_finalize_asks() -> None:
    """A row added for a third medium cannot be a partial row.

    ``dataclass`` already requires the fields; what this adds is that none of
    them is left as a placeholder, which is the shape a hurried fourth row would
    take.
    """
    for source_type, profile in MEDIUM_PROFILES.items():
        assert profile.note_type and profile.note_dir, source_type
        assert profile.id_key and profile.backlink_label, source_type
        assert profile.url_field and profile.coverage_noun, source_type
        assert profile.required_metadata, source_type
        assert "title" in profile.required_metadata, source_type
        for hook in (
            profile.metadata_lines,
            profile.provenance_lines,
            profile.coverage_sections,
            profile.validate,
        ):
            assert callable(hook), (source_type, hook)


def test_no_two_media_write_their_notes_into_the_same_subtree() -> None:
    """``prune`` deletes this medium's note subtree, so sharing one loses notes."""
    dirs = [profile.note_dir for profile in MEDIUM_PROFILES.values()]
    assert len(dirs) == len(set(dirs)), dirs


def test_every_medium_that_can_be_finalized_has_an_adapter() -> None:
    """The finalize table and the adapter registry describe the same media.

    A medium that finalizes but does not project reaches the vault and not the
    library; one that projects but does not finalize is the wall `T-230` exists
    to remove. Either drift is a run that is half in the product.
    """
    for source_type in MEDIUM_PROFILES:
        adapter = get_adapter(source_type, ROOT)
        assert adapter.source_type == source_type


def test_a_retracted_note_stops_existing_for_this_medium_too(tmp_path: Path) -> None:
    """D-090's pruning, over the subtree this medium owns rather than ``videos``."""
    run_dir = twitter_project(tmp_path) / "single-post"
    finalize_run(run_dir)
    stale = run_dir / "vault" / "posts" / "not-a-run-anymore.md"
    stale.write_text("stale", encoding="utf-8")
    orphan = run_dir / "vault" / "knowledge_units" / "source" / "KU-999999.md"
    orphan.write_text("stale", encoding="utf-8")
    keep = run_dir / "vault" / "notes-of-my-own.md"
    keep.write_text("mine", encoding="utf-8")
    finalize_run(run_dir)
    assert not stale.exists()
    assert not orphan.exists()
    assert keep.exists(), "finalize pruned a subtree it does not own"


# ---------------------------------------------------------------------------
# And the library, which is where the vault stops being per-run.
# ---------------------------------------------------------------------------


def test_rebuild_library_merges_a_finalized_twitter_run(tmp_path: Path) -> None:
    runs = twitter_project(tmp_path, "self-thread")
    run_dir = runs / "self-thread"
    finalize_run(run_dir)
    library = rebuild_library(runs)
    status = json.loads(read(runs / "library" / "status.json"))
    assert status["runs_indexed"] >= 1
    nodes = json.loads(read(runs / "library" / "graph.json"))["nodes"]
    twitter_nodes = [
        node for node in nodes if node.get("source_type") == TWITTER_SOURCE_TYPE
    ]
    assert len(twitter_nodes) >= len(units_of(run_dir))
    # The clause in as many words: no YouTube-shaped field reaches a path. The
    # run indexes without a problem recorded against it, and it indexes as its
    # own medium rather than as the default one.
    anchor = json.loads(read(run_dir / "metadata.json"))["video_id"]
    videos = json.loads(read(runs / "library" / "videos.json"))["videos"]
    entry = next(item for item in videos if item["video_id"] == anchor)
    assert entry["problems"] == []
    assert entry["channel"], "the author is what this medium calls a channel"
    assert library["knowledge_nodes"] >= len(units_of(run_dir))


def test_both_media_finalize_in_one_project(tmp_path: Path) -> None:
    """The clause in as many words: one YouTube run and one Twitter run.

    In one project root, through one ``finalize_run``, into one library — which
    is the only place the two media can be shown not to interfere with each
    other rather than merely to work one at a time.

    The Twitter fixture tree is the project root, because a capture records its
    raw evidence relative to ``run_dir.parent.parent``; the YouTube run is
    copied in beside it, which is what makes this one project and not two.
    """
    runs = twitter_project(tmp_path, "single-post")
    shutil.copytree(YOUTUBE_RUNS / "pass-run", runs / "fixture-pass")

    youtube_result = finalize_run(runs / "fixture-pass")
    twitter_result = finalize_run(runs / "single-post")
    assert youtube_result["status"] == "PASS"
    assert twitter_result["status"] == "PASS"

    assert (runs / "fixture-pass" / "vault" / "videos").is_dir()
    assert (runs / "single-post" / "vault" / "posts").is_dir()

    records = adapt_project(runs.parent)
    kinds = {artifact["kind"] for artifact in records.by_model()["artifact"]}
    assert "post" in kinds
    sources = {source["source_type"] for source in records.by_model()["source"]}
    assert {DEFAULT_SOURCE_TYPE, TWITTER_SOURCE_TYPE} <= sources

    library = rebuild_library(runs)
    assert library["runs_indexed"] >= 2
