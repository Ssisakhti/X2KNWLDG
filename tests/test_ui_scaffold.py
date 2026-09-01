"""Tests for the ``T-008`` scaffold: the ``ui`` extra, the ``ui`` subcommand, and ``web/``.

Stdlib only, deliberately. Everything asserted here is a boundary that a later
task would otherwise have to remember on its own:

* ADR 0001 invariant 5 — importing the CLI must not import an optional
  dependency, and the core ``dependencies`` list stays empty.
* ADR 0001 invariant 9 — the local service binds loopback only. ``T-116`` gets
  the refusal for free.
* Risk R17 — ``web/tsconfig.json`` must keep ``skipLibCheck: false`` and keep the
  generated declarations as a root file, or the Node job in CI passes without
  checking the one file it exists to check.

The stub itself is asserted to stay honest: ``x2knwldg ui`` must not print a URL
it is not listening on, and must not report success for a server that does not
exist yet.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from x2knwldg import cli
from x2knwldg.pipeline import PipelineError, project_root

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WEB = PROJECT_ROOT / "web"
GENERATED_TYPES = PROJECT_ROOT / "schemas" / "api" / "v1" / "types.d.ts"


def run_cli(argv: list[str]) -> tuple[int, str]:
    """Invoke ``cli.main`` and return its exit code with anything it printed."""
    import contextlib
    import io

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
        code = cli.main(argv)
    return code, buffer.getvalue()


@pytest.fixture
def ui_extra_present(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pretend the ``ui`` extra is installed.

    The suite must pass on a bare core install, which is exactly the install
    where fastapi is absent — so the present-extra path is faked rather than
    depended on.
    """
    monkeypatch.setattr(cli, "_missing_ui_dependencies", lambda: [])


# ---------------------------------------------------------------------------
# The `ui` subcommand surface
# ---------------------------------------------------------------------------


def test_the_ui_subcommand_is_registered() -> None:
    args = cli.build_parser().parse_args(["ui"])
    assert args.command == "ui"


def test_the_default_host_is_loopback() -> None:
    args = cli.build_parser().parse_args(["ui"])
    assert args.host == "127.0.0.1"
    assert args.host in cli.LOOPBACK_HOSTS


def test_the_port_defaults_to_unset_rather_than_a_hard_coded_value() -> None:
    """Canvas plan section 8.3: the port must not rest on a brittle constant.

    ``None`` means "chosen at bind time", which is a decision ``T-116`` makes
    with a socket rather than one this scaffold makes with a literal.
    """
    assert cli.build_parser().parse_args(["ui"]).port is None


def test_the_ui_options_are_the_four_the_scaffold_froze() -> None:
    args = cli.build_parser().parse_args(
        ["ui", "--root", "/tmp", "--host", "localhost", "--port", "8080", "--no-open"]
    )
    assert args.root == Path("/tmp")
    assert args.host == "localhost"
    assert args.port == 8080
    assert args.no_open is True


def test_the_browser_opens_by_default() -> None:
    assert cli.build_parser().parse_args(["ui"]).no_open is False


# ---------------------------------------------------------------------------
# ADR 0001 invariant 9 — loopback only
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("host", sorted(cli.LOOPBACK_HOSTS))
def test_every_loopback_host_is_accepted(host: str, ui_extra_present: None) -> None:
    code, output = run_cli(["ui", "--host", host])
    assert code == cli.EXIT_UI_NOT_IMPLEMENTED, output
    assert json.loads(output)["host"] == host


@pytest.mark.parametrize(
    "host",
    ["0.0.0.0", "::", "192.168.1.10", "example.com", "127.0.0.2", ""],
)
def test_a_non_loopback_host_is_refused(host: str, ui_extra_present: None) -> None:
    code, output = run_cli(["ui", "--host", host])
    assert code == 1, output
    payload = json.loads(output)
    assert payload["status"] == "ERROR"
    assert "loopback only" in payload["message"]


