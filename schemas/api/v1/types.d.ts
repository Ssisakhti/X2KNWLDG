/**
 * X2KNWLDG local API — v1 TypeScript declarations.
 *
 * GENERATED FILE — do not edit by hand.
 * Source:    schemas/api/v1/openapi.json and schemas/v1/*.schema.json
 * Regenerate: python tools/generate_api_types.py
 * Guarded by: tests/test_api_types.py, which fails if this file is stale.
 *
 * Three cross-field invariants are beyond both JSON Schema and TypeScript and are
 * enforced by src/x2knwldg/ids.py at the point records are produced:
 * a global_id equals source_type:external_id:local_id, a Source.id equals
 * source_type:external_id, and a time_range locator does not end before it starts.
 */

// -------------------------------------------------------------------------
// Shared primitives — schemas/v1/common.schema.json
// -------------------------------------------------------------------------

/**
 * Version of the index model this record conforms to. Bumped only by a new schemas/<version>/
 * directory.
 */
export type SchemaVersion = "1.0";

/**
 * Adapter namespace. Lowercase, snake_case. Open by design: adding a source type must not
 * require a schema change. Known values in v1: youtube (implemented); twitter, medium,
 * article, pdf, file (planned); library (reserved for cross-source library entities such as
 * canonical concepts).
 */
export type SourceType = string;

/**
 * One URL-safe segment of an identifier. Colons are excluded so identifiers split
 * unambiguously, and a leading dot is excluded so no segment can be '.' or '..'. A leading '-'
 * or '_' is allowed: a YouTube video id is base64url and legitimately begins with either, and
 * pipeline.py already accepts [0-9A-Za-z_-]{11} at ingestion (widened in T-003, D-017).
 */
export type IdPart = string;

/**
 * Two-part source identifier: <source-type>:<external-id>. Identifies a Source, not an entity
 * inside it.
 */
export type SourceId = string;

/**
 * Three-part global entity identifier (D-011): <source-type>:<external-id>:<local-id>.
 * Identity for the index, the API, and board files. Parse with a two-limit split on ':'.
 */
export type GlobalId = string;

/**
 * Identifier exactly as it appears in output/library/graph.json. Two-part <video-
 * id>:<knowledge-unit-id> for knowledge units, or concept:<hash> for canonical concepts.
 * Mandated by .claude/commands/kg_navigator.md and emitted by library.py:49. Carried alongside
 * globalId so the two vocabularies cannot drift (ADR 0001 invariant 4).
 */
export type LibraryId = string;

/**
 * Origin of an entity or relation. 'source' is directly supportable from the source, 'derived'
 * is recorded synthesis, 'user' is manual workspace content. Never signalled by colour alone
 * in the UI (ADR 0001 invariant 10). A 'user' record is never written into a canonical file.
 */
export type ProvenanceClass = "source" | "derived" | "user";

/**
 * Run status as reported by the canonical validator files. UNKNOWN means the file is absent or
 * unreadable — it must never be substituted with PASS, and PARTIAL/FAIL must never be coerced
 * upward (ADR 0001 invariant 2).
 */
export type RunStatus = "PASS" | "PARTIAL" | "FAIL" | "UNKNOWN";

/**
 * Confidence copied verbatim from canonical data. Never invented, never defaulted.
 */
export type Confidence = number;

/**
 * Seconds from the start of the media.
 */
export type TimestampSec = number;

/**
 * Path relative to the project root, using forward slashes. Absolute paths and parent
 * traversal are rejected: output/library/status.json and videos.json contain absolute host
 * paths, which the index must never store or trust (risk R15).
 */
export type ProjectRelativePath = string;

export type Sha256 = string;

export type IsoTimestamp = string;

/**
 * Which adapter produced this record, so a stale record can be traced to the code that wrote
 * it.
 */
export type AdapterRef = {
  name: string;
  version: string;
};

/**
 * The 16 relation types of src/x2knwldg/constants.py RELATION_TYPES. Mirrored here
 * deliberately; tests/test_index_schemas.py asserts the two stay identical.
 */
export type CanonicalRelationType = "supports" | "contradicts" | "causes" | "contributes_to" | "depends_on" | "enables" | "inhibits" | "exemplifies" | "is_example_of" | "is_evidence_for" | "refines" | "qualifies" | "is_part_of" | "precedes" | "results_in" | "related_to";

/**
 * Edges synthesised by library.py that are deliberately NOT in RELATION_TYPES. In the current
 * data they are the two most common edges in output/library/graph.json (45 derived_from, 17
 * expresses_concept of 118).
 */
export type LibrarySyntheticRelationType = "derived_from" | "expresses_concept";

/**
 * The 22 source kinds plus the 8 derived kinds of constants.py, plus canonical_concept as
 * emitted by library.py for concept nodes. Drift-tested against constants.py.
 */
export type KnowledgeKind = "claim" | "evidence" | "fact" | "statistic" | "concept" | "definition" | "framework" | "principle" | "process" | "instruction" | "recommendation" | "example" | "case_study" | "analogy" | "caveat" | "limitation" | "assumption" | "counterargument" | "question" | "open_problem" | "reference" | "quote" | "relationship" | "implication" | "generalized_rule" | "mental_model" | "diagnostic_model" | "actionable_experiment" | "hypothesis" | "synthesis" | "canonical_concept";

// -------------------------------------------------------------------------
// Index records — the response bodies, as the adapters produce them
// -------------------------------------------------------------------------

/**
 * A primary source that has been ingested by the pipeline: one output/<source-id>/ directory
 * viewed through an adapter. Canvas plan §10.1. This record is a derived index projection; the
 * canonical directory remains the source of truth.
 */
