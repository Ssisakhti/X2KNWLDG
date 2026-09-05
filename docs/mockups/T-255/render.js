/*
 * Shared drawing vocabulary for the T-255 Source Map mockups.
 *
 * Where a constant already exists in the production modules, it is copied and
 * the module is named, so the mockup can be checked against the code rather
 * than taken on trust. Where T-255 PROPOSES one, it is marked `PROPOSED` and
 * SPEC.md records what it is for.
 *
 * The Source Map draws a different thing from the Knowledge Map, so it needs
 * one channel the Knowledge Map does not have and gives up two it does.
 *
 *   GIVEN UP -- `size` and `edge weight`. Every source is drawn at one size and
 *   every relationship at one thickness. A relationship carries no confidence,
 *   no score and no rank (D-247), and `basis_total` is a count: weighting an
 *   edge by it would draw a ranking the records do not contain. This is the
 *   single most load-bearing refusal in these pictures.
 *
 *   GIVEN UP -- `kind` hue. A source node's `kind` is `null` in every body,
 *   because a source is not a knowledge unit. The Knowledge Map's kind palette
 *   is therefore absent rather than reused for something else.
 *
 *   ADDED -- `medium` and `brief state`. Both are drawn in two channels each,
 *   never colour alone, which is ADR 0001 invariant 10's rule applied to the
 *   two attributes this Map actually varies.
 */
import { DATA } from "./data.js";
import { t, LOCALE, RTL } from "./i18n.js";

export { DATA, t, LOCALE, RTL };

/* ---- from web/src/map/mapStyle.ts -------------------------------------- */

/** Every source node is `provenance_class: "source"`, so every mark is this. */
export const NODE_PROVENANCE_MARK = {
  source: { shape: "circle", size: 9 },
  derived: { shape: "diamond", size: 11 },
  user: { shape: "square", size: 9 },
};
export const PROVENANCE_GLYPH = { source: "◆", derived: "◇", user: "✎" };
export const MAP_DIMMED_NODE_OPACITY = 0.35;
export const MAP_DIMMED_EDGE_OPACITY = 0.25;

/* ---- from web/src/map/labelPolicy.ts ----------------------------------- */
export const MAP_LABEL_CHARS = { normal: 42, neighbour: 64, hovered: 120, selected: 160 };

/* ---- PROPOSED by T-255 ------------------------------------------------- */

/**
 * Medium: hue **and** glyph, so the distinction survives greyscale and a
 * colour-vision difference. The two hues are the `thesis` and `process`
 * families of `KIND_FAMILY_COLOUR`, reused in a mode that draws no kinds.
 */
export const MEDIUM_MARK = {
  youtube: { hue: "#4477aa", glyph: "▶" },
  twitter: { hue: "#009988", glyph: "✦" },
};

/**
 * Brief state: fill **and** word. A hollow mark is a source with no brief, and
 * that is a normal condition rather than an error, so it is drawn as an absence
 * of fill rather than as an alarm colour.
 */
export const BRIEF_MARK = {
  available: { fill: 1, halo: false },
  stale: { fill: 1, halo: true },
  unavailable: { fill: 0, halo: false },
};

/** Scope: a dash pattern **and** the word on the pill. Two values, no third. */
export const SCOPE_MARK = { partial: "6 5", broad: "" };

/** The one weight every relationship is drawn at. See the header. */
export const EDGE_WEIGHT = 1.8;

/** Card geometry. A source card carries a brief, so it is taller than a KU card. */
export const BOX = {
  full: {
    PRIMARY: { width: 660, height: 430 },
    CARD: { width: 340, height: 168 },
    perSide: Infinity,
  },
  compact: {
    PRIMARY: { width: 440, height: 300 },
    CARD: { width: 268, height: 132 },
    perSide: 2,
  },
  stack: { PRIMARY: { width: 0, height: 0 }, CARD: { width: 0, height: 0 }, perSide: 0 },
};

/** Character budgets, in the shape `labelPolicy` states them. */
export const CHARS = {
  TITLE_PRIMARY: 150,
  TITLE_NEIGHBOUR: 84,
  THESIS: 260,
  POINT: 150,
  LABEL: MAP_LABEL_CHARS.normal,
};

export const DRAWER_WIDTH = 560;

/* ---- helpers, ported from the production modules they name ------------- */

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

/**
 * A bidi-isolated run, the mockup's stand-in for the production `Bidi`
 * component. Every source label in this corpus is content whose script may
 * differ from the UI's -- an English post title inside a Persian Map, a Persian
 * one inside an English Map -- and without isolation the surrounding direction
 * reorders its punctuation and throws the ellipsis to the front of the line.
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

/* ---- reading the bodies ------------------------------------------------ */

