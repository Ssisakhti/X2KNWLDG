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
    assert code == 2, output
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
    assert code == 2, "a command that cannot serve must not exit 0"
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


def test_the_real_dependency_probe_does_not_raise_on_the_declared_extra() -> None:
    """Whatever is installed on this machine, the probe answers rather than throws."""
    missing = cli._missing_ui_dependencies()
    assert set(missing) <= set(cli.UI_DEPENDENCIES)


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


def test_the_mcp_server_and_the_ui_resolve_the_root_the_same_way() -> None:
    """One implementation. Two rules for "the project" is the D-020 mistake."""
    source = (PROJECT_ROOT / "src" / "x2knwldg" / "mcp_server.py").read_text(encoding="utf-8")
    assert "PROJECT_ROOT = project_root()" in source
    assert "X2KNWLDG_PROJECT_ROOT" not in source, (
        "the env var is read by pipeline.project_root, not re-read here"
    )


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


def test_no_module_in_the_package_imports_the_ui_extra_at_module_scope() -> None:
    package = PROJECT_ROOT / "src" / "x2knwldg"
    offenders = []
    for module in sorted(package.rglob("*.py")):
        for line in module.read_text(encoding="utf-8").splitlines():
            if re.match(r"^(import|from)\s+(fastapi|uvicorn|starlette)\b", line):
                offenders.append(f"{module.relative_to(PROJECT_ROOT)}: {line.strip()}")
    assert offenders == [], offenders


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