export type Source = {
  schema_version: SchemaVersion;
  /**
   * Two-part <source_type>:<external_id>. Must equal the join of those two fields; enforced by
   * test, not expressible in JSON Schema.
   */
  id: SourceId;
  source_type: SourceType;
  /**
   * The id in the source system. For YouTube this is metadata.json video_id, which stays named
   * video_id in every canonical file (ADR 0001 invariant 6).
   */
  external_id: IdPart;
  /**
   * Canonical URL of the source, or null when the source has none. Never fabricated.
   */
  url?: string | null;
  title?: string | null;
  /**
   * Publisher or author as recorded by the adapter — YouTube channel, Twitter/X handle, Medium
   * author. Null when the canonical metadata does not carry one.
   */
  author?: string | null;
  /**
   * Language tag copied from canonical metadata. Not normalised, not guessed.
   */
  language?: string | null;
  /**
   * Media duration for time-based sources; null for text sources.
   */
  duration_sec?: number | null;
  imported_at?: IsoTimestamp | null;
  extracted_at?: IsoTimestamp | null;
  /**
   * Project-relative path of output/<source-id>/. Read-only to the UI; raw/ inside it is
   * immutable evidence (ADR 0001 invariant 1).
   */
  canonical_dir: ProjectRelativePath;
  /**
   * Run status, read from the canonical validator files only. Never recomputed, never inferred,
   * never coerced toward PASS (ADR 0001 invariant 2).
   */
  status: {
    /**
     * The 'status' field of validation.json, verbatim. UNKNOWN when the file is missing or
     * unreadable.
     */
    validation: RunStatus;
    /**
     * The 'status' field of coverage.json, verbatim.
     */
    coverage: RunStatus;
    /**
     * The top-level 'status' of validation.json, which already aggregates all five sections
     * including coverage. Copied, not derived.
     */
    overall: RunStatus;
    /**
     * coverage.json audit_attempts, verbatim. Capped at 3 by WORKFLOW.md.
     */
    audit_attempts?: number | null;
    validation_path?: ProjectRelativePath | null;
    coverage_path?: ProjectRelativePath | null;
  };
  /**
   * Cached counts for list rendering. A cache convenience only: every count must be reproducible
   * from the canonical files, and a stale count is a bug, never a data achievement.
   */
  counts?: {
    knowledge_units?: number;
    source_units?: number;
    derived_units?: number;
    relationships?: number;
    captions?: number;
    segments?: number;
  };
  /**
   * Global ids of the artifacts belonging to this source.
   */
  artifact_ids?: Array<GlobalId>;
  adapter: AdapterRef;
  /**
   * Source-specific fields the generic model does not model — for YouTube: transcript_source,
   * transcript_hash, pipeline_version, extraction. Free-form on purpose: an adapter must never
   * be forced to drop canonical metadata, and must never be tempted to smuggle it into a typed
   * field where it does not belong.
   */
  adapter_metadata?: Record<string, unknown>;
};

/**
 * One representation or file belonging to a Source — a canonical pipeline file, an immutable
 * raw evidence file, or a remote medium such as a YouTube video. Canvas plan §10.2. An
 * artifact that does not exist locally is reported as unavailable; a missing artifact is never
 * masked with a placeholder or fabricated data (canvas plan §15).
 *
 * Runtime invariants, enforced by the adapter and by the schemas — not by these types:
 * - An artifact must be locatable: a local path, a remote URL, or both.
 * - role 'raw' implies immutable.
 * - role 'external' has no local path.
 */
export type Artifact = {
  schema_version: SchemaVersion;
  /**
   * Three-part global id, local part naming the artifact — e.g. youtube:pqlWNihgdjI:transcript.
   */
  id: GlobalId;
  source_id: SourceId;
  /**
   * What the artifact is. Grounded in the files the pipeline actually writes plus the media
   * types planned for later phases. 'capture' and 'post' were added additively by T-228 (D-233):
   * a Twitter run's evidence is capture.json rather than a transcript, and each item inside it
   * is addressed as an artifact of its own so that a claim can cite a text_span into the post it
   * came from. 'post' is the item, not the file - it is role 'external' with no path, the way
   * 'video' already is. 'source_knowledge' was added the same way by T-252 (D-246): a run's
   * readable Persian brief, written through its own apply gate after extraction and coverage. It
   * is derived knowledge rather than evidence, and it is optional - a run that has none is the
   * normal state and stays so, which is why the adapters omit the record entirely rather than
   * listing it unavailable on every run forever (D-257).
   */
  kind: "metadata" | "raw_source" | "raw_transcript" | "transcript" | "segments" | "capture" | "post" | "knowledge_units" | "relationships" | "graph" | "coverage" | "validation" | "source_knowledge" | "report" | "extraction_bundle" | "vault_note" | "video" | "audio" | "image" | "pdf" | "article";
  /**
   * Storage tier and mutability class. 'raw' is immutable evidence under output/<id>/raw/.
   * 'canonical' is pipeline output under output/<id>/. 'work' is intermediate pipeline scratch.
   * 'export' is a generated view such as a vault note. 'external' has no local file — it lives
   * at a URL.
   */
  role: "raw" | "canonical" | "work" | "export" | "external";
  /**
   * IANA media type when known; null rather than a guess.
   */
  media_type?: string | null;
  /**
   * Project-relative path, or null for an external artifact. Never an absolute host path (risk
   * R15).
   */
  path?: ProjectRelativePath | null;
  /**
   * Remote location, or null. For a YouTube video this is the watch URL: there is no local media
   * file and the UI must never assume one exists.
   */
  url?: string | null;
  bytes?: number | null;
  /**
   * Content hash from io.sha256_file, used for incremental indexing. Null when not hashed or not
   * local.
   */
  sha256?: Sha256 | null;
  /**
   * True for every artifact with role 'raw'. Nothing in the UI or API may write to an immutable
   * artifact (ADR 0001 invariant 1).
   */
  immutable: boolean;
  /**
   * Whether the artifact was present at index time. False is displayed honestly as missing.
   */
  available: boolean;
  indexed_at?: IsoTimestamp | null;
};

/**
 * time_range — implemented in v1
 *
 * Seconds into a time-based medium. end_sec must be greater than or equal to start_sec; JSON
 * Schema cannot compare two fields, so that bound is asserted in tests/test_index_schemas.py
 * and must be enforced by the adapter.
 */
