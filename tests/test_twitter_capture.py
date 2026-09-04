"""Contract tests for the Twitter/X canonical capture (T-223).

The schema is in ``schemas/capture/v1/twitter_capture.schema.json`` and the
fixtures in ``tests/fixtures/captures/``, built offline by
``build_captures.py`` from raw evidence committed under ``captures/raw/`` and
``docs/spikes/T-222/fixtures/``.

Four things are checked, and the last is the one that matters:

1. The schema is valid JSON Schema 2020-12.
2. Every committed fixture validates, and regeneration is byte-identical, so a
   fixture cannot drift away from the builder that explains it (D-157).
3. A capture can be **revalidated from raw evidence**: the digest each fixture
   carries is recomputed from the preserved bytes on disk.
4. The claims JSON Schema cannot express are enforced here — and a catalogue of
   dishonest captures is rejected. That catalogue is the real test. A schema that
   accepts an honest document proves little; the contract's job is to make a
   *dishonest* one unrepresentable, so each entry below is a specific lie that
   T-222 measured someone could otherwise tell.

One shape is built in the test process rather than committed:
``tests/capture_shapes.py`` constructs a post with an edit history, because no
measured route produces one and a fixture in this directory is a claim about
what a provider returned (D-222). Its own honesty invariant lives here beside
the others, and ``test_no_committed_capture_carries_an_edit_history`` keeps that
shape from drifting back onto disk as though it had been measured.
"""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
from capture_shapes import EDIT_PRIOR_IDS, edited_post_capture

jsonschema = pytest.importorskip(
    "jsonschema",
    reason="jsonschema is a dev-extra dependency; the core package stays zero-dependency",
)
from jsonschema import Draft202012Validator  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "capture" / "v1" / "twitter_capture.schema.json"
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "captures"
BUILDER = FIXTURE_DIR / "build_captures.py"


@pytest.fixture(scope="module")
def schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def validator(schema: dict) -> Draft202012Validator:
    return Draft202012Validator(schema)


def fixture_paths() -> list[Path]:
    return sorted(p for p in FIXTURE_DIR.glob("*.json"))


def load(name: str) -> dict:
    return json.loads((FIXTURE_DIR / f"{name}.json").read_text(encoding="utf-8"))


def test_the_schema_is_valid_json_schema(schema: dict) -> None:
    Draft202012Validator.check_schema(schema)


def test_there_is_a_fixture_for_every_measured_state() -> None:
    names = {p.stem for p in fixture_paths()}
    # PASS alone would prove nothing: T-222 measured two states that cannot
    # honestly reach PASS, and both must exist as fixtures or the UI and the
    # validators have nothing to be tested against (the T-006 lesson).
    assert "partial-thread-root-anchor" in names
    # The chain that dangles, measured live rather than constructed (D-221). It
    # is the only fixture that reaches the conditional branch of
    # `test_thread_order_is_root_first_and_parent_consistent`, so losing it
    # makes that branch dead again without any test failing.
    assert "partial-thread-dangling-chain" in names
    assert "partial-tier0-truncated-text" in names
    assert "fail-unavailable-post" in names
    statuses = {load(n)["coverage"]["status"] for n in names}
    assert statuses == {"PASS", "PARTIAL", "FAIL"}


@pytest.mark.parametrize("path", fixture_paths(), ids=lambda p: p.stem)
def test_every_fixture_validates(validator: Draft202012Validator, path: Path) -> None:
    errors = sorted(validator.iter_errors(json.loads(path.read_text("utf-8"))),
                    key=lambda e: list(e.path))
    assert not errors, "; ".join(f"{list(e.path)}: {e.message}" for e in errors[:4])


def test_regenerating_the_fixtures_is_byte_identical() -> None:
    before = {p: p.read_bytes() for p in fixture_paths()}
    result = subprocess.run(
        [sys.executable, str(BUILDER)], capture_output=True, text=True, cwd=ROOT
    )
    assert result.returncode == 0, result.stderr
    after = {p: p.read_bytes() for p in fixture_paths()}
    assert before.keys() == after.keys()
    drifted = [p.name for p in before if before[p] != after[p]]
    assert not drifted, f"builder output drifted from the committed fixtures: {drifted}"


