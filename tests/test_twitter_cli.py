"""``x2knwldg capture`` at the shell: the exit code is the whole contract (T-224).

An exit code is the only thing a wrapper, a CI job or a shell check reads, and
the four failure classes this command has must not collapse into one. In
particular D-209's distinction has to survive all the way out to the process
status: a dropped tunnel (``8``) and a provider whose output moved (``9``) are
different events with different answers, and a caller that cannot tell them
apart will retry the wrong one or discard a good capture over the wrong reason.

Coverage verdicts go out through the same ``0``/``3``/``4`` the rest of the
pipeline uses, so a ``PARTIAL`` thread cannot be read as a whole one.
"""

from __future__ import annotations

import ast
import io as io_module
import json
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest
from twitter_harness import (
    STUB_VERSION_STRING,
    boxed,
    make_stub,
    spike,
    spike_record,
    thread_manifest,
    thread_responses,
)

from x2knwldg import cli
from x2knwldg.twitter import provider as provider_module

EN_POST = spike_record("single_post_en__xcli_guest")["id"]


def run(argv: list[str]) -> tuple[int, dict, list[dict]]:
    """One command. Returns its code, its stdout document, and its stderr ones."""
    out, err = io_module.StringIO(), io_module.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main(argv)
    stdout = json.loads(out.getvalue()) if out.getvalue().strip() else {}
    stderr = [json.loads(line) for line in err.getvalue().splitlines() if line.strip()]
    return code, stdout, stderr


@pytest.fixture
def pinned(monkeypatch: pytest.MonkeyPatch):
    """Install a stub provider and make ``verify`` pin *it*, digest and all.

    The verification path is the real one — see ``twitter_harness`` — but its
    defaults are D-208's recorded values, which no stub can match. So the
    command's provider lookup is redirected here rather than weakened there:
    ``verify`` keeps having no way to be told "accept whatever you find".
    """

    # Held before the patch, so a test that installs a second stub still gets
    # the real verification rather than the stand-in it just installed.
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


def test_a_capture_reports_PASS_and_where_it_put_it(
    tmp_path: Path, pinned, monkeypatch: pytest.MonkeyPatch
) -> None:
    pinned(tmp_path, posts={EN_POST: {"exit": 0, "stdout": spike("single_post_en__xcli_guest")}})
    monkeypatch.delenv("X2KNWLDG_VIA_TUNNEL", raising=False)

    code, payload, _ = run(
        ["capture", EN_POST, "--output", str(tmp_path / "output"), "--via-tunnel"]
    )

    assert code == cli.EXIT_OK
    assert payload["status"] == "PASS"
    assert payload["items"] == 1
    assert Path(payload["capture"]).is_file()


def test_a_root_anchored_thread_exits_PARTIAL_and_says_why(tmp_path: Path, pinned) -> None:
    manifest = thread_manifest()
    pinned(tmp_path, posts=thread_responses())

    code, payload, warnings = run(
        [
            "capture",
            manifest[0]["post_id"],
            "--thread",
            "--via-tunnel",
            "--output",
            str(tmp_path / "output"),
        ]
    )

    assert code == cli.EXIT_PARTIAL
    assert payload["status"] == "PARTIAL"
    assert warnings[0]["status"] == "WARNING"
    assert "LAST post" in warnings[0]["message"]


def test_an_unavailable_post_exits_FAIL(tmp_path: Path, pinned) -> None:
    pinned(tmp_path, default={"exit": 6, "stderr": boxed("Tweet not found: 999 (deleted, ...).")})

    code, payload, _ = run(
        ["capture", "999999999999999999", "--via-tunnel", "--output", str(tmp_path / "output")]
    )

    assert code == cli.EXIT_FAIL
    assert payload["status"] == "FAIL"


def test_a_missing_provider_exits_seven_without_touching_the_network(tmp_path: Path) -> None:
    code, payload, errors = run(
        [
            "capture",
            "20",
            "--via-tunnel",
            "--xcli",
            str(tmp_path / "not-installed"),
            "--output",
            str(tmp_path / "output"),
        ]
    )

    assert code == cli.EXIT_PROVIDER_UNAVAILABLE
    assert payload == {}
    assert errors[-1]["status"] == "PROVIDER_UNAVAILABLE"
    assert errors[-1]["reason"] == "missing"
    assert not (tmp_path / "output").exists()


def test_a_dropped_tunnel_exits_eight_and_a_moved_provider_exits_nine(
    tmp_path: Path, pinned
) -> None:
    """The one distinction D-209 asks the shell to be able to make."""
    pinned(tmp_path, default={"exit": 8, "stderr": boxed("Cannot reach x.com: dial tcp")})
    transport_code, _, transport_errors = run(
        ["capture", "20", "--via-tunnel", "--output", str(tmp_path / "output")]
    )

    pinned(tmp_path / "second", default={"exit": 0, "stdout": "<html>not json</html>"})
    drift_code, _, drift_errors = run(
        ["capture", "20", "--via-tunnel", "--output", str(tmp_path / "output")]
    )

    assert transport_code == cli.EXIT_PROVIDER_UNREACHABLE
    assert transport_errors[-1]["status"] == "PROVIDER_UNREACHABLE"
    assert drift_code == cli.EXIT_PROVIDER_DRIFT
    assert drift_errors[-1]["status"] == "PROVIDER_DRIFT"
    assert transport_code != drift_code