export type LocatorTimeRange = {
  type: "time_range";
  artifact_id?: GlobalId;
  start_sec: TimestampSec;
  end_sec: TimestampSec;
  /**
   * Canonical segment id (segments.json) or caption id (transcript.json) the range came from.
   */
  segment_id?: string;
  /**
   * Verbatim evidence excerpt from the canonical source object. Never paraphrased, never empty.
   */
  excerpt?: string;
};

/**
 * page — reserved
 */
export type LocatorPage = {
  type: "page";
  artifact_id?: GlobalId;
  page: number;
};

/**
 * page_bbox — reserved
 *
 * bbox is [x0, y0, x1, y1] in the page coordinate system of the document.
 */
export type LocatorPageBbox = {
  type: "page_bbox";
  artifact_id?: GlobalId;
  page: number;
  bbox: Array<number>;
};

/**
 * text_span — reserved
 *
 * Half-open character range [start_char, end_char) into the addressed artifact's text.
 */
export type LocatorTextSpan = {
  type: "text_span";
  artifact_id: GlobalId;
  start_char: number;
  end_char: number;
  excerpt?: string;
};

/**
 * post_id — reserved
 */
export type LocatorPostId = {
  type: "post_id";
  artifact_id?: GlobalId;
  post_id: IdPart;
};

/**
 * url_fragment — reserved
 */
export type LocatorUrlFragment = {
  type: "url_fragment";
  artifact_id?: GlobalId;
  url: string;
  fragment: string;
};

/**
 * The precise location of evidence or an anchor inside an artifact. Canvas plan §10.3. A
 * Locator must never be constructed without canonical data: every branch requires its
 * coordinates outright, nulls are not accepted, no field has a default, and each branch is
 * closed so a coordinate belonging to another locator type cannot ride along. In v1 only
 * 'time_range' is produced — the remaining types are reserved so that adding PDFs, articles,
 * or posts needs no schema version bump. 'type' is the discriminator: the branches are written
 * as if/then rather than oneOf so a failure names the real cause instead of reporting that six
 * alternatives all failed. TypeScript generation (T-005) should treat 'type' as the
 * discriminated-union tag. Each branch repeats 'type' and 'artifact_id' rather than sharing
 * them by reference, because 'additionalProperties' does not see through a $ref.
 */
export type Locator = LocatorTimeRange | LocatorPage | LocatorPageBbox | LocatorTextSpan | LocatorPostId | LocatorUrlFragment;

/**
 * The addressable handle for anything the index, the API, or a board can point at — a
 * knowledge unit, a canonical concept, a source, an artifact, a transcript segment, or a piece
 * of user content. It is a projection for addressing and display; the canonical files stay
 * authoritative for content. Canvas plan §10.4.
 *
 * Runtime invariants, enforced by the adapter and by the schemas — not by these types:
 * - Knowledge units and canonical concepts must carry the library id form as well as the
 * global id.
 * - A source-class knowledge unit is grounded in the medium; without a locator it is not
 * source-class.
 * - A derived-class knowledge unit must show its work.
 * - User content never claims a canonical file (three-tier storage boundary, D-006).
 */
export type EntityRef = {
  schema_version: SchemaVersion;
  /**
   * Identity across index, API, and boards (D-011). Must equal source_type + ':' + external_id +
   * ':' + local_id; the equality is asserted in tests, being beyond what JSON Schema can
   * express.
   */
  global_id: GlobalId;
  source_type: SourceType;
  external_id: IdPart;
  /**
   * The id inside the source — a canonical knowledge unit id such as KU-000001 or KU-D-0001, an
   * artifact name, a segment id, or a workspace-generated id for user content.
   */
  local_id: IdPart;
  /**
   * The identifier as output/library/graph.json spells it. Required for knowledge units and
   * canonical concepts, because the kg_navigator skill addresses those nodes by this form and
   * library.py must keep emitting it (ADR 0001 invariant 4, risk R12).
   */
  library_id?: LibraryId | null;
  source_id?: SourceId | null;
  entity_type: "source" | "artifact" | "knowledge_unit" | "concept" | "caption" | "segment" | "coverage_window" | "board" | "board_item" | "user_note" | "user_relation";
  provenance_class: ProvenanceClass;
  /**
   * Knowledge kind for knowledge units and concepts; null for everything else.
   */
  kind?: KnowledgeKind | null;
  /**
   * Display text. For a knowledge unit this is normalized_statement or content, exactly as
   * library.py:52 already chooses it — never a new summary.
   */
  label?: string | null;
  confidence?: Confidence | null;
  /**
   * Where the evidence sits in an artifact. Required for a source-class knowledge unit,
   * mirroring the provenance that validators.py:50 already enforces.
   */
  locator?: Locator | null;
  /**
   * Global ids this unit was synthesised from. Required for a derived-class knowledge unit.
   */
  derived_from?: Array<GlobalId> | null;
  /**
   * The recorded reasoning behind a derived unit, copied verbatim.
   */
  derivation_note?: string | null;
  /**
   * Project-relative path of the canonical file this projection was read from. Null for user
   * content, which has no canonical file.
   */
  canonical_path?: ProjectRelativePath | null;
};

/**
 * One edge as the index and the API expose it, addressing both endpoints by three-part global
 * id. Canvas plan §10.5. Three vocabularies coexist and must stay distinguishable: the 16
 * canonical relation types written by the extraction pipeline, the two synthetic edges
 * library.py adds, and free-form user links. A user relation is never written back into
 * relationships.json.
 *
 * Runtime invariants, enforced by the adapter and by the schemas — not by these types:
 * - A canonical edge uses the controlled vocabulary, carries a confidence, and points at a
 * canonical file.
 * - The two library-synthetic edge types are derived synthesis, never source evidence.
 * - A user relation lives only in the workspace: user provenance, no canonical file, no
 * invented confidence.
 */
