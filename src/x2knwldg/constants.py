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

