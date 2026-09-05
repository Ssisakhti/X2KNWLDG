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

``T-116`` wired the command, so what was "the stub stays honest" is now "the
wiring stays honest": ``x2knwldg ui`` must not print a URL before it is bound to
it, must refuse a non-loopback bind before it probes for the extra, and must
report an unbuilt frontend as its own next-step code rather than as success or
as a breakage.

**Nothing here starts a server.** Every ``ui`` invocation in this file stops at
or before the ``UI_NOT_BUILT`` refusal, by pointing ``--root`` at a directory
with no ``web/dist``. The serving path itself is exercised in
``test_ui_serving.py``, which binds a real socket on an ephemeral port.
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from x2knwldg import cli
from x2knwldg.pipeline import project_root

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
def unbuilt_root(tmp_path: Path) -> Path:
    """A project root that exists and holds no built frontend.

    Every ``ui`` test that gets *past* the argument refusals uses this, so the
    command stops at ``UI_NOT_BUILT`` instead of binding a socket and serving
    the suite forever. Using the repository root would do exactly that on any
    machine where someone has run ``npm run build``, and pass on any machine
    where nobody has -- a test whose result depends on untracked build output.
    """
    root = tmp_path / "project"
    root.mkdir()
    return root


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
def test_every_loopback_host_is_accepted(
    host: str, ui_extra_present: None, unbuilt_root: Path
) -> None:
    """Accepted means *got past the check* -- asserted by where it stops.

    The command reaches ``UI_NOT_BUILT``, which is downstream of the bind
    refusal, so the host was accepted. It cannot be asserted by echoing the
    host back any more: this invocation never binds, and reporting a host it is
    not listening on is precisely what the wiring must not do.
    """
    code, output = run_cli(["ui", "--host", host, "--root", str(unbuilt_root)])
    assert code == cli.EXIT_UI_NOT_BUILT, output
    assert json.loads(output)["status"] == "UI_NOT_BUILT"


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
# The wiring stays honest
# ---------------------------------------------------------------------------


def test_an_unbuilt_frontend_is_its_own_code_not_success_and_not_an_error(
    ui_extra_present: None, unbuilt_root: Path
) -> None:
    """``6`` is "run this next", the same shape of fact as ``5``.

    Not ``0``: nothing was served. Not ``1``: nothing is broken -- the API and
    the index are fine and one ``npm run build`` fixes it. A wrapper that
    cannot tell those apart reports a broken install for a missing build step.
    """
    code, output = run_cli(["ui", "--root", str(unbuilt_root)])
    assert code == cli.EXIT_UI_NOT_BUILT, "a command that served nothing must not exit 0"
    assert code != cli.EXIT_ERROR, "an unbuilt frontend is a next step, not a breakage"
    payload = json.loads(output)
    assert payload["status"] == "UI_NOT_BUILT"
    assert Path(payload["root"]) == unbuilt_root.resolve()
    assert payload["expected"] == str(Path("web") / "dist" / "index.html")
    assert "npm run build" in payload["message"]


def test_an_unbuilt_frontend_is_refused_before_the_index_is_touched(
    ui_extra_present: None, unbuilt_root: Path
) -> None:
    """Nothing is written by a command that is about to refuse.

    Refreshing the index first would leave a ``.x2knwldg/`` behind in a project
    the user was only told to go and build the frontend for.
    """
    code, _ = run_cli(["ui", "--root", str(unbuilt_root)])
    assert code == cli.EXIT_UI_NOT_BUILT
    assert not (unbuilt_root / ".x2knwldg").exists()


def test_it_never_prints_a_url_it_is_not_listening_on(
    ui_extra_present: None, unbuilt_root: Path
) -> None:
    """The refusal path prints no URL at all, whatever ``--port`` asked for."""
    _, output = run_cli(["ui", "--port", "8000", "--root", str(unbuilt_root)])
    assert not re.search(r"https?://", output), output


def test_a_missing_ui_extra_names_the_install_command(
    monkeypatch: pytest.MonkeyPatch, unbuilt_root: Path
) -> None:
    monkeypatch.setattr(cli, "_missing_ui_dependencies", lambda: ["fastapi", "uvicorn"])
    code, output = run_cli(["ui", "--root", str(unbuilt_root)])
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


def _module_scope_imports(source: str) -> list[str]:
    """Every module the file imports *at import time*, by name.

    An AST walk rather than a line regex, for two reasons that only appeared
    once ``T-116`` wired the ``ui`` command. A regex over stripped lines cannot
    tell ``from .server import serve`` at column 0 from the same line indented
    inside a function -- and the second is the lazy import the CLI convention
    *requires* (see ``_run_ui``), while the first is the eager one this rule
    forbids. A regex over unstripped lines gets that right but then misses a
    module-scope import nested in a ``try:``, which is eager and would slip
    through. The AST distinguishes them exactly: an import is lazy when, and
    only when, a function encloses it.
    """
    imported: list[str] = []

    def walk(node: ast.AST, inside_function: bool) -> None:
        for child in ast.iter_child_nodes(node):
            nested = inside_function or isinstance(
                child, (ast.FunctionDef, ast.AsyncFunctionDef)
            )
            if not nested:
                if isinstance(child, ast.Import):
                    imported.extend(alias.name for alias in child.names)
                elif isinstance(child, ast.ImportFrom):
                    # `from . import x` has no module; level > 0 is relative.
                    imported.append("." * child.level + (child.module or ""))
            walk(child, nested)

    walk(ast.parse(source), False)
    return imported


def test_nothing_outside_the_server_package_imports_it_eagerly() -> None:
    """Rule 2: the extra must not be reachable transitively.

    Without this, ``cli.py`` could import ``x2knwldg.server`` at module scope
    and pull the whole framework in while every line still passed rule 1.

    "Eagerly" is the whole of the rule. ``T-116`` reaches ``server.serve``
    from inside ``_run_ui``, which is the lazy-import convention the package
    follows everywhere it touches an optional extra, and is exactly what keeps
    ``import x2knwldg.cli`` free of fastapi on a bare core install -- the
    property :func:`test_importing_the_cli_does_not_import_the_ui_extra`
    measures in a fresh interpreter rather than inferring from text.
    """
    package = PROJECT_ROOT / "src" / "x2knwldg"
    server = package / "server"
    offenders = []
    for module in sorted(package.rglob("*.py")):
        if server in module.parents:
            continue
        source = module.read_text(encoding="utf-8")
        for name in _module_scope_imports(source):
            if re.match(r"^(x2knwldg\.)?server\b", name) or re.match(r"^\.+server\b", name):
                offenders.append(f"{module.relative_to(PROJECT_ROOT)}: imports {name}")
    assert offenders == [], offenders


def test_the_eager_import_rule_catches_what_it_claims_to() -> None:
    """The checker above, checked -- including the two cases that motivated it.

    A rule that silently stopped matching would leave the invariant unguarded
    while staying green, which is the failure mode this whole file exists to
    prevent.
    """
    eager = "from .server import serve\n"
    eager_in_try = "try:\n    from .server import serve\nexcept ImportError:\n    pass\n"
    lazy = "def run():\n    from .server import serve\n    return serve\n"
    lazy_nested = "def outer():\n    def inner():\n        import x2knwldg.server\n"

    assert ".server" in _module_scope_imports(eager)
    assert ".server" in _module_scope_imports(eager_in_try), "a try: block is still import time"
    assert _module_scope_imports(lazy) == [], "a lazy import is the convention, not a violation"
    assert _module_scope_imports(lazy_nested) == []


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


def test_the_frontend_declares_the_toolchain_t109_chose() -> None:
    """``T-008`` chose nothing here; ``T-109`` chose Vite + React + Vitest.

    This replaces the ``T-008``-era guard that asserted *no* runtime dependency,
    whose own docstring named its expiry: "``T-109`` chooses Vite and React".
    It has now chosen, so the guard is rewritten to the property that outlives
    the choice rather than deleted — every tool CI invokes is declared in the
    manifest, so ``npm ci`` installs what ``npm run typecheck``, ``npm test``
    and ``npm run build`` need, and a dependency dropped by a refactor is a
    failure here rather than a red CI job on an unrelated pull request.

    ``typescript`` stays a *dev* dependency: it is a build-time tool, and the
    declarations it checks are erased by ``contract.ts``'s ``export type *``
    (asserted separately), so nothing about the contract reaches the bundle.
    """
    package = _package_json()
    assert {"react", "react-dom"} <= set(package["dependencies"])
    assert {"typescript", "vite", "vitest"} <= set(package["devDependencies"])
    assert "typescript" not in package.get("dependencies", {})


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
    """The creep check covers every optional distribution, not a hand-kept list.

    D-157: the list used to be seven names written into the workflow, and
    ``pyproject.toml`` declares fourteen — so ``mcp``,
    ``youtube-transcript-api`` and ``requests`` could have crept into the core
    install with nothing to say so. The job now derives the names from
    ``pyproject.toml``, which is why this test checks the *derivation* rather
    than a literal line: that the check reads the declarations, that it exempts
    only ``pytest``, and that the UI dependencies this test is named for are in
    fact declared optional and would therefore be caught.
    """
    workflow = _workflow()
    assert 'tomllib.load(handle)["project"]' in workflow, "the creep check must read pyproject"
    assert 'project["optional-dependencies"]' in workflow, "it must read every declared extra"
    assert 'INSTALLED_ON_PURPOSE = {"pytest"}' in workflow, "pytest is the only exemption"

    declared = set()
    for requirements in _optional_dependencies().values():
        declared |= {_distribution_name(entry) for entry in requirements}
    for name in cli.UI_DEPENDENCIES:
        assert name in declared, f"{name} is not a declared extra, so nothing checks it"


