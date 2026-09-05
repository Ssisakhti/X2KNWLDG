"""Acquisition end to end, offline: reference in, capture and evidence out (T-224).

Every capture built here is validated against ``schemas/capture/v1/`` and then
against the cross-field claims JSON Schema cannot express — the same set
``test_twitter_capture.py`` asserts per committed fixture, applied to a document
the seam just produced. A capture that validates is not the claim being tested;
a capture that cannot lie is.

The inputs are committed evidence replayed through a pinned stub (see
``twitter_harness``): the ``T-222`` fixtures, and the real ten-post NASA
self-thread under ``tests/fixtures/captures/raw/``.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from twitter_harness import (
    boxed,
    make_stub,
    spike,
    spike_record,
    thread_manifest,
    thread_responses,
    verified,
)

from x2knwldg.twitter.acquire import (
    AcquisitionError,
    ProviderDrift,
    RateLimited,
    TransientFailure,
    TransportFailure,
    acquire,
    parse_reference,
)
from x2knwldg.twitter.evidence import CredentialLeak, EvidenceConflict, prepare
from x2knwldg.twitter.provider import TIER0

jsonschema = pytest.importorskip(
    "jsonschema",
    reason="jsonschema is a dev-extra dependency; the core package stays zero-dependency",
)
from jsonschema import Draft202012Validator  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads(
    (ROOT / "schemas/capture/v1/twitter_capture.schema.json").read_text("utf-8")
)
VALIDATOR = Draft202012Validator(SCHEMA)

EN_POST = spike_record("single_post_en__xcli_guest")["id"]
FA_POST = spike_record("single_post_fa__xcli_guest")["id"]


def check(capture: dict[str, Any], *, base: Path) -> None:
    """Schema, then the invariants the schema cannot state.

    Kept in one function because a capture is only honest if *all* of it holds:
    a schema-valid document that claims ``PASS`` beside an omitted item is
    exactly the lie the contract was shaped to prevent.
    """
    VALIDATOR.validate(capture)

    coverage = capture["coverage"]
    included = coverage["included_post_ids"]
    assert len(set(included)) == len(included)
    if coverage["status"] == "PASS":
        assert not coverage["omitted_items"]
        assert len(included) == coverage["expected_item_count"]
        assert {item["post_id"] for item in capture["items"]} == set(included)
    else:
        assert coverage["omitted_items"]
        for entry in coverage["omitted_items"]:
            assert entry.get("post_id") or entry.get("descriptor")

    assert capture["completeness"]["downward"]["status"] in {"unprovable", "not_applicable"}
    if capture["anchor"]["role"] == "thread_terminal":
        assert capture["anchor"]["terminal_claim"] == "user_asserted"
    else:
        assert capture["anchor"]["terminal_claim"] == "none"

    items = capture["items"]
    if capture["order"]["basis"] == "parent_links" and len(items) >= 2:
        upward = capture["completeness"]["upward"]
        if upward["status"] == "complete":
            assert "parent_post_id" not in items[0]
        else:
            # An honestly truncated chain does not begin at a root, and its
            # dangling end has to be the id upward completeness names.
            assert items[0].get("parent_post_id") == upward.get("unresolved_at")
        for earlier, later in zip(items[:-1], items[1:], strict=True):
            assert later.get("parent_post_id") == earlier["post_id"]

    for item in items:
        if item["availability"]["state"] == "unavailable":
            for invented in ("author", "created_at", "text", "media", "metrics"):
                assert invented not in item
            assert item["availability"]["reason"] == "not_determinable_at_this_tier"
        else:
            text = item["text"]["canonical"]
            for entity in item["text"].get("entities", []):
                span = text[entity["start_char"] : entity["end_char"]]
                expected = entity.get("shortened") or (
                    f"@{entity['handle']}" if entity.get("handle") else None
                )
                if expected is not None:
                    assert span == expected

    assert {read["tier"] for read in capture["acquisition"]["routes_read"]} <= {0, 1}

    for entry in capture["raw_evidence"]:
        preserved = base / entry["path"]
        assert preserved.is_file(), entry["path"]
        digest = hashlib.sha256(preserved.read_bytes()).hexdigest()
        assert digest == entry["sha256_sanitized"]
        if not entry["sanitization_removed"]:
            assert entry["sha256_raw"] == entry["sha256_sanitized"]


def single_stub(tmp_path: Path, fixture: str, post_id: str) -> Any:
    binary = make_stub(
        tmp_path / "bin", posts={post_id: {"exit": 0, "stdout": spike(fixture)}}
    )
    return verified(binary)


# --- the reference ---------------------------------------------------------


@pytest.mark.parametrize(
    ("reference", "expected"),
    [
        ("20", "20"),
        ("https://x.com/jack/status/20", "20"),
        ("http://twitter.com/jack/status/20", "20"),
        ("https://mobile.twitter.com/jack/status/20?s=20&t=abc", "20"),
        ("https://x.com/NASA/status/2094007256576565379/photo/1", "2094007256576565379"),
        ("x.com/jack/status/20", "20"),
        ("https://x.com/i/status/20", "20"),
        ("  https://x.com/jack/statuses/20  ", "20"),
    ],
)
def test_a_reference_is_parsed_offline(reference: str, expected: str) -> None:
    assert parse_reference(reference) == expected


@pytest.mark.parametrize(
    "reference",
    [
        "",
        "20; rm -rf /",
        "$(id)",
        "not-a-ref",
        "https://x.com/jack",
        "https://x.com.evil.example/jack/status/20",
        "https://youtube.com/watch?v=dQw4w9WgXcQ",
        "file:///etc/passwd",
        "9" * 26,
        "https://x.com/jack/status/twenty",
    ],
)
def test_a_reference_that_is_not_one_is_refused_rather_than_repaired(reference: str) -> None:
    with pytest.raises(AcquisitionError):
        parse_reference(reference)


# --- one post --------------------------------------------------------------


def test_a_single_post_becomes_a_capture_with_its_evidence(tmp_path: Path) -> None:
    provider = single_stub(tmp_path, "single_post_en__xcli_guest", EN_POST)
    output = tmp_path / "output"

    result = acquire(
        f"https://x.com/jack/status/{EN_POST}",
        provider=provider,
        output_root=output,
        via_tunnel=True,
        tunnel_note="always-on tunnel; named Phase 2.2 dependency (D-209)",
        requested_at="2026-09-04T09:00:00Z",
    )

    check(result.capture, base=tmp_path)
    assert result.coverage_status == "PASS"
    assert result.capture["anchor"] == {
        "post_id": EN_POST,
        "role": "single_post",
        "terminal_claim": "none",
    }
    assert result.capture["items"][0]["text"]["form"] == "authored"
    # One route only, so text completeness is never claimed (T-225's work).
    assert result.capture["items"][0]["text"]["completeness"]["status"] == "unverified"
    assert result.capture["acquisition"]["network"] == {
        "via_tunnel": True,
        "note": "always-on tunnel; named Phase 2.2 dependency (D-209)",
    }
    assert (output / EN_POST / "capture.json").is_file()
    assert (output / EN_POST / f"raw/xcli_guest_{EN_POST}.json").is_file()
    # Invisible to the library until a later task gives it a metadata.json.
    assert not (output / EN_POST / "metadata.json").exists()


def test_a_persian_post_keeps_its_authored_text_exactly(tmp_path: Path) -> None:
    """The corpus this project exists for. The canonical text is the authored
    form (D-211), byte for byte what the evidence holds."""
    provider = single_stub(tmp_path, "single_post_fa__xcli_guest", FA_POST)

    result = acquire(
        FA_POST,
        provider=provider,
        output_root=tmp_path / "output",
        via_tunnel=True,
    )

    check(result.capture, base=tmp_path)
    expected = spike_record("single_post_fa__xcli_guest")["text"]
    assert result.capture["items"][0]["text"]["canonical"] == expected
    assert "‌" in expected, "the fixture no longer carries a ZWNJ to preserve"


def test_a_quote_is_a_separate_cited_source_not_embedded_content(tmp_path: Path) -> None:
    post = spike_record("quote_post__xcli_guest")
    provider = single_stub(tmp_path, "quote_post__xcli_guest", post["id"])

    result = acquire(
        post["id"], provider=provider, output_root=tmp_path / "output", via_tunnel=True
    )

    check(result.capture, base=tmp_path)
    quote = result.capture["items"][0]["quote"]
    assert quote["quoted_post_id"] == post["quoted"]["id"]
    assert "text" not in quote


def test_media_alt_text_survives_and_an_absent_field_stays_absent(tmp_path: Path) -> None:
    post = spike_record("photo_with_alt__xcli_guest")
    provider = single_stub(tmp_path, "photo_with_alt__xcli_guest", post["id"])

    result = acquire(
        post["id"], provider=provider, output_root=tmp_path / "output", via_tunnel=True
    )

    check(result.capture, base=tmp_path)
    item = result.capture["items"][0]
    assert item["media"][0]["alt_text"]
    # `[]` and `{}` would claim absence was observed; nothing here does.
    for absent in ("poll", "edits", "article", "metrics"):
        assert absent not in item


def test_a_tier_0_read_says_which_surface_filled_it_and_does_not_claim_whole_text(
    tmp_path: Path,
) -> None:
    """D-207. Tier 0 remains reachable, and a capture taken there is marked."""
    provider = single_stub(tmp_path, "long_note_post_xl__xcli_t0", "1")
    record = spike_record("long_note_post_xl__xcli_t0")
    provider = single_stub(tmp_path, "long_note_post_xl__xcli_t0", record["id"])

    result = acquire(
        record["id"],
        provider=provider,
        output_root=tmp_path / "output",
        via_tunnel=True,
        tier=TIER0,
    )

    check(result.capture, base=tmp_path)
    text = result.capture["items"][0]["text"]
    assert text["supplied_by"] == {"route": "xcli_tier0", "tier": 0, "surface": "syndication_tweet"}
    assert text["completeness"]["status"] == "unverified"
    assert "truncat" in text["completeness"]["note"]


def test_a_post_that_replies_to_another_is_not_called_a_standalone_post(
    tmp_path: Path,
) -> None:
    manifest = thread_manifest()
    reply = manifest[1]
    binary = make_stub(tmp_path / "bin", posts=thread_responses())
    provider = verified(binary)

    result = acquire(
        reply["post_id"], provider=provider, output_root=tmp_path / "output", via_tunnel=True
    )

    check(result.capture, base=tmp_path)
    assert result.capture["anchor"]["role"] == "thread_middle"
    assert any("--thread" in warning for warning in result.warnings)


# --- a thread --------------------------------------------------------------


def test_a_self_thread_anchored_at_its_last_post_is_complete_to_root(
    tmp_path: Path,
) -> None:
    """The measured half of the MVP (D-206): upward is provable, and only upward."""
    manifest = thread_manifest()
    binary = make_stub(tmp_path / "bin", posts=thread_responses())
    provider = verified(binary)

    result = acquire(
        manifest[-1]["post_id"],
        provider=provider,
        output_root=tmp_path / "output",
        via_tunnel=True,
        thread=True,
    )

    check(result.capture, base=tmp_path)
    assert result.coverage_status == "PASS"
    assert [item["post_id"] for item in result.capture["items"]] == [
        entry["post_id"] for entry in manifest
    ]
    assert result.capture["anchor"]["role"] == "thread_terminal"
    assert result.capture["completeness"]["upward"] == {
        "status": "complete",
        "basis": "root_reached",
        "single_author": True,
    }
    assert result.capture["completeness"]["downward"]["status"] == "unprovable"
    assert result.capture["order"]["basis"] == "parent_links"
    assert len(result.evidence_paths) == len(manifest)
    assert len(result.capture["acquisition"]["routes_read"]) == len(manifest)


def test_an_anchor_that_is_a_root_is_partial_and_asks_for_the_last_post(
    tmp_path: Path,
) -> None:
    """D-206's other branch: a root anchor is accepted, reported ``PARTIAL``, and
    the caller is told what to do about it. Descendants have no id to name, so
    the omission carries a descriptor instead."""
    manifest = thread_manifest()
    binary = make_stub(tmp_path / "bin", posts=thread_responses())
    provider = verified(binary)

    result = acquire(
        manifest[0]["post_id"],
        provider=provider,
        output_root=tmp_path / "output",
        via_tunnel=True,
        thread=True,
    )

    check(result.capture, base=tmp_path)
    assert result.coverage_status == "PARTIAL"
    assert result.capture["anchor"]["role"] == "thread_root"
    assert result.capture["coverage"]["omitted_items"][0]["descriptor"] == (
        "descendants of the anchor"
    )
    assert any("LAST post" in warning for warning in result.warnings)


def test_a_broken_chain_names_the_id_it_broke_at(tmp_path: Path) -> None:
    manifest = thread_manifest()
    responses = thread_responses()
    # The third post's parent is unavailable: deleted, protected or suspended,
    # and below Tier 2 those are one message.
    del responses[manifest[1]["post_id"]]
    binary = make_stub(
        tmp_path / "bin",
        posts=responses,
        default={
            "exit": 6,
            "stderr": boxed(
                f"Tweet not found: {manifest[1]['post_id']} (deleted, suspended, or protected)."
            ),
        },
    )
    provider = verified(binary)

    result = acquire(
        manifest[-1]["post_id"],
        provider=provider,
        output_root=tmp_path / "output",
        via_tunnel=True,
        thread=True,
    )

    check(result.capture, base=tmp_path)
    assert result.coverage_status == "PARTIAL"
    upward = result.capture["completeness"]["upward"]
    assert upward["status"] == "incomplete"
    assert upward["basis"] == "unresolved_hop"
    assert upward["unresolved_at"] == manifest[1]["post_id"]
    assert result.capture["items"][0]["post_id"] == manifest[2]["post_id"]


def test_a_parent_by_another_author_ends_the_self_thread_and_is_named(
    tmp_path: Path,
) -> None:
    """ADR 0007 keeps third-party replies out of the MVP. The boundary is
    recorded as an omission rather than trimmed away in silence."""
    manifest = thread_manifest()
    responses = thread_responses()
    root_id = manifest[0]["post_id"]
    stranger = json.loads(Path(ROOT / manifest[0]["path"]).read_text("utf-8"))
    stranger[0]["author"] = dict(stranger[0]["author"], username="stranger", rest_id="99")
    responses[root_id] = {"exit": 0, "stdout": json.dumps(stranger, ensure_ascii=False)}
    binary = make_stub(tmp_path / "bin", posts=responses)
    provider = verified(binary)

    result = acquire(
        manifest[-1]["post_id"],
        provider=provider,
        output_root=tmp_path / "output",
        via_tunnel=True,
        thread=True,
    )

    check(result.capture, base=tmp_path)
    assert result.coverage_status == "PARTIAL"
    assert result.capture["completeness"]["upward"]["unresolved_at"] == root_id
    assert result.capture["completeness"]["upward"]["single_author"] is True
    reason = result.capture["coverage"]["omitted_items"][0]["reason"]
    assert "another author" in reason
    assert root_id not in {item["post_id"] for item in result.capture["items"]}


# --- what must not happen --------------------------------------------------


def test_a_parent_chain_that_loops_is_refused_rather_than_walked(tmp_path: Path) -> None:
    """X cannot produce a cycle; a provider whose output moved could, and
    following one would loop to the hop bound with a duplicate item set."""
    manifest = thread_manifest()
    responses = thread_responses()
    root_id, last_id = manifest[0]["post_id"], manifest[-1]["post_id"]
    looping = json.loads(Path(ROOT / manifest[0]["path"]).read_text("utf-8"))
    looping[0]["reply_to"] = last_id
    responses[root_id] = {"exit": 0, "stdout": json.dumps(looping, ensure_ascii=False)}
    binary = make_stub(tmp_path / "bin", posts=responses)
    provider = verified(binary)
    output = tmp_path / "output"

    with pytest.raises(ProviderDrift) as caught:
        acquire(last_id, provider=provider, output_root=output, via_tunnel=True, thread=True)

    assert "cycle" in str(caught.value)
    assert not list(output.rglob("*.json"))


def test_a_parent_pointer_that_is_not_an_id_is_drift_not_a_bad_reference(
    tmp_path: Path,
) -> None:
    """Nothing the user typed reached that value, so it is the provider's fault
    and must not be reported as if they had mistyped a URL."""
    manifest = thread_manifest()
    responses = thread_responses()
    anchor = json.loads(Path(ROOT / manifest[-1]["path"]).read_text("utf-8"))
    anchor[0]["reply_to"] = "../../etc/passwd"
    responses[manifest[-1]["post_id"]] = {
        "exit": 0,
        "stdout": json.dumps(anchor, ensure_ascii=False),
    }
    binary = make_stub(tmp_path / "bin", posts=responses)
    provider = verified(binary)

    with pytest.raises(ProviderDrift) as caught:
        acquire(
            manifest[-1]["post_id"],
            provider=provider,
            output_root=tmp_path / "output",
            via_tunnel=True,
            thread=True,
        )

    assert "not a post id" in str(caught.value)


def test_an_unavailable_anchor_is_a_FAIL_that_invents_nothing(tmp_path: Path) -> None:
    message = "Tweet not found: 999999999999999999 (deleted, suspended, or protected)."
    binary = make_stub(tmp_path / "bin", default={"exit": 6, "stderr": boxed(message)})
    provider = verified(binary)

    result = acquire(
        "999999999999999999",
        provider=provider,
        output_root=tmp_path / "output",
        via_tunnel=True,
    )

    check(result.capture, base=tmp_path)
    assert result.coverage_status == "FAIL"
    assert result.capture["items"][0]["availability"]["state"] == "unavailable"
    assert result.capture["coverage"]["included_post_ids"] == []
    # "We looked and it is not there" is a finding, and a finding cites bytes:
    # the contract requires evidence, so the tool's own message is preserved.
    assert len(result.capture["raw_evidence"]) == 1
    preserved = tmp_path / result.capture["raw_evidence"][0]["path"]
    assert preserved.read_text("utf-8") == message
    # And it does not guess which of the three reasons it was.
    for reason in ("deleted", "suspended", "protected"):
        assert result.capture["items"][0]["availability"]["reason"] != reason


def test_an_unavailability_with_no_message_leaves_nothing_to_cite(tmp_path: Path) -> None:
    """A finding with no preserved bytes would be an assertion, so it is refused.

    The real tool always names what it could not find (T-222 REPORT.md section 6),
    so this is the shape of a provider that stopped doing so — drift, reported as
    drift, rather than a FAIL resting on nothing.
    """
    binary = make_stub(tmp_path / "bin", default={"exit": 6})
    provider = verified(binary)
    output = tmp_path / "output"

    with pytest.raises(ProviderDrift) as caught:
        acquire("999999999999999999", provider=provider, output_root=output, via_tunnel=True)

    assert "nothing to preserve" in str(caught.value)
    assert not list(output.rglob("*"))


def test_a_transport_failure_writes_nothing_at_all(tmp_path: Path) -> None:
    """D-209. A dropped tunnel must not become a PARTIAL that looks exactly like
    a thread which ends there."""
    binary = make_stub(
        tmp_path / "bin", default={"exit": 8, "stderr": "Cannot reach x.com: dial tcp"}
    )
    provider = verified(binary)
    output = tmp_path / "output"

    with pytest.raises(TransportFailure) as caught:
        acquire("20", provider=provider, output_root=output, via_tunnel=True)

    assert "tunnel" in str(caught.value)
    assert not list(output.rglob("*.json"))


def test_a_transport_failure_part_way_up_a_thread_writes_nothing(tmp_path: Path) -> None:
    manifest = thread_manifest()
    responses = thread_responses()
    responses[manifest[4]["post_id"]] = {"exit": 8, "stderr": "Cannot reach x.com"}
    binary = make_stub(tmp_path / "bin", posts=responses)
    provider = verified(binary)
    output = tmp_path / "output"

    with pytest.raises(TransportFailure):
        acquire(
            manifest[-1]["post_id"],
            provider=provider,
            output_root=output,
            via_tunnel=True,
            thread=True,
        )

    assert not list(output.rglob("*.json")), "five good reads were preserved as a partial thread"


@pytest.mark.parametrize(
    ("response", "fragment"),
    [
        ({"exit": 0, "stdout": "not json at all"}, "not JSON"),
        ({"exit": 0, "stdout": "[]"}, "no record"),
        ({"exit": 0, "stdout": '[{"kind":"user","id":"12"}]'}, "'user' record"),
        ({"exit": 0, "stdout": '[{"kind":"tweet","id":"x"}]'}, "no usable post id"),
        ({"exit": 0, "stdout": '[{"kind":"tweet","id":"20","author":{}}]'}, "author.username"),
    ],
)
def test_a_provider_that_answers_unusably_is_drift_and_writes_nothing(
    tmp_path: Path, response: dict[str, Any], fragment: str
) -> None:
    """Told apart from a transport failure, which is the point of D-209: one is
    the network, the other is the tool this seam pins in order to notice."""
    binary = make_stub(tmp_path / "bin", posts={"20": response})
    provider = verified(binary)
    output = tmp_path / "output"

    with pytest.raises(ProviderDrift) as caught:
        acquire("20", provider=provider, output_root=output, via_tunnel=True)

    assert fragment in str(caught.value)
    assert not list(output.rglob("*.json"))


def test_a_rate_limit_is_transient_and_is_not_blamed_on_the_provider(
    tmp_path: Path,
) -> None:
    """Exit 5 is X's budget, not the tool's output. Reporting it as drift would
    blame a pinned binary for a window that has not reset yet."""
    message = "Rate limited by X on graphql.TweetResultByRestId; the window resets at 20:33:34"
    binary = make_stub(tmp_path / "bin", default={"exit": 5, "stderr": boxed(message)})
    provider = verified(binary)
    output = tmp_path / "output"

    with pytest.raises(RateLimited) as caught:
        acquire("20", provider=provider, output_root=output, via_tunnel=True)

    assert isinstance(caught.value, TransientFailure)
    assert not isinstance(caught.value, ProviderDrift)
    assert "the window resets at 20:33:34" in str(caught.value)
    assert not list(output.rglob("*"))


def test_a_transport_failure_is_transient_too(tmp_path: Path) -> None:
    """Both wear the same label, because a caller's answer to both is to retry."""
    binary = make_stub(tmp_path / "bin", default={"exit": 8, "stderr": boxed("Cannot reach x.com")})
    provider = verified(binary)

    with pytest.raises(TransientFailure):
        acquire("20", provider=provider, output_root=tmp_path / "output", via_tunnel=True)


