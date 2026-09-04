"""The Phase 2.2 gate: the whole journey at the shell, and how it fails (`T-229`).

Every earlier task in this phase proved one link. This proves the chain, and it
proves it through ``cli.main`` rather than through library calls, because that is
the surface an operator and `WORKFLOW.md` actually have: a link that works when
called from Python and not from the command line is a link the documented
workflow cannot use. Before this task nothing in ``twitter.extract`` was
reachable from the CLI at all — ``capture`` wrote a capture and stopped — and
``x2knwldg validate`` called ``pipeline.validate_run`` outright, so it reported
every Twitter run as broken for having no transcript (D-243).

The failure rehearsal is the other half, and it is the half the phase gate exists
for. The named cases are the ones `T-222` measured or `T-224` built refusals for:
the approved provider order, a provider that is not installed, a provider that
cannot reach the network, a provider whose output moved, offline operation, a
partial thread, a tombstone, and raw evidence that has been altered after the
fact. Each has to fail as *itself* — a distinct exit code and a named reason —
because a caller that cannot tell a dropped tunnel from a changed provider will
retry the wrong one or discard a good capture for the wrong reason (D-209).

What is deliberately **not** here: any test that reaches the real network, the
real ``x-cli`` or the user's tunnel. The provider is stubbed through the same
harness `T-224` used, and the live walk over the target environment is an
operator step recorded in `PROJECT_MANAGEMENT.md` §5 rather than something a
test can assert from this machine.
"""

from __future__ import annotations

import importlib.util
import io as io_module
import json
import shutil
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any

import pytest
from twitter_harness import (
    STUB_VERSION_STRING,
    argv_log,
    boxed,
    make_stub,
    spike,
    spike_record,
    thread_manifest,
    thread_responses,
)

from x2knwldg import cli
from x2knwldg.adapters import adapt_project
from x2knwldg.artifacts import MEDIUM_PROFILES
from x2knwldg.twitter import extract
from x2knwldg.twitter import provider as provider_module

ROOT = Path(__file__).resolve().parents[1]
TWITTER_RUNS = ROOT / "tests" / "fixtures" / "twitter-runs"

EN_POST = spike_record("single_post_en__xcli_guest")["id"]
FA_POST = spike_record("single_post_fa__xcli_guest")["id"]

_spec = importlib.util.spec_from_file_location(
    "t229_twitter_build_fixtures", TWITTER_RUNS / "build_fixtures.py"
)
assert _spec and _spec.loader
builder = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(builder)


def run(argv: list[str]) -> tuple[int, Any, list[dict]]:
    """One command. Returns its code, its stdout document, and its stderr ones."""
    out, err = io_module.StringIO(), io_module.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main(argv)
    stdout = json.loads(out.getvalue()) if out.getvalue().strip() else {}
    stderr = [json.loads(line) for line in err.getvalue().splitlines() if line.strip()]
    return code, stdout, stderr


@pytest.fixture
def pinned(monkeypatch: pytest.MonkeyPatch):
    """A stub provider that ``verify`` pins for real, digest and all.

    The same fixture `T-224`'s CLI tests use, for the same reason: the
    verification path stays the real one and is never given a way to be told
    "accept whatever you find" — only the lookup is redirected.
    """
    real_verify = provider_module.verify

    def install(tmp_path: Path, **stub_kwargs) -> Path:
        binary = make_stub(tmp_path / "bin", **stub_kwargs)
        provider = real_verify(
            binary,
            expected_sha256=provider_module.sha256_of(binary),
            expected_version_string=STUB_VERSION_STRING,
        )
        monkeypatch.setattr(provider_module, "verify", lambda _binary=None: provider)
        return binary

    return install