def test_ci_sees_a_fixture_the_generator_newly_writes() -> None:
    """D-157: `git diff` cannot see an untracked file, `git status` can.

    The reproducibility job's whole claim is that regenerating the committed
    fixtures changes nothing. A generator that starts writing an *extra*
    artifact leaves it untracked, which `git diff --quiet` reports as no
    change — so the one failure mode the job cannot afford is the one it could
    not see.
    """
    workflow = _workflow()
    fixtures = workflow.split("  fixtures:", 1)[1].split("\n  web-typecheck:", 1)[0]
    assert "git status --porcelain" in fixtures
    assert "git diff --quiet" not in fixtures

    # And it must check **every** generator that makes the promise, which is
    # the half that was missing: the job was named "run fixtures are
    # reproducible" while regenerating one of the three. Discovered from the
    # filesystem rather than listed here, so a builder added without a line in
    # the workflow fails this test rather than being checked by nothing — which
    # is exactly what happened when `T-251` added a fourth.
    builders = sorted(
        path.relative_to(PROJECT_ROOT).as_posix()
        for path in (PROJECT_ROOT / "tests" / "fixtures").glob("*/build_*.py")
    )
    assert len(builders) == 4, builders
    unchecked = [builder for builder in builders if builder not in fixtures]
    assert unchecked == [], (
        f"the reproducibility job does not regenerate {', '.join(unchecked)}"
    )


def _distribution_name(requirement: str) -> str:
    """The distribution a requirement names, without its extras or version."""
    name = requirement.split(";")[0].strip()
    for separator in ("[", "=", "<", ">", "!", "~", " "):
        name = name.split(separator)[0]
    return name.strip()


def _optional_dependencies() -> dict[str, list[str]]:
    """``pyproject``'s optional-dependency groups, read as text so 3.10 runs it."""
    section = _pyproject_text().split("[project.optional-dependencies]", 1)[1]
    section = section.split("\n[project.scripts]", 1)[0]
    groups: dict[str, list[str]] = {}
    current: str | None = None
    for line in section.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        opened = re.match(r"^([A-Za-z][\w.-]*) = \[(.*)$", stripped)
        if opened is not None:
            current = opened.group(1)
            groups[current] = re.findall(r'"([^"]+)"', opened.group(2))
            # `mcp = ["mcp>=2,<3"]` closes on its own line. Reading only the
            # multi-line form is how `mcp` fell out of the creep list in the
            # first place, so the one-line form is parsed here rather than
            # assumed not to occur.
            if opened.group(2).rstrip().endswith("]"):
                current = None
            continue
        if current is None:
            continue
        if stripped.startswith("]"):
            current = None
            continue
        quoted = re.match(r'^"([^"]+)"', stripped)
        if quoted is not None:
            groups[current].append(quoted.group(1))
    return groups


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
    """Every interpreter the `tests` job runs, from its matrix.

    D-115 turned the matrix from a bare `python-version: [...]` list into
    `include:` rows so one of them could name macOS, so the versions are read
    off those rows now.
    """
    rows = re.findall(r'python-version: "([\d.]+)" *\}', _workflow())
    assert rows, "no python-version rows in ci.yml's tests matrix"
    return [tuple(int(part) for part in version.split(".")) for version in rows]


def _ci_platforms() -> set[str]:
    return set(re.findall(r"\{ *os: (\S+?),", _workflow()))


def test_ci_runs_the_platform_this_project_targets() -> None:
    """D-115: all five jobs were `ubuntu-latest`, and this is a macOS project.

    `routes/media.py`'s containment checks are the ADR-0003 boundary and they
    resolve paths; a case-insensitive filesystem answers `Path.resolve()` and
    `relative_to` differently from ext4, so the one boundary that most needs
    platform evidence had none.
    """
    platforms = _ci_platforms()
    assert any(name.startswith("macos") for name in platforms), sorted(platforms)
    assert any(name.startswith("ubuntu") for name in platforms), sorted(platforms)


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


# ---------------------------------------------------------------------------
# D-071 — every module the frontend imports must be in the repository
# ---------------------------------------------------------------------------
#
# `.gitignore` carried an unanchored `lib/` between `develop-eggs/` and
# `lib64/` — a stock Python packaging pattern that also matched
# `web/src/lib/`. Six modules, 662 lines, were never committed while nine
# tracked files imported them, so `npm run typecheck`, `npm test` and
# `npm run build` all failed on a fresh clone and passed for everyone who had
# the working tree. Nothing could catch it: every check in CI and every check
# here ran against files on disk, and git was the only thing that disagreed.
#
# These two tests are the pair that closes it. The first is the general
# property — what the frontend imports, the repository holds. The second is the
# narrow guard on the rule that broke, because an unanchored pattern added to
# `.gitignore` later would reopen the same hole somewhere else under `web/`.

_RELATIVE_SPECIFIER = re.compile(
    r"""(?:^|[\s;{(])(?:import|export)\b[^;'"]*?['"](\.[^'"]*)['"]"""
    r"""|\bimport\s*\(\s*['"](\.[^'"]*)['"]""",
    re.M,
)
# Extensionless specifiers are the TypeScript norm, `.d.ts` is how the
# generated API declarations are reached, and Vite resolves `?raw` suffixes and
# directory `index` files.
_MODULE_SUFFIXES = ("", ".ts", ".tsx", ".d.ts", ".css", ".json")


#: These two checks ask git a question, so they need a repository to ask. An
#: sdist or a `git archive` tarball is a legitimate way to run this suite, and
#: failing there would be a failure for an environment reason the test can
#: detect — which is the same class of noise D-071 exists to remove. Skipped
#: rather than passed, because passing would report agreement never established.
def _in_a_git_repository() -> bool:
    probe = subprocess.run(
        ["git", "-C", str(PROJECT_ROOT), "rev-parse", "--is-inside-work-tree"],
        capture_output=True,
        text=True,
    )
    return probe.returncode == 0 and probe.stdout.strip() == "true"


needs_git = pytest.mark.skipif(
    not _in_a_git_repository(),
    reason="not a git checkout, so git has nothing to say about what it tracks",
)


def _tracked_paths() -> set[Path]:
    listing = subprocess.run(
        ["git", "-C", str(PROJECT_ROOT), "ls-files", "-z"],
        capture_output=True,
        text=True,
        check=True,
    )
    return {(PROJECT_ROOT / name).resolve() for name in listing.stdout.split("\0") if name}


def _resolve_specifier(importer: Path, specifier: str) -> Path | None:
    """The file a relative import specifier names, the way Vite and tsc read it."""
    base = importer.parent / specifier.split("?", 1)[0]
    candidates = [Path(f"{base}{suffix}") for suffix in _MODULE_SUFFIXES]
    candidates += [base / f"index{suffix}" for suffix in _MODULE_SUFFIXES if suffix]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return None


def _frontend_imports() -> list[tuple[Path, str, Path | None]]:
    found: list[tuple[Path, str, Path | None]] = []
    for module in sorted((WEB / "src").rglob("*")):
        if not module.is_file() or module.suffix not in {".ts", ".tsx"}:
            continue
        for match in _RELATIVE_SPECIFIER.finditer(module.read_text(encoding="utf-8")):
            specifier = match.group(1) or match.group(2)
            if any(character in specifier for character in "*{"):
                # A bundler glob, not a module specifier: `logical.test.ts` and
                # `primitives.test.tsx` read *every* component's source through
                # `import.meta.glob`, and the whole point of those two guards
                # is that a component nobody listed is still checked — so a
                # pattern is the mechanism and an explicit list would be the
                # defect. There is nothing on disk for a pattern to resolve to,
                # and `test_the_globbed_module_patterns_match_something` below
                # is what keeps them from matching nothing.
                continue
            found.append((module, specifier, _resolve_specifier(module, specifier)))
    return found


#: The bundler globs `web/src` reads its own sources through, and the directory
#: each one must find modules in.
_MODULE_GLOBS: dict[str, tuple[str, ...]] = {
    "../{components,views,map}/**/*.tsx": ("components", "views", "map"),
    "../{components,views}/**/*.tsx": ("components", "views"),
}


def test_the_globbed_module_patterns_match_something() -> None:
    """A glob that matched nothing would make its guard vacuous.

    `logical.test.ts` checks D-012 over every component's inline styles and
    `primitives.test.tsx` sweeps for a bare directional glyph; both read the
    sources through `import.meta.glob`, and a pattern that stopped matching
    would turn each into a test that asserts nothing about anything.
    """
    import re as _re

    used: set[str] = set()
    for module in sorted((WEB / "src").rglob("*")):
        if not module.is_file() or module.suffix not in {".ts", ".tsx"}:
            continue
        text = module.read_text(encoding="utf-8")
        for pattern in _re.findall(r'import\.meta\.glob\(\s*"([^"]+)"', text):
            used.add(pattern)
            assert pattern in _MODULE_GLOBS, (
                f"{module.relative_to(PROJECT_ROOT)} globs {pattern!r}, which this "
                "guard does not know how to check; add it to _MODULE_GLOBS"
            )
    assert used, "no module glob found in web/src — the scan is broken"

    for pattern in sorted(used):
        matched = [
            path
            for directory in _MODULE_GLOBS[pattern]
            for path in (WEB / "src" / directory).rglob("*.tsx")
            if ".test." not in path.name
        ]
        assert len(matched) > 10, f"{pattern!r} matches only {len(matched)} modules"


def test_the_import_scanner_actually_finds_the_frontends_imports() -> None:
    """Guards the guard: a regex that silently stops matching asserts nothing."""
    imports = _frontend_imports()
    assert len(imports) > 100, f"only {len(imports)} relative imports found in web/src"
    importers = {module for module, _, _ in imports}
    assert len(importers) > 20, f"only {len(importers)} importing modules found"
    assert any(
        specifier.endswith("readerLink") for _, specifier, _ in imports
    ), "the readerLink grammar D-069 owns is imported by nothing — the scan is broken"


def test_every_relative_import_resolves_to_a_file_on_disk() -> None:
    unresolved = [
        f"{module.relative_to(PROJECT_ROOT)} imports {specifier!r}"
        for module, specifier, target in _frontend_imports()
        if target is None
    ]
    assert not unresolved, "frontend imports that resolve to nothing:\n" + "\n".join(unresolved)