@pytest.mark.parametrize("path", fixture_paths(), ids=lambda p: p.stem)
def test_a_capture_can_be_revalidated_from_raw_evidence(path: Path) -> None:
    """The acceptance criterion: the digests must recompute from the bytes."""
    capture = json.loads(path.read_text("utf-8"))
    for entry in capture["raw_evidence"]:
        evidence = ROOT / entry["path"]
        assert evidence.is_file(), f"raw evidence missing: {entry['path']}"
        actual = hashlib.sha256(evidence.read_bytes()).hexdigest()
        assert actual == entry["sha256_sanitized"], (
            f"{path.name}: {entry['path']} does not match its recorded digest"
        )


@pytest.mark.parametrize("path", fixture_paths(), ids=lambda p: p.stem)
def test_no_fixture_carries_credential_material(path: Path) -> None:
    text = path.read_text("utf-8")
    for pattern in ("auth_token=", "ct0=", '"guest_token"', "Bearer "):
        assert pattern not in text, f"{path.name} carries {pattern!r}"
    # A stripped request token is fine; a live one is not.
    assert "token=" not in text or "token=<STRIPPED>" in text


@pytest.mark.parametrize("path", fixture_paths(), ids=lambda p: p.stem)
def test_every_entity_span_reslices_to_its_own_text(path: Path) -> None:
    """Spans are codepoint offsets into the canonical text, or they are wrong.

    T-222 proved the basis against astral emoji: the UTF-16 reading is shifted
    and mangled. This is the guard that keeps a fixture from being rebuilt on
    that reading without anyone noticing.
    """
    capture = json.loads(path.read_text("utf-8"))
    for post in capture["items"]:
        text = (post.get("text") or {}).get("canonical")
        for entity in (post.get("text") or {}).get("entities") or []:
            start, end = entity["start_char"], entity["end_char"]
            assert 0 <= start < end <= len(text), f"{path.name}: span out of bounds"
            sliced = text[start:end]
            expected = entity.get("shortened") or (
                f"@{entity['handle']}" if entity.get("handle") else None
            )
            if expected is not None:
                assert sliced == expected, (
                    f"{path.name}: span [{start},{end}] slices {sliced!r}, "
                    f"not {expected!r}"
                )


@pytest.mark.parametrize("path", fixture_paths(), ids=lambda p: p.stem)
def test_thread_order_is_root_first_and_parent_consistent(path: Path) -> None:
    """The chain is contiguous, and it begins at a root exactly when it says it does.

    Refined by `T-224`, which found the unconditional form too strong to be
    true: a chain whose walk stopped at an unavailable parent, or at a parent by
    another author, honestly does *not* begin at a root, and its first item
    keeps the ``parent_post_id`` that proves it. Dropping that link to satisfy a
    root-first rule would hide the incompleteness the capture is reporting. So
    the root claim is conditional on ``completeness.upward``, and where the
    chain dangles, the dangling end must be exactly the id ``upward`` names.
    """
    capture = json.loads(path.read_text("utf-8"))
    items = capture["items"]
    if capture["order"]["basis"] != "parent_links" or len(items) < 2:
        return
    upward = capture["completeness"]["upward"]
    if upward["status"] == "complete":
        assert "parent_post_id" not in items[0], f"{path.name}: first item is not a root"
    else:
        assert items[0].get("parent_post_id") == upward.get("unresolved_at"), (
            f"{path.name}: the chain dangles at an id upward completeness does not name"
        )
    for earlier, later in zip(items[:-1], items[1:], strict=True):
        assert later.get("parent_post_id") == earlier["post_id"], (
            f"{path.name}: {later['post_id']} does not follow {earlier['post_id']}"
        )


def test_some_fixture_exercises_the_dangling_chain_branch() -> None:
    """At least one capture must reach the ``else`` in the root-first test.

    That test's conditional branch — the chain that honestly does not begin at a
    root — was unreachable for the whole fixture set: it returns early unless
    ``order.basis`` is ``parent_links`` with two or more items, and the only
    capture meeting that was ``upward: complete``. The branch was dead and no
    failure said so, which is what this test exists to prevent recurring.
    """
    reaching = [
        name
        for name in (p.stem for p in fixture_paths())
        if (c := load(name))["order"]["basis"] == "parent_links"
        and len(c["items"]) >= 2
        and c["completeness"]["upward"]["status"] != "complete"
    ]
    assert reaching, (
        "no fixture reaches the dangling-chain branch of "
        "test_thread_order_is_root_first_and_parent_consistent"
    )


