"""A stand-in for the pinned provider, so acquisition is tested offline (T-224).

The seam's whole job is to run an external binary and preserve what it returned,
which is exactly the part a unit test cannot reach for real: the live tool is
AGPL-3.0, is installed outside the repository, needs the network, and would make
every assertion here a statement about X's availability on the day CI ran.

So these tests drive a **stub binary** and pin it the way the real one is
pinned: the digest is computed from the stub on disk and handed to
:func:`x2knwldg.twitter.provider.verify`, which therefore exercises the real
verification path rather than a bypass. There is no way to skip that check —
``verify`` has no flag for it — and that is the point of testing it this way.

What it replays is **committed evidence**, not invented JSON: the ``T-222``
fixtures under ``docs/spikes/T-222/fixtures/`` and the ten-post NASA self-thread
under ``tests/fixtures/captures/raw/``, both of which are the sanitized bytes a
real acquisition returned. A capture built from them is built from the same
input the live tool produces.

The live tool is covered by the one thing a stub cannot cover, and it is covered
outside the suite: the manual verification recorded in
``docs/PROJECT_MANAGEMENT.md`` §6, run against the real binary on the target
machine.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPIKE_FIXTURES = PROJECT_ROOT / "docs" / "spikes" / "T-222" / "fixtures"
THREAD_RAW = PROJECT_ROOT / "tests" / "fixtures" / "captures" / "raw"

#: What the real binary prints for ``x version`` (D-208). The stub says the same
#: thing, because a capture must carry the string the *binary* reported and the
#: tests assert on that field.
STUB_VERSION_STRING = "x 0.5.0 (commit ff9aa9e, built 2026-07-29T02:41:51Z, darwin/arm64)"

#: x-cli's measured error output: a padded box on stderr, banner line included.
#: Reproduced so :func:`x2knwldg.twitter.provider._tidy` is tested against the
#: shape it actually meets rather than a tidy one-liner.
def boxed(message: str) -> str:
    return f"{' ' * 10}\n   ERROR  \n{' ' * 10}\n  {message}{' ' * 40}\n\n"


_STUB_SOURCE = '''#!/usr/bin/env python3
"""A recorded x-cli, driven by responses.json beside it. Never touches a network."""
import json
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
TABLE = json.loads((HERE / "responses.json").read_text(encoding="utf-8"))
ARGV = sys.argv[1:]

with (HERE / "argv.log").open("a", encoding="utf-8") as log:
    log.write(json.dumps(ARGV) + "\\n")

if ARGV[:1] == ["version"]:
    sys.stdout.write(TABLE["version_string"] + "\\n")
    raise SystemExit(TABLE.get("version_exit", 0))

if ARGV[:1] != ["tweet"]:
    sys.stderr.write("unexpected subcommand\\n")
    raise SystemExit(64)

post_id = ARGV[1] if len(ARGV) > 1 else ""
entry = TABLE["posts"].get(post_id, TABLE.get("default", {"exit": 6}))

if entry.get("sleep"):
    time.sleep(entry["sleep"])
if entry.get("stdout_file"):
    sys.stdout.write(pathlib.Path(entry["stdout_file"]).read_text(encoding="utf-8"))
if entry.get("stdout") is not None:
    sys.stdout.write(entry["stdout"])
if entry.get("stdout_filler"):
    sys.stdout.write("x" * entry["stdout_filler"])
if entry.get("stderr"):
    sys.stderr.write(entry["stderr"])
raise SystemExit(entry.get("exit", 0))
'''


def make_stub(
    directory: Path,
    *,
    posts: dict[str, dict[str, Any]] | None = None,
    default: dict[str, Any] | None = None,
    version_string: str = STUB_VERSION_STRING,
    version_exit: int = 0,
) -> Path:
    """Write an executable stub provider into *directory* and return its path.

    *posts* maps a post id to a response: ``exit``, and any of ``stdout``,
    ``stdout_file``, ``stdout_filler`` (that many bytes of filler, for the size
    bound), ``stderr`` and ``sleep`` (for the timeout).
    """
    directory.mkdir(parents=True, exist_ok=True)
    binary = directory / "x"
    binary.write_text(_STUB_SOURCE, encoding="utf-8")
    binary.chmod(binary.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    write_responses(
        binary, posts=posts or {}, default=default, version_string=version_string,
        version_exit=version_exit,
    )
    return binary


def write_responses(
    binary: Path,
    *,
    posts: dict[str, dict[str, Any]],
    default: dict[str, Any] | None = None,
    version_string: str = STUB_VERSION_STRING,
    version_exit: int = 0,
) -> None:
    """Replace the stub's response table. The stub's own bytes never change, so
    its digest stays valid across as many different recorded sessions as a test
    needs."""
    table: dict[str, Any] = {
        "version_string": version_string,
        "version_exit": version_exit,
        "posts": posts,
    }
    if default is not None:
        table["default"] = default
    (binary.parent / "responses.json").write_text(
        json.dumps(table, ensure_ascii=False), encoding="utf-8"
    )


def verified(binary: Path, **overrides: Any):
    """Verify *binary* against its own digest — the real check, not a bypass."""
    from x2knwldg.twitter.provider import sha256_of, verify

    settings: dict[str, Any] = {
        "expected_sha256": sha256_of(binary),
        "expected_version_string": STUB_VERSION_STRING,
    }
    settings.update(overrides)
    return verify(binary, **settings)


def argv_log(binary: Path) -> list[list[str]]:
    """Every argv the stub was called with, in order."""
    log = binary.parent / "argv.log"
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line]


def spike(name: str) -> str:
    """One committed ``T-222`` fixture: the exact sanitized bytes it recorded."""
    return (SPIKE_FIXTURES / f"{name}.txt").read_text(encoding="utf-8")


def spike_record(name: str) -> dict[str, Any]:
    parsed = json.loads(spike(name))
    return parsed[0] if isinstance(parsed, list) else parsed


def thread_manifest() -> list[dict[str, Any]]:
    """The ten-post NASA self-thread, root first, as committed under ``raw/``."""
    return json.loads((THREAD_RAW / "MANIFEST.json").read_text(encoding="utf-8"))


def thread_responses() -> dict[str, dict[str, Any]]:
    """That thread as a stub response table: every post readable by its id."""
    return {
        entry["post_id"]: {"exit": 0, "stdout_file": str(PROJECT_ROOT / entry["path"])}
        for entry in thread_manifest()
    }


def env_without_tunnel_statement() -> dict[str, str]:
    """A copy of the environment with the tunnel statement removed."""
    env = dict(os.environ)
    env.pop("X2KNWLDG_VIA_TUNNEL", None)
    return env