@needs_git
def test_every_module_the_frontend_imports_is_tracked_by_git() -> None:
    """A fresh clone must be able to type-check, test and build ``web/``.

    Fails on the pre-fix tree with the six ``web/src/lib`` modules that nine
    tracked files import.
    """
    tracked = _tracked_paths()
    missing = sorted(
        {
            f"{target.relative_to(PROJECT_ROOT)} "
            f"(imported by {module.relative_to(PROJECT_ROOT)} as {specifier!r})"
            for module, specifier, target in _frontend_imports()
            if target is not None and target not in tracked
        }
    )
    assert not missing, (
        "the frontend imports files git does not track, so a fresh clone "
        "cannot build it:\n" + "\n".join(missing)
    )


@needs_git
def test_no_frontend_source_file_is_excluded_by_gitignore() -> None:
    """The narrow guard on the rule that broke.

    ``web/dist`` stays ignored — it is build output — so this looks only at
    ``web/src``, where every file is input.
    """
    sources = sorted(path for path in (WEB / "src").rglob("*") if path.is_file())
    assert sources, "no files found under web/src"
    check = subprocess.run(
        ["git", "-C", str(PROJECT_ROOT), "check-ignore", "-v", "--stdin"],
        input="\n".join(str(path) for path in sources),
        capture_output=True,
        text=True,
    )
    # Exit 1 with no output is "nothing matched", which is the passing case.
    assert check.returncode == 1 and not check.stdout.strip(), (
        "a .gitignore rule excludes frontend source files:\n" + check.stdout
    )


# ---------------------------------------------------------------------------
# D-108 — a translated string with nothing rendering it
# ---------------------------------------------------------------------------
#
# The audit found 19 catalogue keys referenced nowhere, and one was not merely
# clutter: `nav.skipToContent` was translated in both locales and
# `<main id="content">` was rendered, and nothing linked the two — so a
# keyboard user tabbed through the brand, the nav and the language switch on
# every page while the string that would have spared them sat in the
# catalogue. For accessibility a half-built affordance is the same as none, and
# the catalogue read as though the work were done.
#
# Checked from here rather than from vitest because reading the tree is what
# this file already does (see D-071 above), and the frontend has no
# `@types/node` to read files with.

I18N_CATALOG = WEB / "src" / "i18n" / "catalog.ts"
#: ``"some.key": "text",`` at the start of a catalogue line.
_CATALOG_KEY = re.compile(r'^\s+"([a-zA-Z0-9_.]+)":', re.M)


def _catalog_keys() -> set[str]:
    keys = set(_CATALOG_KEY.findall(I18N_CATALOG.read_text(encoding="utf-8")))
    assert len(keys) > 100, f"only {len(keys)} catalogue keys found; the regex has gone stale"
    return keys


def _frontend_source(exclude_i18n: bool = True) -> str:
    files = [
        path
        for path in sorted((WEB / "src").rglob("*"))
        if path.is_file()
        and path.suffix in {".ts", ".tsx"}
        and not (exclude_i18n and "i18n" in path.parts)
    ]
    assert len(files) > 20, f"only {len(files)} frontend modules found"
    return "\n".join(path.read_text(encoding="utf-8") for path in files)


def test_the_catalogue_scanner_finds_what_it_is_looking_for() -> None:
    """Guards the guard: an empty corpus would make every key look referenced."""
    assert "nav.skipToContent" in _catalog_keys()
    assert "nav.skipToContent" in _frontend_source()


def test_no_catalogue_key_is_rendered_by_nothing() -> None:
    body = _frontend_source()
    dead = sorted(key for key in _catalog_keys() if f'"{key}"' not in body)
    assert not dead, (
        "these translated strings are rendered by nothing, so the catalogue "
        f"reads as though the feature shipped: {dead}"
    )


def test_the_skip_link_the_catalogue_promises_exists() -> None:
    """The one dead key that was a missing feature, not clutter."""
    shell = (WEB / "src" / "components" / "Shell.tsx").read_text(encoding="utf-8")
    assert "nav.skipToContent" in shell, "the skip link is still not rendered"
    assert 'id="content"' in shell, "the skip link has nowhere to skip to"
    assert shell.index("nav.skipToContent") < shell.index('className="shell__bar"'), (
        "the skip link must come before the header it exists to skip"
    )
    assert ".shell__skip" in (
        WEB / "src" / "styles" / "base.css"
    ).read_text(encoding="utf-8"), "the skip link has no style, so it is always visible"


# ---------------------------------------------------------------------------
# D-113 — the legacy/upstream boundary, enforced rather than stated
# ---------------------------------------------------------------------------
#
# `legacy/upstream/README.md` says three things, and until now said them only
# in prose: nothing under `src/x2knwldg/` imports these scripts, the three
# Whisper drivers must never be run (`CLAUDE.md`: "Do not install or run
# Whisper or WhisperX"), and three of the scripts still have tests.
#
# They are deliberately *kept* rather than deleted — they are attributed
# upstream history, see `THIRD_PARTY_NOTICES.md` — so the fix for "unreferenced
# files inviting use" is not removal but a guard that says so, which is this
# project's stated preference over an intention in a comment.

UPSTREAM = PROJECT_ROOT / "legacy" / "upstream"
WHISPER_MODULES = ("transcribe", "transcribe_whisper", "transcribe_whisperx")


def test_the_upstream_scripts_are_still_where_the_notices_say() -> None:
    """Guards the guard, and the attribution: removing them is not the fix."""
    assert (UPSTREAM / "README.md").is_file()
    for name in WHISPER_MODULES:
        assert (UPSTREAM / f"{name}.py").is_file(), f"{name}.py is attributed upstream history"
    assert (PROJECT_ROOT / "THIRD_PARTY_NOTICES.md").is_file()


def test_nothing_in_the_package_imports_an_upstream_script() -> None:
    modules = sorted(path.stem for path in UPSTREAM.glob("*.py"))
    assert modules, "no upstream scripts found; this guard would pass vacuously"
    offenders: list[str] = []
    for path in sorted((PROJECT_ROOT / "src").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names = [node.module.split(".")[0]]
            for name in names:
                if name in modules:
                    offenders.append(f"{path.relative_to(PROJECT_ROOT)} imports {name}")
    assert not offenders, offenders


def test_no_whisper_driver_is_reachable_from_the_package_or_the_cli() -> None:
    """`CLAUDE.md` forbids running Whisper; nothing may make it reachable."""
    tree = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((PROJECT_ROOT / "src").rglob("*.py"))
    )
    for token in (*WHISPER_MODULES, "whisperx", "faster_whisper"):
        # Named in prose is fine — several modules explain *why* Whisper is
        # refused. An import or a subprocess call is not.
        assert f"import {token}" not in tree, f"the package imports {token}"
        assert f"from {token}" not in tree, f"the package imports from {token}"


def test_the_upstream_readme_names_the_scripts_that_still_have_tests() -> None:
    """The README's third claim, which is the one that rots when a test moves."""
    readme = (UPSTREAM / "README.md").read_text(encoding="utf-8")
    tests = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((PROJECT_ROOT / "tests").glob("test_*.py"))
    )
    for name in ("generate_video_db", "obsidian_exporter", "graph_extractor"):
        assert name in readme, f"the README no longer names {name}"
        assert name in tests, f"the README claims {name} has tests and it does not"


def test_ci_lints_and_type_checks_the_package() -> None:
    """D-114: the largest asymmetry in the project, and now a job.

    `web/` had `tsc --strict` with `noUncheckedIndexedAccess` and a CI job of
    its own; `src/` had no ruff, black or mypy config, no CI step and no mention
    in the docs. The cost was not hypothetical — four imports left dead by a
    refactor were found by running pyflakes by hand.
    """
    workflow = _workflow()
    assert "ruff check ." in workflow, "no ruff step in ci.yml"
    assert re.search(r"^\s+run: mypy\s*$", workflow, re.MULTILINE), "no mypy step in ci.yml"

    config = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "[tool.ruff.lint]" in config, "ruff has no configured rule set"
    assert "[tool.mypy]" in config, "mypy is unconfigured, so its strictness is the default"
    # Declared, so a contributor's `pip install -e '.[dev]'` runs what CI runs.
    assert '"ruff' in config and '"mypy' in config


def test_ci_lints_and_type_checks_the_frontend() -> None:
    """D-203: the same asymmetry as D-114, on the other half of the repository.

    There was no ESLint anywhere — no config, no dependency, no script, no CI
    step — while nine ``// eslint-disable-next-line
    react-hooks/exhaustive-deps`` comments sat in ``web/src`` suppressing
    nothing, and the rule they name is the one rule this code repeatedly needed
    to silence. And five ``.ts`` files under ``web/scripts/`` were in neither
    type-check program, so the code that produces the acceptance captures was
    checked by nothing.
    """
    workflow = _workflow()
    package = _package_json()

    assert "npm run lint" in workflow, "no frontend lint step in ci.yml"
    assert "npm run typecheck:scripts" in workflow, "no scripts type-check step in ci.yml"
    assert package["scripts"].get("lint") == "eslint ."
    assert (PROJECT_ROOT / "web" / "eslint.config.js").is_file()
    # Declared, so a contributor's `npm ci` runs what CI runs.
    for tool in ("eslint", "eslint-plugin-react-hooks", "typescript-eslint"):
        assert tool in package["devDependencies"], f"{tool} is not declared"

    # The rule the suppressions name has to be *on*. A config that turned it
    # off would pass every assertion above and check nothing.
    config = (PROJECT_ROOT / "web" / "eslint.config.js").read_text(encoding="utf-8")
    assert '"react-hooks/exhaustive-deps"' in config
    assert '"react-hooks/rules-of-hooks": "error"' in config
    # And a suppression that stops being needed has to show up as one.
    assert 'reportUnusedDisableDirectives: "error"' in config

    # Every script the docs tell a reader to run is an npm script over a
    # *declared* `tsx`, not an `npx tsx` that fetches an unpinned copy from
    # the registry at run time.
    assert "tsx" in package["devDependencies"], "tsx is still an undeclared execution dependency"
    for script in ("mockups:layout", "mockups:capture", "mockups:review", "measure:orbit"):
        assert script in package["scripts"], f"{script} is not an npm script"
    for path in sorted((PROJECT_ROOT / "web" / "scripts").glob("*.ts")):
        assert path.name in " ".join(package["scripts"].values()) or path.name in {
            "mockup_layout.ts"
        }, f"{path.name} is reachable by no npm script"