export type IndexedRelation = {
  schema_version: SchemaVersion;
  /**
   * Stable edge id. Deterministic for canonical and synthetic edges so a rebuild produces the
   * identical set (rebuild-equivalence, T-104); workspace-generated for user edges.
   */
  id: string;
  from_id: GlobalId;
  to_id: GlobalId;
  relation: string;
  /**
   * 'canonical' — from relationships.json, restricted to constants.RELATION_TYPES.
   * 'library_synthetic' — derived_from and expresses_concept, generated by library.py and
   * deliberately outside RELATION_TYPES; the Map must style them without pretending they are
   * canonical. 'user' — a manual workspace link.
   */
  relation_vocabulary: "canonical" | "library_synthetic" | "user";
  provenance_class: ProvenanceClass;
  /**
   * Copied from the canonical edge. Null for user relations, which have no confidence and must
   * never be given a fabricated one.
   */
  confidence?: Confidence | null;
  /**
   * The source the edge came from. Null for a cross-source or user edge.
   */
  source_id?: SourceId | null;
  /**
   * Project-relative path of the file the edge was read from. Null for user relations.
   */
  canonical_path?: ProjectRelativePath | null;
  /**
   * Mirrors the canonical flag that validators.py:117 checks; without it a self-loop is an
   * error, not a design.
   */
  intentional_self_loop?: boolean;
  created_at?: IsoTimestamp | null;
};

// -------------------------------------------------------------------------
// Source synthesis records — schemas/synthesis/v1/
// -------------------------------------------------------------------------

/**
 * The record model version. The version is the directory: a breaking change becomes
 * schemas/synthesis/v2/.
 */
export type SynthesisSchemaVersion = "1.0";

export type SynthesisSourceId = string;

export type SynthesisKnowledgeUnitId = string;

export type SynthesisSourceRelationId = string;

/**
 * The eight source-to-source relation types. Mirrors constants.SOURCE_RELATION_TYPES, and
 * deliberately not constants.RELATION_TYPES: that vocabulary joins two knowledge units, this
 * one joins two whole sources, and 'supports' means a different-sized claim in each (risk
 * R27).
 */
export type SynthesisSourceRelationType = "explicitly_references" | "responds_to" | "critiques" | "supports" | "contradicts" | "extends" | "applies" | "overlaps_with";

/**
 * How much of the two sources the basis supports. Two values and no third: scope qualifies the
 * claim, it does not measure it, and a percentage would be a number nothing produced (D-247).
 */
export type SynthesisSourceRelationScope = "partial" | "broad";

/**
 * The KU-level canonical vocabulary, mirroring constants.RELATION_TYPES. A basis entry states
 * how one unit relates to another; the source-level type is the aggregation over those, and
 * the two vocabularies stay apart.
 */
export type SynthesisKnowledgeRelationType = "supports" | "contradicts" | "causes" | "contributes_to" | "depends_on" | "enables" | "inhibits" | "exemplifies" | "is_example_of" | "is_evidence_for" | "refines" | "qualifies" | "is_part_of" | "precedes" | "results_in" | "related_to";

/**
 * The status of the run a brief accounts for. UNKNOWN is absent on purpose: a brief is
 * generated after extraction and coverage, so a run whose validators never ran has nothing to
 * summarise, and 'UNKNOWN' here would be a brief claiming a run state nobody measured.
 */
export type SynthesisRunStatus = "PASS" | "PARTIAL" | "FAIL";

export type SynthesisSha256 = string;

export type SynthesisIsoTimestamp = string;

/**
 * A Persian narrative statement, under the permanent output-language policy. The schema can
 * require that text exists and is not empty; it cannot check which language it is in, so the
 * policy is enforced by the apply gate (T-252) and by tests/test_output_language_policy.py,
 * and this description is where the requirement is recorded rather than left implicit.
 */
export type SynthesisNarrativeText = string;

/**
 * The knowledge units a narrative statement rests on. Non-empty, always: an empty list asserts
 * derived knowledge while showing no work, which is exactly what adapters.base._derived_refs
 * refuses one layer down.
 */
export type SynthesisSupportList = Array<SynthesisKnowledgeUnitId>;

/**
 * A Persian statement and the knowledge units it rests on. The pairing is the contract: a
 * statement with no support is an assertion the source never made, and support naming units
 * the run does not hold is worse, because it looks checkable and is not. The second condition
 * needs the run's own unit list and is checked by the apply gate.
 */
export type SourceKnowledgeStatement = {
  content: SynthesisNarrativeText;
  based_on: SynthesisSupportList;
};

/**
 * A supported statement that is addressable — the UI links to one, and a later revision has to
 * be able to say which point it changed. Ids are unique within their list; JSON Schema can
 * require the whole objects to differ but cannot compare one field across array members, so
 * the duplicate-id case is a validator rule and a committed invalid fixture.
 */
export type SourceKnowledgePoint = {
  id: string;
  content: SynthesisNarrativeText;
  based_on: SynthesisSupportList;
};

/**
 * One ground: a unit of the from-endpoint, a unit of the to-endpoint, and how they relate at
 * unit level. The ids are local to their own endpoints — which endpoint owns which is the
 * whole point, and a basis entry whose unit belongs to the other source is a relation that
 * cannot be checked. That ownership needs both runs in hand and is the apply gate's rule,
 * pinned here by a committed invalid fixture.
 */
export type SourceRelationBasisPair = {
  from_ku_id: SynthesisKnowledgeUnitId;
  to_ku_id: SynthesisKnowledgeUnitId;
  relation_type: SynthesisKnowledgeRelationType;
};

/**
 * One readable, derived account of one acquired source, written as output/<run-
 * id>/source_knowledge.json after extraction, normalization, relationship extraction and the
 * coverage audit. It is knowledge, not evidence: every narrative statement names the knowledge
 * units it rests on, evidence excerpts stay in those units and are never copied here, and the
 * record cannot claim a status stronger than the run it describes. Frozen by T-251; the apply
 * gate, the validators and the adapter projection are T-252. A missing artifact is an honest
 * 'unavailable' brief, never an empty successful one.
 */