def bundle_for(run_dir: Path) -> Path:
    """The bundle a model pass would have produced, written where the CLI can read it.

    ``build_fixtures._bundle`` rather than a hand-written expectation: it is the
    extraction the committed fixtures were built by, so what this walks is the
    same shape the rest of the suite is about.
    """
    capture = json.loads((run_dir / "capture.json").read_text(encoding="utf-8"))
    coverage = json.loads((run_dir / "coverage.json").read_text(encoding="utf-8"))
    path = run_dir / "work" / "extraction_bundle.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(builder._bundle(capture, coverage), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def committed_run(tmp_path: Path, case: str) -> Path:
    """One committed fixture, in a project laid out so both of its readers work.

    ``adapt_project`` scans ``<root>/output/*``; a capture resolves its recorded
    ``raw_evidence`` against ``run_dir.parent.parent``, and those paths were
    recorded relative to ``tests/fixtures/`` as ``twitter-runs/<case>/raw/...``
    (D-231). So the run goes in ``output/`` and its ``raw/`` tree is placed a
    second time where the capture says to look. A freshly captured run needs
    none of this — its evidence is recorded relative to its own project — which
    is why the walk below captures rather than copies.
    """
    root = tmp_path / "project"
    (root / "output").mkdir(parents=True)
    shutil.copytree(TWITTER_RUNS / case, root / "output" / case)
    shutil.copytree(TWITTER_RUNS / case / "raw", root / "twitter-runs" / case / "raw")
    return root / "output" / case


# ---------------------------------------------------------------------------
# The journey, at the shell.
# ---------------------------------------------------------------------------


def test_a_thread_walks_from_a_url_to_a_vault_note_at_the_shell(
    tmp_path: Path, pinned
) -> None:
    """Acquisition, evidence, extraction, validation, library, and a note.

    Ten posts, captured from the thread's last post as D-206 requires, then
    every remaining step of `WORKFLOW.md` driven as a command. This is the gate
    sentence in one test: a reference goes in and a vault note comes out, with
    each step's exit code checked on the way.
    """
    manifest = thread_manifest()
    pinned(tmp_path, posts=thread_responses())
    output = tmp_path / "output"

    code, capture_payload, _ = run(
        ["capture", manifest[-1]["post_id"], "--thread", "--via-tunnel", "--output", str(output)]
    )
    assert code == cli.EXIT_OK, capture_payload
    assert capture_payload["items"] == len(manifest)
    run_dir = Path(capture_payload["run_dir"])

    # `capture` now leaves a *run*, not just a file: this is the step that was
    # missing, and the reason nothing downstream could be reached from the CLI.
    assert (run_dir / "metadata.json").is_file()
    assert (run_dir / "coverage.json").is_file()
    assert capture_payload["run_coverage"] == "PARTIAL", "an unaudited run is not a pass"
    assert "apply-bundle" in capture_payload["next"]

    code, applied, _ = run(["apply-bundle", str(run_dir), str(bundle_for(run_dir))])
    assert code == cli.EXIT_OK, applied
    assert applied["status"] == "PASS"

    code, validated, _ = run(["validate", str(run_dir)])
    assert code == cli.EXIT_OK
    assert validated["status"] == "PASS"
    assert "transcript" not in validated, "a post run has a capture section, not a transcript one"
    assert validated["capture"]["status"] == "PASS"

    code, finalized, _ = run(["finalize", str(run_dir)])
    assert code == cli.EXIT_OK
    assert finalized["status"] == "PASS"

    anchor = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))["video_id"]
    note = run_dir / "vault" / "posts" / f"{anchor}.md"
    assert note.is_file()
    assert "type: post" in note.read_text(encoding="utf-8")
    assert (run_dir / "report.md").is_file()
    assert (run_dir / "graph.json").is_file()

    code, listed, _ = run(["status", "--output", str(output)])
    assert code == cli.EXIT_OK
    assert [row["video_id"] for row in listed["videos"]] == [anchor]
    assert listed["videos"][0]["coverage"] == "PASS"

    code, found, _ = run(["search", "Roman", "--output", str(output)])
    assert code == cli.EXIT_OK
    assert found["results"], "a finalized run is not searchable"

    code, library, _ = run(["rebuild-library", "--output", str(output)])
    assert code == cli.EXIT_OK
    assert library["runs_indexed"] == 1
    assert library["runs_skipped"] == 0

    records = adapt_project(tmp_path)
    kinds = {artifact["kind"] for artifact in records.by_model()["artifact"]}
    assert {"capture", "post"} <= kinds


