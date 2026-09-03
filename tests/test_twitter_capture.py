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
"""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

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