export type SourceKnowledge = {
  schema_version: SynthesisSchemaVersion;
  /**
   * The source this brief accounts for. The apply gate additionally checks it against the run it
   * is being written into: a brief carrying another source's id would attach one source's
   * account to another's evidence, and JSON Schema cannot compare a document with its own
   * location.
   */
  source_id: SynthesisSourceId;
  /**
   * The status of the underlying run, copied. Never computed here and never raised: a brief
   * derived from a PARTIAL run is visibly partial, and the validator refuses a status stronger
   * than validation.json states (D-246).
   */
  status: SynthesisRunStatus;
  /**
   * The source's central claim, in Persian, in one statement.
   */
  thesis: SourceKnowledgeStatement;
  /**
   * The points a reader needs, in the order they should be read. At least one: a brief with a
   * thesis and nothing under it is a title, and the Source Map card has a section for these.
   */
  key_points: Array<SourceKnowledgePoint>;
  /**
   * What the source leaves unresolved, contradicts itself about, or does not establish. May be
   * empty — an empty array here says 'none recorded', which is a claim the generator is allowed
   * to make; it is not the same as the field being absent, which is why the field is required
   * and the array is not.
   */
  limitations_or_tensions: Array<SourceKnowledgePoint>;
  /**
   * Digests of the canonical inputs this brief was generated from, so staleness is detectable
   * rather than assumed. A digest that no longer matches the file means the brief describes a
   * run that has since changed, and the reader is told rather than shown an account of something
   * else.
   */
  generated_from: {
    knowledge_units_sha256: SynthesisSha256;
    relationships_sha256: SynthesisSha256;
    coverage_sha256: SynthesisSha256;
  };
  /**
   * When the brief was generated. Optional, and never a substitute for the digests: a timestamp
   * says when, the digests say what from, and only the second can detect staleness.
   */
  generated_at?: SynthesisIsoTimestamp;
};

/**
 * One qualified, directional relationship between two whole acquired sources, with the
 * knowledge-unit pairs it rests on. Deliberately not an IndexedRelation: that record joins two
 * units and carries a confidence, and neither shape can state the thing that keeps a source-
 * level edge honest — the basis. Every automatic source relation is derived provenance,
 * explicitly_references included: the cited link may be source-grounded, but promoting it into
 * a source-to-source relationship is an aggregation the sources themselves never made (D-247).
 * Frozen by T-251; generation, the apply gate and the validators are T-253.
 */
export type SourceRelation = {
  /**
   * Deterministic, from ids.source_relation_id over the two endpoints, the relation type and the
   * scope — and over nothing else. Basis and rationale are content, not identity, so a later
   * pass that finds a fourth ground for the same critique updates this record rather than
   * minting a second one. Direction is part of the identity: 'critiques' is not its own inverse.
   */
  id: SynthesisSourceRelationId;
  from_source_id: SynthesisSourceId;
  /**
   * The far endpoint. It must differ from from_source_id — a source does not critique itself —
   * which ids.source_relation_id refuses and which JSON Schema cannot compare.
   */
  to_source_id: SynthesisSourceId;
  relation_type: SynthesisSourceRelationType;
  scope: SynthesisSourceRelationScope;
  /**
   * Always 'derived'. A const rather than an enum of one, so the field cannot be read as a
   * choice the generator gets to make.
   */
  provenance_class: "derived";
  /**
   * Why the basis supports this relation, in Persian, making no claim stronger than scope and
   * basis carry. The strength rule is a judgement the apply gate makes with the basis in hand;
   * the schema's part is to require that a reason exists at all.
   */
  rationale: SynthesisNarrativeText;
  /**
   * The knowledge-unit pairs this relation rests on. Non-empty: a source-level relation with no
   * grounds is exactly the whole-document verdict risk R27 names. Mixed or contrary grounds stay
   * in the list rather than being dropped — the honest answer to conflicting evidence is a
   * narrower relation or two relations, never a tidier one. No maxItems: this is the canonical
   * record and it carries the whole basis; bounding belongs to the API response, which states
   * basis_total and basis_returned so a truncation is never silent.
   */
  basis: Array<SourceRelationBasisPair>;
  /**
   * The digest of each endpoint run at the time of comparison. A pair is re-evaluated when
   * either digest changes or the synthesis contract version does, which is what keeps the walk
   * bounded (risk R28) without ever presenting a stale conclusion as a current one.
   */
  generated_from: {
    from_run_digest: SynthesisSha256;
    to_run_digest: SynthesisSha256;
  };
};

// -------------------------------------------------------------------------
// API envelopes — schemas/api/v1/openapi.json
// -------------------------------------------------------------------------

/**
 * The API surface version. Fixed for the life of `schemas/api/v1/`. A breaking change becomes
 * `schemas/api/v2/` and a `/api/v2/` path prefix, leaving these paths answering v1 (D-026).
 */
export type ApiVersion = "v1";

/**
 * Where a page sits in a collection.
 */
export type PageInfo = {
  limit: number;
  /**
   * Token for the next page, or null at the end of the collection.
   */
  next_cursor: string | null;
  /**
   * Total matching records, or null when the server did not count them. Null means unknown — it
   * never means zero.
   */
  total?: number | null;
};

/**
 * Closed error vocabulary. `invalid_id` is D-020 surfaced over HTTP: an id that fails `ids.py`
 * or `resolve_run_dir` is refused before anything is read, and is reported as malformed rather
 * than as absent. `unavailable` is the honest answer for an artifact whose record exists but
 * whose file does not — the alternative, a placeholder, is forbidden by canvas plan §15.
 */
export type ErrorCode = "invalid_id" | "invalid_request" | "not_found" | "unavailable" | "index_unavailable" | "internal";

export type ErrorBody = {
  code: ErrorCode;
  /**
   * Human-readable, and safe to show. It names what was wrong with the request, never a host
   * path.
   */
  message: string;
  /**
   * Structured context, or null. Never carries an absolute host path (risk R15).
   */
  detail?: Record<string, unknown> | null;
};

export type ErrorResponse = {
  api_version: ApiVersion;
  schema_version: SchemaVersion;
  error: ErrorBody;
};

/**
 * What the index can answer with. `absent` and `building` are reported plainly: a UI that
 * cannot tell an empty index from an unbuilt one will present 'no sources' as a fact.
 */
export type IndexState = "absent" | "building" | "ready" | "error";

/**
 * Sources per copied status. Counting is the only operation performed on a status.
 */
export type RunStatusTally = {
  PASS: number;
  PARTIAL: number;
  FAIL: number;
  UNKNOWN: number;
};