def test_a_persian_post_completes_the_journey_with_its_text_intact(
    tmp_path: Path, pinned
) -> None:
    """The corpus this project exists for, walked end to end.

    A sanitized committed fixture is what CI can run; the real public Persian
    case over the user's tunnel is an operator step. What this pins is that
    nothing between acquisition and the vault normalizes the text: the authored
    form (D-211) reaches ``report.md`` and the note byte for byte, ZWNJ included.
    """
    pinned(tmp_path, posts={FA_POST: {"exit": 0, "stdout": spike("single_post_fa__xcli_guest")}})
    output = tmp_path / "output"

    code, payload, _ = run(["capture", FA_POST, "--via-tunnel", "--output", str(output)])
    assert code == cli.EXIT_OK, payload
    run_dir = Path(payload["run_dir"])

    assert run(["apply-bundle", str(run_dir), str(bundle_for(run_dir))])[0] == cli.EXIT_OK
    assert run(["finalize", str(run_dir)])[0] == cli.EXIT_OK

    capture = json.loads((run_dir / "capture.json").read_text(encoding="utf-8"))
    authored = extract.canonical_text(capture["items"][0])
    assert "‌" in authored, "the fixture carries no ZWNJ, so this proves nothing"

    anchor = capture["anchor"]["post_id"]
    report = (run_dir / "report.md").read_text(encoding="utf-8")
    note = (run_dir / "vault" / "posts" / f"{anchor}.md").read_text(encoding="utf-8")

    # Every excerpt is a verbatim slice of the authored text, and every one of
    # them reaches the report intact -- so the text survives acquisition,
    # extraction, validation and rendering without being normalized once.
    units = _source_units(run_dir)
    assert units
    for unit in units:
        source = unit["source"]
        excerpt = source["evidence_excerpt"]
        assert excerpt == authored[source["start_char"] : source["end_char"]]
        assert excerpt in report
    assert "‌" in report
    assert "‌" in note


def _source_units(run_dir: Path) -> list[dict[str, Any]]:
    units = json.loads((run_dir / "knowledge_units.json").read_text(encoding="utf-8"))["units"]
    return [unit for unit in units if unit["source_class"] == "source"]


def test_validate_no_longer_reports_a_post_run_as_a_broken_video(
    tmp_path: Path,
) -> None:
    """The command's own version of the seventh YouTube-shaped place (D-240).

    ``x2knwldg validate`` called ``pipeline.validate_run``, which reads
    ``transcript.json`` and ``segments.json``. A Twitter run has neither, so the
    command failed with a missing-canonical-file error — a correct validator
    applied to the wrong medium, reported as damage to the run.
    """
    run_dir = committed_run(tmp_path, "single-post")
    code, payload, _ = run(["validate", str(run_dir)])
    assert code == cli.EXIT_OK
    assert payload["status"] == "PASS"
    assert set(payload) >= {"capture", "evidence", "knowledge_units", "provenance"}
    assert "transcript" not in payload


def test_a_youtube_run_still_validates_through_the_same_command(
    tmp_path: Path,
) -> None:
    project = tmp_path / "output"
    project.mkdir()
    run_dir = project / "pass-run"
    shutil.copytree(ROOT / "tests" / "fixtures" / "runs" / "pass-run", run_dir)
    code, payload, _ = run(["validate", str(run_dir)])
    assert code == cli.EXIT_OK
    assert payload["status"] == "PASS"
    assert "transcript" in payload, "a video run's report has a transcript section"
    assert "capture" not in payload


# ---------------------------------------------------------------------------
# The approved provider order, and what happens when it cannot be followed.
# ---------------------------------------------------------------------------


