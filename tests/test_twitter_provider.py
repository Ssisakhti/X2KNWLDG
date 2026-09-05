"""The provider seam: what it refuses, what it sends, and what it concludes (T-224).

Four groups, and each of them is an acceptance clause of the ``T-224`` row
rather than a coverage exercise:

* the pin is checked, and a mismatch is refused **without running the binary**;
* the reference is an argument, the subcommand is on an allowlist, and no
  credential, cookie or browser profile is read or asked for;
* a timeout and an over-sized response are bounded, deterministic and leave
  nothing behind;
* every exit status maps to one contract ``outcome``, and D-209's distinction
  between "the tunnel is down" and "the provider changed" survives the mapping.

The stub is pinned by its own digest (see ``twitter_harness``), so ``verify``
runs its real check here.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from twitter_harness import (
    STUB_VERSION_STRING,
    argv_log,
    boxed,
    make_stub,
    spike,
    verified,
    write_responses,
)

from x2knwldg.twitter import provider as provider_module
from x2knwldg.twitter.provider import (
    ALLOWED_SUBCOMMANDS,
    BINARY_ENV_VAR,
    DEFAULT_BINARY,
    GUEST,
    TIER0,
    XCLI_BINARY_SHA256,
    XCLI_VERSION_STRING,
    ProviderRefusal,
    read_tweet,
    resolve_binary,
    sha256_of,
    verify,
)

POST = "20"


# --- the pin ---------------------------------------------------------------


def test_the_recorded_pin_is_the_one_the_spike_installed() -> None:
    """D-208's two values, in code, so a drifting pin is a failing test.

    The spike's own results file is the source. If someone edits the constant
    without re-qualifying the artefact, this is what says so.
    """
    results = json.loads(
        (Path(__file__).resolve().parents[1] / "docs/spikes/T-222/results.json").read_text("utf-8")
    )
    recorded = results["provider"] if "provider" in results else results
    flat = json.dumps(recorded)
    assert XCLI_BINARY_SHA256 in flat
    assert "0.5.0" in flat


def test_the_path_is_named_and_never_searched_for(monkeypatch: pytest.MonkeyPatch) -> None:
    """No ``PATH`` lookup: D-208 says refuse a mismatch rather than run whatever
    ``x`` is found, and a ``PATH`` search is how the wrong one gets found."""
    monkeypatch.delenv(BINARY_ENV_VAR, raising=False)
    assert resolve_binary() == DEFAULT_BINARY.expanduser()
    monkeypatch.setenv(BINARY_ENV_VAR, "/opt/pinned/x")
    assert resolve_binary() == Path("/opt/pinned/x")
    assert resolve_binary("/explicit/x") == Path("/explicit/x")


def test_a_missing_provider_is_refused_by_name(tmp_path: Path) -> None:
    with pytest.raises(ProviderRefusal) as caught:
        verify(tmp_path / "absent")
    assert caught.value.reason == "missing"
    # The message has to be actionable, and has to say what it does *not* need.
    assert "credential" in str(caught.value)


def test_a_directory_at_the_pinned_path_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ProviderRefusal) as caught:
        verify(tmp_path)
    assert caught.value.reason == "not_a_file"


def test_a_digest_mismatch_is_refused_without_running_the_binary(tmp_path: Path) -> None:
    """The check that would catch an unexpected binary must not be the check
    that runs it. The stub writes a sentinel when executed; it must not exist."""
    sentinel = tmp_path / "it-ran"
    binary = tmp_path / "x"
    binary.write_text(
        "#!/usr/bin/env python3\n"
        "import pathlib\n"
        f"pathlib.Path({str(sentinel)!r}).write_text('ran')\n",
        encoding="utf-8",
    )
    binary.chmod(0o755)

    with pytest.raises(ProviderRefusal) as caught:
        verify(binary, expected_sha256="0" * 64)
    assert caught.value.reason == "digest_mismatch"
    assert not sentinel.exists(), "an unpinned binary was executed"


def test_a_version_string_the_pin_does_not_expect_is_refused(tmp_path: Path) -> None:
    binary = make_stub(tmp_path / "bin", version_string="x 0.6.0 (commit deadbee)")
    with pytest.raises(ProviderRefusal) as caught:
        verify(
            binary,
            expected_sha256=sha256_of(binary),
            expected_version_string=STUB_VERSION_STRING,
        )
    assert caught.value.reason == "version_mismatch"


def test_a_binary_that_cannot_report_its_version_is_refused(tmp_path: Path) -> None:
    binary = make_stub(tmp_path / "bin", version_exit=3)
    with pytest.raises(ProviderRefusal) as caught:
        verify(binary, expected_sha256=sha256_of(binary))
    assert caught.value.reason == "version_mismatch"


def test_the_capture_provenance_is_observed_rather_than_copied(tmp_path: Path) -> None:
    """``version_string`` and the digest come out of the machine, not out of the
    pin. Copying the pin into the record would make the provenance a restatement
    of our own expectation."""
    binary = make_stub(tmp_path / "bin")
    provider = verified(binary)
    recorded = provider.as_capture_provider()
    assert recorded["binary_sha256"] == sha256_of(binary)
    assert recorded["version_string"] == STUB_VERSION_STRING
    assert recorded["licence"] == "AGPL-3.0"
    # And the real pin is what the defaults would have demanded.
    assert XCLI_VERSION_STRING == STUB_VERSION_STRING


# --- what is sent ----------------------------------------------------------


def test_the_reference_is_an_argument_and_the_cache_is_bypassed(tmp_path: Path) -> None:
    binary = make_stub(tmp_path / "bin", posts={POST: {"exit": 0, "stdout": spike("single_post_en__xcli_guest")}})
    provider = verified(binary)

    read = read_tweet(provider, POST, tier=GUEST)

    assert read.ok
    assert read.post_id == POST
    calls = argv_log(binary)
    assert calls[0] == ["version"]
    assert calls[1] == ["tweet", POST, "--tier", "guest", "--no-cache", "-o", "json"]
    # The id is its own argv element, so it cannot be read as anything else.
    assert calls[1][1] == POST
    assert read.request_shape == "x tweet 20 --tier guest --no-cache -o json"
    # The binary's own path is this machine's business, not evidence.
    assert str(binary) not in read.request_shape


def test_tier_0_is_reachable_but_is_not_the_default(tmp_path: Path) -> None:
    binary = make_stub(tmp_path / "bin", posts={POST: {"exit": 0, "stdout": spike("single_post_en__xcli_t0")}})
    provider = verified(binary)

    assert provider_module.DEFAULT_TIER is GUEST  # D-207
    read = read_tweet(provider, POST, tier=TIER0)
    assert argv_log(binary)[1][3] == "0"
    assert read.as_route_read()["tier"] == 0
    assert read.as_route_read()["route"] == "xcli_tier0"
    assert read.as_route_read()["surface"] == "syndication_tweet"


def test_no_credential_subcommand_is_reachable(tmp_path: Path) -> None:
    """ADR 0007 invariant 1. ``x auth import`` is the tool's cookie reader, and
    an allowlist makes it unreachable by construction rather than by omission."""
    assert ALLOWED_SUBCOMMANDS == {"tweet", "version"}
    binary = make_stub(tmp_path / "bin")
    provider = verified(binary)

    with pytest.raises(ProviderRefusal) as caught:
        provider_module._invoke(
            provider, ["auth", "import"], tier=GUEST, post_id=POST, timeout=5, max_bytes=1024
        )
    assert caught.value.reason == "unsupported_subcommand"
    assert ["auth", "import"] not in argv_log(binary)


def test_an_id_that_never_went_through_the_parser_is_refused(tmp_path: Path) -> None:
    binary = make_stub(tmp_path / "bin")
    provider = verified(binary)
    with pytest.raises(ProviderRefusal) as caught:
        read_tweet(provider, "20; rm -rf /")
    assert caught.value.reason == "malformed_reference"
    assert len(argv_log(binary)) == 1, "a bad id reached the provider"


# --- the bounds ------------------------------------------------------------


def test_a_slow_provider_times_out_and_is_killed(tmp_path: Path) -> None:
    binary = make_stub(tmp_path / "bin", posts={POST: {"exit": 0, "sleep": 30}})
    provider = verified(binary)

    read = read_tweet(provider, POST, timeout=0.5)

    assert read.outcome == "timeout"
    assert read.exit_code is None
    assert read.stdout == b""
    assert read.is_transport_failure
    assert read.latency_ms < 20_000, "the wait was not bounded by the timeout"


def test_an_oversized_response_is_refused_rather_than_truncated(tmp_path: Path) -> None:
    binary = make_stub(tmp_path / "bin", posts={POST: {"exit": 0, "stdout_filler": 5000}})
    provider = verified(binary)

    read = read_tweet(provider, POST, max_bytes=1000)

    assert read.outcome == "provider_error"
    assert read.stdout == b"", "a truncated body was kept"
    assert "over the 1000-byte limit" in read.error_text


# --- what it concludes -----------------------------------------------------


@pytest.mark.parametrize(
    ("exit_code", "message", "expected"),
    [
        (0, "", "ok"),
        (5, "Rate limited by X on graphql.UserTweets; the window resets at 20:33:34", "rate_limited"),
        (6, "Tweet not found: 999 (deleted, suspended, or protected).", "not_found"),
        (1, 'Not a tweet id or status URL: "not-a-ref".', "malformed_reference"),
        (1, "something else entirely", "provider_error"),
        # D-209, and the correction to REPORT.md section 6's table: exit 8 is the
        # whole transport class, so the message is what separates its two cases.
        (8, "The request timed out: raise --timeout", "timeout"),
        (8, "Cannot reach x.com: proxyconnect tcp: dial tcp 127.0.0.1:1: connect: refused", "unreachable"),
        (8, "no such host", "unreachable"),
        (8, "a transport failure with wording we have not seen", "unreachable"),
        (7, "an exit this tool has never returned", "provider_error"),
    ],
)
def test_every_exit_status_maps_to_one_outcome(
    tmp_path: Path, exit_code: int, message: str, expected: str
) -> None:
    binary = make_stub(
        tmp_path / "bin",
        posts={POST: {"exit": exit_code, "stderr": boxed(message) if message else ""}},
    )
    provider = verified(binary)

    read = read_tweet(provider, POST)

    assert read.outcome == expected
    assert read.exit_code == exit_code
    if message:
        # The tool's padded box, unwrapped: the contract caps error_text at 1024.
        assert read.error_text == message
        assert "ERROR" not in read.error_text


def test_a_transport_failure_says_nothing_about_the_provider(tmp_path: Path) -> None:
    """The property D-209 asks for, stated as a property rather than a message."""
    binary = make_stub(tmp_path / "bin", posts={POST: {"exit": 8, "stderr": boxed("Cannot reach x.com")}})
    provider = verified(binary)

    read = read_tweet(provider, POST)

    assert read.is_transport_failure
    assert read.outcome != "provider_error"


def test_a_failed_read_is_still_recorded_as_a_route_read(tmp_path: Path) -> None:
    """A route tried and failed, and a route never tried, are different claims."""
    binary = make_stub(tmp_path / "bin", posts={POST: {"exit": 6, "stderr": boxed("Tweet not found: 20")}})
    provider = verified(binary)

    entry = read_tweet(provider, POST).as_route_read()

    assert entry["outcome"] == "not_found"
    assert entry["exit_code"] == 6
    assert entry["route"] == "xcli_guest"
    assert "Tweet not found" in str(entry["error_text"])


def test_the_response_table_can_change_without_repinning(tmp_path: Path) -> None:
    """A guard on the harness itself: the stub's bytes are the pinned thing, so a
    test that changes what it answers must not change what it is."""
    binary = make_stub(tmp_path / "bin", posts={POST: {"exit": 0, "stdout": "[]"}})
    before = sha256_of(binary)
    write_responses(binary, posts={POST: {"exit": 6}})
    assert sha256_of(binary) == before


def test_the_size_bound_is_applied_while_the_child_is_still_writing(
    tmp_path: Path,
) -> None:
    """"No unbounded read" was a stronger claim than the code made.

    ``max_bytes`` was measured only after ``wait()`` returned, so a provider
    streaming into the temporary file was never interrupted: nothing was *read*
    unbounded, which is what let the defect survive, but the whole of it had
    already been written to disk before the refusal was decided. The stub here
    would take about ten seconds to produce eight megabytes; a bound applied on
    the way past kills it in a fraction of that.
    """
    binary = make_stub(
        tmp_path / "bin",
        posts={POST: {"exit": 0, "stream": {"chunk": 4096, "iterations": 2000, "delay": 0.005}}},
    )
    provider = verified(binary)

    read = read_tweet(provider, POST, max_bytes=1000, timeout=30)

    assert read.outcome == "provider_error"
    assert read.stdout == b""
    assert "over the 1000-byte limit" in read.error_text
    # Killed, not awaited: the child never reported an exit status of its own.
    assert read.exit_code is None
    assert read.latency_ms < 3_000, (
        f"the child ran for {read.latency_ms}ms; the bound was applied after it finished"
    )


def test_a_response_inside_the_bound_still_arrives_whole(tmp_path: Path) -> None:
    """The bound is a bound, not a truncation — and not a new failure mode.

    A response that finishes inside one poll interval is never looked at by the
    waiting loop, so the size check after the child exits is still the one that
    decides for the ordinary case.
    """
    binary = make_stub(tmp_path / "bin", posts={POST: {"exit": 0, "stdout": spike(
        "single_post_en__xcli_guest"
    )}})

    read = read_tweet(verified(binary), POST, max_bytes=1_048_576)

    assert read.outcome == "ok"
    assert read.exit_code == 0
    assert json.loads(read.stdout)[0]["id"] == POST
