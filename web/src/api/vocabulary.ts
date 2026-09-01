/**
 * The controlled vocabularies, as values a `<select>` can be built from.
 *
 * `types.d.ts` gives these as unions of string literals, which the compiler
 * can check but a dropdown cannot enumerate. Each list below is therefore
 * derived from a `Record<Union, true>`: TypeScript refuses the object if a
 * member is missing or misspelled, so a vocabulary that grows in
 * `constants.py` -- regenerated into the declarations -- becomes a compile
 * error here rather than a filter that silently stops offering a kind.
 *
 * `SourceType` is deliberately absent: the contract types it as an open
 * string, because adding a source type must not require a schema change. Its
 * options are read from the indexed sources instead of being guessed.
 */

import type {
  IndexedRelation,
  KnowledgeKind,
  ProvenanceClass,
  RunStatus,
} from "./contract";

function keysOf<T extends string>(record: Record<T, true>): readonly T[] {
  return Object.keys(record) as T[];
}

export const RUN_STATUSES = keysOf<RunStatus>({
  PASS: true,
  PARTIAL: true,
  FAIL: true,
  UNKNOWN: true,
});

export const PROVENANCE_CLASSES = keysOf<ProvenanceClass>({
  source: true,
  derived: true,
  user: true,
});

export const RELATION_VOCABULARIES = keysOf<IndexedRelation["relation_vocabulary"]>({
  canonical: true,
  library_synthetic: true,
  user: true,
});

export const KNOWLEDGE_KINDS = keysOf<KnowledgeKind>({
  claim: true,
  evidence: true,
  fact: true,
  statistic: true,
  concept: true,
  definition: true,
  framework: true,
  principle: true,
  process: true,
  instruction: true,
  recommendation: true,
  example: true,
  case_study: true,
  analogy: true,
  caveat: true,
  limitation: true,
  assumption: true,
  counterargument: true,
  question: true,
  open_problem: true,
  reference: true,
  quote: true,
  relationship: true,
  implication: true,
  generalized_rule: true,
  mental_model: true,
  diagnostic_model: true,
  actionable_experiment: true,
  hypothesis: true,
  synthesis: true,
  canonical_concept: true,
});