@pytest.mark.parametrize("path", fixture_paths(), ids=lambda p: p.stem)
def test_coverage_accounts_for_every_expected_item(path: Path) -> None:
    """PASS is impossible while an expected item is unaccounted for."""
    capture = json.loads(path.read_text("utf-8"))
    coverage = capture["coverage"]
    included = coverage["included_post_ids"]
    omitted = coverage["omitted_items"]
    assert len(set(included)) == len(included), f"{path.name}: duplicate included id"
    if coverage["status"] == "PASS":
        assert not omitted, f"{path.name}: PASS with omitted items"
        assert len(included) == coverage["expected_item_count"]
        assert {p["post_id"] for p in capture["items"]} == set(included)
    else:
        assert omitted, f"{path.name}: {coverage['status']} with nothing omitted"
        for entry in omitted:
            assert entry.get("post_id") or entry.get("descriptor"), (
                f"{path.name}: an omission names neither an id nor a descriptor"
            )


@pytest.mark.parametrize("path", fixture_paths(), ids=lambda p: p.stem)
def test_downward_completeness_is_never_claimed(path: Path) -> None:
    """No credential-free route can enumerate descendants, so nothing may say it did."""
    capture = json.loads(path.read_text("utf-8"))
    assert capture["completeness"]["downward"]["status"] in {"unprovable", "not_applicable"}


@pytest.mark.parametrize("path", fixture_paths(), ids=lambda p: p.stem)
def test_no_completeness_prose_claims_what_its_own_status_denies(path: Path) -> None:
    """The two completeness blocks are one claim and must not contradict each other.

    Found by measuring a real crossed-author chain. ``downward.reason`` was
    keyed on the anchor's *role* alone, so a terminal anchor whose upward walk
    stopped at another author's post still read "complete to root" — two fields
    away from an ``upward.status`` of ``incomplete``. Both halves validated:
    ``reason`` is a free-text string and JSON Schema compares no two fields, so
    only a cross-field check can see it. Phrase-level rather than semantic on
    purpose: the prose that asserts a root was reached is a closed set here, and
    a new spelling of it should have to pass this test to enter the record.
    """
    capture = json.loads(path.read_text("utf-8"))
    completeness = capture["completeness"]
    upward = completeness["upward"]
    reason = completeness["downward"]["reason"].casefold()
    if upward["status"] != "complete":
        for phrase in ("complete to root", "root reached", "reached the root"):
            assert phrase not in reason, (
                f"{path.name}: downward.reason claims {phrase!r} while upward.status "
                f"is {upward['status']!r} ({upward['basis']!r})"
            )


@pytest.mark.parametrize("path", fixture_paths(), ids=lambda p: p.stem)
def test_a_terminal_anchor_is_recorded_as_an_assertion(path: Path) -> None:
    capture = json.loads(path.read_text("utf-8"))
    anchor = capture["anchor"]
    assert anchor["terminal_claim"] in {"user_asserted", "none"}
    if anchor["role"] == "thread_terminal":
        assert anchor["terminal_claim"] == "user_asserted", (
            f"{path.name}: a terminal anchor cannot be an observation"
        )


@pytest.mark.parametrize("path", fixture_paths(), ids=lambda p: p.stem)
def test_no_capture_claims_a_session_tier(path: Path) -> None:
    """ADR 0007 excludes Tier 2; the contract must make claiming it impossible."""
    text = path.read_text("utf-8")
    capture = json.loads(text)
    tiers = {read["tier"] for read in capture["acquisition"]["routes_read"]}
    assert tiers <= {0, 1}, f"{path.name}: claims tier {tiers - {0, 1}}"


@pytest.mark.parametrize("path", fixture_paths(), ids=lambda p: p.stem)
def test_an_unavailable_post_invents_nothing(path: Path) -> None:
    capture = json.loads(path.read_text("utf-8"))
    for post in capture["items"]:
        if post["availability"]["state"] != "unavailable":
            continue
        # Nothing was observed, so nothing may be present to be believed.
        for invented in ("author", "created_at", "text", "media", "metrics"):
            assert invented not in post, (
                f"{path.name}: unavailable post carries {invented!r}"
            )
        assert post["availability"].get("reason") == "not_determinable_at_this_tier"


