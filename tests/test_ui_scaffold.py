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
            found.append((module, specifier, _resolve_specifier(module, specifier)))
    return found


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