/**
 * A run directory the index scanned and could not turn into a `Source`. It is named rather
 * than counted so that a `counts.sources` smaller than `runs.discovered` never has to be
 * explained by guesswork.
 */
export type SkippedRun = {
  /**
   * The run directory, relative to the project root.
   */
  relative_path: ProjectRelativePath;
  /**
   * Why the run could not be indexed, in the words of whatever refused it. Never a host path
   * (D-030).
   */
  reason: string;
};

export type StatusPayload = {
  index: {
    state: IndexState;
    /**
     * When the index last finished a build, or null if it never has.
     */
    built_at: IsoTimestamp | null;
    /**
     * Migration version of the SQLite schema (T-101), or null when no index exists.
     */
    index_version?: number | null;
    /**
     * Why the index is in this state, when it has something to say. Present on `error`; on `ready`
     * after a scan that failed and was rolled back — the stored records are intact and still
     * answerable, and this is the only place that says the last scan did not finish; and on
     * `ready` when the index holds sources whose searchable text could not be read, which is why a
     * search over them reports `total: null`. Such a source is *indexed*, so it is counted in
     * `runs.indexed` and named in no `skipped` entry, and this sentence is the only channel that
     * explains the uncountable total. The count, not the ids: `/api/sources` is where a client
     * learns which source is which. Absent when there is nothing to report; never an empty string.
     * Carries no host filesystem path (ADR 0003).
     */
    message?: string | null;
  };
  /**
   * Records the index holds. A cache convenience, reproducible from the canonical files; a stale
   * count is a bug, never a data achievement.
   */
  counts: {
    sources: number;
    artifacts: number;
    entities: number;
    relations: number;
  };
  sources_by_status: RunStatusTally;
  /**
   * The registered adapters, so a stale record can be traced to the code that wrote it.
   */
  adapters: Array<AdapterRef>;
  /**
   * What the last scan saw on disk, and what it could not index. `discovered` counts run
   * directories holding a `metadata.json`; `indexed` counts those that produced a `Source`.
   * Every other one is named in `skipped`, so a library that is smaller than the filesystem says
   * why rather than simply being smaller. `discovered` equals `indexed` plus the length of
   * `skipped`. A run indexed *with* named gaps counts as indexed and reports those gaps on its
   * own `Source.adapter_metadata`. Optional: an implementation that scans no filesystem omits it
   * rather than reporting a zero it did not measure.
   */
  runs?: {
    discovered: number;
    indexed: number;
    skipped: Array<SkippedRun>;
    /**
     * Why the cross-source `library/` fragment could not be indexed, when it could not be. It is
     * **not** a run: it is not counted in `discovered` or `indexed` and is not listed in
     * `skipped`, so the identity above stays true — it gets a field of its own for the same reason
     * `ScanReport.library_skipped_reason` does, so a caller can test it without matching on a
     * path. Absent when the fragment indexed cleanly *and* when there is no fragment at all: an
     * absent `library/` is the ordinary state of a project that has not run `rebuild-library`,
     * while a present unreadable one is damage and says so. Carries no host filesystem path (ADR
     * 0003).
     */
    library_skipped_reason?: string | null;
  };
};

export type StatusResponse = {
  api_version: ApiVersion;
  schema_version: SchemaVersion;
  data: StatusPayload;
};

export type SourceListResponse = {
  api_version: ApiVersion;
  schema_version: SchemaVersion;
  data: Array<Source>;
  page: PageInfo;
};

export type SourceDetail = {
  source: Source;
  artifacts: Array<Artifact>;
};

export type SourceDetailResponse = {
  api_version: ApiVersion;
  schema_version: SchemaVersion;
  data: SourceDetail;
};

export type ArtifactResponse = {
  api_version: ApiVersion;
  schema_version: SchemaVersion;
  data: Artifact;
};

export type EntityResponse = {
  api_version: ApiVersion;
  schema_version: SchemaVersion;
  data: EntityRef;
};

export type EntityListResponse = {
  api_version: ApiVersion;
  schema_version: SchemaVersion;
  data: Array<EntityRef>;
  page: PageInfo;
};

export type RelationListResponse = {
  api_version: ApiVersion;
  schema_version: SchemaVersion;
  data: Array<IndexedRelation>;
  page: PageInfo;
};

/**
 * A knowledge-unit hit, field for field as `query.search_knowledge` returns it, plus
 * `global_id` and `source_id`. The canonical field names are kept — `video_id` stays
 * `video_id` (ADR 0001 invariant 6) and `id` stays the canonical unit id — so the shape the
 * MCP tools and the CLI already return is the shape the API returns.
 */
export type SearchHitKnowledgeUnit = {
  type: "knowledge_unit";
  video_id: string | null;
  title: string | null;
  /**
   * The canonical knowledge unit id, e.g. `KU-000001`.
   */
  id: string | null;
  kind: string | null;
  source_class: string | null;
  content: string | null;
  confidence: number | null;
  /**
   * Present only when the canonical unit states a numeric start. Absent, not zero, when it does
   * not.
   */
  start_sec?: TimestampSec;
  /**
   * Deep link built by `io.timestamp_url`. Present only alongside `start_sec`.
   */
  source_url?: string;
  /**
   * Present only for a derived-class unit, in the canonical id form the unit itself carries.
   */
  derived_from?: Array<string>;
  /**
   * Additive. Null when the canonical data cannot form one — a run whose metadata states no
   * `video_id` has no addressable entity, and a fabricated id would be worse than none.
   */
  global_id: GlobalId | null;
  /**
   * Additive.
   */
  source_id: SourceId | null;
};

/**
 * A transcript-caption hit, field for field as `query.search_knowledge` returns it, plus
 * `source_id`. It carries no `global_id`: v1 emits no caption entities (D-023), so there is no
 * entity to address. The client navigates by source and timestamp instead.
 */
export type SearchHitTranscriptCaption = {
  type: "transcript_caption";
  video_id: string | null;
  title: string | null;
  /**
   * The canonical caption's `segment_id`.
   */
  caption_id: string | null;
  content: string | null;
  start_sec: TimestampSec;
  end_sec: TimestampSec | null;
  source_url: string;
  source_id: SourceId | null;
};