def test_only_the_pinned_local_route_is_read(tmp_path: Path, pinned) -> None:
    """ADR 0007's order, checked by what the capture says it did.

    FxTwitter is opt-in and oEmbed is corroborative, and neither exists yet
    (`T-225`), so the honest statement is that one route was read and the
    capture names it. A capture claiming corroboration it never obtained is the
    failure this guards.
    """
    binary = pinned(
        tmp_path, posts={EN_POST: {"exit": 0, "stdout": spike("single_post_en__xcli_guest")}}
    )
    code, payload, _ = run(
        ["capture", EN_POST, "--via-tunnel", "--output", str(tmp_path / "output")]
    )
    assert code == cli.EXIT_OK
    assert payload["routes_read"] == 1

    capture = json.loads(Path(payload["capture"]).read_text(encoding="utf-8"))
    routes = {route["route"] for route in capture["acquisition"]["routes_read"]}
    assert routes == {"xcli_guest"}
    for item in capture["items"]:
        assert item["text"]["completeness"]["status"] == "unverified"
    # Every subprocess this command ran was the pinned binary, and no other.
    assert argv_log(binary), "the provider was never invoked"


def test_a_provider_that_is_not_installed_exits_seven_and_writes_nothing(
    tmp_path: Path,
) -> None:
    code, payload, errors = run(
        [
            "capture",
            "20",
            "--via-tunnel",
            "--xcli",
            str(tmp_path / "nothing-here"),
            "--output",
            str(tmp_path / "output"),
        ]
    )
    assert code == cli.EXIT_PROVIDER_UNAVAILABLE
    assert payload == {}
    assert errors[-1]["status"] == "PROVIDER_UNAVAILABLE"
    assert not (tmp_path / "output").exists()


def test_provider_removal_leaves_an_acquired_run_fully_usable(
    tmp_path: Path, pinned
) -> None:
    """Extraction, validation and finalize read the capture, never the provider.

    So a provider that is uninstalled, or a machine with no tunnel at all,
    changes nothing about a run already acquired. This is what makes the
    evidence in ``raw/`` worth preserving, and it is the offline half of the
    rehearsal: the last four steps of the journey run with no provider present.
    """
    pinned(tmp_path, posts={EN_POST: {"exit": 0, "stdout": spike("single_post_en__xcli_guest")}})
    output = tmp_path / "output"
    code, payload, _ = run(["capture", EN_POST, "--via-tunnel", "--output", str(output)])
    assert code == cli.EXIT_OK
    run_dir = Path(payload["run_dir"])

    # The provider goes away. Nothing below may notice.
    shutil.rmtree(tmp_path / "bin")

    assert run(["apply-bundle", str(run_dir), str(bundle_for(run_dir))])[0] == cli.EXIT_OK
    assert run(["validate", str(run_dir)])[0] == cli.EXIT_OK
    assert run(["finalize", str(run_dir)])[0] == cli.EXIT_OK
    assert run(["rebuild-library", "--output", str(output)])[0] == cli.EXIT_OK


def test_a_failed_read_cannot_erase_or_rewrite_a_prior_capture(
    tmp_path: Path, pinned
) -> None:
    """The invariant the acceptance clause states in as many words.

    A second attempt at the same post — whether the provider is unreachable, has
    drifted, or is simply run again — must leave the first capture and its raw
    evidence exactly as they were. Immutable evidence that a retry can overwrite
    is not evidence.
    """
    pinned(tmp_path, posts={EN_POST: {"exit": 0, "stdout": spike("single_post_en__xcli_guest")}})
    output = tmp_path / "output"
    code, payload, _ = run(["capture", EN_POST, "--via-tunnel", "--output", str(output)])
    assert code == cli.EXIT_OK
    run_dir = Path(payload["run_dir"])
    before = {
        path.relative_to(run_dir): path.read_bytes()
        for path in sorted(run_dir.rglob("*"))
        if path.is_file()
    }

    for stub in (
        {"exit": 8, "stderr": boxed("Cannot reach x.com: dial tcp")},
        {"exit": 0, "stdout": "<html>not json</html>"},
        {"exit": 0, "stdout": spike("single_post_en__xcli_guest")},
    ):
        pinned(tmp_path / f"retry-{stub['exit']}-{len(stub)}", default=stub)
        code, _, _ = run(["capture", EN_POST, "--via-tunnel", "--output", str(output)])
        assert code != cli.EXIT_OK, "a second capture over existing evidence must refuse"

    after = {
        path.relative_to(run_dir): path.read_bytes()
        for path in sorted(run_dir.rglob("*"))
        if path.is_file()
    }
    assert after == before


