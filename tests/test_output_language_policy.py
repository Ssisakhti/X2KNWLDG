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
        "prompts/twitter/01_post_extraction.md",
        "prompts/twitter/05_item_coverage_audit.md",
    )
    for relative in prompts:
        assert "Persian" in _text(relative), relative


def test_extraction_prompts_keep_evidence_and_metadata_original() -> None:
    for relative in (
        "prompts/01_segment_extraction.md",
        "prompts/twitter/01_post_extraction.md",
    ):
        text = _text(relative)
        assert "original source language" in text, relative
        assert "original form" in text, relative