/**
 * One result. `type` is the discriminator.
 */
export type SearchHit = SearchHitKnowledgeUnit | SearchHitTranscriptCaption;

export type SearchResponse = {
  api_version: ApiVersion;
  schema_version: SchemaVersion;
  /**
   * The query as executed, echoed so a client batching requests cannot mis-attribute a response.
   */
  query: string;
  data: Array<SearchHit>;
  page: PageInfo;
};

export type GraphPayload = {
  nodes: Array<EntityRef>;
  /**
   * The relations among the nodes on this page, at most `maxItems` of them. `limit` bounds the
   * *nodes*, and an edge list is quadratic in the nodes it connects, so the two are not the same
   * size; `truncated` is true when either was cut.
   */
  edges: Array<IndexedRelation>;
  /**
   * True when `limit` cut the result short. Stated rather than implied, so the Map never
   * presents a partial graph as the whole one.
   */
  truncated: boolean;
};

export type GraphResponse = {
  api_version: ApiVersion;
  schema_version: SchemaVersion;
  data: GraphPayload;
  page: PageInfo;
};

export type NeighborhoodPayload = {
  center_id: GlobalId;
  depth: number;
  nodes: Array<EntityRef>;
  /**
   * The relations among the nodes on this page, at most `maxItems` of them. `limit` bounds the
   * *nodes*, and an edge list is quadratic in the nodes it connects, so the two are not the same
   * size; `truncated` is true when either was cut.
   */
  edges: Array<IndexedRelation>;
  truncated: boolean;
};

export type NeighborhoodResponse = {
  api_version: ApiVersion;
  schema_version: SchemaVersion;
  data: NeighborhoodPayload;
};

/**
 * Whether a source's readable brief is available, and why not when it is not. A brief is a
 * gated derived artifact that may simply not have been generated yet, and an absent one must
 * not reach the client as an empty successful brief — 'this source has no thesis and no key
 * points' is a claim about the source, and it would be false. `state` carries the distinction
 * and `brief` is null whenever the state is `unavailable`. `stale` is its own state rather
 * than an error: the brief exists and describes inputs whose digests have since moved, so it
 * is carried with that said out loud rather than withheld or silently trusted — `stale` is the
 * one state other than `available` in which `brief` is a document. (`T-254` sharpened these
 * two sentences, which had frozen in contradiction with each other: the first said a brief is
 * null in every state but `available`, the second that a stale one is shown rather than
 * withheld. Serving it is what makes `stale` differ from `unavailable` by more than a word.)
 */
export type SourceKnowledgeAvailability = {
  state: "available" | "unavailable" | "stale";
  /**
   * The generated brief, or null when there is not one to show.
   */
  brief: SourceKnowledge | null;
  /**
   * Why the brief is unavailable or stale, project-relative and free of host paths (D-030,
   * D-051). Null when `state` is `available`.
   */
  reason: string | null;
};

/**
 * One source relation as the Source Explore graph needs it: direction, type, scope and how
 * many grounds stand behind it — but not the grounds themselves. `basis_total` is required
 * here precisely because the basis is absent: an edge pill reads `critiques · 3 grounds`, and
 * a summary that omitted the count would let a relation resting on one pair and one resting on
 * forty draw identically. The count is a count, never a strength, a confidence or a rank
 * (D-247).
 */
export type SourceRelationSummary = {
  id: SynthesisSourceRelationId;
  from_source_id: SynthesisSourceId;
  to_source_id: SynthesisSourceId;
  relation_type: SynthesisSourceRelationType;
  scope: SynthesisSourceRelationScope;
  /**
   * Always `derived` for an automatic source relation.
   */
  provenance_class: "derived";
  /**
   * How many knowledge-unit pairs the stored relation rests on.
   */
  basis_total: number;
};

/**
 * One source relation with its Persian rationale and a bounded page of its basis. The two
 * counts are both required and are not the same number: `basis_total` is what the canonical
 * record holds, `basis_returned` is what is in this body. A response that carried only the
 * second would present a truncated basis as the whole of it, which is the overclaim risk R27
 * names, arriving through the API instead of through the model. `basis` is capped at
 * `maxItems`, the value of constants.MAX_SOURCE_RELATION_BASIS, for the reason
 * `GraphPayload.edges` is capped: an unbounded array in a response is an unbounded response.
 */
export type SourceRelationDetail = {
  id: SynthesisSourceRelationId;
  from_source_id: SynthesisSourceId;
  to_source_id: SynthesisSourceId;
  relation_type: SynthesisSourceRelationType;
  scope: SynthesisSourceRelationScope;
  provenance_class: "derived";
  rationale: SynthesisNarrativeText;
  /**
   * The grounds carried in this body, in the stored order. Mixed and contrary grounds are
   * included rather than filtered: hiding them would make the relation read cleaner than the
   * evidence is.
   */
  basis: Array<SourceRelationBasisPair>;
  basis_total: number;
  basis_returned: number;
};

/**
 * The source topology: one node per acquired source, and the relations among them. The nodes
 * are `EntityRef` records with `entity_type: "source"` — the same addressable handle every
 * other entity uses, so a source selection resolves the way a knowledge unit selection does.
 * Chapters, posts in a self-thread, transcript segments, knowledge units and concepts are not
 * nodes here; that is the whole point of the second Map mode (D-244).
 */
export type SourceGraphPayload = {
  nodes: Array<EntityRef>;
  relations: Array<SourceRelationSummary>;
  /**
   * True when `limit` cut the result short. Stated rather than implied, exactly as
   * `GraphPayload.truncated` is.
   */
  truncated: boolean;
  counts: SourceGraphCounts;
};

/**
 * Returned, omitted and total, counted separately. Three numbers rather than one because they
 * answer three different questions, and collapsing them is how a bounded result comes to look
 * like a complete one. `sources_total` may be null, which means not counted — never zero, the
 * same rule `PageInfo.total` carries.
 */
export type SourceGraphCounts = {
  sources_returned: number;
  relations_returned: number;
  /**
   * Relations the bound left out of this body. Counted, never silent — the same discipline the
   * synthesis file's `candidates.omitted` carries upstream.
   */
  relations_omitted: number;
  sources_total: number | null;
};