def test_altered_raw_evidence_fails_validation_and_cannot_be_finalized(
    tmp_path: Path,
) -> None:
    """The corrupted-evidence case, at the shell.

    ``evidence_integrity`` recomputes the digest of the preserved bytes and
    re-derives the item set from them, so a raw file edited after the fact is a
    ``FAIL`` — and ``finalize`` refuses a ``FAIL`` before its first write, so the
    tampering cannot reach ``report.md``, the vault or the library.
    """
    run_dir = committed_run(tmp_path, "single-post")
    project_root = run_dir.parent.parent
    capture = json.loads((run_dir / "capture.json").read_text(encoding="utf-8"))
    evidence = project_root / capture["raw_evidence"][0]["path"]
    assert evidence.is_file(), evidence
    evidence.write_text(
        evidence.read_text(encoding="utf-8").replace("twttr", "twttr "), encoding="utf-8"
    )

    code, payload, _ = run(["validate", str(run_dir)])
    assert code == cli.EXIT_FAIL
    assert payload["status"] == "FAIL"
    assert payload["evidence"]["status"] == "FAIL"

    code, _, errors = run(["finalize", str(run_dir)])
    assert code == cli.EXIT_FAIL
    assert errors[-1]["status"] == "FAIL"
    assert not (run_dir / "report.md").exists()
    assert not (run_dir / "vault").exists()
    assert not (run_dir / "graph.json").exists()


def test_a_partial_thread_is_reported_as_partial_at_every_step(
    tmp_path: Path,
) -> None:
    """`PARTIAL` travels: exit `3`, and a finalized run that says so.

    An honestly incomplete run is a deliverable (`WORKFLOW.md` §4.5), and the
    thing that must never happen is `PARTIAL` arriving as `0`.
    """
    run_dir = committed_run(tmp_path, "partial-thread")
    code, payload, _ = run(["validate", str(run_dir)])
    assert code == cli.EXIT_PARTIAL
    assert payload["status"] == "PARTIAL"

    code, finalized, _ = run(["finalize", str(run_dir)])
    assert code == cli.EXIT_PARTIAL
    assert finalized["status"] == "PARTIAL"
    assert "**Coverage: PARTIAL**" in (run_dir / "report.md").read_text(encoding="utf-8")


def test_a_tombstone_is_a_named_failure_and_finalizes_nothing(
    tmp_path: Path,
) -> None:
    run_dir = committed_run(tmp_path, "tombstone")
    code, payload, _ = run(["validate", str(run_dir)])
    assert code == cli.EXIT_FAIL
    assert payload["capture"]["status"] == "FAIL"

    code, _, errors = run(["finalize", str(run_dir)])
    assert code == cli.EXIT_FAIL
    assert errors[-1]["status"] == "FAIL"
    assert not (run_dir / "report.md").exists()
    assert not (run_dir / "vault").exists()


