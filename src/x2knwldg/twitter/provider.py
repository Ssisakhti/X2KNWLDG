"""The qualified local acquisition provider: the pinned ``x-cli`` binary (T-224).

``x-cli`` is **invoked, never imported**. It is AGPL-3.0 (D-208), so it stays a
separately installed binary reached as a subprocess: nothing is vendored, the
licence boundary is the process boundary, and the Python core keeps zero
dependencies. ADR 0007 decision 1 and the ``T-224`` row both fix that shape,
and a later legal or maintenance review is the only thing that may change it.

Five rules hold here, each of them a refusal rather than a preference:

**The binary is named, never searched for.** D-208 says the pin is
``~/.local/bin/x``, and the task row says the seam must refuse a mismatch
"rather than run whatever ``x`` it finds". So there is no ``PATH`` lookup:
:func:`resolve_binary` takes an explicit path, else ``X2KNWLDG_XCLI``, else the
pinned default, and nothing else is consulted.

**The digest is checked before the binary is executed.** :func:`verify` hashes
the file first and only then runs ``x version``. An unexpected binary at the
pinned path is therefore never run at all — the check that would have caught it
cannot be the check that runs it.

**What the capture reports is observed, then compared.** ``version_string``
comes out of the tool, not out of :data:`XCLI_PIN`, and a disagreement is a
refusal. Copying the pin into the record would make the provenance field a
restatement of our own expectation rather than evidence about the binary.

**Only two subcommands can be reached.** :data:`ALLOWED_SUBCOMMANDS` is an
allowlist, so ``x auth import`` — the one command that reads browser cookies —
is unreachable from this package by construction and not merely by omission
(ADR 0007 invariant 1). ``--no-cache`` is always passed, so a read never comes
out of the tool's own HTTP cache and every capture rests on a request that was
actually made.

**A reference is data.** ``argv`` is a list and ``shell`` is never true, so a
post id is an argument and can never be a shell fragment. :mod:`.acquire`
refuses a malformed reference offline, before this module is reached.

Exit statuses are measured, not read off the tool's documentation — the same
doctrine that produced the capture contract, and for the same reason: the
`T-222 report <../../../docs/spikes/T-222/REPORT.md>`_ §7 found the tool's own
field table wrong in four places. §6's table gave ``8`` as "timeout"; measured
here on 2026-09-04, ``8`` is the whole **transport** class, and it is returned
for an unreachable host as well:

    $ HTTPS_PROXY=http://127.0.0.1:1 x tweet <id> --tier guest --no-cache -o json
    ERROR  Cannot reach x.com: proxyconnect tcp: dial tcp 127.0.0.1:1: ...
    exit 8

That distinction is D-209's obligation and it is why :func:`_classify` reads the
message inside exit ``8``: "the tunnel is down" and "the provider changed" must
not arrive as one outcome, because a routine network drop that reads as provider
drift would discard a good capture. ``unreachable`` and ``timeout`` say nothing
about the provider; ``provider_error`` says the tool answered and we could not
use what it said.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import IO

#: The pinned artefact (D-208). Platform-specific by nature: the digest and the
#: version string are of one build, ``darwin/arm64``, which is the target
#: machine. Another platform needs its own recorded pin — a decision, taken and
#: written down, never a flag a caller can pass to make the check pass.
XCLI_TOOL = "tamnd/x-cli"
XCLI_VERSION = "0.5.0"
XCLI_VERSION_STRING = "x 0.5.0 (commit ff9aa9e, built 2026-07-29T02:41:51Z, darwin/arm64)"
XCLI_BINARY_SHA256 = "6cb6b7f9b5fdb2366f113919423e87b4ddf9d41ce10bfc65b43614bed9987c97"
XCLI_LICENCE = "AGPL-3.0"

#: Where the pin lives (D-208), outside the repository so nothing is vendored.
DEFAULT_BINARY = Path("~/.local/bin/x")

#: An operator's override, for a machine that keeps the pinned build elsewhere.
#: It moves *where* the binary is looked for; it cannot move *which* binary is
#: acceptable, because :func:`verify` still has to match the recorded digest.
BINARY_ENV_VAR = "X2KNWLDG_XCLI"

#: Reachable subcommands. ``auth`` is the reason this is an allowlist.
ALLOWED_SUBCOMMANDS = frozenset({"tweet", "version"})

DEFAULT_TIMEOUT_SEC = 30.0

#: A single post's JSON. The largest record T-222 measured was under 40 KB; a
#: megabyte is three orders of magnitude of headroom and still a bound, and an
#: over-limit response is refused rather than truncated, because a truncated
#: body is not evidence of anything.
DEFAULT_MAX_BYTES = 1_048_576


@dataclass(frozen=True)
class Tier:
    """One read tier, with the route and surface names the capture contract uses.

    ``tier`` in the contract is ``0`` or ``1`` only: Tier 2 is session cookies,
    which ADR 0007 decision 6 excludes, so a session-derived capture is
    unrepresentable rather than merely disallowed.
    """

    number: int
    flag: str
    route: str
    surface: str


#: Tier 0, the syndication surface. Qualified, and **not** the default: it
#: returned 280 characters of a real 2967-character post and 273 of 418 of a
#: Persian one, with no field announcing either loss (D-207).
TIER0 = Tier(number=0, flag="0", route="xcli_tier0", surface="syndication_tweet")

#: Tier 1, an anonymous guest token. The default read (D-207): it passed every
#: MVP cell in T-222 and is the only measured route that returns long posts whole.
GUEST = Tier(number=1, flag="guest", route="xcli_guest", surface="guest_graphql")

TIERS = {TIER0.flag: TIER0, GUEST.flag: GUEST}
DEFAULT_TIER = GUEST

#: Exit statuses whose meaning T-222 measured directly (REPORT.md §6), plus the
#: correction this module measured for ``8``. ``1`` is deliberately absent: it
#: is a refusal whose *kind* is only in the message, so :func:`_classify`
#: decides it rather than a table pretending to know.
_EXIT_OUTCOMES = {
    0: "ok",
    5: "rate_limited",
    6: "not_found",
}

#: Inside exit 8: how the tool says it ran out of time. Matched
#: case-insensitively on the tool's own wording, and it is the **only** test
#: applied there — an exit 8 whose message matches nothing is ``unreachable``,
#: the safer of the two, because it makes no claim about the provider at all.
#:
#: A companion ``_UNREACHABLE_MARKERS`` ("cannot reach", "no such host",
#: "connection refused", "network is") used to sit here and was never read by
#: anything: ``_classify`` falls straight through to ``return "unreachable"``,
#: so the behaviour was right by accident and the comment above the two tuples
#: described a matching step that did not exist. Deleted rather than wired in,
#: because wiring it in would mean deciding what an exit 8 matching *neither*
#: list is — and the answer to that is already the fallthrough.
_TIMEOUT_MARKERS = ("timed out", "timeout")

#: The offline refusal at exit 1: not a reference, and no request was sent.
_MALFORMED_MARKER = "not a tweet id or status url"

_BANNER = re.compile(r"^\s*(ERROR|WARN|WARNING|INFO)\s*$", re.IGNORECASE)


class ProviderRefusal(Exception):
    """The pinned provider is not usable, and nothing was run or written.

    Its own type because the answers differ: a missing binary is an
    installation to fix, a digest mismatch is a pin to review, and neither is a
    fact about X or about a post. :mod:`x2knwldg.cli` maps it to its own exit
    code so a wrapper can tell "install the provider" from "the run failed".
    """

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        #: ``missing`` | ``not_a_file`` | ``digest_mismatch`` | ``version_mismatch``
        #: | ``unrunnable`` | ``unsupported_subcommand``
        self.reason = reason


@dataclass(frozen=True)
class VerifiedProvider:
    """A binary that matched the pin, and the observations that prove it did."""

    binary: Path
    tool: str
    version: str
    version_string: str
    binary_sha256: str
    licence: str

    def as_capture_provider(self) -> dict[str, str]:
        """The capture contract's ``acquisition.provider`` object.

        Every value here was observed on this machine in this run — the digest
        by hashing the file, the version string by asking the binary — and only
        then checked against the pin. The pin is the expectation; this is the
        evidence.
        """
        return {
            "tool": self.tool,
            "version": self.version,
            "version_string": self.version_string,
            "binary_sha256": self.binary_sha256,
            "licence": self.licence,
        }


@dataclass(frozen=True)
class Read:
    """One request actually made, and what came back.

    A failed read is a first-class result rather than an exception: the capture
    contract records it, because "the route was tried and failed" and "the route
    was never tried" are different claims and an outage that leaves no trace is
    indistinguishable from the second.
    """

    tier: Tier
    #: The post this read was for. Carried on the result rather than recovered
    #: from ``request_shape`` later: a caller that has to parse the argv shape
    #: back into an id is one typo away from pairing bytes with the wrong post.
    post_id: str
    outcome: str
    request_shape: str
    exit_code: int | None
    latency_ms: int
    stdout: bytes
    error_text: str

    @property
    def ok(self) -> bool:
        return self.outcome == "ok"

    @property
    def is_transport_failure(self) -> bool:
        """D-209: this read says nothing about the provider.

        ``unreachable`` and ``timeout`` are the tunnel being down, or the
        network being slow. A caller must not read either as provider drift.
        """
        return self.outcome in {"unreachable", "timeout"}

    def as_route_read(self) -> dict[str, object]:
        """The capture contract's ``acquisition.routes_read`` entry."""
        entry: dict[str, object] = {
            "route": self.tier.route,
            "tier": self.tier.number,
            "surface": self.tier.surface,
            "outcome": self.outcome,
            "request_shape": self.request_shape,
            "latency_ms": self.latency_ms,
        }
        if self.exit_code is not None:
            entry["exit_code"] = self.exit_code
        if self.error_text:
            entry["error_text"] = self.error_text[:1024]
        return entry


