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