export type SourceGraphResponse = {
  api_version: ApiVersion;
  schema_version: SchemaVersion;
  data: SourceGraphPayload;
  page: PageInfo;
};

/**
 * One selected source, its readable brief, and its qualified relations in both directions.
 * `incoming` and `outgoing` are separate arrays rather than one list with a direction flag,
 * because direction is what the Focus composition places on the left and the right and what
 * the semantic companion list has to state in text — and a client that has to derive it by
 * comparing `to_source_id` with `center_id` is a client that can derive it wrongly.
 */
export type SourceNeighborhoodPayload = {
  center_id: GlobalId;
  /**
   * The selected source's own `EntityRef`, echoed back.
   */
  source: EntityRef;
  source_knowledge: SourceKnowledgeAvailability;
  /**
   * Relations whose `to_source_id` is the selected source.
   */
  incoming: Array<SourceRelationDetail>;
  /**
   * Relations whose `from_source_id` is the selected source.
   */
  outgoing: Array<SourceRelationDetail>;
  /**
   * The `EntityRef` of every source named by a returned relation, so no relation names an
   * endpoint the client has no node for. ADR 0002 is emphatic that an edge to a node the page
   * will not show asserts a node that does not exist.
   */
  neighbors: Array<EntityRef>;
  truncated: boolean;
};

export type SourceNeighborhoodResponse = {
  api_version: ApiVersion;
  schema_version: SchemaVersion;
  data: SourceNeighborhoodPayload;
};

// -------------------------------------------------------------------------
// Operations
// -------------------------------------------------------------------------

/**
 * Every operation of the frozen contract, keyed by operationId: its path, its parameters, and
 * the body a 2xx carries. A typed fetch wrapper built on this cannot call a path the contract
 * does not define or read a field it does not return.
 *
 * Header parameters are omitted — the only one is the Range header of getArtifactMedia, which
 * belongs to the transport rather than to the payload.
 */
export interface Endpoints {
  /**
   * Index state and honest tallies
   */
  getStatus: {
    path: "/api/status";
    method: "get";
    params: Record<string, never>;
    query: Record<string, never>;
    response: StatusResponse;
  };
  /**
   * List ingested sources
   */
  listSources: {
    path: "/api/sources";
    method: "get";
    params: Record<string, never>;
    query: {
      limit?: number;
      cursor?: string;
      source_type?: SourceType;
      status?: RunStatus;
    };
    response: SourceListResponse;
  };
  /**
   * One source with its artifacts
   */
  getSource: {
    path: "/api/sources/{source_id}";
    method: "get";
    params: {
      source_id: SourceId;
    };
    query: Record<string, never>;
    response: SourceDetailResponse;
  };
  /**
   * The knowledge units of one source
   */
  listSourceEntities: {
    path: "/api/sources/{source_id}/entities";
    method: "get";
    params: {
      source_id: SourceId;
    };
    query: {
      limit?: number;
      cursor?: string;
      provenance_class?: ProvenanceClass;
      kind?: KnowledgeKind;
      min_confidence?: Confidence;
    };
    response: EntityListResponse;
  };
  /**
   * The relations of one source
   */
  listSourceRelations: {
    path: "/api/sources/{source_id}/relations";
    method: "get";
    params: {
      source_id: SourceId;
    };
    query: {
      limit?: number;
      cursor?: string;
      relation_vocabulary?: "canonical" | "library_synthetic" | "user";
    };
    response: RelationListResponse;
  };
  /**
   * One entity by global id
   */
  getEntity: {
    path: "/api/entities/{entity_id}";
    method: "get";
    params: {
      entity_id: GlobalId;
    };
    query: Record<string, never>;
    response: EntityResponse;
  };
  /**
   * One artifact record
   */
  getArtifact: {
    path: "/api/artifacts/{artifact_id}";
    method: "get";
    params: {
      artifact_id: GlobalId;
    };
    query: Record<string, never>;
    response: ArtifactResponse;
  };
  /**
   * The bytes of one artifact
   */
  getArtifactMedia: {
    path: "/api/media/{artifact_id}";
    method: "get";
    params: {
      artifact_id: GlobalId;
    };
    query: Record<string, never>;
    response: Blob;
  };
  /**
   * Search knowledge units and transcript text
   */
  search: {
    path: "/api/search";
    method: "get";
    params: Record<string, never>;
    query: {
      q: string;
      limit?: number;
      cursor?: string;
      source_id?: SourceId;
      include_transcript?: boolean;
    };
    response: SearchResponse;
  };
  /**
   * Nodes and edges for the Knowledge Map
   */
  getGraph: {
    path: "/api/graph";
    method: "get";
    params: Record<string, never>;
    query: {
      limit?: number;
      cursor?: string;
      source_id?: SourceId;
      provenance_class?: ProvenanceClass;
      relation_vocabulary?: "canonical" | "library_synthetic" | "user";
    };
    response: GraphResponse;
  };
  /**
   * The neighborhood of one entity
   */
  getNeighborhood: {
    path: "/api/graph/neighborhood/{entity_id}";
    method: "get";
    params: {
      entity_id: GlobalId;
    };
    query: {
      depth?: number;
      limit?: number;
      relation_vocabulary?: "canonical" | "library_synthetic" | "user";
    };
    response: NeighborhoodResponse;
  };
  /**
   * One node per acquired source, and the relations among them
   */
  getSourceGraph: {
    path: "/api/source-graph";
    method: "get";
    params: Record<string, never>;
    query: {
      limit?: number;
      cursor?: string;
    };
    response: SourceGraphResponse;
  };
  /**
   * One selected source, its readable brief and its qualified relations
   */
  getSourceNeighborhood: {
    path: "/api/source-graph/neighborhood/{source_id}";
    method: "get";
    params: {
      source_id: SourceId;
    };
    query: {
      limit?: number;
    };
    response: SourceNeighborhoodResponse;
  };
}

/**
 * Every operationId the contract defines.
 */
export type OperationId = keyof Endpoints;