def test_a_rate_limit_exits_eight_and_names_itself(tmp_path: Path, pinned) -> None:
    """Same code as a dropped tunnel — a caller's answer to both is to wait —
    and the envelope says which, so the wait can be the right length."""
    pinned(
        tmp_path,
        default={"exit": 5, "stderr": boxed("Rate limited by X; the window resets at 20:33:34")},
    )

    code, _, errors = run(
        ["capture", "20", "--via-tunnel", "--output", str(tmp_path / "output")]
    )

    assert code == cli.EXIT_PROVIDER_UNREACHABLE
    assert errors[-1]["status"] == "PROVIDER_RATE_LIMITED"
    assert "resets at" in errors[-1]["message"]


def test_a_reference_that_is_not_one_exits_error(tmp_path: Path, pinned) -> None:
    pinned(tmp_path)

    code, _, errors = run(
        ["capture", "https://x.com/jack", "--via-tunnel", "--output", str(tmp_path / "output")]
    )

    assert code == cli.EXIT_ERROR
    assert errors[-1]["status"] == "ERROR"


def test_the_tunnel_statement_is_required_and_costs_no_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-209: stated, never inferred — and the refusal happens before the
    provider is even verified, so a refusal to guess never costs a request."""
    monkeypatch.delenv("X2KNWLDG_VIA_TUNNEL", raising=False)

    code, _, errors = run(["capture", EN_POST, "--output", str(tmp_path / "output")])

    assert code == cli.EXIT_ERROR
    assert "--via-tunnel" in errors[-1]["message"]
    assert not (tmp_path / "output").exists()


def test_the_standing_statement_in_the_environment_is_accepted(
    tmp_path: Path, pinned, monkeypatch: pytest.MonkeyPatch
) -> None:
    pinned(tmp_path, posts={EN_POST: {"exit": 0, "stdout": spike("single_post_en__xcli_guest")}})
    monkeypatch.setenv("X2KNWLDG_VIA_TUNNEL", "1")

    code, payload, _ = run(["capture", EN_POST, "--output", str(tmp_path / "output")])

    assert code == cli.EXIT_OK
    capture = json.loads(Path(payload["capture"]).read_text("utf-8"))
    assert capture["acquisition"]["network"]["via_tunnel"] is True


def test_a_session_tier_cannot_be_asked_for() -> None:
    """ADR 0007 decision 6 excludes Tier 2, and argparse is where that lands."""
    with pytest.raises(SystemExit) as caught:
        with redirect_stderr(io_module.StringIO()):
            cli.main(["capture", "20", "--tier", "2", "--via-tunnel"])
    assert caught.value.code == cli.EXIT_USAGE


def test_the_acquisition_path_needs_no_third_party_package() -> None:
    """ADR 0001 invariant 5, checked by reading the imports rather than hoping.

    The seam is ``subprocess`` and the standard library, so a bare core install
    keeps importing and running with the provider present exactly as it did
    without it. A dependency creeping in here would only show up in the
    zero-dependency CI job, and only if something imported it at module scope.
    """
    package = Path(cli.__file__).parent / "twitter"
    stdlib = {
        "__future__", "collections", "dataclasses", "datetime", "hashlib", "json",
        "os", "pathlib", "re", "subprocess", "tempfile", "time", "typing", "urllib",
    }
    for module in sorted(package.glob("*.py")):
        tree = ast.parse(module.read_text("utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] in stdlib, f"{module.name}: {alias.name}"
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                assert node.module is not None
                root = node.module.split(".")[0]
                assert root in stdlib, f"{module.name}: {node.module}"


def test_capture_then_validate_exits_PARTIAL_not_ERROR(tmp_path: Path, pinned) -> None:
    """§T1's state, graded by §T7's table, at the shell.

    ``capture`` leaves an initialized run scaffolded to ``PARTIAL``; §T7 grades
    "an unaudited run" ``3``. It exited ``1 ERROR`` with "Missing JSON file:
    …/knowledge_units.json", because ``initialize_run`` wrote two of the four
    canonical documents and ``validate_run`` reads all four. Two commands is the
    smallest sequence that shows it, and it is the sequence WORKFLOW.md prints.
    """
    pinned(tmp_path, posts={EN_POST: {"exit": 0, "stdout": spike("single_post_en__xcli_guest")}})
    output = tmp_path / "output"

    capture_code, _, _ = run(["capture", EN_POST, "--via-tunnel", "--output", str(output)])
    assert capture_code == cli.EXIT_OK

    code, payload, errors = run(["validate", str(output / EN_POST)])

    assert code == cli.EXIT_PARTIAL, errors
    assert payload["status"] == "PARTIAL"
    assert payload["capture"]["status"] == "PASS"
