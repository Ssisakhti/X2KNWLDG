"""Regenerate the Source Map contract fixtures in this directory (``T-251``).

    .venv/bin/python tests/fixtures/source-map/build_fixtures.py

**Nothing in this directory is real evidence.** Every document here is
synthetic, and every Persian narrative line is written about the fixture itself
rather than about any real video or post. No report, answer or UI may present
this content as knowledge extracted from a source.

The documents are *generated* rather than hand-written for one reason: every
identifier and every digest in them has to be a fact about the committed runs
they cite. A hand-written fixture whose ``based_on`` names ``KU-000007`` looks
exactly like a valid one and pins nothing — the schema cannot check it, and the
test that reads it would agree with it. So this file reads
``tests/fixtures/runs/pass-run``, ``tests/fixtures/runs/partial-run`` and
``tests/fixtures/twitter-runs/quote``, takes their real unit ids, and computes
their real input digests through ``x2knwldg.synthesis`` — the same function the
`T-252` and `T-253` gates will use, so a fixture cannot drift from the rule.

Regeneration is byte-identical and is checked by CI, which is why nothing here
carries a timestamp taken from the clock.

## The invalid catalogue

The valid documents prove the contract accepts honest records. The invalid ones
are the load-bearing half, because a schema that rejects nothing is a schema
that promises nothing. Each carries a ``_fixture_note`` naming the single lie it
tells, and ``tests/test_source_map_schemas.py`` requires every one of them to be
refused — by the schema where the schema can see it, and by a stated rule where
it cannot. ``_fixture_note`` is deliberately a key the schemas reject under
``additionalProperties: false``, so the note lives in a sidecar rather than in
the document; see :func:`_write_invalid`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

FIXTURE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = FIXTURE_DIR.parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from x2knwldg import constants, ids, synthesis  # noqa: E402

RUNS_DIR = PROJECT_ROOT / "tests" / "fixtures" / "runs"
TWITTER_DIR = PROJECT_ROOT / "tests" / "fixtures" / "twitter-runs"

#: The three committed runs these fixtures are built from. Two media, and a
#: `PARTIAL` alongside a `PASS`, because "a brief may not claim a status
#: stronger than its run" is a rule that needs a run which is not `PASS` to be
#: testable at all.
YOUTUBE_RUN = RUNS_DIR / "pass-run"
YOUTUBE_PARTIAL_RUN = RUNS_DIR / "partial-run"
TWITTER_RUN = TWITTER_DIR / "quote"

#: Frozen, so regeneration is byte-identical. Obviously not a real generation
#: time — the same device `tests/fixtures/runs/build_fixtures.py` uses.
FIXTURE_TIMESTAMP = "2026-01-01T00:00:00+00:00"

FIXTURE_NOTE = (
    "Synthetic test fixture — not real evidence about any source. "
    "Regenerate with tests/fixtures/source-map/build_fixtures.py."
)


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, document: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def _source_id(run_dir: Path) -> str:
    metadata = _read(run_dir / "metadata.json")
    declared = metadata.get("source_type")
    source_type = declared if isinstance(declared, str) and declared else "youtube"
    return f"{source_type}:{metadata['video_id']}"


def _unit_ids(run_dir: Path, source_class: str | None = None) -> list[str]:
    """The run's own unit ids, read rather than assumed."""
    units = _read(run_dir / "knowledge_units.json")["units"]
    return [
        unit["id"]
        for unit in units
        if source_class is None or unit.get("source_class") == source_class
    ]


def _status(run_dir: Path) -> str:
    return _read(run_dir / "validation.json")["status"]


# --------------------------------------------------------------------------
# The valid documents
# --------------------------------------------------------------------------


