"""Tests for ``x2knwldg.mcp_server`` — the MCP tool surface.

Before this file the module was 350 lines, ten tools, three resources, one
prompt, and not one import from any test: the only thing referring to it read
the file as text and grepped for a string. Every defect in it was found by
reading, which is exactly the position a test suite exists to get out of.

Rules this file keeps:

* **No network, no clock, no randomness.** Nothing in here reaches outside the
  process, and nothing is timing- or ordering-dependent.
* **``output/`` is never touched.** Every test builds a throwaway project in
  ``tmp_path`` from the committed fixtures in ``tests/fixtures/runs/``, which are
  copied and never written to — ``test_repository.py`` and ``test_adapters.py``
  assert those trees' mtimes are unchanged.
* **It runs everywhere.** The tools are plain functions, so nothing here needs
  the ``mcp`` extra installed. Only the handful of tests that assert the
  *registration* skip without it.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from x2knwldg import mcp_server

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_RUNS = PROJECT_ROOT / "tests" / "fixtures" / "runs"

#: The fixture whose canonical files are complete enough to read segments,
#: coverage windows and captions out of.
PASS_RUN = "pass-run"


# ---------------------------------------------------------------------------
# A throwaway project
# ---------------------------------------------------------------------------


def _make_project(tmp_path: Path, runs: tuple[str, ...] = (PASS_RUN,)) -> Path:
    """A directory that looks like this project, holding copies of *runs*.

    Copies, so the committed fixtures keep their content *and* their mtimes.
    """
    root = tmp_path / "project"
    (root / "output").mkdir(parents=True)
    (root / "WORKFLOW.md").write_text("# workflow\n", encoding="utf-8")
    (root / "prompts").mkdir()
    for name in mcp_server.EXTRACTION_PROMPTS:
        (root / "prompts" / f"{name}.md").write_text(f"# {name}\n", encoding="utf-8")
    (root / "schemas").mkdir()
    (root / "schemas" / "extraction_bundle.schema.json").write_text("{}\n", encoding="utf-8")
    for run in runs:
        shutil.copytree(FIXTURE_RUNS / run, root / "output" / run)
    return root


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the server at a throwaway project and return its root."""
    root = _make_project(tmp_path)
    monkeypatch.setattr(mcp_server, "PROJECT_ROOT", root.resolve())
    return root.resolve()


