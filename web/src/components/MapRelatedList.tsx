/**
 * The complete related list (`T-207`, D-132, risk R20).
 *
 * This is the surface that **cannot omit anything**, and that is its whole
 * reason for existing. The stage carries the cards its density policy can
 * place; this list carries every neighbour the API returned, in the
 * deterministic order `neighbourhood.ts` fixes, whether or not it has a card,
 * whether or not the Map has drawn its mark. "No neighbour silently
 * disappears" is `T-207`'s acceptance criterion and it is a property of this
 * component: nothing here filters, slices or caps.
 *
 * Each row says three things a reader needs *before* opening it, and D-130's
 * acceptance question is exactly whether it does:
 *
 * 1. **What it says** -- the statement, verbatim, cut by the one cutter with
 *    the cut marked (D-131).
 * 2. **Why it is worth opening** -- its real relation to the focus, with its
 *    direction and its vocabulary. A neighbour more than one hop out states no
 *    relation to the focus itself, so it says *that* instead of borrowing one.
 * 3. **Whether it is on the Map** -- drawn, or returned by the index and not
 *    yet loaded. Those are different facts and the row keeps them apart.
 *
 * The card is `MapResultCard`, the same one the search rail uses, with the
 * relation in its context slot. §8.6 allows one card-content formatter and
 * this is not a second one: a related row and a search hit are the same card
 * carrying different context.
 *
 * **Depth is a control here** because depth is what this list contains. It is
 * not in the URL (D-136): `mapLink`'s grammar is frozen at selection plus the
 * three filters `GET /api/graph` accepts, and depth bounds one request without
 * changing which graph is drawn. Values are the contract's own 1..3 and the
 * request is refused rather than clamped above that (`parseDepth`).
 */

import type { AsyncStatus } from "../api/useAsync";
import type { MapGraph } from "../map/graphProjection";
import type { StageOmission, StagePlacement } from "../map/constellation";
import { STAGE_OMISSIONS } from "../map/constellation";
import { MAP_DEPTHS, type MapDepth, type Neighbourhood } from "../map/neighbourhood";
import type { NeighbourhoodFailure } from "../map/useNeighbourhood";
import type { MapPeekBinding } from "../map/useMapPeek";
import { previewOfEntity } from "../map/useMapSearch";
import { ApiFailure } from "../api/errors";
import { useI18n, type MessageKey } from "../i18n";
import { ErrorState } from "./ErrorState";
import { MapResultCard } from "./MapResultCard";
import { RelationCues } from "./MapRelation";

/**
 * Why a returned neighbour has no card on the stage, in words.
 *
 * A `Record` of literal keys rather than a template: the scaffold guard finds
 * a shipped string by its literal, and a computed key makes a live translation
 * read as abandoned (§8.6).
 */
const OMISSION_LABEL: Record<StageOmission, MessageKey> = {
  not_loaded: "map.stage.omitted.notLoaded",
  off_stage: "map.stage.omitted.offStage",
  crowded: "map.stage.omitted.crowded",
  budget: "map.stage.omitted.budget",
};