def test_the_loopback_refusal_happens_before_the_dependency_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A bad bind address is refused whether or not the extra is installed.

    Ordering matters: if the dependency check came first, the invariant would go
    unenforced on every machine that has not installed the extra.
    """

    def explode() -> list[str]:  # pragma: no cover - must not be reached
        raise AssertionError("the dependency probe ran before the host was checked")

    monkeypatch.setattr(cli, "_missing_ui_dependencies", explode)
    code, output = run_cli(["ui", "--host", "0.0.0.0"])
    assert code == 1
    assert "loopback only" in json.loads(output)["message"]


@pytest.mark.parametrize("port", ["0", "-1", "65536", "99999"])
def test_a_port_outside_the_valid_range_is_refused(port: str, ui_extra_present: None) -> None:
    code, output = run_cli(["ui", "--port", port])
    assert code == 1, output
    assert "Port out of range" in json.loads(output)["message"]


# ---------------------------------------------------------------------------
# The stub stays honest
# ---------------------------------------------------------------------------


def test_the_stub_reports_that_it_is_not_implemented(ui_extra_present: None) -> None:
    code, output = run_cli(["ui"])
    assert code == cli.EXIT_UI_NOT_IMPLEMENTED, "a command that cannot serve must not exit 0"
    payload = json.loads(output)
    assert payload["status"] == "UI_NOT_IMPLEMENTED"
    assert payload["blocked_on"] == ["T-105", "T-106", "T-107", "T-108", "T-116"]
    assert Path(payload["root"]) == project_root()


def test_the_stub_never_prints_a_url_it_is_not_listening_on(ui_extra_present: None) -> None:
    _, output = run_cli(["ui", "--port", "8000"])
    assert not re.search(r"https?://", output), output


def test_a_missing_ui_extra_names_the_install_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli, "_missing_ui_dependencies", lambda: ["fastapi", "uvicorn"])
    code, output = run_cli(["ui"])
    assert code == 1
    message = json.loads(output)["message"]
    assert "fastapi, uvicorn" in message
    assert "pip install 'x2knwldg[ui]'" in message


def test_a_root_that_does_not_exist_is_refused(
    tmp_path: Path, ui_extra_present: None
) -> None:
    code, output = run_cli(["ui", "--root", str(tmp_path / "absent")])
    assert code == 1
    assert "Project root does not exist" in json.loads(output)["message"]


def test_a_root_that_is_a_file_is_refused(tmp_path: Path, ui_extra_present: None) -> None:
    target = tmp_path / "not-a-directory.txt"
    target.write_text("x", encoding="utf-8")
    code, output = run_cli(["ui", "--root", str(target)])
    assert code == 1
    assert "Project root does not exist" in json.loads(output)["message"]


def test_the_real_dependency_probe_names_an_absent_package(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The probe must *report* an absent package, not raise on it.

    ``find_spec`` raises ``ModuleNotFoundError`` for a dotted name whose parent
    is missing, which is the failure mode a bare ``import`` check would have hit.
    """
    monkeypatch.setattr(cli, "UI_DEPENDENCIES", ("json", "x2knwldg_not_installed"))
    assert cli._missing_ui_dependencies() == ["x2knwldg_not_installed"]


def test_the_real_dependency_probe_agrees_with_an_actual_import() -> None:
    """The probe must answer *correctly*, on whatever this machine has installed.

    Asserting only ``set(missing) <= set(UI_DEPENDENCIES)`` could not fail: a
    probe hard-wired to return ``[]`` — reporting a fully installed extra on a
    bare core install, which is how the ``ui`` command would then die on an
    ``ImportError`` instead of naming the missing package — satisfied it. So the
    oracle here is an independent one: importing each package for real. Whatever
    the probe says, that has to be the truth about this interpreter.
    """
    import importlib

    unimportable = []
    for name in cli.UI_DEPENDENCIES:
        try:
            importlib.import_module(name)
        except Exception:
            unimportable.append(name)
    assert cli._missing_ui_dependencies() == unimportable


# ---------------------------------------------------------------------------
# project_root — one rule, shared with the MCP server
# ---------------------------------------------------------------------------


def test_an_explicit_root_wins_over_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("X2KNWLDG_PROJECT_ROOT", str(tmp_path / "from-env"))
    assert project_root(tmp_path) == tmp_path.resolve()


def test_the_environment_wins_over_the_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("X2KNWLDG_PROJECT_ROOT", str(tmp_path))
    monkeypatch.chdir(PROJECT_ROOT)
    assert project_root() == tmp_path.resolve()


