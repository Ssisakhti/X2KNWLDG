"""The capture becomes a run: item segmentation, provenance and coverage (T-227).

Every case runs over a **committed capture** — the eight in
``tests/fixtures/captures/``, each derived from bytes a real acquisition
returned — plus the one shape no route produces, constructed by
``capture_shapes`` (D-222). So these are assertions about real captures rather
than about a convenient shape invented to make them pass.

A run is staged by copying a capture and its raw evidence into a temporary tree
at the **same relative paths** the capture records, so ``evidence_integrity``
resolves them the way it does in ``output/`` with no test-only seam. A parameter
for "where the project root is" would have been a second root-resolution rule,
which is what D-039 removed.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from capture_shapes import EDIT_PRIOR_IDS, edited_post_capture
from x2knwldg.constants import OMISSION_REASONS
from x2knwldg.io import dumps_json
from x2knwldg.twitter import extract
from x2knwldg.validators import (
    validate_item_coverage,
    validate_item_coverage_links,
    validate_knowledge_units,
    validate_post_provenance,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "captures"


def capture_names() -> list[str]:
    return sorted(p.stem for p in FIXTURE_DIR.glob("*.json"))


def load(name: str) -> dict[str, Any]:
    return json.loads((FIXTURE_DIR / f"{name}.json").read_text(encoding="utf-8"))


def stage(tmp_path: Path, capture: dict[str, Any]) -> Path:
    """Write *capture* as an acquired run under ``tmp_path/output/<anchor>/``.

    Raw evidence is copied to the exact relative path the capture names, because
    that is what the capture asserts is true and the point of the integrity
    check is to test that assertion rather than a rewritten copy of it.
    """
    source_id = capture["anchor"]["post_id"]
    run_dir = tmp_path / "output" / source_id
    (run_dir / "raw").mkdir(parents=True, exist_ok=True)
    for entry in capture["raw_evidence"]:
        destination = tmp_path / entry["path"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / entry["path"], destination)
    (run_dir / "capture.json").write_text(
        json.dumps(capture, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return run_dir


# ---------------------------------------------------------------------------
# 1. Every committed capture becomes a run, and the run agrees with it
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", capture_names())
def test_every_capture_initializes_into_a_run(tmp_path: Path, name: str) -> None:
    capture = load(name)
    run_dir = stage(tmp_path, capture)
    metadata = extract.initialize_run(run_dir)

    assert metadata["source_type"] == "twitter"
    assert metadata["video_id"] == capture["anchor"]["post_id"]
    assert metadata["item_count"] == len(capture["items"])
    assert metadata["canonical_hashes"] == {"capture.json": metadata["canonical_hashes"]["capture.json"]}

    coverage = json.loads((run_dir / "coverage.json").read_text(encoding="utf-8"))
    result = validate_item_coverage(coverage, capture)
    assert result["status"] == "PASS", result["errors"]
    assert validate_item_coverage_links(coverage, []) == []


@pytest.mark.parametrize("name", capture_names())
def test_no_run_writes_a_second_segmentation(tmp_path: Path, name: str) -> None:
    """The capture's ``items`` array *is* the segmentation.

    A ``segments.json`` here would be a second answer to "where does this post
    start", and the two would disagree the moment either was edited. The
    boundaries live in one sealed file.
    """
    run_dir = stage(tmp_path, load(name))
    extract.initialize_run(run_dir)
    assert not (run_dir / "segments.json").exists()
    assert not (run_dir / "transcript.json").exists()


@pytest.mark.parametrize("name", capture_names())
def test_item_order_is_the_captures_order(tmp_path: Path, name: str) -> None:
    """Root-first, taken from the capture and never re-sorted."""
    capture = load(name)
    run_dir = stage(tmp_path, capture)
    extract.initialize_run(run_dir)
    coverage = json.loads((run_dir / "coverage.json").read_text(encoding="utf-8"))
    assert [entry["post_id"] for entry in coverage["items"]] == extract.post_order(capture)
    assert extract.post_order(capture) == [item["post_id"] for item in capture["items"]]


@pytest.mark.parametrize("name", capture_names())
def test_every_included_post_has_a_coverage_entry(tmp_path: Path, name: str) -> None:
    """The acceptance clause, over every real capture."""
    capture = load(name)
    run_dir = stage(tmp_path, capture)
    extract.initialize_run(run_dir)
    coverage = json.loads((run_dir / "coverage.json").read_text(encoding="utf-8"))
    entries = {entry["post_id"] for entry in coverage["items"]}
    assert set(capture["coverage"]["included_post_ids"]) <= entries


@pytest.mark.parametrize("name", capture_names())
def test_the_captures_omissions_are_partitioned_not_copied(tmp_path: Path, name: str) -> None:
    """An omission naming an *included* post is not an exclusion.

    Found by running this over the real fixtures: the truncated post is both
    included and omitted — the omission is about its missing text, not about the
    post being absent — and so is an unavailable one. Copying the capture's
    ``omitted_items`` straight into ``excluded_items`` filed a post as excluded
    from an audit it is the subject of. Membership decides, and the reason is
    carried verbatim either way.
    """
    capture = load(name)
    run_dir = stage(tmp_path, capture)
    extract.initialize_run(run_dir)
    coverage = json.loads((run_dir / "coverage.json").read_text(encoding="utf-8"))

    audited = {entry["post_id"] for entry in coverage["items"]}
    expected = [
        entry
        for entry in capture["coverage"]["omitted_items"]
        if entry.get("post_id") not in audited
    ]
    assert coverage["excluded_items"] == expected
    for excluded in coverage["excluded_items"]:
        assert excluded.get("post_id") not in audited, (
            "an item that was never a candidate cannot be 'covered'"
        )
    # And nothing the capture omitted has simply vanished: an omission about an
    # included post is accounted for on that post's own entry.
    for entry in capture["coverage"]["omitted_items"]:
        post_id = entry.get("post_id")
        if post_id is None or post_id not in audited:
            continue
        own = next(e for e in coverage["items"] if e["post_id"] == post_id)
        assert own["omitted_items"] or own["unresolved_items"], (
            f"{post_id} was omitted by the capture and its entry accounts for nothing"
        )


def test_a_truncated_post_is_auditable_but_holds_the_run_off_pass(tmp_path: Path) -> None:
    """``known_truncated`` is a gap a second route can close, so it is unresolved.

    Not ``omitted``: omitting it would file a resolvable gap as a decision. And
    not ignored: 280 characters of a 2967-character post is 2687 characters
    nothing has accounted for, which is exactly what ``PASS`` is supposed to be
    impossible over.
    """
    capture = load("partial-tier0-truncated-text")
    run_dir = stage(tmp_path, capture)
    extract.initialize_run(run_dir)
    coverage = json.loads((run_dir / "coverage.json").read_text(encoding="utf-8"))
    entry = coverage["items"][0]
    assert entry["status"] == "pending"
    types = [item["type"] for item in entry["unresolved_items"]]
    assert "capture_text_truncated" in types
    assert entry["omitted_items"] == []

    # Audited as far as it goes, the gap still refuses a PASS.
    coverage["status"] = "PASS"
    coverage["audit_attempts"] = 1
    result = validate_item_coverage(coverage, capture)
    assert result["status"] == "FAIL"
    assert "pass_with_unresolved_items" in {e["code"] for e in result["errors"]}


@pytest.mark.parametrize("name", capture_names())
def test_unverified_text_is_not_treated_as_a_gap(tmp_path: Path, name: str) -> None:
    """The normal state of a single-route read must not block every run.

    Text completeness has no in-band signal on any measured route, so
    ``unverified`` is what an honest one-route capture says. If that counted as
    unaccounted-for, no Twitter run could ever reach ``PASS`` and the verdict
    would carry no information at all. The limitation is recorded rather than
    scored: in the capture, and in ``metadata.capture_coverage_status``.
    """
    capture = load(name)
    run_dir = stage(tmp_path, capture)
    metadata = extract.initialize_run(run_dir)
    coverage = json.loads((run_dir / "coverage.json").read_text(encoding="utf-8"))
    assert metadata["capture_coverage_status"] == capture["coverage"]["status"]
    for item, entry in zip(capture["items"], coverage["items"], strict=True):
        status = ((item.get("text") or {}).get("completeness") or {}).get("status")
        types = [unresolved["type"] for unresolved in entry["unresolved_items"]]
        if status == "unverified":
            assert "capture_text_truncated" not in types


# ---------------------------------------------------------------------------
# 2. Evidence integrity — the digests, and the one check that replaces
#    recomputation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", capture_names())
def test_evidence_integrity_passes_on_an_untouched_run(tmp_path: Path, name: str) -> None:
    capture = load(name)
    run_dir = stage(tmp_path, capture)
    metadata = extract.initialize_run(run_dir)
    result = extract.evidence_integrity(run_dir, metadata, capture)
    assert result["status"] == "PASS", result["errors"]


def test_an_edited_capture_is_caught_by_its_recorded_digest(tmp_path: Path) -> None:
    capture = load("pass-single-post-en")
    run_dir = stage(tmp_path, capture)
    metadata = extract.initialize_run(run_dir)
    tampered = json.loads((run_dir / "capture.json").read_text(encoding="utf-8"))
    tampered["items"][0]["text"]["canonical"] = "A sentence nobody posted."
    (run_dir / "capture.json").write_text(
        json.dumps(tampered, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    result = extract.evidence_integrity(run_dir, metadata, tampered)
    assert result["status"] == "FAIL"
    assert "canonical_file_digest_mismatch" in {e["code"] for e in result["errors"]}


def test_an_edited_capture_with_a_fixed_digest_is_caught_by_re_derivation(
    tmp_path: Path,
) -> None:
    """The check that exists because a capture is re-derivable and not recomputable.

    ``segments.json`` is a pure function of the captions, so the YouTube path
    recomputes it. A capture is a provider read and is a pure function of
    nothing — so the *item set* is rebuilt from the preserved responses instead.
    This is the attack the recorded digest cannot see: change the canonical text
    and update ``canonical_hashes`` to match, leaving ``raw/`` untouched, which
    is the file an attacker has no reason to touch.
    """
    capture = load("pass-single-post-en")
    run_dir = stage(tmp_path, capture)
    extract.initialize_run(run_dir)

    tampered = json.loads((run_dir / "capture.json").read_text(encoding="utf-8"))
    tampered["items"][0]["text"]["canonical"] = "A sentence nobody posted."
    text = json.dumps(tampered, indent=2, ensure_ascii=False) + "\n"
    (run_dir / "capture.json").write_text(text, encoding="utf-8")
    metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
    from x2knwldg.io import sha256_text

    metadata["canonical_hashes"]["capture.json"] = sha256_text(text)

    result = extract.evidence_integrity(run_dir, metadata, tampered)
    assert result["status"] == "FAIL"
    codes = {e["code"] for e in result["errors"]}
    assert "canonical_file_digest_mismatch" not in codes, "the digest was updated to match"
    assert "item_disagrees_with_preserved_response" in codes


def test_missing_raw_evidence_is_named(tmp_path: Path) -> None:
    capture = load("pass-single-post-en")
    run_dir = stage(tmp_path, capture)
    metadata = extract.initialize_run(run_dir)
    (tmp_path / capture["raw_evidence"][0]["path"]).unlink()
    result = extract.evidence_integrity(run_dir, metadata, capture)
    assert result["status"] == "FAIL"
    assert "raw_evidence_missing" in {e["code"] for e in result["errors"]}


def test_raw_evidence_outside_the_project_is_refused(tmp_path: Path) -> None:
    capture = load("pass-single-post-en")
    run_dir = stage(tmp_path, capture)
    metadata = extract.initialize_run(run_dir)
    escaped = json.loads(json.dumps(capture))
    escaped["raw_evidence"][0]["path"] = "../../etc/passwd"
    result = extract.evidence_integrity(run_dir, metadata, escaped)
    assert result["status"] == "FAIL"
    assert "raw_evidence_outside_project" in {e["code"] for e in result["errors"]}


# ---------------------------------------------------------------------------
# 3. The item states: unavailable, quoted, edited
# ---------------------------------------------------------------------------


def test_an_unavailable_post_is_omitted_and_never_covered(tmp_path: Path) -> None:
    """Nothing was observed, so there is nothing to audit — and it is still named."""
    capture = load("fail-unavailable-post")
    run_dir = stage(tmp_path, capture)
    extract.initialize_run(run_dir)
    coverage = json.loads((run_dir / "coverage.json").read_text(encoding="utf-8"))
    entry = coverage["items"][0]
    assert entry["status"] == "omitted"
    assert entry["knowledge_units"] == []
    reasons = [omission["type"] for omission in entry["omitted_items"]]
    assert reasons == ["source_unavailable"]
    assert "source_unavailable" in OMISSION_REASONS


def test_a_claim_may_not_cite_an_unavailable_post(tmp_path: Path) -> None:
    capture = load("fail-unavailable-post")
    unit = {
        "id": "KU-000001",
        "kind": "claim",
        "source_class": "source",
        "content": "Invented from a post that was never read.",
        "confidence": 0.9,
        "source": {
            "post_id": capture["items"][0]["post_id"],
            "start_char": 0,
            "end_char": 5,
            "evidence_excerpt": "never",
        },
    }
    document = {"schema_version": "1.0", "source_type": "twitter", "units": [unit]}
    result = validate_post_provenance(document, capture)
    assert result["status"] == "FAIL"
    assert "claim_cites_unavailable_post" in {e["code"] for e in result["errors"]}


def test_a_quoted_post_is_an_external_reference_and_is_not_fetched(tmp_path: Path) -> None:
    """ADR 0007 decision 8: a separate cited source, never embedded content."""
    capture = load("pass-quote-post")
    run_dir = stage(tmp_path, capture)
    metadata = extract.initialize_run(run_dir)
    references = metadata["external_references"]
    assert len(references) == 1
    reference = references[0]
    quote = capture["items"][0]["quote"]
    assert reference["relation"] == "quotes"
    assert reference["post_id"] == quote["quoted_post_id"]
    assert reference["author_username"] == quote["quoted_author_username"]
    assert reference["fetched"] is False
    # The quoted post is not an item of this run, so it gets no coverage entry:
    # there is nothing of it here to cover.
    coverage = json.loads((run_dir / "coverage.json").read_text(encoding="utf-8"))
    assert quote["quoted_post_id"] not in {entry["post_id"] for entry in coverage["items"]}


def test_an_edit_history_names_prior_versions_and_audits_none_of_them(
    tmp_path: Path,
) -> None:
    """The shape no route produces (D-222), and what extraction does with it.

    The prior ids are named on the item and appear **nowhere else**: not as
    items, not as coverage entries, not as external references. Extraction cites
    the canonical text it has and does not go looking for the text it does not.
    """
    capture = edited_post_capture()
    run_dir = stage(tmp_path, capture)
    metadata = extract.initialize_run(run_dir)
    coverage = json.loads((run_dir / "coverage.json").read_text(encoding="utf-8"))

    assert capture["items"][0]["edits"] == list(EDIT_PRIOR_IDS)
    audited = {entry["post_id"] for entry in coverage["items"]}
    excluded = {entry.get("post_id") for entry in coverage["excluded_items"]}
    referenced = {reference["post_id"] for reference in metadata["external_references"]}
    for prior in EDIT_PRIOR_IDS:
        assert prior not in audited
        assert prior not in excluded
        assert prior not in referenced
    # And the run is still whole: an edit history is metadata on one post, not
    # another post to account for (D-224).
    assert metadata["item_count"] == 1
    assert validate_item_coverage(coverage, capture)["status"] == "PASS"


def test_an_edited_run_still_re_derives_from_its_preserved_response(
    tmp_path: Path,
) -> None:
    """``edits`` is excluded from the re-derivation comparison, deliberately.

    The preserved response cannot supply a field the route never returned, so
    comparing it would report the constructed shape as tampered with. What the
    check still covers is everything the record *does* determine.
    """
    capture = edited_post_capture()
    run_dir = stage(tmp_path, capture)
    metadata = extract.initialize_run(run_dir)
    result = extract.evidence_integrity(run_dir, metadata, capture)
    assert result["status"] == "PASS", result["errors"]


# ---------------------------------------------------------------------------
# 4. Persian/RTL — where a span goes wrong and nowhere else
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["pass-single-post-fa", "pass-single-post-fa-video"])
def test_a_span_into_rtl_text_is_its_own_excerpt(name: str) -> None:
    """The exact-slice rule, on text made of ZWNJ, Persian digits and a NBSP.

    A cleaned-and-casefolded comparison — which is what the YouTube path does,
    correctly, for assembled caption text — would discard exactly the
    characters this post is built from. So the excerpt is compared verbatim, and
    these two fixtures are where a normalizing excerpt path would show up.
    """
    capture = load(name)
    text = capture["items"][0]["text"]["canonical"]
    start, end = 0, text.index("\n") if "\n" in text else len(text)
    unit = {
        "id": "KU-000001",
        "kind": "fact",
        "source_class": "source",
        "content": "The first line of the post.",
        "confidence": 0.9,
        "source": {
            "post_id": capture["items"][0]["post_id"],
            "start_char": start,
            "end_char": end,
            "evidence_excerpt": text[start:end],
        },
    }
    document = {"schema_version": "1.0", "source_type": "twitter", "units": [unit]}
    assert validate_knowledge_units(document)["status"] == "PASS"
    assert validate_post_provenance(document, capture)["status"] == "PASS"

    # And a normalized excerpt — the same span with its invisible characters
    # stripped — is refused rather than quietly accepted.
    stripped = text[start:end].replace("‌", "").replace("\xa0", " ")
    if stripped != text[start:end]:
        document["units"][0]["source"]["evidence_excerpt"] = stripped
        result = validate_post_provenance(document, capture)
        assert result["status"] == "FAIL"
        assert "evidence_excerpt_is_not_its_span" in {e["code"] for e in result["errors"]}


def test_a_span_is_codepoints_not_utf16_code_units() -> None:
    """The basis D-211 settled, asserted against astral characters.

    The dangling-chain fixture's first post ends in three U+1F602, each one
    UTF-16 surrogate pair. A UTF-16 reading of any offset after them is shifted,
    and Python string indexing is natively codepoint-indexed — so this passes
    only because the basis is right.
    """
    capture = load("partial-thread-dangling-chain")
    text = capture["items"][0]["text"]["canonical"]
    assert any(ord(character) > 0xFFFF for character in text), "fixture lost its astral chars"
    assert len(text) < len(text.encode("utf-16-le")) // 2

    start = text.index("Now")
    end = len(text)
    unit = {
        "id": "KU-000001",
        "kind": "quote",
        "source_class": "source",
        "content": "The remark, quoted through the astral characters that end it.",
        "confidence": 0.9,
        "source": {
            "post_id": capture["items"][0]["post_id"],
            "start_char": start,
            "end_char": end,
            "evidence_excerpt": text[start:end],
        },
    }
    document = {"schema_version": "1.0", "source_type": "twitter", "units": [unit]}
    assert validate_post_provenance(document, capture)["status"] == "PASS"


# ---------------------------------------------------------------------------
# 5. A whole run, validated — and PASS held back where it must be
# ---------------------------------------------------------------------------


def audited_run(tmp_path: Path, name: str) -> tuple[Path, dict[str, Any]]:
    """Stage *name*, then write the units and audit an honest extraction would.

    One claim per available post, citing that post's first line exactly. Written
    here rather than committed because what is under test is the *validators*,
    and a committed expected-output would only prove that this function and that
    file still agree.
    """
    capture = load(name)
    run_dir = stage(tmp_path, capture)
    extract.initialize_run(run_dir)
    coverage = json.loads((run_dir / "coverage.json").read_text(encoding="utf-8"))

    units: list[dict[str, Any]] = []
    for entry in coverage["items"]:
        if entry["status"] != "pending":
            continue
        item = extract.posts_by_id(capture)[entry["post_id"]]
        text = extract.canonical_text(item) or ""
        end = text.index("\n") if "\n" in text else len(text)
        if end < 3:
            continue
        unit_id = f"KU-{len(units) + 1:06d}"
        units.append(
            {
                "id": unit_id,
                "kind": "fact",
                "source_class": "source",
                "content": f"What post {entry['post_id']} states in its first line.",
                "confidence": 0.9,
                "source": {
                    "post_id": entry["post_id"],
                    "start_char": 0,
                    "end_char": end,
                    "evidence_excerpt": text[:end],
                },
            }
        )
        entry["status"] = "covered"
        entry["knowledge_units"] = [unit_id]
        entry["unresolved_items"] = []

    coverage["audit_attempts"] = 1
    coverage["status"] = "PASS" if capture["coverage"]["status"] == "PASS" else "PARTIAL"
    statuses = [entry["status"] for entry in coverage["items"]]
    coverage["summary"] = {
        "total_items": len(coverage["items"]),
        "covered_items": statuses.count("covered"),
        "pending_items": statuses.count("pending"),
        "unresolved_important_items": sum(
            len(entry["unresolved_items"]) for entry in coverage["items"]
        ),
        "excluded_items": len(coverage["excluded_items"]),
    }
    knowledge = {
        "schema_version": "1.0",
        "video_id": capture["anchor"]["post_id"],
        "source_type": "twitter",
        "units": units,
    }
    (run_dir / "knowledge_units.json").write_text(dumps_json(knowledge), encoding="utf-8")
    (run_dir / "relationships.json").write_text(
        dumps_json({"schema_version": "1.0", "relationships": []}), encoding="utf-8"
    )
    (run_dir / "coverage.json").write_text(dumps_json(coverage), encoding="utf-8")
    return run_dir, capture


def test_an_audited_pass_capture_validates_as_a_passing_run(tmp_path: Path) -> None:
    run_dir, _ = audited_run(tmp_path, "pass-thread-terminal-anchor")
    result = extract.validate_run(run_dir)
    for section in ("capture", "evidence", "knowledge_units", "provenance", "relationships", "coverage"):
        assert result[section]["status"] == "PASS", (section, result[section]["errors"])
    assert result["status"] == "PASS"
    assert (run_dir / "validation.json").is_file()


def test_a_partial_capture_can_never_validate_as_a_passing_run(tmp_path: Path) -> None:
    """A run is never more complete than the evidence under it.

    ``partial-thread-dangling-chain`` is whole as far as it goes — both its
    posts are audited and cited — and it still cannot be a ``PASS``, because the
    capture names a post it could not reach. The audit being complete and the
    capture being complete are different claims.
    """
    run_dir, capture = audited_run(tmp_path, "partial-thread-dangling-chain")
    result = extract.validate_run(run_dir)
    assert capture["coverage"]["status"] == "PARTIAL"
    assert result["provenance"]["status"] == "PASS", result["provenance"]["errors"]
    assert result["coverage"]["status"] == "PASS", result["coverage"]["errors"]
    assert result["capture"]["status"] == "PASS"
    assert result["capture"]["warnings"], "the reason must be visible in the run"
    assert result["status"] == "PARTIAL"


def test_a_fail_capture_cannot_be_rescued_by_a_clean_extraction(tmp_path: Path) -> None:
    run_dir, _ = audited_run(tmp_path, "fail-unavailable-post")
    result = extract.validate_run(run_dir)
    assert result["capture"]["status"] == "FAIL"
    assert result["status"] == "FAIL"


def test_a_coverage_pass_is_refused_while_an_item_is_unaccounted_for(
    tmp_path: Path,
) -> None:
    """The T-227 acceptance clause, at the level that decides a verdict."""
    run_dir, capture = audited_run(tmp_path, "pass-thread-terminal-anchor")
    coverage = json.loads((run_dir / "coverage.json").read_text(encoding="utf-8"))
    dropped = coverage["items"].pop()
    coverage["summary"]["total_items"] -= 1
    coverage["summary"]["covered_items"] -= 1
    (run_dir / "coverage.json").write_text(dumps_json(coverage), encoding="utf-8")
    result = extract.validate_run(run_dir)
    assert result["coverage"]["status"] == "FAIL"
    error = next(
        e for e in result["coverage"]["errors"] if e["code"] == "included_post_without_coverage"
    )
    assert dropped["post_id"] in error["post_ids"]
    assert result["status"] == "FAIL"


def test_re_initializing_a_run_refuses_rather_than_discarding_an_audit(
    tmp_path: Path,
) -> None:
    run_dir, _ = audited_run(tmp_path, "pass-single-post-en")
    with pytest.raises(extract.RunAlreadyInitialized):
        extract.initialize_run(run_dir)


def test_a_capture_that_is_not_v1_is_refused(tmp_path: Path) -> None:
    run_dir = tmp_path / "output" / "1795393908886712425"
    run_dir.mkdir(parents=True)
    (run_dir / "capture.json").write_text('{"schema_version": "1.0"}', encoding="utf-8")
    with pytest.raises(extract.ExtractionError, match="not a v1 capture"):
        extract.initialize_run(run_dir)


# ---------------------------------------------------------------------------
# 6. Registration — a discoverable run must not refuse the whole project
# ---------------------------------------------------------------------------


def test_a_twitter_run_coexists_with_a_youtube_run_in_one_projection(
    tmp_path: Path,
) -> None:
    """D-227, stated as the failure it prevents.

    ``T-227`` made a Twitter run discoverable — ``io.run_dirs`` globs
    ``output/*/metadata.json`` — and nothing was registered for the source type,
    so ``get_adapter`` refused and one acquired post took down the projection of
    every YouTube run with it. The refusal is deliberate and was not weakened;
    the source type is registered instead.
    """
    import shutil

    from x2knwldg.adapters import adapt_project

    shutil.copytree(ROOT / "tests" / "fixtures" / "runs" / "pass-run", tmp_path / "output" / "pass-run")
    run_dir = stage(tmp_path, load("pass-thread-terminal-anchor"))
    extract.initialize_run(run_dir)

    records = adapt_project(tmp_path)
    by_type = {source["source_type"] for source in records.sources}
    assert by_type == {"youtube", "twitter"}
    # The YouTube run is untouched by the Twitter one being there.
    youtube = next(s for s in records.sources if s["source_type"] == "youtube")
    assert youtube["counts"]["knowledge_units"] > 0
    assert records.entities, "the YouTube run's entities must still be projected"


def test_the_twitter_source_record_validates_against_the_v1_schema(tmp_path: Path) -> None:
    """The gap that let a schema-invalid record through.

    ``counts`` is ``additionalProperties: false`` over six named keys, and this
    adapter first shipped ``{entities, relations, artifacts}`` — three keys the
    model does not define. Nothing failed: ``check_records`` enforces id
    uniqueness rather than the schema, and no existing test validates a
    *Twitter* projection. So the projection is validated here, against the same
    schema the other record families are held to.
    """
    pytest.importorskip("jsonschema")
    pytest.importorskip("referencing")
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource

    from x2knwldg.adapters import adapt_run

    # The same registry the index contract tests build: every v1 schema keyed by
    # its own `$id`, so a `$ref` resolves from disk and never over the network.
    schema_dir = ROOT / "schemas" / "v1"
    schemas = [
        json.loads(path.read_text(encoding="utf-8")) for path in sorted(schema_dir.glob("*.json"))
    ]
    registry = Registry().with_resources(
        (schema["$id"], Resource.from_contents(schema)) for schema in schemas
    )
    schema = next(s for s in schemas if s["$id"].endswith("source.schema.json"))
    validator = Draft202012Validator(schema, registry=registry)

    for name in ("pass-thread-terminal-anchor", "fail-unavailable-post", "partial-tier0-truncated-text"):
        run_dir, _ = audited_run(tmp_path / name, name)
        extract.validate_run(run_dir)
        for source in adapt_run(run_dir, tmp_path / name).sources:
            errors = sorted(validator.iter_errors(source), key=str)
            assert not errors, f"{name}: {[e.message for e in errors]}"
            # And the counts are reproducible from the canonical files, which is
            # what the schema says a cached count has to be.
            knowledge = json.loads((run_dir / "knowledge_units.json").read_text(encoding="utf-8"))
            assert source["counts"]["knowledge_units"] == len(knowledge["units"])


def test_the_twitter_projection_is_honestly_empty_rather_than_absent(
    tmp_path: Path,
) -> None:
    """A source with no knowledge attached, which is what it is until T-228.

    Zero counts and no entities is the honest projection of a run whose units
    are not yet mapped; ``adapter_metadata`` says which task owns the rest, so
    the emptiness does not read as a damaged run. What must **not** happen is a
    locator being invented here: no branch of
    ``schemas/v1/locator.schema.json`` can carry a post id and a span together,
    and D-212 hands that widening to ``T-228``.
    """
    from x2knwldg.adapters import adapt_run

    run_dir = stage(tmp_path, load("pass-quote-post"))
    extract.initialize_run(run_dir)
    records = adapt_run(run_dir, tmp_path)

    assert len(records.sources) == 1
    source = records.sources[0]
    # The six keys the model defines, and only those. `segments` is the item
    # count — a post is the segment — and `captions` is absent rather than
    # zeroed, because there are none and `0` would say a count was taken.
    assert source["counts"] == {
        "knowledge_units": 0,
        "source_units": 0,
        "derived_units": 0,
        "relationships": 0,
        "segments": 1,
    }
    assert "captions" not in source["counts"]
    assert source["artifact_ids"] == []
    assert source["adapter_metadata"]["projection"] == "source_only"
    assert source["adapter"]["version"] == "0.1"
    assert records.entities == [] and records.relations == [] and records.artifacts == []
    # A post is not a time-based medium, so there is no duration to state and
    # `0` would be a measurement rather than an absence.
    assert source["duration_sec"] is None


def test_the_projected_status_is_the_one_validation_stated(tmp_path: Path) -> None:
    """No branch may turn a stated PARTIAL into anything else (ADR 0001 invariant 2)."""
    from x2knwldg.adapters import adapt_run

    run_dir, _ = audited_run(tmp_path, "partial-thread-dangling-chain")
    result = extract.validate_run(run_dir)
    assert result["status"] == "PARTIAL"
    source = adapt_run(run_dir, tmp_path).sources[0]
    # Three verbatim copies, and `overall` is validation.json's own top-level
    # status rather than anything recomputed here.
    assert source["status"]["overall"] == "PARTIAL"
    assert source["status"]["validation"] == "PARTIAL"
    # coverage.json's own stated status, which is PARTIAL because the capture
    # under it is: the audit being complete and the capture being complete are
    # different claims, and only the second one is missing here.
    assert source["status"]["coverage"] == "PARTIAL"
    assert source["status"]["audit_attempts"] == 1


def test_an_uninitialized_capture_is_not_discoverable_at_all(tmp_path: Path) -> None:
    """Acquisition alone leaves nothing for the library to find.

    ``run_dirs`` globs ``output/*/metadata.json``, and acquisition writes none —
    so a captured post is invisible until extraction gives it one, and it can
    never appear as a broken YouTube run in the meantime.
    """
    from x2knwldg.adapters import adapt_project

    stage(tmp_path, load("pass-single-post-en"))
    assert adapt_project(tmp_path).sources == []