def _brief(run_dir: Path, thesis: str, points: list[tuple[str, str]]) -> dict[str, Any]:
    """A ``source_knowledge.json`` whose every support id is real.

    ``based_on`` names the run's **source-class** units. A derived unit is a
    legitimate support in principle — it is knowledge of the run — but grounding
    a brief in the units that carry locators keeps the disclosure path in the
    fixture the same one the product promises: brief → knowledge unit → exact
    evidence.
    """
    support = _unit_ids(run_dir, "source")
    return {
        "schema_version": synthesis.SCHEMA_VERSION,
        "source_id": _source_id(run_dir),
        "status": _status(run_dir),
        "thesis": {"content": thesis, "based_on": support},
        "key_points": [
            {"id": point_id, "content": content, "based_on": support}
            for point_id, content in points
        ],
        "limitations_or_tensions": [],
        "generated_from": synthesis.canonical_input_digests(run_dir),
        "generated_at": FIXTURE_TIMESTAMP,
    }


def youtube_brief() -> dict[str, Any]:
    return _brief(
        YOUTUBE_RUN,
        "این منبعِ آزمایشی (test fixture) نشان می‌دهد که هر واحد دانش باید شواهدی را که بر آن "
        "تکیه دارد همراه خود بیاورد.",
        [
            (
                "SP-001",
                "ادعای بدون شاهدِ زمان‌دار، دانشِ برگرفته از منبع نیست و نباید چنین نمایش داده شود.",
            ),
            (
                "SP-002",
                "پوشش (coverage) پنجره‌به‌پنجره ممیزی می‌شود، نه یک‌جا برای کل منبع.",
            ),
        ],
    )


def twitter_brief() -> dict[str, Any]:
    return _brief(
        TWITTER_RUN,
        "این پستِ آزمایشی نقلِ قول (quote post) را همچون ارجاع در نظر می‌گیرد، نه همچون محتوایی "
        "که خودش برداشت شده باشد.",
        [
            (
                "SP-001",
                "متنِ نویسنده بایت‌به‌بایت حفظ می‌شود؛ پستِ نقل‌شده یک ارجاع است، نه یک ورودیِ "
                "برداشت (ingestion).",
            ),
        ],
    )


def partial_brief() -> dict[str, Any]:
    """A brief over a run that is not ``PASS``.

    Its ``status`` is read from the run, not chosen: the point of this fixture
    is that a `PARTIAL` brief exists, is valid, and is visibly partial.
    """
    return _brief(
        YOUTUBE_PARTIAL_RUN,
        "این منبعِ آزمایشی ناقص است: یک پنجرهٔ پوشش پس از سه تلاشِ ممیزی همچنان بی‌پوشش مانده "
        "است، و این گزارش همان وضعیت را بازگو می‌کند.",
        [
            (
                "SP-001",
                "گزارشِ برگرفته از اجرای ناقص، هرگز نباید کامل‌تر از خودِ اجرا نمایش داده شود.",
            ),
        ],
    )


def source_relations() -> dict[str, Any]:
    """One qualified YouTube↔X relation, with a basis each endpoint really owns.

    Direction is from the X post to the video, and the id is built rather than
    written down: :func:`ids.source_relation_id` over the two endpoints, the
    type and the scope. That is what makes this fixture a check on the id rule
    as well as on the record shape — a change to how the digest is computed
    moves the value here and the regeneration check notices.
    """
    from_source = _source_id(TWITTER_RUN)
    to_source = _source_id(YOUTUBE_RUN)
    relation_type = "critiques"
    scope = "partial"
    return {
        "schema_version": synthesis.SCHEMA_VERSION,
        "generated_at": FIXTURE_TIMESTAMP,
        "candidates": {
            "considered": 1,
            "omitted": 0,
            "bound": constants.MAX_SOURCE_CANDIDATES,
        },
        "relations": [
            {
                "id": ids.source_relation_id(from_source, to_source, relation_type, scope),
                "from_source_id": from_source,
                "to_source_id": to_source,
                "relation_type": relation_type,
                "scope": scope,
                "provenance_class": "derived",
                "rationale": "این پستِ آزمایشی یکی از ادعاهای مشخصِ آن ویدیوی آزمایشی را نقد "
                "می‌کند؛ گسترهٔ (scope) نسبت جزئی است، چون تنها یک جفت واحد دانش پشتیبان آن است.",
                "basis": [
                    {
                        "from_ku_id": _unit_ids(TWITTER_RUN, "source")[0],
                        "to_ku_id": _unit_ids(YOUTUBE_RUN, "source")[0],
                        "relation_type": "contradicts",
                    }
                ],
                "generated_from": {
                    "from_run_digest": synthesis.run_digest(TWITTER_RUN),
                    "to_run_digest": synthesis.run_digest(YOUTUBE_RUN),
                },
            }
        ],
    }