@pytest.fixture
def not_a_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the server at a directory that is not a project at all."""
    root = tmp_path / "somewhere-else"
    (root / "output").mkdir(parents=True)
    monkeypatch.setattr(mcp_server, "PROJECT_ROOT", root.resolve())
    return root.resolve()


def _segment_ids(root: Path, run: str) -> list[str]:
    document = json.loads((root / "output" / run / "segments.json").read_text(encoding="utf-8"))
    return [segment["segment_id"] for segment in document["segments"]]


def _window_ids(root: Path, run: str) -> list[str]:
    document = json.loads((root / "output" / run / "coverage.json").read_text(encoding="utf-8"))
    return [window["window_id"] for window in document.get("windows", [])]


# ---------------------------------------------------------------------------
# The surface exists and is wired
# ---------------------------------------------------------------------------


def test_the_module_imports_without_the_mcp_extra() -> None:
    """The tools are behaviour; the decorators are only registration.

    When the tools lived inside ``if MCPServer is not None:`` they could not be
    tested at all on a bare core install, which is one of the two CI jobs.
    """
    assert mcp_server.TOOLS
    assert callable(mcp_server.list_ingested_videos)


def test_every_tool_resource_and_prompt_is_reachable_by_name() -> None:
    """Nothing in the surface may be registered and then unreachable."""
    exported = list(mcp_server.TOOLS) + [fn for _, fn in mcp_server.RESOURCES]
    exported += list(mcp_server.PROMPTS)
    assert len(exported) == 14, [fn.__name__ for fn in exported]
    for function in exported:
        assert getattr(mcp_server, function.__name__) is function
        assert function.__doc__, f"{function.__name__} has no description for the client"


def test_the_registered_server_exposes_exactly_the_declared_surface() -> None:
    if mcp_server.mcp is None:
        pytest.skip("the mcp extra is not installed")
    import asyncio

    names = {tool.name for tool in asyncio.run(mcp_server.mcp.list_tools())}
    assert names == {function.__name__ for function in mcp_server.TOOLS}
    prompts = {prompt.name for prompt in asyncio.run(mcp_server.mcp.list_prompts())}
    assert prompts == {function.__name__ for function in mcp_server.PROMPTS}


def test_every_error_code_the_server_raises_is_in_the_d030_taxonomy() -> None:
    assert "invalid_id" in mcp_server.ERROR_CODES
    assert "not_found" in mcp_server.ERROR_CODES
    assert "index_unavailable" in mcp_server.ERROR_CODES


# ---------------------------------------------------------------------------
# The root is proven, never assumed
# ---------------------------------------------------------------------------


def test_a_root_that_is_not_a_project_is_refused_not_answered_empty(
    not_a_project: Path,
) -> None:
    """The defect: a misconfigured root reported "you have no videos".

    An empty library is a claim about the user's data. "I am looking in the
    wrong directory" is a claim about the server. Reporting the second as the
    first is the same dishonesty as coercing PARTIAL to PASS.
    """
    with pytest.raises(mcp_server.McpToolError) as caught:
        mcp_server.list_ingested_videos()
    assert caught.value.code == "index_unavailable"
    assert "not an X2KNWLDG project" in caught.value.message


@pytest.mark.parametrize("marker", mcp_server.PROJECT_MARKERS)
def test_each_project_marker_is_load_bearing(
    marker: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Removing any one of them must be enough to make the root refuse."""
    root = _make_project(tmp_path)
    target = root / marker
    shutil.rmtree(target) if target.is_dir() else target.unlink()
    monkeypatch.setattr(mcp_server, "PROJECT_ROOT", root.resolve())
    with pytest.raises(mcp_server.McpToolError) as caught:
        mcp_server._checked_project_root()
    assert caught.value.code == "index_unavailable"
    assert marker in caught.value.message


def test_a_good_root_is_accepted(project: Path) -> None:
    assert mcp_server._checked_project_root() == project
    assert mcp_server._output_root() == project / "output"