def test_an_apply_gate_refusal_leaves_the_run_as_it_was(tmp_path: Path) -> None:
    """The gate, reached through the command rather than the library.

    A bundle that fails validation is refused rather than written (D-229,
    D-230), so the run cannot reach the disk in a state its own validators
    reject — and the exit code is `1`, a refusal, not `4`, a verdict.
    """
    run_dir = committed_run(tmp_path, "single-post")
    before = (run_dir / "knowledge_units.json").read_bytes()
    bundle = run_dir / "work" / "bad_bundle.json"
    bundle.parent.mkdir(parents=True, exist_ok=True)
    bundle.write_text(
        json.dumps(
            {
                "knowledge_units": [
                    {
                        "id": "KU-000001",
                        "kind": "quote",
                        "source_class": "source",
                        "content": "a quote that is not in the capture",
                        "confidence": 0.9,
                        "source": {
                            "post_id": "20",
                            "start_char": 0,
                            "end_char": 5,
                            "evidence_excerpt": "never appeared in the post",
                        },
                    }
                ],
                "relationships": [],
                "coverage": {"status": "PASS", "audit_attempts": 1, "items": []},
            }
        ),
        encoding="utf-8",
    )
    code, _, errors = run(["apply-bundle", str(run_dir), str(bundle)])
    assert code == cli.EXIT_ERROR
    assert errors, "a refusal that says nothing is not a refusal"
    assert (run_dir / "knowledge_units.json").read_bytes() == before


# ---------------------------------------------------------------------------
# What the documentation is allowed to promise.
# ---------------------------------------------------------------------------


def test_the_capability_table_promises_no_route_that_does_not_exist() -> None:
    """`WORKFLOW.md`'s Twitter capability table, checked against the code.

    The phase row requires the `T-225`/`T-226` selection be *recorded* before
    this task runs, "since its capability table may not promise a route that
    does not exist" (D-243: neither is selected, and the table says so). This is
    that requirement as a test: if a later task adds a provider, this fails until
    the table is updated, and if the table names one now, it fails today.
    """
    workflow = (ROOT / "WORKFLOW.md").read_text(encoding="utf-8")
    table = workflow[workflow.index("<!-- twitter-capability-table -->") :]
    table = table[: table.index("<!-- /twitter-capability-table -->")]
    assert "xcli_guest" in table
    for absent in ("FxTwitter", "FxEmbed", "oEmbed", "Firefox"):
        assert absent in table, f"{absent} must be listed, as unsupported"
        line = next(row for row in table.splitlines() if absent in row)
        assert "not implemented" in line.lower() or "unsupported" in line.lower(), line

    from x2knwldg.twitter.provider import TIERS

    # The table names the tiers and the one route. If a tier or a route is added,
    # this fails until the table says what it is -- which is the point: the
    # documentation must not lag the code it describes.
    assert {tier.number for tier in TIERS.values()} == {0, 1}, sorted(TIERS)
    routes = {tier.route for tier in TIERS.values()}
    assert routes == {"xcli_tier0", "xcli_guest"}, routes
    assert "tiers 0 and 1" in table


def test_the_documented_commands_all_exist() -> None:
    """Every command `WORKFLOW.md`'s Twitter section tells an operator to run.

    Documentation that names a command the CLI does not have is the failure mode
    the row's "only to behaviour now implemented" clause is about, and it is the
    one a reader discovers instead of a test.
    """
    workflow = (ROOT / "WORKFLOW.md").read_text(encoding="utf-8")
    named = {
        line.split("x2knwldg ")[1].split()[0].strip("`")
        for line in workflow.splitlines()
        if "x2knwldg " in line
    }
    parser_help = io_module.StringIO()
    with redirect_stdout(parser_help), pytest.raises(SystemExit):
        cli.main(["--help"])
    available = parser_help.getvalue()
    for command in sorted(named):
        assert command in available, f"WORKFLOW.md names `x2knwldg {command}`, which does not exist"


def test_both_media_are_documented_as_reaching_the_same_end() -> None:
    """The finalize table and the workflow cannot describe different media."""
    workflow = (ROOT / "WORKFLOW.md").read_text(encoding="utf-8")
    for source_type in MEDIUM_PROFILES:
        assert source_type in workflow, f"{source_type} finalizes but is undocumented"