def empty_source_relations() -> dict[str, Any]:
    """A pass that compared a pair and emitted nothing.

    The no-relation case, and it is a fixture rather than an omission: "these
    two sources are not related" and "that pair was never compared" are
    different findings, and only the ``candidates`` block tells them apart.
    """
    return {
        "schema_version": synthesis.SCHEMA_VERSION,
        "generated_at": FIXTURE_TIMESTAMP,
        "candidates": {
            "considered": 1,
            "omitted": 0,
            "bound": constants.MAX_SOURCE_CANDIDATES,
        },
        "relations": [],
    }


def bounded_source_relations() -> dict[str, Any]:
    """A pass that hit its bound and said so.

    ``omitted`` is non-zero, which is the whole content of this fixture: risk
    R28's bound is allowed to bind, and is not allowed to bind silently.
    """
    document = source_relations()
    bound = constants.MAX_SOURCE_CANDIDATES
    document["candidates"] = {"considered": bound, "omitted": 7, "bound": bound}
    return document


# --------------------------------------------------------------------------
# The invalid catalogue — one document, one lie
# --------------------------------------------------------------------------


def _mutate(document: Any, **changes: Any) -> dict[str, Any]:
    copied = json.loads(json.dumps(document))
    copied.update(changes)
    return copied


def _relation(**changes: Any) -> dict[str, Any]:
    """The valid container with its single relation altered."""
    document = source_relations()
    document["relations"][0].update(changes)
    return document


#: A unit id that is real in this fixture corpus and is **not** held by
#: ``pass-run``. The misowned-basis case needs one: the first version of that
#: fixture used ``KU-000001``, which *both* endpoints hold, so the document it
#: produced was perfectly honest and the case tested nothing. Found by `T-253`
#: when the gate that should have refused it accepted it.
_MISOWNED_UNIT_ID = "KU-000002"


