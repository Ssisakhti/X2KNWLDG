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

#: The eight source-to-source relation types of `SOURCE_MAP_SPEC.md` §3.3, and
#: only those (`T-251`, D-247).
#:
#: Deliberately **not** `RELATION_TYPES`. That vocabulary connects two knowledge
#: units inside one run; this one connects two whole acquired sources, and the
#: two questions are not the same size. `supports` and `contradicts` appear in
#: both and mean different things in each: a unit supporting a unit is a claim
#: about two sentences, a source supporting a source is an aggregation over many
#: pairs whose honesty depends on the basis carried with it. Merging the two
#: lists would let a KU-level edge be read as a whole-source verdict, which is
#: risk **R27** stated as a data model.
#:
#: `explicitly_references` is in here and is still `derived` provenance: the
#: cited link may be source-grounded, but promoting it to a source-to-source
#: relation is an aggregation the sources themselves never made.
SOURCE_RELATION_TYPES = {
    "explicitly_references",
    "responds_to",
    "critiques",
    "supports",
    "contradicts",
    "extends",
    "applies",
    "overlaps_with",
}

#: How much of the two sources a relation's basis supports. Two values, and no
#: third: `scope` qualifies the claim, it does not measure it. A percentage
#: would be a number nothing produced (D-247).
SOURCE_RELATION_SCOPES = {"partial", "broad"}

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
    # T-227. An *included* post that was never observed — a tombstone — has no
    # content to audit, and the omission is minted by
    # `twitter.extract.create_pending_coverage` rather than chosen by an
    # auditor. `other_explained` is the right value for a judgement call and the
    # wrong one for a case the pipeline generates on every such run: "explain
    # yourself" invites a different sentence each time for one structural fact.
    "source_unavailable",
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

#: The most edges any one graph response carries.
#:
#: Defect D-175: `limit` bounded the *nodes* and nothing bounded the edges, and
#: the two are not the same size — an edge list is quadratic in the nodes it
#: connects. `GraphPayload.edges` declared no `maxItems`, so one unauthenticated
#: `GET` returned an arbitrarily large body built entirely in memory: on a
#: 600-node all-pairs index, `limit=500` produced **349,500 edges in an 83 MB
#: response at 265 MB peak allocation**, with `page.total: 600` giving the
#: client no signal that anything was unusual. The Map cannot draw that many
#: edges either, so this is a bound the reader was already living inside.
#:
#: `truncated` is what says the graph was cut, and it already means exactly
#: that: "a slice of a larger graph", stated rather than implied.
MAX_GRAPH_EDGES = 5000

#: The most candidate counterpart sources one source's synthesis pass compares.
#:
#: Risk **R28**: candidate discovery grows quadratically. An all-pairs walk over
#: *n* sources is ``n(n-1)`` ordered comparisons, each of them a model pass over
#: two whole knowledge-unit sets — so the cost is not the pair count but the
#: knowledge-unit pairs behind it. Measured on this corpus with
#: ``tools/measure_source_bounds.py`` on 2026-09-05: **12 sources, 63 knowledge
#: units, 0–33 per source — 132 ordered source pairs and 2,718 knowledge-unit
#: pairs, the largest single pair being 363.**
#:
#: 25 leaves every source in that corpus fully compared — 11 candidates each,
#: well inside the bound — and starts binding at 27 sources, which is where a
#: growing library would otherwise start paying quadratically. The bound is
#: never silent: a synthesis run reports ``candidates_considered`` and
#: ``candidates_omitted``, because "we did not look" and "there was nothing
#: there" are different statements and only one of them is true.
MAX_SOURCE_CANDIDATES = 25

#: The most basis entries one relation carries in one response.
#:
#: Risk **R27**: a source edge overclaims a whole-source verdict. The basis is
#: what keeps ``critiques`` from meaning "these two sources disagree" — it names
#: the knowledge-unit pairs the claim rests on. Measured with the same tool on
#: the same corpus: one basis entry built from the widest real identifier
#: serializes to **89 bytes**, so **368** of them fit the 32 KiB budget a
#: relation-detail response is measured against — an order of magnitude under
#: `MAX_GRAPH_EDGES`, because this is one detail panel rather than a whole graph.
#:
#: 200 sits inside that budget at 17,800 bytes and above the largest
#: knowledge-unit pair product any two sources in the corpus can even form
#: except one (363). A basis wider than this has stopped qualifying a relation
#: and started restating the source, which is the overclaim R27 names. Where it
#: does bind, ``basis_total`` and ``basis_returned`` are both required in the
#: response: a truncated basis is stated, never implied.
MAX_SOURCE_RELATION_BASIS = 200

#: D-030's error taxonomy, as the closed ``ErrorCode`` vocabulary the frozen
#: `schemas/api/v1/openapi.json` publishes.
#:
#: Defect D-184: this lived in `server/envelope.py` and a *second* list lived in
#: `mcp_server.py`, both described as "D-030's taxonomy", and they already
#: disagreed — the MCP server said `internal_error` where the envelope and the
#: frozen enum both say `internal`. No test imported both, so nothing could see
#: it, and an agent reading an MCP reply got a code outside the vocabulary the
#: HTTP contract publishes. It lives here for the same reason `MAX_PAGE_LIMIT`
#: does: two statements of one fact was the defect, so the fact has one home and
#: both surfaces read it. `server/envelope.py` re-exports it, so every existing
#: import keeps working.
ERROR_CODES = (
    "invalid_id",
    "invalid_request",
    "not_found",
    "unavailable",
    "index_unavailable",
    "internal",
)