def test_no_gated_job_name_has_drifted_from_the_ruleset() -> None:
    """D-203: renaming a gated job silently removes a required gate.

    ``main`` is protected by a ruleset that requires status checks *by name*,
    so a job whose ``name:`` changes stops reporting the check the rule waits
    for — and a pull request then blocks for ever with every job green. This
    happened: adding the lint step renamed
    ``web (typecheck, test, build)`` to ``web (lint, typecheck, test, build)``
    and the ruleset was the only thing that noticed.

    The names are listed here rather than fetched, because a test that asked
    GitHub would skip on every machine without a token — including the one
    that matters, a contributor's. What it protects against is the rename, and
    a rename is visible in the diff of *this* file beside the workflow's.
    """
    gated = {
        "tests (python ${{ matrix.python-version }}, ${{ matrix.os }})",
        "core package without extras",
        "extra installs (${{ matrix.extra }})",
        "run fixtures are reproducible",
        "web (typecheck, test, build)",
        "lint and types",
        "frontend against the real API",
        "the Map in a browser",
        "requirements.txt installs",
    }
    declared = set(re.findall(r"^\s+name: (.+)$", _workflow(), re.MULTILINE))
    missing = sorted(name for name in gated if name not in declared)
    assert not missing, (
        "these job names are required by the `main is gated by CI` ruleset and no "
        f"longer exist in ci.yml, so the checks they name will never report: {missing}. "
        "Rename them back, or change the ruleset in the same breath."
    )


def test_every_ci_action_is_pinned_to_a_commit() -> None:
    """D-203: every ``uses:`` was a mutable major tag.

    ``actions/checkout@v4`` is a *reference the upstream owner can move*, and a
    workflow that trusts one runs whatever that owner points it at next — with
    this repository's checkout and its token in scope. The version stays in a
    comment beside the SHA, because a pin nobody can read is a pin nobody will
    ever update.
    """
    unpinned: list[str] = []
    for number, line in enumerate(_workflow().splitlines(), 1):
        # An actual step, not a comment that talks about one: the note at the
        # top of the workflow explains the pinning and quotes `uses:`.
        match = re.match(r"\s*-?\s*uses:\s*(\S+)\s*(?:#.*)?$", line)
        if match is None:
            continue
        reference = match.group(1)
        if "@" not in reference:
            unpinned.append(f"{number}: {reference}")
            continue
        pin = reference.split("@", 1)[1]
        if not re.fullmatch(r"[0-9a-f]{40}", pin):
            unpinned.append(f"{number}: {reference}")
            continue
        # The SHA alone is unreviewable; the version it is has to be beside it.
        assert re.search(r"#\s*v\d", line), (
            f"{number}: {reference} is pinned but does not say which version it is"
        )
    assert not unpinned, f"these `uses:` are not pinned to a commit: {unpinned}"


def test_the_gitignore_keeps_no_exception_for_a_file_that_is_not_there() -> None:
    """D-203: ``!vault/graphs/.gitkeep`` protected nothing.

    The directory does not exist, nothing in the package writes it, and nothing
    ever has — so the exception read as a directory the project keeps.
    """
    ignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
    dead: list[str] = []
    for line in ignore.splitlines():
        stripped = line.strip()
        if not stripped.startswith("!") or any(glob in stripped for glob in "*?["):
            continue
        target = PROJECT_ROOT / stripped[1:]
        # The *directory* is the test, not the file. `!.env.example` names a
        # template a contributor may add to a directory that plainly exists,
        # which is a convention rather than a claim; `!vault/graphs/.gitkeep`
        # named a placeholder in a directory nothing creates, which reads as a
        # directory the project keeps and is the defect.
        if not target.parent.is_dir():
            dead.append(stripped)
    assert not dead, (
        "these .gitignore exceptions name files in directories that do not "
        f"exist, so they protect nothing: {dead}"
    )


def test_ci_runs_the_frontend_against_a_real_server() -> None:
    """D-116: 13 integration tests gated on a variable nothing set.

    They exist because "a mock agrees with whatever the frontend assumed", so
    skipping everywhere made them the only tests in the tree that could not
    fail. The job must both set the variable and refuse a silent skip.
    """
    workflow = _workflow()
    assert "X2KNWLDG_API_BASE" in workflow, "no job sets X2KNWLDG_API_BASE"
    assert "dev_api.py" in workflow, "no job serves an API for them to talk to"

    # Both of these were wrong on the first attempt, and both would have left
    # the job green while proving nothing — so they are asserted by shape, not
    # by the presence of a message that can be reworded.
    #
    # `pipefail`: Actions runs `bash -e` without it, so `vitest | tee` exits
    # with tee's status and the step passes on a failing suite.
    assert "set -o pipefail" in workflow, (
        "the integration step pipes vitest into tee without pipefail, so a "
        "failing frontend suite would pass the job"
    )
    # The skip check has to match what vitest actually prints. It marks a
    # skipped test with a glyph, never the word on the line, so a grep over the
    # test lines can never fire; the summary's skip count is the discriminator.
    assert re.search(r'grep -qE "\[0-9\]\+ skipped"', workflow), (
        "the job does not check the integration tests actually ran; a skip "
        "would pass it"
    )


def test_ci_installs_requirements_txt() -> None:
    """D-111: nothing installed it, so nothing noticed it was wrong."""
    assert "pip install -r requirements.txt" in _workflow()