def test_the_working_directory_is_the_last_resort(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("X2KNWLDG_PROJECT_ROOT", raising=False)
    monkeypatch.chdir(tmp_path)
    assert project_root() == tmp_path.resolve()


def test_the_mcp_server_does_not_re_read_the_root_environment_variable() -> None:
    """D-039: ``pipeline.project_root`` reads the env var, and nothing else does.

    A text check, because "no second reader" is a property of the whole file
    rather than of any one call. The behavioural half is the test below.
    """
    source = (PROJECT_ROOT / "src" / "x2knwldg" / "mcp_server.py").read_text(encoding="utf-8")
    assert "PROJECT_ROOT = project_root()" in source
    # Naming the variable in a refusal message is fine and useful; *reading* it
    # here would be the second implementation D-039 removed.
    for reader in ("os.environ", "os.getenv", "getenv("):
        assert reader not in source, f"mcp_server.py reads the environment itself: {reader}"


def test_the_mcp_server_and_the_ui_resolve_the_root_the_same_way(tmp_path: Path) -> None:
    """One implementation. Two rules for "the project" is the D-020 mistake.

    Run in a subprocess with the env var set, because ``mcp_server`` resolves
    its root at import: grepping the source for the assignment proved the line
    existed, not that it produced the same answer the ``ui`` command produces.
    """
    root = tmp_path / "elsewhere"
    root.mkdir()
    probe = (
        "import json;"
        "from x2knwldg import cli;"
        "from x2knwldg import mcp_server;"
        "args=cli.build_parser().parse_args(['ui']);"
        "from x2knwldg.pipeline import project_root;"
        "print(json.dumps([str(mcp_server.PROJECT_ROOT), str(project_root(args.root))]))"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        env={
            "PYTHONPATH": str(PROJECT_ROOT / "src"),
            "PATH": "/usr/bin:/bin",
            "X2KNWLDG_PROJECT_ROOT": str(root),
        },
    )
    assert result.returncode == 0, result.stderr
    server_root, ui_root = json.loads(result.stdout)
    assert server_root == ui_root == str(root.resolve())


# ---------------------------------------------------------------------------
# ADR 0001 invariant 5 — the core stays zero-dependency
# ---------------------------------------------------------------------------


def test_importing_the_cli_does_not_import_the_ui_extra() -> None:
    """The lazy-import rule, checked in a fresh interpreter.

    Checking ``sys.modules`` in *this* process would prove nothing: pytest has
    already imported half the package.
    """
    probe = (
        "import sys, x2knwldg.cli;"
        "leaked=[n for n in ('fastapi','uvicorn','starlette') if n in sys.modules];"
        "print(','.join(leaked))"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        env={"PYTHONPATH": str(PROJECT_ROOT / "src"), "PATH": "/usr/bin:/bin"},
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "", f"leaked into module scope: {result.stdout.strip()}"


def test_no_module_outside_the_server_package_imports_the_ui_extra() -> None:
    """The core stays zero-dependency; the ``ui`` extra's own code may use it.

    Narrowed when Track B landed (`T-105`-`T-108`). The original rule was "no
    module in ``x2knwldg`` imports fastapi at module scope", written when the
    server did not exist — and read literally it forbids the server from
    importing the framework it *is*, which would mean hiding a `fastapi` import
    inside every route function to satisfy a test rather than an invariant.

    The invariant ADR 0001 invariant 5 actually states is that installing and
    using the **core** package must not require an optional dependency. So the
    rule is now two rules, and together they are stricter than the one they
    replaced:

    1. Nothing outside ``server/`` imports the extra (this test).
    2. Nothing outside ``server/`` imports ``server`` at module scope
       (:func:`test_nothing_outside_the_server_package_imports_it_eagerly`), so
       the extra cannot be reached transitively either.

    ``x2knwldg.server`` itself is exempt from neither: it is only reached by
    importing it deliberately, and its ``__init__`` resolves ``create_app``
    lazily so that even ``import x2knwldg.server`` does not need the extra.
    """
    package = PROJECT_ROOT / "src" / "x2knwldg"
    server = package / "server"
    offenders = []
    for module in sorted(package.rglob("*.py")):
        if server in module.parents:
            continue
        for line in module.read_text(encoding="utf-8").splitlines():
            if re.match(r"^(import|from)\s+(fastapi|uvicorn|starlette)\b", line):
                offenders.append(f"{module.relative_to(PROJECT_ROOT)}: {line.strip()}")
    assert offenders == [], offenders


def test_nothing_outside_the_server_package_imports_it_eagerly() -> None:
    """Rule 2: the extra must not be reachable transitively.

    Without this, ``cli.py`` could import ``x2knwldg.server`` at module scope
    and pull the whole framework in while every line still passed rule 1.
    """
    package = PROJECT_ROOT / "src" / "x2knwldg"
    server = package / "server"
    offenders = []
    for module in sorted(package.rglob("*.py")):
        if server in module.parents:
            continue
        for line in module.read_text(encoding="utf-8").splitlines():
            if re.match(r"^(from|import)\s+(x2knwldg\.)?server\b", line.strip()):
                offenders.append(f"{module.relative_to(PROJECT_ROOT)}: {line.strip()}")
            if re.match(r"^from\s+\.\s*server\b|^from\s+\.server\b", line.strip()):
                offenders.append(f"{module.relative_to(PROJECT_ROOT)}: {line.strip()}")
    assert offenders == [], offenders


def test_importing_the_server_package_does_not_import_the_ui_extra() -> None:
    """``import x2knwldg.server`` alone must not need fastapi.

    ``server/__init__`` resolves ``create_app`` through a module ``__getattr__``
    for exactly this reason: the envelope is stdlib-only and testable on a bare
    core install, and only touching ``create_app`` requires the extra.
    """
    probe = (
        "import sys, x2knwldg.server;"
        "leaked=[n for n in ('fastapi','uvicorn','starlette') if n in sys.modules];"
        "print(','.join(leaked))"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        env={"PYTHONPATH": str(PROJECT_ROOT / "src"), "PATH": "/usr/bin:/bin"},
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "", f"leaked into module scope: {result.stdout.strip()}"


# ---------------------------------------------------------------------------
# pyproject.toml — the `ui` extra
# ---------------------------------------------------------------------------


def _pyproject_text() -> str:
    return (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")


def test_the_core_dependency_list_is_still_empty() -> None:
    """Runs on every supported Python, including 3.10 without ``tomllib``."""
    assert "\ndependencies = []\n" in _pyproject_text()


def test_the_ui_extra_is_declared() -> None:
    text = _pyproject_text()
    assert "\nui = [" in text
    assert '"fastapi' in text
    assert '"uvicorn' in text


def test_the_ui_extra_holds_exactly_the_packages_the_cli_probes() -> None:
    tomllib = pytest.importorskip("tomllib", reason="stdlib tomllib arrived in 3.11")
    data = tomllib.loads(_pyproject_text())
    assert data["project"]["dependencies"] == []
    extras = data["project"]["optional-dependencies"]
    assert "ui" in extras
    declared = {re.split(r"[<>=!\[ ]", spec, maxsplit=1)[0] for spec in extras["ui"]}
    assert declared == set(cli.UI_DEPENDENCIES)


def test_every_ui_requirement_is_version_bounded() -> None:
    tomllib = pytest.importorskip("tomllib", reason="stdlib tomllib arrived in 3.11")
    extras = tomllib.loads(_pyproject_text())["project"]["optional-dependencies"]
    for spec in extras["ui"]:
        assert ">=" in spec, f"unpinned floor: {spec}"
        assert "<" in spec, f"no upper bound, so a major bump lands silently: {spec}"


# ---------------------------------------------------------------------------
# .gitignore
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("entry", ["node_modules/", ".vite/", "*.tsbuildinfo"])
def test_the_frontend_toolchain_is_ignored(entry: str) -> None:
    lines = [
        line.strip()
        for line in (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert entry in lines


def _check_ignore(relative: str) -> bool:
    """Whether git would ignore ``relative``. Asks git, not the file's text."""
    result = subprocess.run(
        ["git", "check-ignore", "-q", "--no-index", relative],
        cwd=PROJECT_ROOT,
        capture_output=True,
    )
    if result.returncode not in {0, 1}:  # 128 = not a repository, git absent, ...
        pytest.skip(f"git check-ignore unavailable: {result.stderr.decode().strip()}")
    return result.returncode == 0


def test_git_actually_ignores_the_frontend_toolchain() -> None:
    assert _check_ignore("web/node_modules/typescript/package.json")
    assert _check_ignore("web/.vite/deps/index.js")
    assert _check_ignore("web/tsconfig.tsbuildinfo")


def test_the_lock_file_is_committed_and_not_ignored() -> None:
    """``npm ci`` in CI reads it, so it must be in the tree."""
    assert (WEB / "package-lock.json").is_file()
    assert not _check_ignore("web/package-lock.json")
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "web/package-lock.json"],
        cwd=PROJECT_ROOT,
        capture_output=True,
    )
    if tracked.returncode == 128:  # pragma: no cover - git absent
        pytest.skip("git unavailable")
    assert tracked.returncode == 0, "web/package-lock.json is not tracked by git"


# ---------------------------------------------------------------------------
# web/ — the scaffold Track C inherits
# ---------------------------------------------------------------------------


def _package_json() -> dict:
    return json.loads((WEB / "package.json").read_text(encoding="utf-8"))


def _tsconfig() -> dict:
    return json.loads((WEB / "tsconfig.json").read_text(encoding="utf-8"))


def test_the_web_directory_holds_the_files_the_scaffold_promised() -> None:
    for relative in ("README.md", "package.json", "package-lock.json", "tsconfig.json"):
        assert (WEB / relative).is_file(), relative
    assert (WEB / "src" / "api" / "contract.ts").is_file()


def test_the_typecheck_script_is_the_one_ci_runs() -> None:
    assert _package_json()["scripts"]["typecheck"] == "tsc --noEmit"


def test_the_frontend_has_no_runtime_dependencies_yet() -> None:
    """``T-109`` chooses Vite and React. ``T-008`` does not choose for it."""
    package = _package_json()
    assert package.get("dependencies", {}) == {}
    assert set(package["devDependencies"]) == {"typescript"}


def test_the_lock_file_agrees_with_the_manifest() -> None:
    lock = json.loads((WEB / "package-lock.json").read_text(encoding="utf-8"))
    package = _package_json()
    assert lock["name"] == package["name"]
    assert lock["version"] == package["version"]


def test_the_typescript_config_is_strict() -> None:
    options = _tsconfig()["compilerOptions"]
    assert options["strict"] is True
    assert options["noEmit"] is True


def test_skip_lib_check_stays_off_or_r17_reopens() -> None:
    """With ``skipLibCheck`` on, ``tsc`` skips ``types.d.ts`` — the only file the
    Node job in CI exists to check — and the job passes without looking."""
    assert _tsconfig()["compilerOptions"]["skipLibCheck"] is False


def test_the_generated_declarations_are_a_root_file_of_the_program() -> None:
    included = _tsconfig()["include"]
    matches = [entry for entry in included if entry.endswith("types.d.ts")]
    assert matches, f"types.d.ts is not in include: {included}"
    for entry in matches:
        assert (WEB / entry).resolve() == GENERATED_TYPES


def test_the_contract_module_re_exports_the_committed_declarations() -> None:
    source = (WEB / "src" / "api" / "contract.ts").read_text(encoding="utf-8")
    match = re.search(r'export type \* from "([^"]+)";', source)
    assert match, source
    resolved = (WEB / "src" / "api" / f"{match.group(1)}.d.ts").resolve()
    assert resolved == GENERATED_TYPES, resolved


def test_only_the_contract_module_reaches_outside_web() -> None:
    """One place holds the path to the generated file, so a move breaks a test
    rather than a build."""
    offenders = []
    for module in sorted((WEB / "src").rglob("*.ts")):
        if module.name == "contract.ts":
            continue
        for line in module.read_text(encoding="utf-8").splitlines():
            if "../../.." in line or "schemas/api" in line:
                offenders.append(f"{module.relative_to(WEB)}: {line.strip()}")
    assert offenders == [], offenders


# ---------------------------------------------------------------------------
# CI
# ---------------------------------------------------------------------------


def _workflow() -> str:
    return (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")


def test_ci_type_checks_the_frontend() -> None:
    workflow = _workflow()
    assert "web-typecheck:" in workflow
    assert "actions/setup-node" in workflow
    assert "npm ci" in workflow
    assert "npm run typecheck" in workflow


def test_ci_refuses_a_ui_dependency_in_the_bare_core_install() -> None:
    workflow = _workflow()
    creep_check = next(
        line for line in workflow.splitlines() if line.strip().startswith("for package in")
    )
    for name in cli.UI_DEPENDENCIES:
        assert name in creep_check, f"{name} may creep into the core install unnoticed"


def _declared_extras() -> set[str]:
    """The extras pyproject declares, read as text so this runs on 3.10 too."""
    section = _pyproject_text().split("[project.optional-dependencies]", 1)[1]
    section = section.split("\n[", 1)[0]
    return set(re.findall(r"^([A-Za-z][\w.-]*) = \[", section, re.MULTILINE))


def test_ci_installs_every_declared_extra() -> None:
    """Three of the five extras were never installed by any job.

    An extra nobody installs is an extra nobody has proved installable: a
    yanked release, an impossible pin, or a package that no longer builds on a
    supported Python would all pass CI silently, and the failure would land on
    whoever ran ``pip install 'x2knwldg[youtube]'`` first.
    """
    rows = set(re.findall(r"^\s+- extra: (\S+)\s*$", _workflow(), re.MULTILINE))
    declared = _declared_extras()
    assert declared, "no extras parsed out of pyproject.toml"
    assert declared <= rows, f"declared but never installed in CI: {sorted(declared - rows)}"


def test_ci_imports_what_each_extra_unlocks() -> None:
    """Installing is not importing. Every matrix row must name modules to load."""
    rows = re.findall(r"- extra: (\S+)\s*\n\s+imports: \"([^\"]+)\"", _workflow())
    assert {extra for extra, _ in rows} == _declared_extras()
    for extra, imports in rows:
        assert imports.strip(), extra


def _ci_python_versions() -> list[tuple[int, ...]]:
    matrix = re.search(r"python-version: \[([^\]]+)\]", _workflow())
    assert matrix, "no python-version matrix in ci.yml"
    return [
        tuple(int(part) for part in version.split("."))
        for version in re.findall(r'"([\d.]+)"', matrix.group(1))
    ]


def test_ci_runs_the_python_floor_pyproject_declares() -> None:
    match = re.search(r'requires-python = ">=([\d.]+)"', _pyproject_text())
    assert match, "no requires-python in pyproject.toml"
    floor = tuple(int(part) for part in match.group(1).split("."))
    assert floor in _ci_python_versions(), (
        f"pyproject claims support from {match.group(1)}, and CI never runs it"
    )


def test_ci_runs_an_interpreter_at_least_as_new_as_this_one() -> None:
    """CI tested 3.10/3.12/3.13 while every number measured here came from 3.14.

    A version nobody in CI runs is a version nobody has evidence about, and the
    developer's daily interpreter is the worst one to have no evidence about.
    """
    assert max(_ci_python_versions()) >= sys.version_info[:2], (
        f"this suite runs on {sys.version_info.major}.{sys.version_info.minor}, "
        "which is newer than anything CI tests"
    )


@pytest.mark.parametrize("escape", ["|| true", "continue-on-error", "exit 0 #"])
def test_ci_has_no_way_to_pass_silently(escape: str) -> None:
    """A job that cannot fail is a job that proves nothing."""
    assert escape not in _workflow()


# ---------------------------------------------------------------------------
# `import-transcript` and `process` share their options
# ---------------------------------------------------------------------------


SHARED_IMPORT_OPTIONS = ("video_id", "video_url", "title", "channel", "language", "output")


def test_process_and_import_transcript_agree_on_every_shared_option() -> None:
    """``process`` re-declared all six by hand beside ``_add_import_options``.

    ``_run_process`` hands a local file straight to ``_run_import``, so a
    default that drifted between the two declarations — ``--language``,
    ``--output`` — would silently change what a documented invocation does.
    One declaration is the fix; this is the guard.
    """
    parser = cli.build_parser()
    process = vars(parser.parse_args(["process", "some-source"]))
    imported = vars(parser.parse_args(["import-transcript", "some.srt"]))
    for option in SHARED_IMPORT_OPTIONS:
        assert process[option] == imported[option], option


def test_both_parsers_take_the_shared_options_from_one_helper() -> None:
    """Both commands must be *built* from the one declaration, not merely
    happen to agree today."""
    seen: list[str] = []
    real = cli._add_shared_import_options

    def recording(parser: object) -> None:
        seen.append(getattr(parser, "prog", "?"))
        real(parser)  # type: ignore[arg-type]

    original = cli._add_shared_import_options
    try:
        cli._add_shared_import_options = recording  # type: ignore[assignment]
        cli.build_parser()
    finally:
        cli._add_shared_import_options = original  # type: ignore[assignment]
    assert len(seen) == 2, seen
    assert any("import-transcript" in name for name in seen), seen
    assert any("process" in name for name in seen), seen