def test_a_second_acquisition_refuses_rather_than_overwriting(tmp_path: Path) -> None:
    provider = single_stub(tmp_path, "single_post_en__xcli_guest", EN_POST)
    output = tmp_path / "output"

    first = acquire(EN_POST, provider=provider, output_root=output, via_tunnel=True)
    before = first.capture_path.read_bytes()

    with pytest.raises(AcquisitionError) as caught:
        acquire(EN_POST, provider=provider, output_root=output, via_tunnel=True)

    assert "immutable" in str(caught.value)
    assert first.capture_path.read_bytes() == before


def test_evidence_that_differs_from_what_is_already_preserved_is_refused(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "output" / "20" / "raw" / "xcli_guest_20.json"
    destination.parent.mkdir(parents=True)
    destination.write_text('[{"kind":"tweet","id":"20"}]', encoding="utf-8")

    with pytest.raises(EvidenceConflict):
        prepare(
            raw=b'[{"kind":"tweet","id":"20","text":"different"}]',
            destination=destination,
            relative_to=tmp_path,
            route="xcli_guest",
        )


def test_a_credential_that_survives_redaction_stops_everything(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The spike's near-miss, made a rule: a redactor is not evidence that
    redaction worked, so the scan runs afterwards and is a hard stop."""
    import x2knwldg.twitter.evidence as evidence_module

    # Redaction is defeated, and the scan alone has to catch it. Emptying the
    # pattern list would disable both halves and prove nothing, which is how a
    # test of this shape gets written wrong.
    monkeypatch.setattr(evidence_module, "sanitize", lambda text: (text, []))
    with pytest.raises(CredentialLeak):
        prepare(
            raw=b'{"guest_token":"1234567890123456789"}',
            destination=tmp_path / "raw.json",
            relative_to=tmp_path,
            route="xcli_guest",
        )


def test_no_capture_carries_credential_material(tmp_path: Path) -> None:
    provider = single_stub(tmp_path, "long_note_post__xcli_t0", spike_record("long_note_post__xcli_t0")["id"])

    result = acquire(
        spike_record("long_note_post__xcli_t0")["id"],
        provider=provider,
        output_root=tmp_path / "output",
        via_tunnel=True,
        tier=TIER0,
    )

    text = result.capture_path.read_text("utf-8")
    for pattern in ("auth_token=", "ct0=", '"guest_token"', "Bearer "):
        assert pattern not in text
    for preserved in result.evidence_paths:
        body = preserved.read_text("utf-8")
        assert '"guest_token"' not in body
        assert "token=" not in body or "token=<STRIPPED>" in body


def test_the_tunnel_statement_is_recorded_as_given(tmp_path: Path) -> None:
    """It is the operator's statement, not an inference, so both answers are
    representable and neither is a default (D-209)."""
    provider = single_stub(tmp_path, "single_post_en__xcli_guest", EN_POST)

    result = acquire(
        EN_POST, provider=provider, output_root=tmp_path / "output", via_tunnel=False
    )

    assert result.capture["acquisition"]["network"] == {"via_tunnel": False}


# ---------------------------------------------------------------------------
# Defects found by execution, and the behaviour that replaced them
# ---------------------------------------------------------------------------


def _record_saying(text: str) -> str:
    """The committed English record with its authored text replaced.

    A real recording with one field changed, so what is being tested is the
    *text*, not a hand-built record that might differ from x-cli's shape in some
    other way at the same time.
    """
    record = spike_record("single_post_en__xcli_guest")
    record["text"] = text
    return json.dumps([record], ensure_ascii=False)


@pytest.mark.parametrize(
    "authored",
    [
        # The measured Persian case: a sentence *about* a cookie, carrying none.
        "برای احراز هویت، کوکی ct0=abc123def در هدر می‌رود.",
        "Send it as Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9 and it works.",
        "Try https://syndication.twimg.com/tweet-result?id=20&token=abcd1234",
    ],
    ids=("cookie-name", "bearer-shape", "syndication-token"),
)
def test_a_post_whose_own_text_would_be_redacted_is_refused(
    tmp_path: Path, authored: str
) -> None:
    """The run that could never validate, refused before it exists.

    ``acquire`` parses ``items[].text.canonical`` out of the **unsanitized**
    stdout and preserves the **sanitized** bytes, so a post whose authored text
    matches a credential pattern used to capture ``PASS`` and then fail every
    subsequent ``validate`` with ``item_disagrees_with_preserved_response`` —
    which WORKFLOW.md §T7 reads as tampered evidence and answers with
    "re-acquire", which produced the identical run again. There is no repair, so
    the read is refused with nothing written and the operator is told why.
    """
    binary = make_stub(
        tmp_path / "bin", posts={EN_POST: {"exit": 0, "stdout": _record_saying(authored)}}
    )
    output = tmp_path / "output"

    with pytest.raises(AcquisitionError) as caught:
        acquire(EN_POST, provider=verified(binary), output_root=output, via_tunnel=True)

    assert EN_POST in str(caught.value)
    assert "cannot be both preserved" in str(caught.value)
    # Nothing written: not the capture, not the evidence, not the directory.
    assert not (output / EN_POST / "capture.json").exists()
    assert not (output / EN_POST / "raw").exists()


def test_the_refusal_is_about_authored_text_and_not_about_the_envelope(
    tmp_path: Path,
) -> None:
    """A guest token *around* the post is redacted as it always was.

    The refusal has to be narrow or it refuses the ordinary case: the same
    patterns match provider envelope fields all the time, and those are exactly
    what redaction is for. Only a hit inside a ``text`` a person wrote is a
    refusal.
    """
    record = spike_record("single_post_en__xcli_guest")
    record["guest_token"] = "1234567890123456789"
    binary = make_stub(
        tmp_path / "bin",
        posts={EN_POST: {"exit": 0, "stdout": json.dumps([record], ensure_ascii=False)}},
    )

    result = acquire(
        EN_POST, provider=verified(binary), output_root=tmp_path / "output", via_tunnel=True
    )

    entry = result.capture["raw_evidence"][0]
    assert entry["sanitization_removed"], "the envelope token should have been redacted"
    assert entry["sha256_raw"] != entry["sha256_sanitized"]
    # And the item is still the post, byte for byte.
    assert result.capture["items"][0]["text"]["canonical"] == record["text"]


def test_the_capture_and_the_preserved_bytes_can_never_disagree(tmp_path: Path) -> None:
    """The invariant the refusal exists to hold, stated over what reached disk.

    Every available item's canonical text must appear verbatim in the file the
    capture cites for it. That is what ``extract._rederivation_errors`` re-checks
    at every ``validate``, and it is what redaction inside authored text broke.
    """
    provider = single_stub(tmp_path, "single_post_fa__xcli_guest", FA_POST)

    result = acquire(
        FA_POST, provider=provider, output_root=tmp_path / "output", via_tunnel=True
    )

    preserved = "".join(path.read_text("utf-8") for path in result.evidence_paths)
    for item in result.capture["items"]:
        canonical = item["text"]["canonical"]
        assert json.dumps(canonical, ensure_ascii=False)[1:-1] in preserved


def test_a_record_for_another_post_is_drift_not_a_crash(tmp_path: Path) -> None:
    """A redirect, or a retweet unrolled into what it quotes.

    ``_assemble`` used to find the anchor with a bare ``next(...)``, so this
    raised ``StopIteration`` — a type neither ``cli._run_capture`` nor
    ``cli.USER_FACING_ERRORS`` catches, which means ``capture`` died on a raw
    traceback where WORKFLOW.md §T7 documents exit 9. Secondarily,
    ``_preserve_reads`` pairs bytes to records by id, so the mismatched record
    would have produced an item with no preserved evidence at all.
    """
    other = spike_record("single_post_fa__xcli_guest")
    binary = make_stub(
        tmp_path / "bin",
        posts={EN_POST: {"exit": 0, "stdout": json.dumps([other], ensure_ascii=False)}},
    )
    output = tmp_path / "output"

    with pytest.raises(ProviderDrift) as caught:
        acquire(EN_POST, provider=verified(binary), output_root=output, via_tunnel=True)

    assert EN_POST in str(caught.value) and other["id"] in str(caught.value)
    assert not (output / EN_POST / "capture.json").exists()


@pytest.mark.parametrize(
    "reference",
    [
        # 200 digits. The 25-digit bound guarded the bare-id branch only, so
        # this returned a 200-character "post id" that named a run directory and
        # became argv to the pinned binary.
        "https://x.com/user/status/" + "1" * 200,
        # `str.isdigit()` is not ASCII-only. This used to be returned as a post
        # id and refused four frames later by `resolve_run_dir`, as a *video*.
        "١٢٣٤٥",
        "https://x.com/user/status/١٢٣٤٥",
    ],
    ids=("two-hundred-digits-in-a-url", "arabic-indic-digits", "arabic-indic-digits-in-a-url"),
)
def test_what_is_not_a_post_id_is_refused_as_one(reference: str) -> None:
    with pytest.raises(AcquisitionError) as caught:
        parse_reference(reference)
    assert "video" not in str(caught.value).lower()


def test_the_bound_is_the_same_on_both_branches() -> None:
    """One rule, applied twice, rather than two rules that drifted apart."""
    longest = "1" * 25
    assert parse_reference(longest) == longest
    assert parse_reference(f"https://x.com/u/status/{longest}") == longest
    for over in (longest + "1", f"https://x.com/u/status/{longest}1"):
        with pytest.raises(AcquisitionError):
            parse_reference(over)