def test_requirements_txt_names_the_extras_pyproject_declares() -> None:
    """The file describes the extras in prose; the prose has to be true."""
    text = (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8")
    for extra in sorted(_declared_extras()):
        assert re.search(rf"^#\s+{re.escape(extra)}\b", text, re.MULTILINE), (
            f"requirements.txt does not describe the {extra!r} extra"
        )
    assert "not functional yet" not in text, "the `ui` layer shipped in T-116"


# ---------------------------------------------------------------------------
# D-105 — no API-supplied URL reaches an `href` unchecked
# ---------------------------------------------------------------------------
#
# Five sites rendered `hit.source_url`, `source.url` and `artifact.url`
# straight into `href`, with `target` and `rel` repeated at each one and no
# scheme check, while the markdown path a few lines away had used `isSafeHref`
# all along. The behaviour is tested in `primitives.test.tsx`; what is checked
# here is the shape, because the defect *was* a shape — a bare `<a>` over a
# value the server supplied — and it is the recurrence that matters.

#: A bare anchor whose href is an API-supplied value.
_UNGUARDED_HREF = re.compile(
    r"<a\s[^>]*href=\{(?:hit\.source_url|source\.url|artifact\.url|watchUrl|node\.href)\}"
)


def test_no_component_renders_an_api_url_through_a_bare_anchor() -> None:
    offenders: list[str] = []
    for path in sorted((WEB / "src").rglob("*.tsx")):
        if path.name.endswith(".test.tsx"):
            continue
        text = path.read_text(encoding="utf-8")
        for match in _UNGUARDED_HREF.finditer(text):
            line = text[: match.start()].count("\n") + 1
            # `Markdown` guards `node.href` with `isSafeHref` inline and has
            # since it was written; it is the precedent, not an offender.
            if path.name == "Markdown.tsx" and "isSafeHref" in text:
                continue
            offenders.append(f"{path.relative_to(PROJECT_ROOT)}:{line}")
    assert not offenders, (
        "these render a server-supplied URL into an href with no scheme check; "
        f"use `ExternalLink`: {offenders}"
    )


def test_the_guarded_link_primitive_exists_and_checks_the_scheme() -> None:
    """Guards the guard: the test above passes trivially if nothing uses it."""
    primitives = (WEB / "src" / "components" / "primitives.tsx").read_text(encoding="utf-8")
    assert "export function ExternalLink" in primitives
    assert "isSafeHref" in primitives

    users = [
        path.name
        for path in sorted((WEB / "src").rglob("*.tsx"))
        if not path.name.endswith(".test.tsx")
        and "ExternalLink" in path.read_text(encoding="utf-8")
        and path.name != "primitives.tsx"
    ]
    assert len(users) >= 3, f"only {users} use the guarded link"


def test_this_suite_runs_where_git_can_be_asked() -> None:
    """Guards the two skips above.

    A `skipif` that is always true turns a check into a claim nobody made, so
    the development checkout — and CI, which runs `actions/checkout` — must be
    a place where git answers. Only a tarball may skip.
    """
    if not (PROJECT_ROOT / ".git").exists():
        pytest.skip("running from an export rather than a checkout")
    assert _in_a_git_repository(), (
        "there is a .git here but git will not answer, so the D-071 checks "
        "would silently skip in the one place they must run"
    )


def _ci_run_blocks() -> list[tuple[str, str]]:
    """Every ``run:`` block in ci.yml as ``(first line, whole block)``.

    Parsed by indentation rather than with a YAML library, because this module
    is stdlib-only on purpose and ``pyyaml`` is not a declared dependency.
    """
    lines = _workflow().split("\n")
    blocks: list[tuple[str, str]] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if stripped == "run: |" or stripped.startswith("run: |"):
            indent = len(line) - len(line.lstrip())
            body: list[str] = []
            index += 1
            while index < len(lines):
                nxt = lines[index]
                if nxt.strip() and (len(nxt) - len(nxt.lstrip())) <= indent:
                    break
                body.append(nxt)
                index += 1
            text = "\n".join(body)
            first = next((b.strip() for b in body if b.strip()), "")
            blocks.append((first, text))
            continue
        if stripped.startswith("run: ") and not stripped.startswith("run: |"):
            blocks.append((stripped[5:], stripped[5:]))
        index += 1
    return blocks


#: A pipeline whose left side is a command under test. `||` is not a pipe.
_PIPED = re.compile(r"(?<!\|)\|(?!\|)\s*(?:tee|grep|head|tail|jq|sed|awk)\b")


def _piped_lines(block: str) -> list[str]:
    """Lines in *block* whose exit status a pipe would discard.

    Indentation decides, not the presence of an ``exit 1`` somewhere in the
    block: the first version of this helper exempted any block containing one,
    and the block it was written to catch ended with ``exit 1`` inside its skip
    branch — so the guard passed against the exact hole that had shipped.

    A piped line at the block's own indentation is the step doing its work, and
    its status is the step's. A piped line indented deeper sits inside an
    ``if``/``||`` branch that already fails on purpose, where the pipe only
    formats a message on the way out.
    """
    body = [line for line in block.split("\n") if line.strip()]
    if not body:
        return []
    base = min(len(line) - len(line.lstrip()) for line in body)
    return [
        line
        for line in body
        if _PIPED.search(line) and (len(line) - len(line.lstrip())) == base
    ]


def test_no_ci_step_loses_a_failure_to_a_pipe() -> None:
    """The hole the first run of the `integration` job had.

    Actions runs ``bash -e`` and **not** ``-o pipefail``, so ``cmd | tee log``
    exits with ``tee``'s status: the frontend suite could be entirely red and
    the step would report success. ``|| true`` and ``continue-on-error`` are
    already refused above; this is the same failure wearing a subtler hat, and
    it is the one that actually shipped.

    A pipe inside a branch that already ``exit 1``s is fine — there the pipe
    only formats a message on the way out.
    """
    offenders: list[str] = []
    for first, block in _ci_run_blocks():
        if "set -o pipefail" in block:
            continue
        for line in _piped_lines(block):
            offenders.append(f"{first[:50]} → {line.strip()[:60]}")
    assert not offenders, (
        "these steps pipe a command whose exit status is then lost, so the "
        f"step passes even when the command fails: {offenders}"
    )


def test_the_pipe_guard_can_actually_fail() -> None:
    """Guards the guard: the sweep must find the pipes that are there.

    A parser that returns nothing would pass the test above while checking
    nothing, which is precisely the shape of defect it exists to catch.
    """
    blocks = _ci_run_blocks()
    assert len(blocks) > 15, f"only {len(blocks)} run blocks parsed out of ci.yml"

    # The sweep must see the pipe that is there, and must *not* see the one
    # that is exempt — a guard checked only for "finds something" is how the
    # first version of this test passed against the hole it was written for.
    integration = next(block for _first, block in blocks if "vitest" in block)
    assert _piped_lines(integration), "the vitest pipeline is not being seen"

    fixtures = next(block for _first, block in blocks if "build_fixtures.py" in block)
    assert "| head" in fixtures, "the fixtures block no longer has its pipe"
    assert not _piped_lines(fixtures), (
        "the fixtures pipe sits inside a branch that already exits 1, so it "
        "must be exempt; counting it would make this guard cry wolf"
    )


# ---------------------------------------------------------------------------
# T-202 — the Knowledge Map's renderer pins (D-117, ADR 0005)
# ---------------------------------------------------------------------------

#: The Map's runtime graph packages. Sigma v4 is a *prerelease*: ADR 0005
#: chooses one exact beta, and a range would let the lockfile move to another
#: one on any refresh, so the pin is the decision and this is its guard.
MAP_RUNTIME_PINS = (
    "sigma",
    "graphology",
    "graphology-types",
    "graphology-layout-forceatlas2",
)

#: Present only because Sigma's published declarations ``import "events"`` and
#: that package ships none. With ``skipLibCheck: false`` (risk R17) the whole
#: type-check fails without it, so it is pinned beside the renderer it serves.
#: Sigma v3.0.3 depends on ``events`` too, so this is not a v4 defect.
MAP_DEV_PINS = ("@types/events",)

_EXACT_VERSION = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.]+)?$")


def test_every_map_dependency_is_pinned_to_one_exact_version() -> None:
    """D-117: a moving prerelease range is forbidden.

    ``^4.0.0-beta.5`` resolves to *any* later 4.x, betas included, so the
    version this project measured on the real graph would be replaced by one it
    never rendered — silently, on an unrelated ``npm install``. The gate's
    result is only about the version the gate ran.
    """
    package = _package_json()
    for name in MAP_RUNTIME_PINS:
        version = package["dependencies"][name]
        assert _EXACT_VERSION.match(version), f"{name} is not an exact pin: {version}"
    for name in MAP_DEV_PINS:
        version = package["devDependencies"][name]
        assert _EXACT_VERSION.match(version), f"{name} is not an exact pin: {version}"


def test_the_gate_page_states_the_version_that_actually_ran() -> None:
    """The gate page prints the renderer version into its own log.

    That line is what a recorded walk quotes, so it must be the version the
    manifest installs. Two spellings of one version is how a result gets
    attributed to a release that was never running.
    """
    pinned = _package_json()["dependencies"]["sigma"]
    main = (WEB / "src" / "map" / "gate" / "main.ts").read_text(encoding="utf-8")
    match = re.search(r'PINNED_SIGMA = "([^"]+)"', main)
    assert match is not None, "the gate page no longer states its renderer version"
    assert match.group(1) == pinned


def test_the_gate_page_stays_out_of_the_production_build() -> None:
    """``gate.html`` is a development harness, not a second Map.

    Vite's build input defaults to ``index.html`` alone, which is what keeps
    the harness out of ``dist/``. Configuring extra inputs would include it, so
    this asserts the default is still in force rather than trusting it.
    """
    assert (WEB / "gate.html").is_file()
    config = (WEB / "vite.config.ts").read_text(encoding="utf-8")
    assert "rollupOptions" not in config, (
        "vite.config.ts now configures rollup inputs; confirm gate.html is "
        "still excluded from the production build before relaxing this"
    )
    assert "gate" not in (WEB / "index.html").read_text(encoding="utf-8")


def test_nothing_in_the_application_imports_the_gate() -> None:
    """`#/map` belongs to ``T-204``. The gate must not become the Map by
    accident, so no application module reaches into its directory."""
    offenders: list[str] = []
    for path in sorted((WEB / "src").rglob("*.ts*")):
        if "map/gate" in path.as_posix():
            continue
        if "gate/" in path.read_text(encoding="utf-8"):
            offenders.append(path.relative_to(WEB).as_posix())
    assert not offenders, f"these modules import the T-202 gate: {offenders}"


