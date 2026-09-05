/**
 * What the marks on the Map mean (`T-205`).
 *
 * A legend is not decoration here, it is the other half of ADR 0005 invariant
 * 9. The canvas draws provenance as a *shape* and relation vocabulary as the
 * shape of an edge's ends, precisely so that neither distinction depends on
 * seeing colour -- and a shape carries no meaning at all until something says
 * which shape means what. This component is that something, and it reads the
 * same tables the reducers draw from (`map/mapStyle.ts`), so "the legend
 * agrees with the marks" is a property of the code rather than a promise.
 *
 * Every row states its meaning in **words** as well as in a mark. A row that
 * were only a colour swatch would reintroduce the colour-only distinction the
 * canvas was careful to avoid, so the tests assert that each row has text.
 *
 * The provenance rows also carry the Library's own `ProvenanceBadge`, which is
 * the signal the user has already learned in the Library and the Reader. The
 * legend is where the DOM's vocabulary and the canvas's vocabulary are stated
 * to be the same vocabulary.
 */

import type { ReactNode } from "react";

import type { ProvenanceClass } from "../api/contract";
import { PROVENANCE_CLASSES, RELATION_VOCABULARIES } from "../api/vocabulary";
import { useI18n, type MessageKey } from "../i18n";
import {
  edgeProvenanceMarks,
  EDGE_VOCABULARY_MARK,
  KIND_FAMILIES,
  kindFamilyColour,
  NODE_PROVENANCE_MARK,
  unrecognisedEdgeProvenanceMark,
  UNRECOGNISED_PROVENANCE_MARK,
  UNRECOGNISED_VOCABULARY_MARK,
  type MapEdgeExtremity,
  type MapNodeShape,
  type KindFamily,
} from "../map/mapStyle";
import { useMapStage } from "../map/useMapStage";
import { Disclosure } from "./Disclosure";
import { ProvenanceBadge } from "./Provenance";
import { FORWARD_GLYPH } from "./primitives";

/**
 * A drawable stand-in for each canvas shape.
 *
 * These are the same silhouettes the SDF shapes draw, so the legend can be
 * read beside the canvas rather than translated from it.
 */
const SHAPE_GLYPH: Record<MapNodeShape, string> = {
  circle: "●",
  diamond: "◆",
  square: "■",
  triangle: "▲",
};

/**
 * The same, for the marks at the ends of an edge. `none` is a bare line.
 *
 * `arrow` is the one directional glyph here, and it is wrapped in
 * `.glyph-inline-forward` where it is rendered so it mirrors under
 * `dir="rtl"` (D-203): the legend's rows reverse with the writing direction
 * and U+2192 does not, so an unmirrored arrow described the opposite end of
 * an edge from the one it labels.
 */
const EXTREMITY_GLYPH: Record<MapEdgeExtremity, string> = {
  none: "─",
  arrow: FORWARD_GLYPH,
  diamond: "◆",
  circle: "●",
  bar: "┤",
  square: "■",
};

/** An extremity glyph, mirrored when it is the directional one. */
function Extremity({ head }: { head: MapEdgeExtremity }) {
  const glyph = EXTREMITY_GLYPH[head];
  return head === "arrow" ? (
    <span className="glyph-inline-forward">{glyph}</span>
  ) : (
    <>{glyph}</>
  );
}




/**
 * Every mark's message key, spelled out rather than built.
 *
 * `t(FAMILY_LABEL[family])` type-checks and renders correctly, and it
 * would still be wrong here: `tests/test_ui_scaffold.py` looks for the literal
 * key in the source to tell a string that ships from a string the catalogue
 * only promises, and a computed key makes all eighteen of these read as
 * abandoned. `Provenance.tsx` spells its vocabulary keys out for the same
 * reason, and the `Record` keeps the compiler's exhaustiveness either way.
 */
const SHAPE_LABEL: Record<MapNodeShape, MessageKey> = {
  circle: "map.legend.shape.circle",
  diamond: "map.legend.shape.diamond",
  square: "map.legend.shape.square",
  triangle: "map.legend.shape.triangle",
};

const FAMILY_LABEL: Record<KindFamily, MessageKey> = {
  thesis: "map.legend.family.thesis",
  evidence: "map.legend.family.evidence",
  concept: "map.legend.family.concept",
  framework: "map.legend.family.framework",
  process: "map.legend.family.process",
  example: "map.legend.family.example",
  fact: "map.legend.family.fact",
  recommendation: "map.legend.family.recommendation",
  caveat: "map.legend.family.caveat",
  question: "map.legend.family.question",
  synthesis: "map.legend.family.synthesis",
  reference: "map.legend.family.reference",
  unstated: "map.legend.family.unstated",
  unrecognised: "map.legend.family.unrecognised",
};

/**
 * One mark and its meaning.
 *
 * The glyph is `aria-hidden`: it is a picture of the mark, and the row's
 * meaning is the text beside it. `marks` carries the `data-*` attributes the
 * tests read, which is how "the legend agrees with the table" is checked
 * against the table rather than against a rendered string.
 */
function Row({
  glyph,
  colour,
  marks,
  children,
}: {
  glyph: string;
  colour?: string;
  marks: Record<string, string>;
  children: ReactNode;
}) {
  return (
    <li className="row" {...marks}>
      <span
        // `glyph-inline-forward` on the one directional glyph: the row
        // reverses with the writing direction and U+2192 does not, so an
        // unmirrored arrow described the opposite end of an edge from the one
        // it labels (D-203).
        className={`badge__glyph${glyph === EXTREMITY_GLYPH.arrow ? " glyph-inline-forward" : ""}`}
        aria-hidden="true"
        style={colour === undefined ? undefined : { color: colour }}
      >
        {glyph}
      </span>
      <span>{children}</span>
    </li>
  );
}

