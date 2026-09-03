/*
 * Shared drawing vocabulary for the T-211 mockups.
 *
 * Every constant here is copied from the production modules it names, so the
 * mockup can be checked against the code rather than taken on trust. Where
 * T-211 PROPOSES a new value, the constant is marked `PROPOSED` and SPEC.md
 * records what it replaces.
 */
import { DATA } from "./data.js";
import { CHROME, STATEMENTS, RELATIONS, EXCERPTS } from "./fa.js";

/* ---- from web/src/map/mapStyle.ts ------------------------------------- */
export const KIND_FAMILY = {
  claim: "thesis", principle: "thesis", evidence: "evidence",
  concept: "concept", definition: "concept", canonical_concept: "concept",
  framework: "framework", mental_model: "framework", diagnostic_model: "framework",
  process: "process", instruction: "process",
  example: "example", case_study: "example", analogy: "example",
  fact: "fact", statistic: "fact",
  recommendation: "recommendation", actionable_experiment: "recommendation",
  caveat: "caveat", limitation: "caveat", assumption: "caveat", counterargument: "caveat",
  question: "question", open_problem: "question", hypothesis: "question",
  relationship: "synthesis", implication: "synthesis", generalized_rule: "synthesis",
  synthesis: "synthesis", reference: "reference", quote: "reference",
};

export const KIND_FAMILY_COLOUR = {
  thesis: "#4477aa", evidence: "#228833", concept: "#aa3377", framework: "#ee7733",
  process: "#009988", example: "#999933", fact: "#1e9fd0", recommendation: "#ddaa33",
  caveat: "#cc3311", question: "#6644aa", synthesis: "#8b5a2b", reference: "#5f7a86",
  unstated: "#8b847b", unrecognised: "#e4007f",
};

export const NODE_PROVENANCE_MARK = {
  source: { shape: "circle", size: 9 },
  derived: { shape: "diamond", size: 11 },
  user: { shape: "square", size: 9 },
};

export const EDGE_VOCABULARY_MARK = {
  canonical: { head: "arrow", size: 2.2 },
  library_synthetic: { head: "diamond", size: 1.4 },
  user: { head: "circle", size: 1.4 },
};

export const PROVENANCE_GLYPH = { source: "◆", derived: "◇", user: "✎" };

export const MAP_DIMMED_NODE_OPACITY = 0.35;
export const MAP_DIMMED_EDGE_OPACITY = 0.25;

/* ---- from web/src/map/labelPolicy.ts ---------------------------------- */
export const MAP_LABEL_CHARS = { normal: 42, neighbour: 64, hovered: 120, selected: 160 };
export const MAP_LABEL_ELLIPSIS = "…";

/* ---- PROPOSED by T-211. SPEC.md records what each replaces. ------------ */
export const PROPOSED = {
  PRIMARY_BOX: { width: 560, height: 232 },   // was MAP_STAGE_PRIMARY_BOX 416x176
  CARD_BOX: { width: 320, height: 148 },      // was MAP_STAGE_CARD_BOX 320x296
  CHIP_BOX: { width: 220, height: 76 },       // new: a hop-2 mark carries less
  PRIMARY_CHARS: 200,                         // MAP_STAGE_PRIMARY_CHARS, unchanged
  NEIGHBOUR_CHARS: 110,                       // MAP_STAGE_NEIGHBOUR_CHARS, unchanged
  CHIP_CHARS: 64,                             // = MAP_LABEL_CHARS.neighbour
  DRAWER_WIDTH: 560,
  RING: [{ hop: 1, rx: 520, ry: 640 }, { hop: 2, rx: 880, ry: 980 }],
};

/**
 * A port of `cutToBudget` in web/src/map/labelPolicy.ts: collapse whitespace,
 * cut by CODE POINT (never by UTF-16 unit, which halves a surrogate pair), and
 * prefer a word boundary only when the last space falls at 60% of the budget
 * or later.
 */
export function cutToBudget(value, budget) {
  const text = String(value ?? "").replace(/\s+/g, " ").trim();
  const points = Array.from(text);
  if (points.length <= budget) return { shown: text, truncated: false };
  let cut = points.slice(0, budget).join("");
  const space = cut.lastIndexOf(" ");
  if (space >= Math.floor(budget * 0.6)) cut = cut.slice(0, space);
  return { shown: cut.trimEnd(), truncated: true };
}

/* ---- locale ------------------------------------------------------------ */
export const LOCALE = new URLSearchParams(location.search).get("lang") === "fa" ? "fa" : "en";
export const RTL = LOCALE === "fa";

const EN = {
  "app.title": "Knowledge Canvas", "nav.library": "Library", "nav.map": "Map",
  "map.title": "Knowledge Map", "map.state.nodes": "Nodes loaded",
  "map.state.edges": "Edges drawn", "map.state.extent": "Extent",
  "map.state.complete": "This is the whole graph these filters describe.",
  "map.search.title": "Search this Map", "map.focus.title": "Focus",
  "map.focus.clear": "Clear the focus", "map.quickRead.title": "Quick Read",
  "map.quickRead.statement": "Stored statement", "map.quickRead.technical": "Technical metadata",
  "map.related.title": "Related knowledge", "map.legend.title": "What the marks mean",
  "map.legend.shape.circle": "circle", "map.legend.shape.diamond": "diamond",
  "map.legend.shape.square": "square",
  "provenance.source": "Source-backed", "provenance.derived": "Derived",
  "provenance.user": "Written by you", "common.notStated": "not stated",
  "reader.units.confidence": "Confidence",
};

export const t = (key) => (RTL ? CHROME[key] ?? EN[key] : EN[key]) ?? key;

/** The statement to display. English is the real record; Persian is mockup-only. */
export function statement(record) {
  if (!RTL) return record.label ?? "";
  return STATEMENTS[record.local_id] ?? record.label ?? "";
}
export const relationGloss = (r) => (RTL ? RELATIONS[r] ?? r : r);
export const excerptOf = (rec) => {
  const raw = rec.locator?.excerpt ?? null;
  if (!raw) return null;
  return RTL ? EXCERPTS[rec.local_id] ?? raw : raw;
};

/* ---- small helpers ----------------------------------------------------- */
export const kindColour = (kind) =>
  KIND_FAMILY_COLOUR[KIND_FAMILY[kind] ?? (kind ? "unrecognised" : "unstated")];
/**
 * A bidi-isolated run, the mockup's stand-in for the production `Bidi`
 * component. Content whose script differs from the UI's -- an untranslated
 * English statement inside a Persian Map -- must be isolated, or the
 * surrounding direction reorders its punctuation: the truncation ellipsis
 * jumps to the front of the line.
 */
export const bdi = (text) => {
  const node = document.createElement("bdi");
  node.textContent = text;
  return node;
};

export const el = (tag, cls, text) => {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
};
export const svg = (tag, attrs = {}) => {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, String(v));
  return node;
};
export const mmss = (s) =>
  `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

/** The four provenance shapes, as SVG path data centred on the origin. */
export function markPath(shape, r) {
  if (shape === "circle") return null;
  if (shape === "diamond") return `M0,${-r} L${r},0 L0,${r} L${-r},0 Z`;
  if (shape === "square") return `M${-r},${-r} H${r} V${r} H${-r} Z`;
  return `M0,${-r} L${r * 0.87},${r * 0.5} L${-r * 0.87},${r * 0.5} Z`;
}

export { DATA };