def test_the_third_party_notices_record_every_map_dependency() -> None:
    """Licences are recorded where the repository already records provenance,
    with the version they were checked at — an unpinned notice would document a
    licence the installed package may not carry."""
    notices = (PROJECT_ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    package = _package_json()
    for name in MAP_RUNTIME_PINS + MAP_DEV_PINS:
        version = package["dependencies"].get(name) or package["devDependencies"][name]
        assert f"{name}@{version}" in notices, f"{name}@{version} is not recorded"


def test_the_notices_record_every_package_that_reaches_the_bundle() -> None:
    """D-203: the file omitted most of what it ships.

    React, react-dom, react-router, react-router-dom, scheduler, cookie and
    set-cookie-parser are all in the production bundle and none was recorded,
    against this file's own claim to record what reaches it. All MIT, so there
    was no licence exposure — but a notices file that omits most of what it
    ships is a record nobody can rely on, and "it happens to be MIT" is a fact
    that has to be checked rather than assumed.

    Walked from ``package-lock.json`` rather than from a list, because a list
    is the thing that went stale: the next transitive package to reach the
    bundle fails here.
    """
    import json as _json

    notices = (PROJECT_ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    lock = _json.loads((WEB / "package-lock.json").read_text(encoding="utf-8"))
    packages = lock["packages"]

    # The production closure: the declared runtime dependencies and everything
    # they depend on. `devDependencies` are excluded by construction — nothing
    # under `web/src` imports them and `npm run build` never sees them — and
    # the two that *are* recorded (the gate's) have their own section.
    closure: set[str] = set()

    def walk(name: str) -> None:
        if name in closure:
            return
        node = packages.get(f"node_modules/{name}")
        if node is None:
            return
        closure.add(name)
        for dependency in (node.get("dependencies") or {}):
            walk(dependency)

    for declared in _package_json()["dependencies"]:
        walk(declared)

    assert len(closure) > 8, f"the closure walk found only {sorted(closure)}"

    missing: list[str] = []
    for name in sorted(closure):
        version = packages[f"node_modules/{name}"]["version"]
        if f"{name}@{version}" not in notices:
            missing.append(f"{name}@{version}")
    assert not missing, (
        "these packages reach the browser bundle and THIRD_PARTY_NOTICES.md "
        f"does not record them at the version the lockfile resolves: {missing}"
    )


# ---------------------------------------------------------------------------
# T-203 — the Map asks for a page the contract will actually serve
# ---------------------------------------------------------------------------


def test_the_map_requests_no_more_than_the_contract_maximum() -> None:
    """``GRAPH_PAGE_LIMIT`` is the frozen document's ``limit`` maximum.

    D-118 bounds the Map's first request by the contract maximum rather than by
    a number the frontend liked. Written out in TypeScript it is a second copy
    of a value the OpenAPI document owns, and the two would drift silently: a
    larger literal is a ``400`` on the Map's very first request, and the client
    would have been refused by the bound it was supposed to respect.
    """
    walk = (WEB / "src" / "map" / "graphWalk.ts").read_text(encoding="utf-8")
    match = re.search(r"GRAPH_PAGE_LIMIT = (\d+)", walk)
    assert match is not None, "the Map no longer states the page size it asks for"

    document = json.loads(
        (PROJECT_ROOT / "schemas" / "api" / "v1" / "openapi.json").read_text(encoding="utf-8")
    )
    maximum = document["components"]["parameters"]["Limit"]["schema"]["maximum"]
    assert int(match.group(1)) == maximum, (
        f"the Map asks for {match.group(1)} nodes per page and the contract's "
        f"maximum is {maximum}"
    )
    # And the contract's own maximum is the package's, so this reaches the one
    # constant rather than agreeing with a second copy of it (D-101).
    from x2knwldg.constants import MAX_PAGE_LIMIT

    assert maximum == MAX_PAGE_LIMIT


# ---------------------------------------------------------------------------
# T-204 — the Map has one address, one renderer, and one lifecycle
# ---------------------------------------------------------------------------


def _web_modules(exclude_gate: bool = True) -> list[Path]:
    return [
        path
        for path in sorted((WEB / "src").rglob("*"))
        if path.is_file()
        and path.suffix in {".ts", ".tsx"}
        and not (exclude_gate and "map/gate" in path.as_posix())
    ]


def test_the_map_is_addressable_and_linked() -> None:
    """``#/map`` is a route and a navigation entry, not a panel.

    The acceptance for `T-204` is that direct navigation and reload work, and
    under ``HashRouter`` those are the same event — so what has to exist is a
    declared route and something that links to it. A Map reachable only by
    typing the fragment is a Map `T-206`'s URL grammar would have nothing to
    hang selection and filters off.

    `T-256` made ``/map`` two Maps, so the route's element is a dispatch rather
    than a view. What this asserts is therefore the property rather than the
    spelling: one declared route, something linking to it, and a dispatch that
    reaches **both** views. Pinning ``<MapView />`` here would have made adding
    a second mode look like breaking the first.
    """
    app = (WEB / "src" / "App.tsx").read_text(encoding="utf-8")
    assert re.search(r'path="/map"\s+element=\{<\w+\s*/>\}', app), (
        "App.tsx no longer declares a /map route"
    )
    shell = (WEB / "src" / "components" / "Shell.tsx").read_text(encoding="utf-8")
    assert 'to="/map"' in shell, "the Shell no longer links to the Map"

    route = (WEB / "src" / "views" / "MapRoute.tsx").read_text(encoding="utf-8")
    for view in ("MapView", "SourceMapView"):
        assert view in route, f"the /map route no longer reaches {view}"
    # The mode is read from the URL, not from state: that is what makes a
    # Source Map a link rather than something a reload loses.
    assert "parseMapState" in route, "the /map route no longer reads its mode from the URL"


def test_the_application_constructs_the_renderer_in_exactly_one_module() -> None:
    """§8.6: no second Sigma lifecycle wrapper.

    The gate is excluded because it is a development harness outside the
    application (`T-202`), and it already has a test of its own saying so. What
    this forbids is a *second* place in the app that constructs a renderer,
    because two constructors are two lifecycles, and ADR 0005 invariant 10 —
    every renderer killed on unmount and on replacement — is a property of one.
    """
    builders = [
        path.relative_to(WEB).as_posix()
        for path in _web_modules()
        if re.search(r"\bnew Sigma\b", path.read_text(encoding="utf-8"))
    ]
    assert builders == ["src/map/sigmaRenderer.ts"], (
        f"the application constructs Sigma in {builders}; §8.6 allows one place"
    )


def test_the_renderer_module_is_never_imported_statically() -> None:
    """`sigma` evaluates ``WebGL2RenderingContext`` at module scope.

    So a static import anywhere in the application's module graph throws a
    ``ReferenceError`` the moment jsdom loads it — and takes the Library's and
    the Reader's suites down with it, for a module neither of them uses. The
    Map reaches the renderer through a dynamic ``import`` instead, which is
    also what keeps a 360 kB chunk out of the two routes that draw no graph.
    """
    offenders: list[str] = []
    for path in _web_modules():
        text = path.read_text(encoding="utf-8")
        name = path.relative_to(WEB).as_posix()
        if name != "src/map/sigmaRenderer.ts" and re.search(r'^\s*import .*"sigma"', text, re.M):
            offenders.append(f"{name} imports sigma statically")
        if re.search(r'^\s*import .*"(?:\./|\.\./map/)sigmaRenderer"', text, re.M):
            offenders.append(f"{name} imports the renderer module statically")
    assert not offenders, "\n".join(offenders)

    # And the dynamic reach is really there, so this pair cannot both pass by
    # the Map having stopped loading a renderer at all.
    view = (WEB / "src" / "views" / "MapView.tsx").read_text(encoding="utf-8")
    assert 'import("../map/sigmaRenderer")' in view, (
        "MapView no longer loads the renderer on demand"
    )


def test_the_map_writes_no_display_attribute_onto_the_graph() -> None:
    """D-124: node attributes are ``x``, ``y`` and the API's record.

    A label, size or colour stored on the graph would put presentation inside
    the data the inspector reads back, and would break the field-by-field
    comparison D-125's refusal depends on. `T-205`'s style matrix belongs in
    the renderer's reducers, so nothing outside the `T-202` gate — which is not
    the Map — may set a graph attribute at all.
    """
    offenders = [
        path.relative_to(WEB).as_posix()
        for path in _web_modules()
        if re.search(r"\bset(?:Node|Edge)Attributes?\b", path.read_text(encoding="utf-8"))
    ]
    assert not offenders, (
        f"these modules write graph attributes outside the projection: {offenders}"
    )


def test_the_map_stage_states_a_size() -> None:
    """Sigma is created with ``allowInvalidContainer: false``.

    That is deliberate — a container with no size should be a refusal the Map
    states rather than a blank canvas nobody can explain — but it means the
    stage's size is load-bearing, and `T-209` measured *how*: the renderer
    refuses a dimension of exactly zero and accepts everything else, so a
    two-pixel stage is drawn into and reported as a picture (D-145).

    `T-212` gave the stage its size a second way and this test had to follow.
    In the workspace composition the stage is not a band on a page with a
    block size of its own: it is absolutely placed against the field, which is
    the route viewport less the app bar (D-153). So the question this asks is
    unchanged — *is the container's size stated in the stylesheet* — while
    what counts as an answer now depends on the composition:

    * the workspace stage is inset to a field that itself states a block size;
    * the document composition below 48rem, which `T-213` replaces with SPEC
      §5's third tier, keeps both the size and the **minimum** D-145 is about.

    There is deliberately no minimum on the workspace stage. A minimum only
    protects a reader when something can take the overflow, and in a workspace
    nothing can: the document does not scroll, so a stage taller than the field
    is a clipped graph rather than a scrollable one. A short window is a small
    field, which is what a small window *is* here.
    """
    renderer = (WEB / "src" / "map" / "sigmaRenderer.ts").read_text(encoding="utf-8")
    assert "allowInvalidContainer: false" in renderer
    base = (WEB / "src" / "styles" / "base.css").read_text(encoding="utf-8")

    narrow = re.search(r"@media \(max-width: 48rem\) \{.*?\n\}\n", base, re.S)
    assert narrow is not None, "the Map lost the breakpoint its document composition lives in"
    workspace = base.replace(narrow.group(0), "")

    stage = re.search(r"\.map__stage\s*\{[^}]*\}", workspace)
    assert stage is not None, "the Map's stage has no style, so it has no size"
    assert "position: absolute" in stage.group(0) and "inset: 0" in stage.group(0), (
        "the workspace stage is neither sized nor inset to its field, so "
        "`allowInvalidContainer: false` will refuse the renderer"
    )
    field = re.search(r"\n\.map\s*\{[^}]*\}", workspace)
    assert field is not None, "the Map has no field for the stage to be inset to"
    assert "block-size" in field.group(0), (
        "the Map's field declares no block size, so the stage inset to it has "
        "no size either and `allowInvalidContainer: false` will refuse the renderer"
    )

    narrow_stage = re.search(r"\.map__stage\s*\{[^}]*\}", narrow.group(0))
    assert narrow_stage is not None, "the document composition's stage has no style"
    assert "block-size" in narrow_stage.group(0), (
        "the document composition's stage declares no block size, so "
        "`allowInvalidContainer: false` will refuse the renderer"
    )
    assert "min-block-size" in narrow_stage.group(0), (
        "the document composition's stage declares no *minimum* block size, so "
        "a narrow window draws a graph a reader cannot see and the route still "
        "calls it drawn (D-145)"
    )

    view = (WEB / "src" / "views" / "MapView.tsx").read_text(encoding="utf-8")
    assert 'className="map__stage"' in view
    assert "ResizeObserver" in view, "nothing hands a container resize to the renderer"


# ---------------------------------------------------------------------------
# T-212 — the Map is a viewport workspace, and the document does not scroll
# ---------------------------------------------------------------------------


def test_the_map_workspace_does_not_scroll_the_document() -> None:
    """D-153's first clause, and the one jsdom cannot answer.

    The rejected screen was not badly coloured; it was composed as a document.
    `T-211` measured it on the real build at 2852x1688: the stage began 790 px
    down, and focusing one entity produced a document 3.4 screens tall, so the
    Search -> Focus -> Quick Read loop the Map exists for needed about 4100 px
    of scrolling. Every component test in `web/` runs in jsdom, which has no
    layout at all — every rectangle is zero and no stylesheet is applied — so
    the rule that the document does not scroll can only be checked where it is
    written.

    SPEC §2 states it as ``html, body { overflow: hidden }``. It is scoped to
    the route rather than written globally because three routes share this
    document and the other two *are* documents: the Library and the Reader
    must scroll. What must hold is that the workspace frame is a fixed-height
    grid with no overflow of its own, and that the document around it cannot
    scroll while that frame is mounted.
    """
    base = (WEB / "src" / "styles" / "base.css").read_text(encoding="utf-8")
    tokens = (WEB / "src" / "styles" / "tokens.css").read_text(encoding="utf-8")

    frame = re.search(r"\.shell--workspace\s*\{[^}]*\}", base)
    assert frame is not None, "no workspace frame, so the Map is still a document"
    assert "overflow: hidden" in frame.group(0), (
        "the workspace frame scrolls, which is the composition D-153 replaces"
    )
    assert "grid-template-rows: var(--bar-height) 1fr" in frame.group(0), (
        "the workspace is not the app bar plus the field, so the stage does "
        "not fill the usable route viewport"
    )
    assert "--bar-height:" in tokens, (
        "`--bar-height` is not a token, so the bar's height and the grid row "
        "it is given are two numbers that can disagree"
    )

    # The document itself, and it must be conditional: the rule may not reach
    # the two routes that have to scroll.
    document = re.search(r"html:has\(\.shell--workspace\)[^{]*\{[^}]*\}", base)
    assert document is not None, (
        "nothing stops the document scrolling behind the workspace (SPEC §2)"
    )
    assert "overflow: hidden" in document.group(0)
    assert not re.search(r"\nhtml,\s*\nbody\s*\{[^}]*overflow: hidden", base), (
        "`overflow: hidden` is written on `html, body` unconditionally, which "
        "stops the Library and the Reader scrolling as well"
    )

    # And the field the stage is inset to must be the frame's second row
    # rather than the old centred text column.
    main = re.search(r"\.shell--workspace \.shell__main\s*\{[^}]*\}", base)
    assert main is not None, "the workspace's main is still the document column"
    assert "max-inline-size: none" in main.group(0), (
        "the workspace keeps the 78rem column that left 1604 px of the review "
        "viewport unused (`T-211` §1)"
    )


def test_the_card_policy_is_told_where_the_floating_chrome_is() -> None:
    """A card is drawn over whatever the route puts on the stage.

    The overlay is a sibling of the renderer's container rather than a child
    of it (D-137), so nothing clips a card that leaves the stage — which was
    already how `T-209` found two statements sitting behind the search rail.
    The workspace made that failure mode ordinary rather than rare: the
    controls are *on* the field now. So the policy takes the chrome's own
    rectangles, and the route measures them rather than stating them as
    insets — the composition mirrors under ``dir="rtl"``, and a hand-written
    inset per edge is the defect D-191 carries forward from the mockup.
    """
    policy = (WEB / "src" / "map" / "constellation.ts").read_text(encoding="utf-8")
    assert "obstacles?: readonly StageRect[]" in policy, (
        "the density policy cannot be told where the floating chrome is"
    )
    view = (WEB / "src" / "views" / "MapView.tsx").read_text(encoding="utf-8")
    assert "obstacles: chrome" in view, "the route does not tell the policy about its chrome"
    assert "data-map-chrome" in view, "no surface is marked as chrome, so none is measured"
    assert "getBoundingClientRect" in view, (
        "the chrome is not measured, so its position is stated somewhere and "
        "will be stated wrong in the mirrored composition"
    )


# ---------------------------------------------------------------------------
# T-207 — the constellation is bounded, the depth is the contract's, and the
#         overlay owns nothing
# ---------------------------------------------------------------------------


def test_the_map_asks_for_a_depth_the_contract_will_serve() -> None:
    """``MAP_DEPTH_MIN``/``MAP_DEPTH_MAX`` are the frozen document's own bounds.

    The same rule as ``GRAPH_PAGE_LIMIT`` (`T-203`), for the same reason: a
    bound written out in TypeScript is a second copy of a value the OpenAPI
    document owns, and the two drift silently. Here the drift is worse than a
    refused request — the neighbourhood response *echoes ``depth`` back*, so a
    client asking beyond the maximum is refused, and one that clamped would
    report a bound the reader never set.
    """
    module = (WEB / "src" / "map" / "neighbourhood.ts").read_text(encoding="utf-8")
    low = re.search(r"MAP_DEPTH_MIN = (\d+)", module)
    high = re.search(r"MAP_DEPTH_MAX = (\d+)", module)
    assert low is not None and high is not None, (
        "the Map no longer states the depth bounds it asks within"
    )

    document = json.loads(
        (PROJECT_ROOT / "schemas" / "api" / "v1" / "openapi.json").read_text(encoding="utf-8")
    )
    operation = document["paths"]["/api/graph/neighborhood/{entity_id}"]["get"]
    depth = next(
        parameter
        for parameter in operation["parameters"]
        if parameter.get("name") == "depth"
    )
    assert int(low.group(1)) == depth["schema"]["minimum"]
    assert int(high.group(1)) == depth["schema"]["maximum"]
    # And the package's own bounds are the document's, so this reaches one
    # constant rather than agreeing with a second copy of it.
    from x2knwldg.repository.base import MAX_DEPTH, MIN_DEPTH

    assert depth["schema"]["minimum"] == MIN_DEPTH
    assert depth["schema"]["maximum"] == MAX_DEPTH

    # The neighbourhood is not paged — the response carries no `page` — so
    # `limit` is the only bound there is, and it must be one the server serves.
    hook = (WEB / "src" / "map" / "useNeighbourhood.ts").read_text(encoding="utf-8")
    requested = re.search(r"NEIGHBOURHOOD_LIMIT = (\d+)", hook)
    assert requested is not None, "the Map no longer states how many neighbours it asks for"
    assert int(requested.group(1)) <= document["components"]["parameters"]["Limit"]["schema"][
        "maximum"
    ]


def test_the_card_overlay_owns_no_control_the_dom_does_not() -> None:
    """D-132's overlay is presentation, and `T-208` depends on it staying so.

    Two failures are being held off at once. A focusable card over a canvas
    builds a second accessibility tree over entities the related list already
    lists, and a *control* that exists only inside the overlay makes the canvas
    the only way to reach it — which is the "essential content only on hover or
    WebGL" that `T-208`'s gate forbids. So the overlay renders no button, link
    or field, takes no pointer events, and is hidden from the accessibility
    tree; selecting a neighbour is a click on its mark (the same `focusEntity`
    the rail calls) or a real control in the related list.
    """
    overlay = (WEB / "src" / "components" / "MapOrbit.tsx").read_text(encoding="utf-8")
    for element in ("<button", "<a ", "<input", "<select", "onClick"):
        assert element not in overlay, (
            f"the card overlay renders {element!r}; D-132's overlay is presentation, "
            "and a control that exists only over the canvas is unreachable without it"
        )
    assert 'aria-hidden="true"' in overlay, "the overlay is not hidden from the accessibility tree"

    base = (WEB / "src" / "styles" / "base.css").read_text(encoding="utf-8")
    rule = re.search(r"\.map__overlay\s*\{[^}]*\}", base)
    assert rule is not None, "the card overlay has no style, so it has no box over the stage"
    assert "pointer-events: none" in rule.group(0), (
        "the overlay would swallow the clicks that select a node on the canvas"
    )
    assert "position: absolute" in rule.group(0)


def test_the_stage_overlay_is_not_inside_the_container_the_renderer_owns() -> None:
    """``MapSession.kill()`` empties the renderer's container.

    It has to: Sigma appends its own canvases there, and a killed renderer's
    leftovers would otherwise sit under the next one's. So a React subtree
    rendered *inside* that container is removed from under React the first time
    a filter replaces the renderer — the cards would vanish and never come
    back, with nothing in the console to say why. The overlay is a sibling.
    """
    session = (WEB / "src" / "map" / "mapSession.ts").read_text(encoding="utf-8")
    assert "replaceChildren()" in session, (
        "the session no longer clears the container, so this guard is guarding nothing"
    )
    view = (WEB / "src" / "views" / "MapView.tsx").read_text(encoding="utf-8")
    stage = view.index('className="map__stage"')
    overlay = view.index("<MapOrbit")
    closing = view.index("/>", stage)
    assert closing < overlay, (
        "the card overlay is rendered inside the container the renderer owns; "
        "`MapSession.kill()` would remove it from under React"
    )


def test_the_map_builds_its_card_content_in_exactly_one_place() -> None:
    """§8.6 allows one card-content formatter, and one text cutter.

    The rail's cards, the Peek, the on-stage cards and the related list all
    render one record shape, and every one of them builds it through
    ``previewOfEntity``/``previewOfHit``. A second builder would be a second
    set of decisions about what a missing confidence renders as — and the
    integration that closed the `T-205`/`T-206` fan-out already found one:
    the DOM card had grown its own cutter, which counted UTF-16 units and
    would halve a surrogate pair in the Persian half of this library.
    """
    builders = [
        path.relative_to(WEB).as_posix()
        for path in _web_modules()
        if re.search(r"unaddressable:\s*(?:null|\"|')", path.read_text(encoding="utf-8"))
    ]
    assert builders == ["src/map/useMapSearch.ts"], (
        f"these modules build a Map preview themselves: {builders}; §8.6 allows one"
    )

    # Application modules only: a test naming the ellipsis is asserting on the
    # cut, not performing one.
    cutters = [
        path.relative_to(WEB).as_posix()
        for path in _web_modules()
        if ".test." not in path.name
        and path.name != "labelPolicy.ts"
        and "MAP_LABEL_ELLIPSIS" in path.read_text(encoding="utf-8")
    ]
    assert not cutters, f"these modules cut display text themselves: {cutters}"


# ---------------------------------------------------------------------------
# T-208 — the DOM path is the primary one, and each policy has one home
# ---------------------------------------------------------------------------


def test_the_map_has_a_dom_companion_for_everything_it_draws() -> None:
    """D-120 pairs the WebGL surface with a DOM one, and `T-208` built it.

    Until this list existed, the DOM half of that pair could only be reached
    through a *query*: the search rail lists what matches and the related list
    lists a selection's neighbourhood, so a reader with no pointer, no WebGL2
    or a screen reader had the counts and no way to reach the entities the
    counts were about. That is "essential content exists only on the canvas",
    which the phase gate forbids outright.

    What is guarded here is the wiring, because the wiring is what a later
    refactor drops: the route renders the companion, and the companion reads
    the accumulated graph through the one projection.
    """
    view = (WEB / "src" / "views" / "MapView.tsx").read_text(encoding="utf-8")
    assert "<MapOutline" in view, "the Map route renders no companion list"
    outline = (WEB / "src" / "components" / "MapOutline.tsx").read_text(encoding="utf-8")
    assert "outlineOfGraph" in outline, (
        "the companion no longer reads the accumulated graph through `outline.ts`"
    )
    assert "previewOfEntity" not in outline, (
        "the companion builds its own card content; §8.6 allows one formatter, "
        "and `outlineOfGraph` already goes through it"
    )


def test_the_companion_lists_are_not_windowed() -> None:
    """A row that is not in the DOM is a row no reader can reach.

    ``VirtualList`` exists and measures its rows, and it is the right tool for
    the Reader's captions. It is the wrong tool for these two lists, and the
    trade is deliberate: windowing keeps most rows out of the DOM, which costs
    exactly the claim they exist to make — the related list may omit no
    neighbour (R20), and the outline is the surface that has to be reachable
    when nothing else is. Both bound their length instead, and both count what
    the bound leaves out.
    """
    for name in ("MapOutline.tsx", "MapRelatedList.tsx"):
        source = (WEB / "src" / "components" / name).read_text(encoding="utf-8")
        assert "VirtualList" not in source, (
            f"{name} windows its rows; a row outside the DOM is unreachable, and "
            "these two lists exist to be complete"
        )


def test_the_map_announces_a_picture_only_when_there_is_one() -> None:
    """An empty box announced as an image of the knowledge graph is a lie.

    ``role="img"`` with a label saying "Knowledge graph, drawn" is true while
    the renderer holds the graph and false in the four states where it does
    not — no WebGL2, a refused container, no page yet, and no node to draw.
    So the role is conditional, and a constant one is the regression.
    """
    view = (WEB / "src" / "views" / "MapView.tsx").read_text(encoding="utf-8")
    # Comments are stripped first: the JSX comment above the stage quotes the
    # attribute in order to explain why it is conditional.
    code = re.sub(r"/\*.*?\*/", "", view, flags=re.DOTALL)
    assert 'role="img"' not in code, (
        "the stage claims to be a picture unconditionally; it is only a picture "
        "while a live renderer holds the graph"
    )
    assert 'role={drawing ? "img" : undefined}' in code


def _code_without_comments(path: Path) -> str:
    """A module's code, with its prose removed.

    These guards read source as text, and this project's source carries a lot
    of prose: a file that *explains* why it no longer builds its own
    disclosure would otherwise read as one that does.
    """
    source = path.read_text(encoding="utf-8")
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return re.sub(r"^\s*//.*$", "", source, flags=re.MULTILINE)


def test_the_map_has_one_disclosure_and_one_motion_policy() -> None:
    """Two policies `T-208` added, each with exactly one home.

    A second ``<details>`` is not a styling choice: the panel that grew one
    inside another (Quick Read did, in `T-207`) had two collapsed states for
    one panel, and the outer one hid a summary the reader needed. And a second
    reader of the reduced-motion query would be a second answer to it — the
    stylesheet cannot reach a camera animated in script on a canvas, which is
    the whole reason `map/motion.ts` exists.
    """
    disclosures = [
        path.relative_to(WEB).as_posix()
        for path in _web_modules()
        if ".test." not in path.name and "<details" in _code_without_comments(path)
    ]
    assert disclosures == ["src/components/Disclosure.tsx"], (
        f"these modules build a disclosure themselves: {disclosures}"
    )

    readers = [
        path.relative_to(WEB).as_posix()
        for path in _web_modules()
        if ".test." not in path.name and "prefers-reduced-motion" in _code_without_comments(path)
    ]
    assert readers == ["src/map/motion.ts"], (
        f"these modules read the reduced-motion preference themselves: {readers}"
    )

    base = (WEB / "src" / "styles" / "base.css").read_text(encoding="utf-8")
    assert "@media (prefers-reduced-motion: reduce)" in base, (
        "the stylesheet answers no reduced-motion preference, so `motion.ts` is "
        "answering for the canvas alone"
    )


# ---------------------------------------------------------------------------
# T-209 — the browser gate: dev-only, pinned, type-checked, and run by CI
# ---------------------------------------------------------------------------
#
# The gate is the phase's last task and the only witness for WebGL, layout,
# real focus order and the reduced-motion camera. Everything below exists so
# that it cannot quietly stop being any of those things: a harness that leaks
# into the bundle, a range instead of a pin, a spec `npm test` tries to run in
# jsdom, or a job nobody runs are each a way for a green tree to mean less
# than it says.

#: The gate's own dependency. A development one: nothing under `web/src`
#: imports it and `npm run build` never sees it, which is why it is pinned and
#: recorded separately from the Map's runtime packages.
GATE_DEV_PINS = ("@playwright/test",)


def test_the_browser_gate_is_pinned_to_one_exact_version() -> None:
    """A browser gate's result is about the harness that produced it.

    The same argument as D-117 for the renderer: a range lets an unrelated
    `npm install` change what the walk measured, and a measurement that
    describes a version nobody recorded is not a measurement.
    """
    package = _package_json()
    for name in GATE_DEV_PINS:
        version = package["devDependencies"][name]
        assert _EXACT_VERSION.match(version), f"{name} is not an exact pin: {version}"


def test_the_browser_gate_is_recorded_with_its_licence() -> None:
    """Apache-2.0, not MIT, so it has a section of its own in the notices."""
    notices = (PROJECT_ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    package = _package_json()
    for name in GATE_DEV_PINS:
        version = package["devDependencies"][name]
        assert f"{name}@{version}" in notices, f"{name}@{version} is not recorded"
    assert "Apache-2.0" in notices, "the gate's licence is recorded as something it is not"


def test_the_browser_gate_stays_out_of_the_application() -> None:
    """The harness is not the Map, and the Map does not know it exists.

    `gate.html` has the same guard (`T-202`) for the same reason: a harness
    written to answer a question must not become a second implementation of
    the thing it is asking about.
    """
    gate = WEB / "browser"
    assert gate.is_dir(), "the browser gate is gone"
    assert list(gate.glob("*.spec.ts")), "the browser gate holds no specs"

    offenders = [
        path.relative_to(WEB).as_posix()
        for path in sorted((WEB / "src").rglob("*.ts*"))
        if "browser/" in path.read_text(encoding="utf-8")
    ]
    assert not offenders, f"these application modules reach into the gate: {offenders}"

    # And the other direction: the gate asserts on behaviour rather than on
    # the constants it is checking. A spec that imported `MAP_STAGE_CARD_BOX`
    # would agree with whatever the module says, which is the one thing a gate
    # must not do.
    borrowed = [
        path.name
        for path in sorted(gate.rglob("*.ts"))
        if re.search(r'from\s+"\.\./src', path.read_text(encoding="utf-8"))
    ]
    assert not borrowed, f"these specs import the application's own numbers: {borrowed}"


def test_the_unit_suite_does_not_try_to_run_the_browser_gate() -> None:
    """`npm test` stays hermetic, and jsdom never sees a Playwright spec.

    Vitest's `include` is `src/**`, so the gate's files are outside it. If that
    ever widened, every spec in `web/browser/` would fail in jsdom for reasons
    that have nothing to do with the Map.
    """
    config = (WEB / "vite.config.ts").read_text(encoding="utf-8")
    include = re.search(r'include:\s*\[(.*?)\]', config, re.DOTALL)
    assert include is not None, "the test program no longer states what it includes"
    assert "browser" not in include.group(1), (
        "vitest now collects the browser gate's specs, which cannot run in jsdom"
    )
    playwright = (WEB / "playwright.config.ts").read_text(encoding="utf-8")
    assert 'testDir: "./browser"' in playwright, "the gate no longer states where its specs are"


def test_the_browser_gate_is_type_checked_by_its_own_program() -> None:
    """Playwright transpiles specs without type-checking them.

    So without a program of its own the gate would be the only unchecked
    TypeScript in the repository — and it is the code that decides whether the
    phase is finished.
    """
    package = _package_json()
    assert package["scripts"].get("typecheck:browser") == (
        "tsc --noEmit --project browser/tsconfig.json"
    )
    assert package["scripts"].get("browser") == "playwright test"
    config = json.loads(
        re.sub(
            r'^\s*"//":\s*\[.*?\],\s*$',
            "",
            (WEB / "browser" / "tsconfig.json").read_text(encoding="utf-8"),
            flags=re.DOTALL | re.MULTILINE,
        )
    )
    # `src` keeps `skipLibCheck: false`, which is risk R17's mitigation; the
    # gate needs it on for declarations this project does not own, so the two
    # programs are separate rather than one relaxed one.
    assert config["compilerOptions"]["skipLibCheck"] is True
    root = json.loads((WEB / "tsconfig.json").read_text(encoding="utf-8"))
    assert root["compilerOptions"]["skipLibCheck"] is False


def test_ci_walks_the_map_in_a_browser() -> None:
    """The gate that nobody runs is the gate that stops being true.

    D-116 is the precedent: thirteen integration tests gated on a variable no
    job set, so the only tests that could disagree with the frontend never ran
    anywhere. This job installs a browser, serves the committed fixtures and
    walks the route.
    """
    workflow = _workflow()
    assert "npm run browser" in workflow, "no job walks the Map in a browser"
    assert "playwright install" in workflow, "the browser job installs no browser"
    assert "npm run typecheck:browser" in workflow, "no job type-checks the gate"
    # A failed walk has to leave its trace behind, or the next person debugs a
    # red job by re-running it and hoping.
    assert "upload-artifact" in workflow, "a failed browser walk keeps nothing"


def test_the_browser_gate_keeps_its_artifacts_out_of_the_repository() -> None:
    """Traces and screenshots are what one run produced, not what it asserts."""
    for entry in ("web/test-results/x", "web/playwright-report/x"):
        assert _check_ignore(entry), f"{entry} is not ignored, so a walk dirties the tree"