def resolve_binary(explicit: Path | str | None = None, *, env: dict[str, str] | None = None) -> Path:
    """Where to look for the pinned binary. Three sources, in order, no ``PATH``."""
    environment = os.environ if env is None else env
    if explicit is not None:
        return Path(explicit).expanduser()
    override = environment.get(BINARY_ENV_VAR)
    if override:
        return Path(override).expanduser()
    return DEFAULT_BINARY.expanduser()


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tidy(text: str) -> str:
    """The tool's boxed error output as one line.

    ``x`` pads its messages into a box and prints them on **stderr** — measured
    with no ANSI escapes when stdout is not a terminal, but with a banner line
    and a great deal of trailing whitespace. The contract caps ``error_text`` at
    1024 characters, so the box is unwrapped rather than stored.
    """
    lines = [line.strip() for line in text.splitlines()]
    kept = [line for line in lines if line and not _BANNER.match(line)]
    return " ".join(kept).strip()


def verify(
    binary: Path | str | None = None,
    *,
    expected_sha256: str = XCLI_BINARY_SHA256,
    expected_version_string: str = XCLI_VERSION_STRING,
    tool: str = XCLI_TOOL,
    version: str = XCLI_VERSION,
    licence: str = XCLI_LICENCE,
    timeout: float = DEFAULT_TIMEOUT_SEC,
) -> VerifiedProvider:
    """Check the pin, then prove the binary runs. Raise :class:`ProviderRefusal`.

    Order matters and is the point: the digest is computed from the file on disk
    **before** anything is executed, so a binary that is not the pinned one is
    refused without being run. Only then is ``x version`` invoked, which does
    two further things — it proves the build executes on this machine (an
    architecture mismatch fails here rather than mid-acquisition), and it
    produces the version string the capture will carry as evidence.

    The keyword arguments exist so a test can pin a stub binary the same way
    this pins the real one. They do not exist so a caller can pass the digest of
    whatever it happens to have found: every one of them defaults to D-208's
    recorded value, and :mod:`x2knwldg.cli` passes none of them.
    """
    path = Path(binary) if binary is not None else resolve_binary()
    path = path.expanduser()
    if not path.exists():
        raise ProviderRefusal(
            "missing",
            f"The pinned acquisition provider is not installed at {path}. "
            f"Install {tool} {version} there, or set {BINARY_ENV_VAR} to it. "
            "No X credential, cookie or browser profile is ever used or needed.",
        )
    if not path.is_file():
        raise ProviderRefusal("not_a_file", f"The provider path is not a file: {path}")

    observed_digest = sha256_of(path)
    if observed_digest != expected_sha256:
        raise ProviderRefusal(
            "digest_mismatch",
            f"The binary at {path} is not the pinned build (D-208). "
            f"Expected SHA-256 {expected_sha256}, found {observed_digest}. "
            "Refused without being run. Re-pin deliberately if this build is the "
            "one you mean to qualify.",
        )

    try:
        # An argv list with ``shell`` left false, and a fixed subcommand: there
        # is no interpolation here for anything to be injected into.
        completed = subprocess.run(
            [str(path), "version"],
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ProviderRefusal(
            "unrunnable", f"The pinned binary at {path} could not be executed: {exc}"
        ) from exc

    observed_version = completed.stdout.decode("utf-8", "replace").strip()
    if completed.returncode != 0 or observed_version != expected_version_string:
        raise ProviderRefusal(
            "version_mismatch",
            f"The binary at {path} matched the pinned digest but reported "
            f"{observed_version!r} (exit {completed.returncode}) rather than the pinned "
            f"{expected_version_string!r}. The pin's two halves disagree; review it "
            "rather than working around it.",
        )

    return VerifiedProvider(
        binary=path,
        tool=tool,
        version=version,
        version_string=observed_version,
        binary_sha256=observed_digest,
        licence=licence,
    )


#: How often the size bound is checked while the child is still running. Short
#: enough that the cap is a cap rather than a report, long enough that an
#: ordinary read — which finishes in a second or two — is woken a handful of
#: times. ``process.wait`` returns the moment the child exits, so this is a
#: ceiling on the check interval and not a floor on the latency.
_POLL_INTERVAL_SEC = 0.05


def _await(
    process: subprocess.Popen[bytes],
    out: IO[bytes],
    *,
    timeout: float,
    max_bytes: int,
    started: float,
) -> tuple[int | None, bool, int | None]:
    """Wait for the child, enforcing both bounds **while it runs**.

    Returns ``(exit_code, timed_out, overflowed_at)``; the exit code is ``None``
    whenever the process was killed.

    The size bound used to be applied only after ``wait()`` returned, so the
    docstring's "no unbounded read" was a stronger claim than the code: a child
    streaming into the temporary file was never interrupted, and the refusal
    that says "over the limit; refused rather than truncated" arrived only once
    the whole of it was on disk. Nothing was *read* unbounded, which is what
    made the bug survive review, but the machine had already written it. So the
    file is measured on the way past and the child is killed at the boundary,
    which is what the bound is for.
    """
    deadline = started + timeout
    while True:
        try:
            return process.wait(timeout=_POLL_INTERVAL_SEC), False, None
        except subprocess.TimeoutExpired:
            pass
        size = os.fstat(out.fileno()).st_size
        if size > max_bytes:
            process.kill()
            process.wait()
            return None, False, size
        if time.monotonic() >= deadline:
            process.kill()
            process.wait()
            return None, True, None


def _classify(exit_code: int, message: str) -> str:
    """One exit status and its message, as a contract ``outcome``."""
    known = _EXIT_OUTCOMES.get(exit_code)
    if known is not None:
        return known
    lowered = message.lower()
    if exit_code == 8:
        # D-209's obligation. Exit 8 is the transport class as a whole, so the
        # message is what separates a dropped tunnel from a slow one. Neither
        # is evidence about the provider.
        if any(marker in lowered for marker in _TIMEOUT_MARKERS):
            return "timeout"
        return "unreachable"
    if exit_code == 1 and _MALFORMED_MARKER in lowered:
        return "malformed_reference"
    return "provider_error"


def read_tweet(
    provider: VerifiedProvider,
    post_id: str,
    *,
    tier: Tier = DEFAULT_TIER,
    timeout: float = DEFAULT_TIMEOUT_SEC,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> Read:
    """Read one post at one tier. Returns a :class:`Read`, success or not.

    *post_id* must already be a bare numeric id — :func:`.acquire.parse_reference`
    is what turns a user's URL into one, and it refuses anything else offline,
    before this function can be reached.
    """
    if not post_id.isdigit():
        # Defence in depth against a caller that skipped the parser. Never a
        # shell hazard — ``argv`` is a list — but an id-shaped argument is the
        # only thing this seam is allowed to send.
        raise ProviderRefusal(
            "malformed_reference", f"Not a post id: {post_id!r}. Parse the reference first."
        )
    return _invoke(
        provider,
        ["tweet", post_id, "--tier", tier.flag, "--no-cache", "-o", "json"],
        tier=tier,
        post_id=post_id,
        timeout=timeout,
        max_bytes=max_bytes,
    )


def _invoke(
    provider: VerifiedProvider,
    args: list[str],
    *,
    tier: Tier,
    post_id: str,
    timeout: float,
    max_bytes: int,
) -> Read:
    """Run one bounded subprocess. No shell, no unbounded read, no orphan.

    ``stdout`` and ``stderr`` go to temporary files rather than pipes, which is
    what makes the size bound enforceable *and* deadlock-free: a pipe large
    enough to fill its buffer would block the child while the parent waited on
    ``wait()``, and reading a pipe to find out how big it is means having
    already accepted however much arrived.
    """
    subcommand = args[0]
    if subcommand not in ALLOWED_SUBCOMMANDS:
        raise ProviderRefusal(
            "unsupported_subcommand",
            f"{subcommand!r} is not a reachable subcommand. Only {sorted(ALLOWED_SUBCOMMANDS)} "
            "are, so nothing in this package can invoke the tool's credential import.",
        )

    # The argv shape, with the binary's own path left out: where the tool is
    # installed is this machine's business, and the shape is what the capture
    # records as evidence of the request.
    request_shape = " ".join(["x", *args])
    argv = [str(provider.binary), *args]

    started = time.monotonic()
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        process = subprocess.Popen(argv, stdout=out, stderr=err)
        exit_code, timed_out, overflowed_at = _await(
            process, out, timeout=timeout, max_bytes=max_bytes, started=started
        )
        latency_ms = int((time.monotonic() - started) * 1000)

        out.seek(0)
        err.seek(0)
        stderr_text = _tidy(err.read().decode("utf-8", "replace"))
        # Checked again after the child is gone, because a process that finishes
        # inside one poll interval never gets looked at by the loop.
        size = overflowed_at if overflowed_at is not None else out.seek(0, 2)
        if size > max_bytes:
            # Refused, not truncated: half a JSON document is not evidence, and
            # a capture built from it would carry a digest of something that was
            # never a complete answer.
            return Read(
                tier=tier,
                post_id=post_id,
                outcome="provider_error",
                request_shape=request_shape,
                exit_code=exit_code,
                latency_ms=latency_ms,
                stdout=b"",
                error_text=(
                    f"output was {size} bytes, over the {max_bytes}-byte limit; "
                    "refused rather than truncated"
                ),
            )
        out.seek(0)
        stdout = out.read()

    if timed_out:
        return Read(
            tier=tier,
            post_id=post_id,
            outcome="timeout",
            request_shape=request_shape,
            exit_code=None,
            latency_ms=latency_ms,
            stdout=b"",
            error_text=f"no answer within {timeout:g}s; the process was killed",
        )

    assert exit_code is not None
    return Read(
        tier=tier,
        post_id=post_id,
        outcome=_classify(exit_code, stderr_text),
        request_shape=request_shape,
        exit_code=exit_code,
        latency_ms=latency_ms,
        stdout=stdout,
        error_text=stderr_text,
    )
