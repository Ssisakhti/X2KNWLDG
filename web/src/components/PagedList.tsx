/**
 * The one paged-list ladder, in one place (D-203).
 *
 * Five surfaces repeated the identical sequence — refuse, load, empty, total,
 * items, More — with five copies of every decision in it: the Library's
 * sources, the Reader's units and relations, the search results, and the Map's
 * search rail. Copies of a ladder are copies of every bug in it, and this one
 * had three:
 *
 * 1. **A failed later page destroyed the loaded ones.** `usePaged.loadMore`'s
 *    catch set the same `error` the *first* page's failure sets, and every one
 *    of the five branched on that field before rendering items — so one
 *    transient hiccup on "More" replaced fifty loaded records with an error
 *    panel, and the only way back discarded every page already fetched.
 *    `usePaged` now separates the two, and this renders `moreError` where the
 *    gap is: after the items, beside the button that failed, with what is
 *    loaded still on screen.
 * 2. **"More" dropped keyboard focus** on two of the five. D-180 wrapped seven
 *    controls in `withFocusRescue` and these were not among them; the button
 *    is built here now, so there is one place for that to be true.
 * 3. **Async status was announced nowhere.** Every loading state was a bare
 *    `<p class="muted">`, so a reader on a screen reader submitted a search
 *    and heard nothing — not that it had started, and not that hits had
 *    arrived. The status line is a `role="status"` live region here, and it
 *    says which state the list is in rather than only "loading".
 *
 * What is deliberately *not* here is anything about what an item looks like.
 * The items are the caller's, rendered through `children`, because a source
 * card, an entity card, a relation row and a search hit have nothing in common
 * but their position in this ladder.
 */

import type { ReactNode } from "react";

import type { PagedState } from "../api/usePaged";
import { useI18n } from "../i18n";
import { withFocusRescue } from "../lib/focusRescue";
import { ErrorState } from "./ErrorState";

export function PagedList<T>({
  state,
  empty,
  children,
  label,
}: {
  /** The walk this list is a view of. */
  state: PagedState<T>;
  /** What to say when the walk succeeded and found nothing. */
  empty: ReactNode;
  /** The loaded items, rendered by whoever owns their shape. */
  children: (items: readonly T[]) => ReactNode;
  /**
   * What this list holds, for the announcement.
   *
   * A screen reader is told "loading sources", not "loading": three lists on
   * one route all announcing the same word say nothing about which one moved.
   */
  label: string;
}) {
  const { t } = useI18n();

  // The first page failed, so there is nothing to show. This is the only state
  // that replaces the list, and it is the distinction `moreError` exists for.
  if (state.error !== null) {
    return <ErrorState error={state.error} onRetry={state.reload} />;
  }

  const total =
    state.total === null ? t("common.unknownTotal") : t("common.total", { count: state.total });

  return (
    <>
      {/*
        One live region per list, carrying whichever of the three things is
        true: loading, the total, or empty. `role="status"` is polite, and the
        text is replaced rather than appended, so a reader hears the list's
        current state and not a log of it.
      */}
      <p
        className={state.status === "loading" ? "muted" : "faint"}
        role="status"
        data-paged-status={state.status}
      >
        {state.status === "loading"
          ? t("common.loadingNamed", { name: label })
          : state.items.length === 0
            ? empty
            : total}
      </p>

      {state.status === "loading" ? null : children(state.items)}

      {/*
        A page that did not arrive is a gap at the end of a list, not a reason
        to forget the list. Reported here, with everything already loaded still
        on screen and the button still there to try again.
      */}
      {state.moreError !== null && (
        <>
          <p className="faint" role="status">
            {t("common.pageFailed")}
          </p>
          <ErrorState error={state.moreError} onRetry={state.loadMore} />
        </>
      )}

      {state.hasMore && (
        <button
          type="button"
          className="button"
          // D-180's rule, applied where the button is built rather than at
          // each of the five call sites that used to build one.
          onClick={withFocusRescue(state.loadMore)}
          disabled={state.loadingMore}
          data-paged-more
        >
          {state.loadingMore ? t("common.loading") : t("common.more")}
        </button>
      )}
    </>
  );
}