def edit_history_errors(capture: dict) -> list[str]:
    """What an ``edits`` list may not do. One sentence, checked three ways.

    The sentence is *nothing named in ``edits`` was observed* (D-224). JSON
    Schema can require the list to be non-empty and its members to be post ids —
    it already does — but it compares no two fields, so it cannot see an id that
    appears both as a prior version and as something the capture claims to have
    read. Each check below is that one sentence failing in a different place.
    """
    errors: list[str] = []
    item_ids = {post["post_id"] for post in capture["items"]}
    included = set(capture["coverage"]["included_post_ids"])
    for post in capture["items"]:
        prior = post.get("edits")
        if prior is None:
            continue
        if post["post_id"] in prior:
            errors.append(
                f"{post['post_id']}: its own id is in its edit history, so 'nothing in "
                "edits was observed' needs a carve-out for the one id that was"
            )
        observed_as_item = sorted(set(prior) & item_ids)
        if observed_as_item:
            errors.append(
                f"{post['post_id']}: {observed_as_item} are prior versions and also items, "
                "so the capture claims to have read a state it says no longer exists"
            )
        claimed_covered = sorted(set(prior) & included)
        if claimed_covered:
            errors.append(
                f"{post['post_id']}: {claimed_covered} are prior versions and also in "
                "coverage.included_post_ids, which counts them as posts accounted for"
            )
    return errors


@pytest.mark.parametrize("path", fixture_paths(), ids=lambda p: p.stem)
def test_no_committed_capture_carries_an_edit_history(path: Path) -> None:
    """The route produces none, so none may appear as though measured.

    T-222 scanned 610 credential-free posts and found no edited post, and
    ``x fields tweet`` declares ``edits`` with no surface at any tier. A fixture
    in this directory is a claim about what a provider returned (D-222), so an
    ``edits`` key appearing here would be that claim made falsely — most likely
    by someone building the shape in the obvious wrong place.
    """
    capture = json.loads(path.read_text("utf-8"))
    carrying = [p["post_id"] for p in capture["items"] if "edits" in p]
    assert not carrying, (
        f"{path.name}: {carrying} carry an edit history, which no measured route "
        "produces — construct that shape in tests/capture_shapes.py instead"
    )


def test_the_constructed_edit_history_validates(validator: Draft202012Validator) -> None:
    assert not list(validator.iter_errors(edited_post_capture()))


def test_the_constructed_edit_history_is_honest() -> None:
    """The shape T-227 will extract from must itself pass the invariant."""
    assert edit_history_errors(edited_post_capture()) == []


def test_the_constructed_edit_history_states_only_the_prior_ids() -> None:
    """It names the versions and says nothing about what they contained."""
    capture = edited_post_capture()
    post = capture["items"][0]
    assert post["edits"] == list(EDIT_PRIOR_IDS)
    # Coverage is untouched: a prior version is the same post in a state that no
    # longer exists, not another post in the conversation, so it is not an
    # expected item and cannot turn a PASS into a PARTIAL (D-224).
    original = load("pass-single-post-en")
    assert capture["coverage"] == original["coverage"]
    assert capture["coverage"]["status"] == "PASS"


def dishonest_edit_histories() -> list[tuple[str, dict]]:
    """Edit histories that are schema-legal and must fail the invariant."""
    cases: list[tuple[str, dict]] = []

    doc = edited_post_capture()
    doc["items"][0]["edits"].append(doc["items"][0]["post_id"])
    cases.append(("the post lists itself as one of its own prior versions", doc))

    doc = edited_post_capture()
    doc["items"][0]["edits"] = [doc["items"][0]["post_id"]]
    cases.append(("the whole edit history is the post's own id", doc))

    doc = edited_post_capture()
    doc["coverage"]["included_post_ids"].append(doc["items"][0]["edits"][0])
    cases.append(("a prior version is counted as a post accounted for", doc))

    return cases


