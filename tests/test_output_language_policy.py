"""Regression guard for the project's permanent output-language contract."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _text(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_canonical_agent_guides_state_the_persian_output_policy() -> None:
    for relative in ("WORKFLOW.md", "AGENTS.md", "CLAUDE.md"):
        text = _text(relative)
        assert "output-language policy" in text
        assert "Persian" in text
        assert "evidence_excerpt" in text
        assert "source titles" in text


def test_every_model_pass_carries_the_language_policy() -> None:
    prompts = (
        "prompts/01_segment_extraction.md",
        "prompts/02_normalize_deduplicate.md",
        "prompts/03_relationships.md",
        "prompts/04_derived_synthesis.md",
        "prompts/05_coverage_audit.md",
        # `T-252`. Not a bundle pass — it writes the readable brief — but it is
        # a pass that produces narrative, which is exactly what this policy
        # governs. The permanent policy applies to "every model pass, supported
        # source type, report, graph label, and vault note", so a pass added
        # without it is the gap this test exists to catch.
        "prompts/06_source_knowledge.md",
        # `T-253`. Its narrative field is one `rationale` per relation, and it
        # is governed by the same permanent policy as every other pass.
        "prompts/07_source_relations.md",
        "prompts/twitter/01_post_extraction.md",
        "prompts/twitter/05_item_coverage_audit.md",
    )
    for relative in prompts:
        assert "Persian" in _text(relative), relative


def test_the_brief_pass_states_the_policy_it_is_most_likely_to_break() -> None:
    """The brief is the one narrative artifact with no evidence beside it.

    Every other pass writes units that carry an excerpt in the source language,
    so the separation is visible in the output itself. A brief carries none —
    it is Persian narrative all the way down — which makes it the pass where
    "write this in Persian" and "never copy an excerpt here" are easiest to
    lose, and therefore the pass that has to say both out loud.
    """
    text = _text("prompts/06_source_knowledge.md")
    assert "Persian" in text
    assert "Persian technical terminology" in text
    assert "evidence_excerpt" in text
    assert "derived knowledge" in text


def test_extraction_prompts_keep_evidence_and_metadata_original() -> None:
    for relative in (
        "prompts/01_segment_extraction.md",
        "prompts/twitter/01_post_extraction.md",
    ):
        text = _text(relative)
        assert "original source language" in text, relative
        assert "original form" in text, relative


# ---------------------------------------------------------------------------
# The rule itself, exercised
# ---------------------------------------------------------------------------
#
# Everything above reads prose. That was the whole of this file for as long as
# it has existed: nine prompts and three guides were asserted to contain the
# word "Persian", and the validator that actually refuses English narrative was
# never called. A guard named for a policy has to touch the thing that enforces
# it, or the policy is enforced by whatever a model felt like doing and the
# green tick means only that a word appears in a file.
#
# It reaches two fields, and that is the honest extent of it. `WORKFLOW.md`
# says which two and says plainly that the rest is policy no exit code covers;
# the last test here is what keeps that paragraph in the file.


def test_an_english_source_brief_is_refused() -> None:
    """`validate_source_knowledge`, over a statement with no Perso-Arabic character."""
    from x2knwldg.validators import validate_source_knowledge

    def brief(thesis: str) -> dict[str, object]:
        return {
            "schema_version": "1.0",
            "source_id": "youtube:fixture-pass",
            "status": "PASS",
            "thesis": {"content": thesis, "based_on": ["KU-000001"]},
            "key_points": [
                {"id": "SP-001", "content": thesis, "based_on": ["KU-000001"]}
            ],
            "limitations_or_tensions": [],
            "generated_from": {
                "knowledge_units_sha256": "0" * 64,
                "relationships_sha256": "1" * 64,
                "coverage_sha256": "2" * 64,
            },
            "generated_at": "2026-01-01T00:00:00+00:00",
        }

    arguments = {
        "unit_ids": {"KU-000001"},
        "source_id": "youtube:fixture-pass",
        "run_status": "PASS",
        "current_digests": {
            "knowledge_units_sha256": "0" * 64,
            "relationships_sha256": "1" * 64,
            "coverage_sha256": "2" * 64,
        },
    }

    english = validate_source_knowledge(
        brief("This source argues that evidence must be preserved verbatim."), **arguments
    )
    assert "narrative_not_in_persian_script" in {
        error["code"] for error in english["errors"]
    }

    persian = validate_source_knowledge(
        brief("این منبع استدلال می‌کند که شواهد باید عیناً حفظ شوند."), **arguments
    )
    assert persian == {"status": "PASS", "errors": [], "warnings": []}


def test_a_persian_brief_may_carry_an_english_term_in_parentheses() -> None:
    """The spelling the policy asks for must not be what the guard refuses.

    A script check that rejected mixed text would forbid exactly the form
    `CLAUDE.md`, `AGENTS.md` and `WORKFLOW.md` all instruct: the Persian term
    with the English one beside it.
    """
    from x2knwldg.validators import _narrative_script_error

    assert _narrative_script_error("پوشش (coverage) کامل است", "thesis") is None
    assert _narrative_script_error("coverage is complete", "thesis") is not None


def test_an_english_relation_rationale_is_refused() -> None:
    """`validate_source_relations`, over the one narrative field a relation has.

    Asserted as *this code is present* rather than over a whole verdict: the
    container here is deliberately minimal, so other errors may stand beside
    the one this file is about.
    """
    from x2knwldg.ids import source_relation_id
    from x2knwldg.validators import validate_source_relations

    from_source, to_source = "twitter:2094039408081068233", "youtube:fixture-pass"

    def container(rationale: str) -> dict[str, object]:
        return {
            "schema_version": "1.0",
            "generated_at": "2026-01-01T00:00:00+00:00",
            "candidates": {"considered": 1, "omitted": 0, "bound": 25},
            "relations": [
                {
                    "id": source_relation_id(from_source, to_source, "critiques", "partial"),
                    "from_source_id": from_source,
                    "to_source_id": to_source,
                    "relation_type": "critiques",
                    "scope": "partial",
                    "provenance_class": "derived",
                    "rationale": rationale,
                    "basis": [
                        {
                            "from_ku_id": "KU-000001",
                            "to_ku_id": "KU-000002",
                            "relation_type": "contradicts",
                        }
                    ],
                    "generated_from": {
                        "from_run_digest": "a" * 64,
                        "to_run_digest": "b" * 64,
                    },
                }
            ],
        }

    arguments = {
        "units_by_source": {
            from_source: frozenset({"KU-000001"}),
            to_source: frozenset({"KU-000002"}),
        },
        "digests_by_source": {from_source: "a" * 64, to_source: "b" * 64},
        "considered_pairs": frozenset({(from_source, to_source)}),
        "explicit_reference_pairs": frozenset(),
        "candidate_counts": {"considered": 1, "omitted": 0, "bound": 25},
    }

    english = validate_source_relations(
        container("This thread critiques a claim the video makes."), **arguments
    )
    assert "narrative_not_in_persian_script" in {
        error["code"] for error in english["errors"]
    }

    persian = validate_source_relations(
        container("این رشته یکی از ادعاهای آن ویدیو را نقد می‌کند."), **arguments
    )
    assert "narrative_not_in_persian_script" not in {
        error["code"] for error in persian["errors"]
    }


def test_the_workflow_states_which_fields_are_machine_checked() -> None:
    """The boundary is documented, so it cannot be read as "all of them".

    `validators._narrative_script_error` has two call sites and the policy
    lists six field families. Stating that difference out loud is the honest
    alternative to a guard that does not exist, and this is what stops the
    paragraph being deleted as pessimistic.
    """
    workflow = _text("WORKFLOW.md")
    assert "What a validator checks, and what it does not" in workflow
    for named in ("_narrative_script_error", "validate_source_knowledge", "validate_source_relations"):
        assert named in workflow, named
    # And the fields it does *not* reach, named rather than implied.
    for unchecked in ("`normalized_statement`", "`derivation_note`"):
        assert unchecked in workflow, unchecked
