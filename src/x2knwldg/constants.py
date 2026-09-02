SOURCE_KINDS = {
    "claim",
    "evidence",
    "fact",
    "statistic",
    "concept",
    "definition",
    "framework",
    "principle",
    "process",
    "instruction",
    "recommendation",
    "example",
    "case_study",
    "analogy",
    "caveat",
    "limitation",
    "assumption",
    "counterargument",
    "question",
    "open_problem",
    "reference",
    "quote",
}

DERIVED_KINDS = {
    "relationship",
    "implication",
    "generalized_rule",
    "mental_model",
    "diagnostic_model",
    "actionable_experiment",
    "hypothesis",
    "synthesis",
}

KNOWLEDGE_KINDS = SOURCE_KINDS | DERIVED_KINDS

RELATION_TYPES = {
    "supports",
    "contradicts",
    "causes",
    "contributes_to",
    "depends_on",
    "enables",
    "inhibits",
    "exemplifies",
    "is_example_of",
    "is_evidence_for",
    "refines",
    "qualifies",
    "is_part_of",
    "precedes",
    "results_in",
    "related_to",
}

OMISSION_REASONS = {
    "intro_noninformational",
    "sponsor",
    "small_talk",
    "transition",
    "repetition",
    "housekeeping",
    "audience_reaction",
    "unintelligible",
    "off_topic",
    "other_explained",
}

COVERAGE_STATUSES = {"pending", "covered", "uncovered", "omitted", "partial"}


# The workflow allows at most three total coverage-repair audit attempts
# (CLAUDE.md, WORKFLOW.md, prompts/05). validators.py enforces it.
MAX_AUDIT_ATTEMPTS = 3

# --------------------------------------------------------------------------
# Timing contract — one home per number
#
# These are the numbers the workflow states about *time*, and each one had
# been restated at its point of use. A duplicated bound is a bound that can
# disagree with itself, so they follow the precedent MAX_AUDIT_ATTEMPTS set:
# defined once here, imported everywhere, never re-typed as a literal.
# --------------------------------------------------------------------------

# Segmentation (segmenter.create_segments, pipeline.import_transcript).
# The four are coupled: SEGMENT_OVERLAP_SEC < SEGMENT_MIN_SEC <=
# SEGMENT_TARGET_SEC <= SEGMENT_MAX_SEC. create_segments re-checks the
# relation on whatever it is actually given.
SEGMENT_TARGET_SEC = 240
SEGMENT_MIN_SEC = 120
SEGMENT_MAX_SEC = 360
SEGMENT_OVERLAP_SEC = 15

# Coverage window width (coverage.create_pending_coverage). Written into
# coverage.json as `window_size_sec`, so its type is part of the file format:
# keep it an int, or every stored document gains a `.0`.
COVERAGE_WINDOW_SEC = 300

# The largest silence between consecutive captions that is not reported as a
# transcript gap (transcripts.transcript_integrity).
MAX_CAPTION_GAP_SEC = 120

# Float tolerance for comparing two times in seconds. Timestamps are parsed
# from millisecond-resolution text and re-serialised through JSON, so an exact
# == on two seconds values is a coin flip. Six independent copies of an epsilon
# are six chances for two comparisons to disagree about whether the same pair
# of times matches, so there is one.
TIME_TOLERANCE_SEC = 0.01

#: The most rows any *remote* surface hands back for one request.
#:
#: Defect D-101: `server/params.py` capped a page at 500 and the MCP tool
#: capped nothing — `query.search_knowledge` floor-checks `limit` and says, in
#: as many words, that it has no ceiling on purpose, because a local CLI search
#: is bounded by the corpus. That reasoning is right for the CLI and wrong for
#: a tool an agent calls: `limit=10**18` returned the entire corpus in one
#: reply. Two bounds for the same data was the defect, so the bound lives here
#: and both surfaces read it.
MAX_PAGE_LIMIT = 500