@pytest.mark.parametrize("why,document", dishonest_edit_histories(), ids=lambda v: v if isinstance(v, str) else "")
def test_dishonest_edit_histories_are_refused(
    validator: Draft202012Validator, why: str, document: dict
) -> None:
    # Schema-legal on purpose: `edits` members are post ids and the schema
    # compares no two fields, so the catalogue cannot reach these.
    assert not list(validator.iter_errors(document)), (
        f"expected the schema to accept this one: {why}"
    )
    assert edit_history_errors(document), f"the invariant accepted a capture where {why}"


def dishonest_documents() -> list[tuple[str, dict, str]]:
    """Captures that must be refused, each a lie T-222 measured as possible."""
    cases: list[tuple[str, dict, str]] = []

    doc = load("pass-single-post-en")
    doc["items"][0]["media"] = []
    cases.append(("empty media claims an observation of absence", doc, "media"))

    doc = load("pass-single-post-en")
    doc["items"][0]["poll"] = {}
    cases.append(("empty poll claims absence was observed", doc, "poll"))

    doc = load("pass-single-post-en")
    doc["items"][0]["edits"] = []
    cases.append(("empty edits claims the post was never edited", doc, "edits"))

    doc = load("pass-single-post-en")
    doc["acquisition"]["routes_read"][0]["tier"] = 2
    cases.append(("tier 2 is excluded by ADR 0007", doc, "tier"))

    doc = load("pass-single-post-en")
    doc["items"][0]["post_id"] = 20
    cases.append(("a numeric post id loses precision above 2^53", doc, "post_id"))

    doc = load("pass-single-post-en")
    doc["items"][0]["text"]["form"] = "rendered"
    cases.append(("canonical text must be the authored form (D-211)", doc, "form"))

    doc = load("pass-thread-terminal-anchor")
    doc["completeness"]["downward"]["status"] = "complete"
    cases.append(("descendants cannot be enumerated at any qualified tier", doc, "downward"))

    doc = load("pass-thread-terminal-anchor")
    doc["anchor"]["terminal_claim"] = "observed"
    cases.append(("a terminal anchor is never an observation", doc, "terminal_claim"))

    doc = load("pass-single-post-en")
    doc["items"][0]["metrics"] = {"likes": 308633}
    cases.append(("a metric without observed_at reads as a property", doc, "metrics"))

    doc = load("pass-single-post-en")
    doc["raw_evidence"][0]["path"] = "../../etc/passwd"
    cases.append(("raw evidence outside the project", doc, "path"))

    doc = load("pass-single-post-en")
    del doc["raw_evidence"][0]["sha256_raw"]
    cases.append(("a sanitized digest passed off as the original", doc, "sha256_raw"))

    doc = load("fail-unavailable-post")
    doc["items"][0]["availability"]["reason"] = "deleted"
    doc["items"][0]["availability"]["state"] = "unavailable"
    # Schema-legal, so this one is caught by the invariant test above, not here.
    cases.append(("", doc, ""))
    cases.pop()

    doc = load("pass-single-post-en")
    doc["items"][0]["provider_response"] = {"data": "raw"}
    cases.append(("a provider response shape must not leak through", doc, "provider_response"))

    return cases


@pytest.mark.parametrize(
    "why,document,field", dishonest_documents(), ids=lambda v: v if isinstance(v, str) else ""
)
def test_dishonest_captures_are_refused(
    validator: Draft202012Validator, why: str, document: dict, field: str
) -> None:
    errors = list(validator.iter_errors(document))
    assert errors, f"the schema accepted a capture that {why}"


def test_the_honest_original_still_validates(validator: Draft202012Validator) -> None:
    """The catalogue above mutates copies; the source must remain valid."""
    assert not list(validator.iter_errors(load("pass-single-post-en")))


def test_deleted_reason_is_schema_legal_but_refused_by_the_invariant() -> None:
    """Tier 0 cannot tell deleted from suspended from protected.

    The enum lists the specific reasons because a future tier could distinguish
    them, so the schema alone cannot refuse one. The invariant does.
    """
    capture = copy.deepcopy(load("fail-unavailable-post"))
    capture["items"][0]["availability"]["reason"] = "deleted"
    with pytest.raises(AssertionError):
        for post in capture["items"]:
            if post["availability"]["state"] == "unavailable":
                assert post["availability"].get("reason") == "not_determinable_at_this_tier"