def invalid_cases() -> list[tuple[str, str, str, Any]]:
    """``(filename, refused_by, note, document)`` for every dishonest record.

    ``refused_by`` is either ``schema`` — the JSON Schema alone refuses it — or
    ``gate``, meaning it needs a second document in hand and is therefore a rule
    for the `T-252`/`T-253` apply gates. Recording which is which is the point:
    a fixture filed under ``schema`` that the schema in fact accepts is a
    contract that does not do what its README says, and the test checks the
    claim rather than trusting it.
    """
    brief = youtube_brief()
    relations = source_relations()
    real_units = _unit_ids(YOUTUBE_RUN, "source")

    cases: list[tuple[str, str, str, Any]] = []

    # ---- source_knowledge ------------------------------------------------
    cases.append((
        "brief-support-names-an-unknown-unit.json",
        "gate",
        "thesis.based_on names KU-999999, which pass-run does not hold. The "
        "schema cannot see the run, so this is the apply gate's rule; a brief "
        "citing a unit that does not exist looks checkable and is not.",
        _mutate(brief, thesis={"content": brief["thesis"]["content"], "based_on": ["KU-999999"]}),
    ))
    cases.append((
        "brief-support-is-empty.json",
        "schema",
        "thesis.based_on is an empty list — derived knowledge asserting itself "
        "while showing no work.",
        _mutate(brief, thesis={"content": brief["thesis"]["content"], "based_on": []}),
    ))
    cases.append((
        "brief-source-id-is-another-source.json",
        "gate",
        "source_id names the X run while the digests are the YouTube run's, "
        "attaching one source's account to another's evidence.",
        _mutate(brief, source_id=_source_id(TWITTER_RUN)),
    ))
    cases.append((
        "brief-status-is-stronger-than-the-run.json",
        "gate",
        "status is PASS over partial-run, whose validation.json says PARTIAL. "
        "A brief may never be more confident than the run beneath it (D-246).",
        _mutate(partial_brief(), status="PASS"),
    ))
    cases.append((
        "brief-status-is-unknown.json",
        "schema",
        "status is UNKNOWN. A brief is generated after extraction and coverage, "
        "so a run whose validators never ran has nothing to summarise.",
        _mutate(brief, status="UNKNOWN"),
    ))
    duplicate = _mutate(brief)
    duplicate["key_points"] = [
        {"id": "SP-001", "content": "نکتهٔ نخست.", "based_on": real_units},
        {"id": "SP-001", "content": "نکتهٔ دوم، با همان شناسه.", "based_on": real_units},
    ]
    cases.append((
        "brief-duplicate-point-id.json",
        "gate",
        "Two key points share SP-001. uniqueItems compares whole objects, so "
        "two points differing only in wording pass the schema; the gate "
        "compares ids.",
        duplicate,
    ))
    cases.append((
        "brief-digest-is-stale.json",
        "gate",
        "knowledge_units_sha256 is a real-looking digest that is not the file's. "
        "This is exactly what staleness detection exists to catch, so it must "
        "not be accepted as current.",
        _mutate(
            brief,
            generated_from={**brief["generated_from"], "knowledge_units_sha256": "0" * 64},
        ),
    ))
    cases.append((
        "brief-digests-are-incomplete.json",
        "schema",
        "generated_from omits coverage_sha256, leaving one input's staleness "
        "undetectable while the record looks complete.",
        _mutate(
            brief,
            generated_from={
                key: value
                for key, value in brief["generated_from"].items()
                if key != "coverage_sha256"
            },
        ),
    ))
    cases.append((
        "brief-carries-an-evidence-excerpt.json",
        "schema",
        "The thesis carries an evidence_excerpt. Excerpts live in the knowledge "
        "units and are never copied into derived narrative; "
        "additionalProperties: false makes this unrepresentable rather than "
        "merely discouraged.",
        _mutate(
            brief,
            thesis={
                "content": brief["thesis"]["content"],
                "based_on": real_units,
                "evidence_excerpt": "A knowledge unit must carry the evidence it rests on.",
            },
        ),
    ))
    cases.append((
        "brief-has-no-key-points.json",
        "schema",
        "key_points is empty. A brief with a thesis and nothing under it is a "
        "title, and the Source Map card has a section for these.",
        _mutate(brief, key_points=[]),
    ))

    # ---- source_relations -------------------------------------------------
    cases.append((
        "relation-basis-is-empty.json",
        "schema",
        "basis is empty — the whole-document verdict risk R27 names, with "
        "nothing behind it.",
        _relation(basis=[]),
    ))
    cases.append((
        "relation-basis-unit-belongs-to-the-other-endpoint.json",
        "gate",
        "to_ku_id names KU-000002, which is a real unit id elsewhere in the "
        "fixture corpus and is not one the to-endpoint's run holds. Well-formed, "
        "plausible, and checkable only with both runs in hand — which is why it "
        "is the gate's rule and not the schema's.",
        _relation(
            basis=[
                {
                    "from_ku_id": _unit_ids(TWITTER_RUN, "source")[0],
                    "to_ku_id": _MISOWNED_UNIT_ID,
                    "relation_type": "contradicts",
                }
            ]
        ),
    ))
    cases.append((
        "relation-carries-a-confidence.json",
        "schema",
        "A confidence nothing produced. It is not merely omitted from the "
        "contract, it is unrepresentable (D-247).",
        _relation(confidence=0.9),
    ))
    cases.append((
        "relation-type-is-a-knowledge-unit-type.json",
        "schema",
        "relation_type is 'causes' — a KU-level canonical type, not one of the "
        "eight source-level ones. The two vocabularies stay apart.",
        _relation(relation_type="causes"),
    ))
    cases.append((
        "relation-scope-invents-a-percentage.json",
        "schema",
        "scope is '80%'. Scope qualifies the claim, it does not measure it.",
        _relation(scope="80%"),
    ))
    cases.append((
        "relation-provenance-claims-source.json",
        "schema",
        "provenance_class is 'source'. Every automatic source relation is "
        "derived, explicitly_references included.",
        _relation(provenance_class="source"),
    ))
    cases.append((
        "relation-joins-a-source-to-itself.json",
        "gate",
        "Both endpoints are the same source. ids.source_relation_id refuses to "
        "mint an id for this, so the record cannot even acquire the id its "
        "schema requires — the id here is the one for the honest pair.",
        _relation(from_source_id=_source_id(YOUTUBE_RUN)),
    ))
    cases.append((
        "relation-id-does-not-match-its-parts.json",
        "gate",
        "A well-formed SR- id that is not the digest of this record's "
        "endpoints, type and scope. A pattern check is a shape check; only "
        "recomputing the digest catches this.",
        _relation(id="SR-0123456789abcdef"),
    ))
    cases.append((
        "relation-has-no-rationale.json",
        "schema",
        "rationale is missing. A relation with grounds and no stated reason "
        "leaves the aggregation unexplained.",
        _mutate_relation_without(relations, "rationale"),
    ))
    cases.append((
        "relation-digests-are-missing.json",
        "schema",
        "generated_from omits to_run_digest, so half the pair can change "
        "without the relation ever going stale.",
        _mutate_relation_without(relations, "generated_from"),
    ))
    cases.append((
        "container-omits-the-candidate-counts.json",
        "schema",
        "candidates is missing, so an empty or short relations list cannot be "
        "told from a pair that was never compared (risk R28).",
        {
            key: value
            for key, value in empty_source_relations().items()
            if key != "candidates"
        },
    ))
    cases.append((
        "container-duplicates-a-relation-id.json",
        "gate",
        "Two records share one SR- id while differing in rationale. uniqueItems "
        "compares whole records, so the schema accepts it and the gate must not.",
        _duplicate_relation_id(),
    ))
    return cases