export function MapLegend() {
  const { t } = useI18n();
  // The stage the canvas is drawing on, so a swatch here is the ink there.
  const stage = useMapStage();
  const familyInk = kindFamilyColour(stage);
  const edgeInk = edgeProvenanceMarks(stage);
  const unrecognisedEdgeInk = unrecognisedEdgeProvenanceMark(stage);

  return (
    // Collapsed by default (`T-208`): a legend is read once and then known,
    // and it is the longest panel on the route. Folded, it still names itself,
    // and the marks it explains are not going anywhere.
    <Disclosure
      id="legend"
      title={t("map.legend.title")}
      /*
       * `Disclosure`'s first rule is that a collapsed panel still states its
       * own content — "a disclosure that says only 'Related knowledge' turns a
       * reader's screen into a row of doors". This panel was the one that did
       * exactly that: folded, it was a bordered card carrying a title and
       * nothing else, which reads as a panel that failed to load rather than
       * one that is closed. What it holds is a fixed vocabulary rather than a
       * changing count, so the summary names the vocabulary.
       */
      summary={t("map.legend.summary", {
        shapes: PROVENANCE_CLASSES.length + 1,
        hues: KIND_FAMILIES.length,
      })}
      preferOpen={false}
      marks={{ "data-map-legend": "" }}
    >
      <p className="faint">{t("map.legend.noColourOnly")}</p>

      <h3 className="faint">{t("map.legend.nodesShape")}</h3>
      <ul className="stack">
        {PROVENANCE_CLASSES.map((provenance: ProvenanceClass) => {
          const mark = NODE_PROVENANCE_MARK[provenance];
          return (
            <Row
              key={provenance}
              glyph={SHAPE_GLYPH[mark.shape]}
              marks={{
                "data-map-legend-provenance": provenance,
                "data-shape": mark.shape,
              }}
            >
              <ProvenanceBadge provenance={provenance} /> {t("map.legend.shape")}: {t(SHAPE_LABEL[mark.shape])}
            </Row>
          );
        })}
        <Row
          glyph={SHAPE_GLYPH[UNRECOGNISED_PROVENANCE_MARK.shape]}
          marks={{
            "data-map-legend-provenance": "unrecognised",
            "data-shape": UNRECOGNISED_PROVENANCE_MARK.shape,
          }}
        >
          {t("map.legend.unrecognised")} — {t("map.legend.shape")}: {t(SHAPE_LABEL[UNRECOGNISED_PROVENANCE_MARK.shape])}
        </Row>
      </ul>

      <h3 className="faint">{t("map.legend.edges")}</h3>
      <ul className="stack">
        {RELATION_VOCABULARIES.map((vocabulary) => {
          const mark = EDGE_VOCABULARY_MARK[vocabulary];
          return (
            <Row
              key={vocabulary}
              glyph={EXTREMITY_GLYPH[mark.head]}
              marks={{
                "data-map-legend-vocabulary": vocabulary,
                "data-head": mark.head,
              }}
            >
              {t(`vocabulary.${vocabulary}`)} — {t("map.legend.head")}: <Extremity head={mark.head} />
            </Row>
          );
        })}
        <Row
          glyph={EXTREMITY_GLYPH[UNRECOGNISED_VOCABULARY_MARK.head]}
          marks={{
            "data-map-legend-vocabulary": "unrecognised",
            "data-head": UNRECOGNISED_VOCABULARY_MARK.head,
          }}
        >
          {t("map.legend.unrecognised")} — {t("map.legend.head")}: <Extremity head={UNRECOGNISED_VOCABULARY_MARK.head} />
        </Row>
        {PROVENANCE_CLASSES.map((provenance: ProvenanceClass) => {
          const mark = edgeInk[provenance];
          return (
            <Row
              key={`edge-${provenance}`}
              glyph={EXTREMITY_GLYPH[mark.tail]}
              colour={mark.colour}
              marks={{
                "data-map-legend-edge-provenance": provenance,
                "data-tail": mark.tail,
                "data-colour": mark.colour,
              }}
            >
              {t(`provenance.${provenance}`)} — {t("map.legend.tail")}: <Extremity head={mark.tail} />
            </Row>
          );
        })}
        <Row
          glyph={EXTREMITY_GLYPH[unrecognisedEdgeInk.tail]}
          colour={unrecognisedEdgeInk.colour}
          marks={{
            "data-map-legend-edge-provenance": "unrecognised",
            "data-tail": unrecognisedEdgeInk.tail,
            "data-colour": unrecognisedEdgeInk.colour,
          }}
        >
          {t("map.legend.unrecognised")} — {t("map.legend.tail")}:{" "}
          <Extremity head={unrecognisedEdgeInk.tail} />
        </Row>
      </ul>

      <h3 className="faint">{t("map.legend.nodesColour")}</h3>
      <p className="faint">{t("map.legend.kindNote")}</p>
      <ul className="stack">
        {KIND_FAMILIES.map((family) => (
          <Row
            key={family}
            glyph={SHAPE_GLYPH.circle}
            colour={familyInk[family]}
            marks={{
              "data-map-legend-family": family,
              "data-colour": familyInk[family],
            }}
          >
            {t(FAMILY_LABEL[family])}
          </Row>
        ))}
      </ul>
      <p className="faint">{t("map.legend.unrecognisedNote")}</p>
    </Disclosure>
  );
}