export function MapRelatedList({
  focus,
  neighbourhood,
  status,
  error,
  onRetry,
  depth,
  onDepthChange,
  graph,
  onFocus,
  peek,
  placement,
}: {
  /** The focused `global_id`, or `null`. */
  focus: string | null;
  /** The projected neighbourhood, or `null` before one has been read. */
  neighbourhood: Neighbourhood | null;
  status: AsyncStatus;
  error: NeighbourhoodFailure | null;
  onRetry: () => void;
  depth: MapDepth;
  onDepthChange: (depth: MapDepth) => void;
  /** The accumulated graph, so "drawn on the Map" is read rather than assumed. */
  graph: MapGraph | null;
  onFocus: (globalId: string | null) => void;
  peek: MapPeekBinding;
  /** What the density policy placed, so a row can say its card is on the stage. */
  placement: StagePlacement | null;
}) {
  const { t } = useI18n();

  if (focus === null) {
    return (
      <section className="panel stack map__related" aria-label={t("map.related.title")}>
        <h2 className="panel__title">{t("map.related.title")}</h2>
        <p className="muted">{t("map.related.noFocus")}</p>
      </section>
    );
  }

  const onStage = new Set((placement?.cards ?? []).map((card) => card.globalId));
  const related = neighbourhood?.related ?? [];

  return (
    <section
      className="panel stack map__related"
      aria-label={t("map.related.title")}
      data-map-related={related.length}
      data-map-related-depth={neighbourhood?.depth ?? depth}
    >
      <h2 className="panel__title">{t("map.related.title")}</h2>
      <p className="faint">{t("map.related.hint")}</p>

      <div className="row">
        <label className="field">
          <span>{t("map.related.depth")}</span>
          <select
            value={depth}
            onChange={(event) => {
              // The option values are this Map's own depths, so the parse
              // cannot fail -- but it is read back through the same guard the
              // request uses rather than trusted, because a value that only
              // *happens* to be valid is not a checked value.
              const chosen = MAP_DEPTHS.find((value) => String(value) === event.currentTarget.value);
              if (chosen !== undefined) onDepthChange(chosen);
            }}
          >
            {MAP_DEPTHS.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </label>
        <span className="faint">{t("map.related.depthNote")}</span>
      </div>

      {error instanceof ApiFailure && <ErrorState error={error} onRetry={onRetry} />}
      {error !== null && !(error instanceof ApiFailure) && (
        <div className="notice notice--internal" role="alert" data-map-related-conflict={error.field}>
          <strong>{t("map.conflict.title")}</strong>
          <p>
            {t("map.conflict.detail", { kind: error.kind, id: error.id, field: error.field })}
          </p>
        </div>
      )}

      {status === "loading" && <p className="muted">{t("common.loading")}</p>}

      {neighbourhood !== null && (
        <>
          <p className="faint" data-map-related-count={related.length}>
            {t("map.related.count", {
              count: related.length,
              depth: neighbourhood.depth,
              edges: neighbourhood.edgesReturned,
            })}
          </p>
          {neighbourhood.truncated && (
            <p className="notice notice--unavailable" data-map-related-truncated>
              {t("map.related.truncated")}
            </p>
          )}
          {neighbourhood.edgesUnjoinable > 0 && (
            <p className="faint" data-map-related-unjoinable={neighbourhood.edgesUnjoinable}>
              {t("map.related.unjoinable", { count: neighbourhood.edgesUnjoinable })}
            </p>
          )}
          {neighbourhood.unreachable > 0 && (
            <p className="faint" data-map-related-unreachable={neighbourhood.unreachable}>
              {t("map.related.unreachable", { count: neighbourhood.unreachable })}
            </p>
          )}
          {placement !== null && placement.omittedTotal > 0 && (
            <div className="stack" data-map-stage-omitted={placement.omittedTotal}>
              <p className="faint">
                {t("map.stage.omitted", { count: placement.omittedTotal })}
              </p>
              <ul className="stack map__list">
                {STAGE_OMISSIONS.filter((reason) => placement.omitted[reason] > 0).map((reason) => (
                  <li key={reason} className="faint" data-map-stage-omission={reason}>
                    {t(OMISSION_LABEL[reason], { count: placement.omitted[reason] })}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {related.length === 0 && <p className="muted">{t("map.related.none")}</p>}
        </>
      )}

      {related.map((entity) => {
        const drawn = graph !== null && graph.hasNode(entity.globalId);
        return (
          <MapResultCard
            key={entity.globalId}
            // From the index, because that is where this record came from --
            // the neighbourhood endpoint -- and drawn or not is read from the
            // accumulated graph rather than assumed either way.
            preview={previewOfEntity(entity.record, { origin: "index", loaded: drawn })}
            focused={false}
            onFocus={onFocus}
            peek={drawn ? peek.handlers(entity.globalId) : undefined}
          >
            <div className="stack" data-map-related-entity={entity.globalId}>
              <RelationCues
                relations={entity.toCentre}
                subject="this"
                empty={t("map.related.viaPath", { hops: entity.hops })}
              />
              <p className="faint">
                {t("map.related.hops", { count: entity.hops })}
                {onStage.has(entity.globalId) && (
                  <span data-map-related-on-stage> — {t("map.related.onStage")}</span>
                )}
              </p>
            </div>
          </MapResultCard>
        );
      })}
    </section>
  );
}