/** `?data=dense` draws the ten-source corpus; the default is the served four. */
export const DATASET =
  new URLSearchParams(location.search).get("data") === "dense" ? "dense" : "served";
export const FIELD = DATA[DATASET];

/** Which relationship ids in this field were written rather than gated. */
export const SYNTHETIC_IDS = new Set(DATA.dense.synthetic_ids ?? []);
export const isSynthetic = (relation) => SYNTHETIC_IDS.has(relation.id);

export const mediumOf = (node) => MEDIUM_MARK[node.source_type] ?? MEDIUM_MARK.youtube;

/** The brief state for a source id, read from the neighbourhood bodies. */
export function briefStateOf(sourceId) {
  const body = FIELD.focus?.[sourceId];
  return body?.source_knowledge?.state ?? "unavailable";
}

/** The run status a brief declares, or `null` where there is no brief. */
export function statusOf(sourceId) {
  const body = FIELD.focus?.[sourceId];
  return body?.source_knowledge?.brief?.status ?? null;
}

export const nodeBySourceId = (nodes) =>
  new Map(nodes.map((node) => [node.source_id, node]));

/** A relation's direction as seen from `sourceId`, read from its own ends. */
export const directionFrom = (relation, sourceId) =>
  relation.from_source_id === sourceId ? "outgoing" : "incoming";

export const otherEnd = (relation, sourceId) =>
  relation.from_source_id === sourceId ? relation.to_source_id : relation.from_source_id;

/* ---- shared chrome pieces ---------------------------------------------- */

/** The provenance / medium / brief badges every card head carries. */
export function badges(node, into, { status = null, state = null } = {}) {
  const provenance = el("span", "badge badge--source");
  provenance.append(
    el("span", "badge__glyph", PROVENANCE_GLYPH.source),
    " ",
    t("provenance.source"),
  );
  const medium = el("span", "badge badge--medium");
  const mark = mediumOf(node);
  medium.style.setProperty("--medium-hue", mark.hue);
  medium.append(
    el("span", "badge__glyph", mark.glyph),
    " ",
    t(`source.medium.${node.source_type}`),
  );
  into.append(provenance, medium);

  if (state !== null) {
    const brief = el("span", `badge badge--brief badge--brief-${state}`);
    brief.append(`${t("source.brief.state")}: ${t(`source.brief.${state}`)}`);
    into.append(brief);
  }
  if (status !== null) {
    const run = el("span", `badge badge--status badge--status-${status.toLowerCase()}`);
    run.append(`${t("source.status")}: `, el("span", "mono", status));
    into.append(run);
  }
}

/**
 * One relationship, as a pill.
 *
 * Two variants, and the difference is what a pill is *for*. On the stage it
 * labels an edge — direction, vocabulary, scope — and it has to fit in the run
 * of clear space between a card and its neighbour, which the seat search
 * measures rather than assumes. In a list it is a row and can carry the basis
 * count as well. Building one pill for both put a four-part row on a 234 px run
 * and two of them found no seat at all, which the capture gate refused.
 *
 * The `written` marker is on BOTH, because that is the disclosure: a reader
 * looking at one edge must be able to see that its judgement was invented.
 */
export function relationPill(relation, sourceId, { active = false, row = false, nearLabel = null } = {}) {
  // `.relpill` is absolutely positioned, because on the stage it is seated on a
  // path. In a list it is in flow, and T-211's `.relpill--inline` is what says
  // so — without it the drawer's pills stacked on the drawer's own corner and
  // ran off its inline edge, under RTL most visibly.
  const pill = el("div", `relpill${active ? " relpill--active" : ""}${row ? " relpill--inline" : ""}`);
  const arrow = RTL ? "←" : "→";
  const direction = directionFrom(relation, sourceId);
  const name = el("strong", "", relation.relation_type);
  name.classList.add("relpill__vocab-name");
  // The near end is the focus, named by its own external id. Writing the word
  // "Source" there named a *type* where an *end* belongs, and read as though
  // every edge joined the same anonymous thing.
  const near = el("span", "relpill__focus", nearLabel ?? sourceId.split(":").slice(1).join(":"));
  if (direction === "incoming") {
    pill.append(name, el("span", "relpill__dir", arrow), near);
  } else {
    pill.append(near, el("span", "relpill__dir", arrow), name);
  }
  pill.append(
    el("span", "relpill__scope", t(`source.relations.scope.${relation.scope}`)),
  );
  if (row) {
    pill.append(
      el("span", "relpill__basis", `${relation.basis_total} ${t("source.basis.pairs")}`),
    );
  }
  if (isSynthetic(relation)) pill.append(el("span", "relpill__written", t("source.synthetic.mark")));
  return pill;
}