def test_main_refuses_to_start_on_a_root_that_is_not_a_project(
    not_a_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Refuse to start, rather than come up and answer every question wrongly."""

    class _Server:
        def run(self) -> None:  # pragma: no cover - must not be reached
            raise AssertionError("the server started on a root that is not a project")

    monkeypatch.setattr(mcp_server, "mcp", _Server())
    with pytest.raises(SystemExit) as caught:
        mcp_server.main()
    assert "not an X2KNWLDG project" in str(caught.value)


def test_main_starts_on_a_real_project(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    started: list[bool] = []

    class _Server:
        def run(self) -> None:
            started.append(True)

    monkeypatch.setattr(mcp_server, "mcp", _Server())
    mcp_server.main()
    assert started == [True]


def test_main_without_the_extra_names_the_install_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mcp_server, "mcp", None)
    with pytest.raises(SystemExit) as caught:
        mcp_server.main()
    assert ".[mcp]" in str(caught.value)


# ---------------------------------------------------------------------------
# ADR 0003 — an id is resolved, never joined
# ---------------------------------------------------------------------------


HOSTILE_IDS = [
    "../escape",
    "../../etc",
    "a/../../b",
    "/etc/passwd",
    "..",
    ".",
    "",
    ".hidden",
    "with space",
    "null\x00byte",
]

#: Every tool whose first positional argument names a run.
ID_TOOLS = [
    (mcp_server.get_extraction_segment, ("SEG-0001",)),
    (mcp_server.get_coverage_window, ("W-0001",)),
    (mcp_server.validate_video_output, ()),
    (mcp_server.apply_extraction_bundle, ("work/extraction_bundle.json",)),
    (mcp_server.finalize_video, ()),
]


@pytest.mark.parametrize("video_id", HOSTILE_IDS)
@pytest.mark.parametrize("tool,rest", ID_TOOLS, ids=[fn.__name__ for fn, _ in ID_TOOLS])
def test_a_hostile_id_is_refused_by_every_tool_that_takes_one(
    tool: Any, rest: tuple[Any, ...], video_id: str, project: Path
) -> None:
    """ADR 0003: refused, reported, nothing read — and never rewritten."""
    with pytest.raises(mcp_server.McpToolError) as caught:
        tool(video_id, *rest)
    assert caught.value.code == "invalid_id", caught.value.message


def test_apply_extraction_data_refuses_a_hostile_id_too(project: Path) -> None:
    with pytest.raises(mcp_server.McpToolError) as caught:
        mcp_server.apply_extraction_data("../escape", {"knowledge_units": []})
    assert caught.value.code == "invalid_id"


def test_a_refused_id_is_not_reported_as_absence(project: Path) -> None:
    """D-030: ``invalid_id`` and ``not_found`` are different answers.

    Collapsing them hides a traversal attempt behind an ordinary "no such
    video", which is exactly the report an attacker wants.
    """
    with pytest.raises(mcp_server.McpToolError) as refused:
        mcp_server.validate_video_output("../escape")
    with pytest.raises(mcp_server.McpToolError) as absent:
        mcp_server.validate_video_output("no-such-run")
    assert refused.value.code == "invalid_id"
    assert absent.value.code == "not_found"


def test_a_traversal_never_reads_a_file_outside_the_output_root(
    project: Path, tmp_path: Path
) -> None:
    secret = tmp_path / "secret.json"
    secret.write_text('{"segments": [{"segment_id": "SEG-0001"}]}', encoding="utf-8")
    with pytest.raises(mcp_server.McpToolError):
        mcp_server.get_extraction_segment("../secret", "SEG-0001")


# ---------------------------------------------------------------------------
# The two filesystem-path parameters
# ---------------------------------------------------------------------------


def test_a_transcript_path_outside_the_project_is_refused(
    project: Path, tmp_path: Path
) -> None:
    outside = tmp_path / "elsewhere.srt"
    outside.write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n", encoding="utf-8")
    with pytest.raises(mcp_server.McpToolError) as caught:
        mcp_server.import_timestamped_transcript(str(outside), "new-run")
    assert caught.value.code == "invalid_request"
    assert not (project / "output" / "new-run").exists(), "a refused import created a run"


@pytest.mark.parametrize(
    "value", ["/etc/passwd", "../../etc/passwd", "~/.ssh/id_rsa", "", "a\x00b"]
)
def test_a_hostile_bundle_path_is_refused(value: str, project: Path) -> None:
    with pytest.raises(mcp_server.McpToolError) as caught:
        mcp_server.apply_extraction_bundle(PASS_RUN, value)
    assert caught.value.code in {"invalid_request", "not_found"}


def test_a_project_relative_path_is_accepted(project: Path) -> None:
    resolved = mcp_server._checked_input_path(
        f"output/{PASS_RUN}/metadata.json", what="bundle_path"
    )
    assert resolved == project / "output" / PASS_RUN / "metadata.json"


def test_an_absolute_path_inside_the_project_is_accepted(project: Path) -> None:
    inside = project / "output" / PASS_RUN / "metadata.json"
    assert mcp_server._checked_input_path(str(inside), what="bundle_path") == inside


def test_a_path_naming_a_directory_is_refused(project: Path) -> None:
    with pytest.raises(mcp_server.McpToolError) as caught:
        mcp_server._checked_input_path(f"output/{PASS_RUN}", what="bundle_path")
    assert caught.value.code == "not_found"


# ---------------------------------------------------------------------------
# apply_extraction_data writes nothing on the way to an error
# ---------------------------------------------------------------------------


def test_apply_extraction_data_leaves_no_phantom_run_behind(project: Path) -> None:
    """The defect: it wrote ``<run>/work/mcp_extraction_bundle.json`` *first*.

    A typo'd id therefore minted a run-shaped directory that no import had
    created, and the next listing had it to trip over.
    """
    before = sorted(path.name for path in (project / "output").iterdir())
    with pytest.raises(mcp_server.McpToolError) as caught:
        mcp_server.apply_extraction_data("typo-run", {"knowledge_units": []})
    assert caught.value.code == "not_found"
    assert sorted(path.name for path in (project / "output").iterdir()) == before
    assert not (project / "output" / "typo-run").exists()


def test_apply_extraction_data_refuses_a_run_with_no_transcript(project: Path) -> None:
    """A directory is not an ingested run."""
    (project / "output" / "empty-run").mkdir()
    with pytest.raises(mcp_server.McpToolError) as caught:
        mcp_server.apply_extraction_data("empty-run", {"knowledge_units": []})
    assert caught.value.code == "not_found"
    assert not (project / "output" / "empty-run" / "work").exists()


# ---------------------------------------------------------------------------
# Nothing raw crosses the boundary
# ---------------------------------------------------------------------------


def test_redaction_removes_the_project_root(project: Path) -> None:
    text = f"could not read {project}/output/{PASS_RUN}/coverage.json"
    assert str(project) not in mcp_server._redact(text)
    assert "<project>" in mcp_server._redact(text)


def test_redaction_removes_the_home_directory(project: Path) -> None:
    assert str(Path.home()) not in mcp_server._redact(f"opened {Path.home()}/.ssh/config")


def test_redaction_reduces_an_unanticipated_absolute_path_to_its_name(
    project: Path,
) -> None:
    assert mcp_server._redact("failed on /usr/local/lib/thing.json").endswith("thing.json")
    assert "/usr/local/lib" not in mcp_server._redact("failed on /usr/local/lib/thing.json")


def test_a_corrupt_canonical_file_does_not_leak_its_absolute_path(project: Path) -> None:
    """A ``JSONDecodeError`` used to reach the client naming the host path."""
    (project / "output" / PASS_RUN / "segments.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(mcp_server.McpToolError) as caught:
        mcp_server.get_extraction_segment(PASS_RUN, "SEG-0001")
    assert caught.value.code == "unavailable"
    assert str(project) not in str(caught.value)


def test_a_missing_canonical_file_names_the_file_and_not_the_machine(
    project: Path,
) -> None:
    (project / "output" / PASS_RUN / "coverage.json").unlink()
    with pytest.raises(mcp_server.McpToolError) as caught:
        mcp_server.get_coverage_window(PASS_RUN, "W-0001")
    assert caught.value.code == "not_found"
    assert "coverage.json" in caught.value.message
    assert str(project) not in str(caught.value)


def test_an_unexpected_exception_becomes_a_coded_error_not_a_traceback(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(*args: object, **kwargs: object) -> None:
        raise RuntimeError(f"boom in {project}/output")

    monkeypatch.setattr(mcp_server, "validate_run", explode)
    with pytest.raises(mcp_server.McpToolError) as caught:
        mcp_server.validate_video_output(PASS_RUN)
    # D-184: `internal`, the code the frozen `ErrorCode` enum publishes. This
    # module used to say `internal_error` — one taxonomy, two spellings, and
    # no test imported both lists, so nothing could see the divergence.
    assert caught.value.code == "internal"
    assert str(project) not in str(caught.value)


def test_no_successful_reply_carries_an_absolute_host_path(project: Path) -> None:
    """A client is told a run's id and its project-relative path, never where
    the project sits on this machine."""
    rows = mcp_server.list_ingested_videos()
    assert rows
    for row in rows:
        assert not str(row["path"]).startswith("/"), row
        assert str(row["path"]).startswith("output/"), row
        assert str(project) not in json.dumps(row)


# ---------------------------------------------------------------------------
# D-091 — rule 2 applies to replies, not only to failures
# ---------------------------------------------------------------------------
#
# `_redact` was called exclusively inside `_boundary`'s `except` arms, so a
# successful return was passed through verbatim — violating this module's own
# rule 2, "absolute paths never appear in a successful reply either". The test
# above covered exactly one tool, which is why the leak survived in the others:
# `rebuild_cross_video_library` returned `skipped_runs[].reason` and `path`
# naming the operator's checkout, and `finalize_video` returned `report` and
# `graph` as absolute paths.


def _leaked(project: Path, value: object) -> list[str]:
    """Every host path in *value*, so a failure names what escaped."""
    text = json.dumps(value, default=str)
    roots = [str(project), str(project.resolve()), str(project.resolve().parent)]
    return [root for root in roots if len(root) > 1 and root in text]


def test_rebuild_cross_video_library_redacts_its_reply(project: Path) -> None:
    broken = project / "output" / "broken-run"
    broken.mkdir(parents=True, exist_ok=True)
    (broken / "metadata.json").write_text("{not json", encoding="utf-8")

    reply = mcp_server.rebuild_cross_video_library()
    assert _leaked(project, reply) == [], reply
    assert reply["skipped_runs"], "the broken run was not reported at all"
    reason = reply["skipped_runs"][0]["reason"]
    # D-063: the reason still states the damage. Redacting by deleting the
    # sentence would satisfy this test's first assertion and close D-045's
    # diagnostic channel.
    assert "Malformed JSON" in reason
    assert "<project>" in reason
    assert not str(reply["path"]).startswith("/"), reply["path"]


def test_finalize_video_redacts_the_paths_it_reports(project: Path) -> None:
    reply = mcp_server.finalize_video(PASS_RUN)
    assert _leaked(project, reply) == [], reply
    for key in ("report", "graph"):
        assert not str(reply[key]).startswith("/"), (key, reply[key])
        assert str(reply[key]).endswith((".md", ".json"))


def test_every_tool_that_answers_at_all_answers_without_a_host_path(project: Path) -> None:
    """The property, over the tools that need no arguments to run."""
    calls = (
        ("list_ingested_videos", lambda: mcp_server.list_ingested_videos()),
        ("validate_video_output", lambda: mcp_server.validate_video_output(PASS_RUN)),
        ("get_extraction_segment", lambda: mcp_server.get_extraction_segment(PASS_RUN, 1)),
        ("get_coverage_window", lambda: mcp_server.get_coverage_window(PASS_RUN, 1)),
        ("extract_video_knowledge", lambda: mcp_server.extract_video_knowledge(PASS_RUN)),
        ("search_video_knowledge", lambda: mcp_server.search_video_knowledge("knowledge")),
        ("rebuild_cross_video_library", lambda: mcp_server.rebuild_cross_video_library()),
        ("finalize_video", lambda: mcp_server.finalize_video(PASS_RUN)),
    )
    for name, call in calls:
        try:
            reply = call()
        except mcp_server.McpToolError:
            continue
        assert _leaked(project, reply) == [], (name, reply)


def test_extracted_content_is_not_mangled_by_the_redaction(project: Path) -> None:
    """The reason there are two rules and not one.

    A named root can never be meaningful content, so it is substituted
    everywhere. The catch-all is applied only to a string that is *entirely* a
    path — otherwise a unit quoting a filesystem path mid-sentence would come
    back with its text rewritten.
    """
    from x2knwldg.mcp_server import _redact_reply

    prose = "Install it under /usr/local/bin/tool and then run it."
    assert _redact_reply({"content": prose}) == {"content": prose}
    assert _redact_reply(["/usr/local/bin/tool"]) == ["<path>/tool"]


# ---------------------------------------------------------------------------
# The tools do their job
# ---------------------------------------------------------------------------


def test_list_ingested_videos_reports_every_run(tmp_path: Path, monkeypatch) -> None:
    root = _make_project(tmp_path, runs=("pass-run", "partial-run", "fail-run"))
    monkeypatch.setattr(mcp_server, "PROJECT_ROOT", root.resolve())
    rows = {row["video_id"]: row for row in mcp_server.list_ingested_videos()}
    assert len(rows) == 3
    # Read off the fixtures rather than hard-coded: `fail-run` fails
    # *validation*, and its coverage document honestly says PASS.
    for run in ("pass-run", "partial-run", "fail-run"):
        coverage = json.loads(
            (root / "output" / run / "coverage.json").read_text(encoding="utf-8")
        )
        row = rows[coverage["video_id"]]
        assert row["coverage"] == coverage["status"]
        assert row["path"] == f"output/{run}"


def test_list_ingested_videos_is_empty_only_when_the_project_is(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _make_project(tmp_path, runs=())
    monkeypatch.setattr(mcp_server, "PROJECT_ROOT", root.resolve())
    assert mcp_server.list_ingested_videos() == []


def test_one_unreadable_run_does_not_hide_the_others(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A single corrupt ``metadata.json`` must not make every other video
    invisible, and must not be reported as covered either."""
    root = _make_project(tmp_path, runs=("pass-run", "fail-run"))
    (root / "output" / "fail-run" / "metadata.json").write_text("{oops", encoding="utf-8")
    monkeypatch.setattr(mcp_server, "PROJECT_ROOT", root.resolve())
    rows = {row["video_id"]: row for row in mcp_server.list_ingested_videos()}
    assert len(rows) == 2
    assert rows["fail-run"]["coverage"] == "UNREADABLE"
    assert "error" in rows["fail-run"]


def test_get_extraction_segment_returns_the_named_segment(project: Path) -> None:
    segment_id = _segment_ids(project, PASS_RUN)[0]
    segment = mcp_server.get_extraction_segment(PASS_RUN, segment_id)
    assert segment["segment_id"] == segment_id
    assert "captions" in segment or "start_sec" in segment


def test_get_extraction_segment_refuses_an_unknown_segment(project: Path) -> None:
    with pytest.raises(mcp_server.McpToolError) as caught:
        mcp_server.get_extraction_segment(PASS_RUN, "SEG-999999")
    assert caught.value.code == "not_found"
    assert "SEG-999999" in caught.value.message


def test_get_coverage_window_returns_the_window_and_its_captions(project: Path) -> None:
    window_id = _window_ids(project, PASS_RUN)[0]
    result = mcp_server.get_coverage_window(PASS_RUN, window_id)
    assert result["window"]["window_id"] == window_id
    assert isinstance(result["captions"], list)


def test_get_coverage_window_uses_the_same_membership_rule_as_the_auditor(
    project: Path,
) -> None:
    """Every caption in the run must land in at least one window, or a caption
    is audited-but-invisible here (the non-speech cue case in WORKFLOW.md §2)."""
    transcript = json.loads(
        (project / "output" / PASS_RUN / "transcript.json").read_text(encoding="utf-8")
    )
    seen: set[float] = set()
    for window_id in _window_ids(project, PASS_RUN):
        for caption in mcp_server.get_coverage_window(PASS_RUN, window_id)["captions"]:
            seen.add(caption["start_sec"])
    assert seen == {caption["start_sec"] for caption in transcript["captions"]}


def test_get_coverage_window_refuses_an_unknown_window(project: Path) -> None:
    with pytest.raises(mcp_server.McpToolError) as caught:
        mcp_server.get_coverage_window(PASS_RUN, "W-999999")
    assert caught.value.code == "not_found"


def test_validate_video_output_reports_the_fixture_verdict(project: Path) -> None:
    result = mcp_server.validate_video_output(PASS_RUN)
    assert result["status"] == "PASS"


def test_validate_video_output_never_coerces_a_partial_to_a_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _make_project(tmp_path, runs=("partial-run",))
    monkeypatch.setattr(mcp_server, "PROJECT_ROOT", root.resolve())
    assert mcp_server.validate_video_output("partial-run")["status"] == "PARTIAL"


def test_import_timestamped_transcript_creates_a_run(project: Path) -> None:
    source = project / "incoming.srt"
    source.write_text(
        "1\n00:00:00,000 --> 00:00:02,000\nhello there\n\n"
        "2\n00:00:02,000 --> 00:00:04,000\nsecond cue\n",
        encoding="utf-8",
    )
    result = mcp_server.import_timestamped_transcript("incoming.srt", "imported-run")
    assert result["status"] == "IMPORTED"
    assert result["video_id"] == "imported-run"
    assert result["path"] == "output/imported-run"
    assert (project / "output" / "imported-run" / "transcript.json").is_file()


def test_import_timestamped_transcript_refuses_a_hostile_id(project: Path) -> None:
    source = project / "incoming.srt"
    source.write_text("1\n00:00:00,000 --> 00:00:02,000\nhi\n", encoding="utf-8")
    with pytest.raises(mcp_server.McpToolError):
        mcp_server.import_timestamped_transcript("incoming.srt", "../escape")
    assert not (project.parent / "escape").exists()


def test_apply_extraction_bundle_applies_a_bundle_from_the_project(project: Path) -> None:
    bundle = json.loads(
        (FIXTURE_RUNS / PASS_RUN / "work" / "extraction_bundle.json").read_text(
            encoding="utf-8"
        )
    )
    target = project / "bundle.json"
    target.write_text(json.dumps(bundle), encoding="utf-8")
    result = mcp_server.apply_extraction_bundle(PASS_RUN, "bundle.json")
    assert result["status"] in {"PASS", "PARTIAL", "FAIL"}


def test_apply_extraction_data_applies_an_inline_bundle(project: Path) -> None:
    bundle = json.loads(
        (FIXTURE_RUNS / PASS_RUN / "work" / "extraction_bundle.json").read_text(
            encoding="utf-8"
        )
    )
    result = mcp_server.apply_extraction_data(PASS_RUN, bundle)
    assert result["status"] in {"PASS", "PARTIAL", "FAIL"}
    assert (project / "output" / PASS_RUN / "work" / "mcp_extraction_bundle.json").is_file()


def test_finalize_video_writes_the_artifacts(project: Path) -> None:
    result = mcp_server.finalize_video(PASS_RUN)
    assert result["status"] in {"PASS", "PARTIAL", "FAIL"}
    assert (project / "output" / PASS_RUN / "report.md").is_file()


def test_search_video_knowledge_finds_a_unit(project: Path) -> None:
    units = json.loads(
        (project / "output" / PASS_RUN / "knowledge_units.json").read_text(encoding="utf-8")
    )
    unit = units["units"][0]
    term = unit["normalized_statement"].split()[2]
    answer = mcp_server.search_video_knowledge(term, video_id=PASS_RUN, limit=5)
    assert answer["results"], f"no hit for {term!r} in a run that contains it"
    assert all(isinstance(hit, dict) for hit in answer["results"])
    # An agent must be able to tell "nothing matched" from "could not look".
    assert answer["unreadable"] == []


def test_search_video_knowledge_refuses_a_hostile_video_id(project: Path) -> None:
    with pytest.raises(mcp_server.McpToolError):
        mcp_server.search_video_knowledge("anything", video_id="../escape")


def test_rebuild_cross_video_library_rebuilds(project: Path) -> None:
    result = mcp_server.rebuild_cross_video_library()
    assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# Resources and the prompt
# ---------------------------------------------------------------------------


def test_the_workflow_resource_reads_the_projects_workflow(project: Path) -> None:
    assert mcp_server.workflow_resource() == "# workflow\n"


def test_the_schema_resource_reads_the_projects_schema(project: Path) -> None:
    assert mcp_server.extraction_schema_resource() == "{}\n"


@pytest.mark.parametrize("name", mcp_server.EXTRACTION_PROMPTS)
def test_every_numbered_prompt_is_served(name: str, project: Path) -> None:
    assert mcp_server.extraction_prompt_resource(name) == f"# {name}\n"


@pytest.mark.parametrize(
    "name",
    ["../../etc/passwd", "06_invented_pass", "01_segment_extraction.md", "", "."],
)
def test_a_prompt_name_outside_the_allow_list_is_refused(name: str, project: Path) -> None:
    with pytest.raises(mcp_server.McpToolError) as caught:
        mcp_server.extraction_prompt_resource(name)
    assert caught.value.code == "invalid_id"


def test_a_bad_root_is_index_unavailable_and_not_an_internal_error(
    not_a_project: Path,
) -> None:
    """The refusal must keep its own code all the way out.

    Every helper that wraps a broad ``except Exception`` is a chance to relabel
    "this root is not a project" as "something went wrong", which is the
    unhelpful half of the same answer.
    """
    for call in (
        mcp_server.list_ingested_videos,
        lambda: mcp_server.validate_video_output("pass-run"),
        lambda: mcp_server.search_video_knowledge("x"),
        mcp_server.rebuild_cross_video_library,
        lambda: mcp_server.extraction_prompt_resource("01_segment_extraction"),
    ):
        with pytest.raises(mcp_server.McpToolError) as caught:
            call()
        assert caught.value.code == "index_unavailable", caught.value.message


def test_the_resources_refuse_a_root_that_is_not_a_project(not_a_project: Path) -> None:
    for function in (mcp_server.workflow_resource, mcp_server.extraction_schema_resource):
        with pytest.raises(mcp_server.McpToolError) as caught:
            function()
        assert caught.value.code == "index_unavailable"


def test_the_prompt_never_authorises_claiming_a_pass() -> None:
    """WORKFLOW.md §5 and D-040: completion is exit 0, and nothing else."""
    text = mcp_server.extract_video_knowledge("pass-run")
    assert "pass-run" in text
    assert "Never report complete unless" in text
    assert "PASS" in text


# ---------------------------------------------------------------------------
# D-101 — one page bound, honoured by every remote surface
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("limit", [0, -1, 10**18, 501, 2**63], ids=repr)
def test_an_out_of_range_limit_is_refused(project: Path, limit: int) -> None:
    """`query.search_knowledge` floor-checks and says it has no ceiling on
    purpose — right for a local CLI search, wrong for a tool an agent calls,
    where `limit=10**18` returned the entire corpus in one reply. The HTTP side
    has capped at 500 all along, so this was two bounds for the same data."""
    with pytest.raises(mcp_server.McpToolError) as caught:
        mcp_server.search_video_knowledge("knowledge", limit=limit)
    assert caught.value.code == "invalid_request"


@pytest.mark.parametrize("limit", [True, 1.5, "10", None], ids=repr)
def test_a_limit_of_the_wrong_type_is_refused(project: Path, limit: object) -> None:
    with pytest.raises(mcp_server.McpToolError) as caught:
        mcp_server.search_video_knowledge("knowledge", limit=limit)  # type: ignore[arg-type]
    assert caught.value.code == "invalid_request"


@pytest.mark.parametrize("limit", [1, 10, 500])
def test_a_limit_within_the_bound_still_answers(project: Path, limit: int) -> None:
    answer = mcp_server.search_video_knowledge("knowledge", limit=limit)
    assert isinstance(answer["results"], list)
    assert len(answer["results"]) <= limit


def test_the_bound_is_the_one_the_http_surface_uses() -> None:
    """Stated once, in `constants`, so the two cannot drift apart again."""
    from x2knwldg.constants import MAX_PAGE_LIMIT

    params = pytest.importorskip(
        "x2knwldg.server.params", reason="the HTTP layer is the `ui` extra"
    )
    assert params.MAX_LIMIT == MAX_PAGE_LIMIT


# ---------------------------------------------------------------------------
# One taxonomy (D-184)
# ---------------------------------------------------------------------------


def test_the_mcp_and_http_error_vocabularies_are_the_same_one() -> None:
    """The test that did not exist, which is why the two had already diverged.

    Both modules carried a list, both called it "D-030's taxonomy", and they
    disagreed: the MCP server said ``internal_error`` where the envelope and
    the frozen ``ErrorCode`` enum both say ``internal``. So an agent reading an
    MCP reply got a code outside the closed vocabulary the HTTP contract
    publishes, and its own test asserted the divergent value.
    """
    import json
    from pathlib import Path

    from x2knwldg.server.envelope import ERROR_CODES as HTTP_CODES

    assert set(mcp_server.ERROR_CODES) == set(HTTP_CODES)

    frozen = json.loads(
        (Path(__file__).resolve().parents[1] / "schemas" / "api" / "v1" / "openapi.json")
        .read_text(encoding="utf-8")
    )
    published = set(frozen["components"]["schemas"]["ErrorCode"]["enum"])
    assert set(mcp_server.ERROR_CODES) == published, "the frozen document is what closes it"


def test_a_malformed_video_id_is_invalid_id_from_every_tool() -> None:
    """The same bad id was two codes depending on which tool was called.

    ``_run_dir`` states the rule -- a rejected id is ``invalid_id``, and
    collapsing it into anything else hides a traversal attempt behind an
    ordinary refusal -- and ``search_video_knowledge`` let the id reach
    ``search_knowledge``, come back a ``PipelineError``, and be rendered
    ``invalid_request``.
    """
    for bad in ("../other", ".hidden", "with/slash"):
        with pytest.raises(mcp_server.McpToolError) as searched:
            mcp_server.search_video_knowledge("anything", video_id=bad)
        assert searched.value.code == "invalid_id", bad

        with pytest.raises(mcp_server.McpToolError) as segmented:
            mcp_server.get_extraction_segment(bad, "seg_000001")
        assert segmented.value.code == "invalid_id", bad