def _mutate_relation_without(container: dict[str, Any], field: str) -> dict[str, Any]:
    document = json.loads(json.dumps(container))
    document["relations"][0].pop(field, None)
    return document


def _duplicate_relation_id() -> dict[str, Any]:
    document = source_relations()
    twin = json.loads(json.dumps(document["relations"][0]))
    twin["rationale"] = "همان شناسه، با دلیلی متفاوت — که یعنی دو رکورد برای یک نسبت."
    document["relations"].append(twin)
    return document


# --------------------------------------------------------------------------
# Writing
# --------------------------------------------------------------------------


def _write_invalid(name: str, refused_by: str, note: str, document: Any) -> None:
    """The document itself, plus a sidecar naming the lie.

    The note cannot live inside the document: every schema here sets
    ``additionalProperties: false``, so a ``_fixture_note`` key would make the
    record invalid *for the wrong reason* and the fixture would stop testing
    what it was written to test. A sidecar keeps the document exactly as
    dishonest as it is meant to be.
    """
    _write(FIXTURE_DIR / "invalid" / name, document)
    _write(
        FIXTURE_DIR / "invalid" / f"{name[:-5]}.note.json",
        {"fixture": True, "fixture_note": FIXTURE_NOTE, "refused_by": refused_by, "lie": note},
    )


def build() -> None:
    _write(FIXTURE_DIR / "valid" / "youtube-source_knowledge.json", youtube_brief())
    _write(FIXTURE_DIR / "valid" / "twitter-source_knowledge.json", twitter_brief())
    _write(FIXTURE_DIR / "valid" / "partial-source_knowledge.json", partial_brief())
    _write(FIXTURE_DIR / "valid" / "synthesis" / "source_relations.json", source_relations())
    _write(
        FIXTURE_DIR / "valid" / "synthesis" / "source_relations.empty.json",
        empty_source_relations(),
    )
    _write(
        FIXTURE_DIR / "valid" / "synthesis" / "source_relations.bounded.json",
        bounded_source_relations(),
    )
    for name, refused_by, note, document in invalid_cases():
        _write_invalid(name, refused_by, note, document)


def main() -> int:
    build()
    written = sorted(
        path.relative_to(PROJECT_ROOT).as_posix()
        for path in FIXTURE_DIR.rglob("*.json")
    )
    print(f"wrote {len(written)} fixture documents under {FIXTURE_DIR.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
