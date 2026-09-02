/**
 * A panel that can be put away, and says what it holds while it is (`T-208`).
 *
 * `T-207` left three panels competing for one screen -- the search rail,
 * Quick Read and the related list -- and made Quick Read a `<details>` as far
 * as it went. This is the rest of that sentence, and the reason it is one
 * component rather than a `<details>` per panel is that the *rule* is what
 * matters, not the element:
 *
 * 1. **A collapsed panel still states its own content.** The summary carries
 *    the panel's count -- entities related, nodes loaded, hits matched -- so
 *    putting a panel away never hides the fact that there is something in it.
 *    A disclosure that says only "Related knowledge" turns a reader's screen
 *    into a row of doors.
 * 2. **The journey opens the right one.** `preferOpen` is a *preference*, not
 *    a lock: it follows the step D-130's journey is on (nothing selected ->
 *    search; something selected -> read it), and the reader may still overrule
 *    it. A panel forced open on every render would fight the reader's own
 *    click; a panel that ignored the journey would leave the answer to a
 *    selection folded away.
 * 3. **It is the platform's disclosure.** `<details>`/`<summary>` is
 *    focusable, operable by Enter and Space, exposed as expanded or
 *    collapsed, and it works with no script at all. A `<div>` with
 *    `aria-expanded` and a click handler is the same widget rebuilt worse.
 *
 * The heading stays inside the summary so the document keeps one outline: the
 * panel is still a labelled region with an `<h2>`, and the toggle *is* the
 * heading rather than a control beside it.
 *
 * ## Why the element is not re-rendered from state
 *
 * `open` is written twice: once as a prop, at mount, and after that only
 * imperatively when the *preference* changes. It is deliberately not a
 * rendered prop, and the reason is a defect this component had first:
 *
 * A `<details>` fires `toggle` **asynchronously** -- including for a change
 * a script made. Rendering `open={state}` therefore turns every programmatic
 * change into a `toggle` event that arrives one task later and writes the
 * value back into the state that caused it. Two preference changes in quick
 * succession (a graph arrives, the renderer refuses it, and the companion
 * panel's step changes twice) let the *first* event's value land after the
 * second change, and the panel closed itself with nothing having been
 * clicked. Writing the element once and then imperatively means React never
 * re-asserts `open` on an unrelated render, so a late event can only report
 * -- and it reports by reading the element, not by trusting its own payload.
 */

import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";

export function Disclosure({
  id,
  title,
  summary,
  preferOpen,
  className,
  marks,
  onKeyDown,
  children,
}: {
  /** A stable name for this panel, for the test seam and for nothing else. */
  id: string;
  /** The panel's heading, already translated. */
  title: string;
  /**
   * What the panel holds, in the reader's language -- a count, or a state.
   *
   * Rendered beside the heading whether the panel is open or closed, which is
   * the whole point: this is the line that keeps a folded panel honest.
   */
  summary?: ReactNode;
  /** Whether the journey wants this panel open right now. */
  preferOpen: boolean;
  className?: string;
  /** `data-*` attributes for the section, passed explicitly (`T-207`). */
  marks?: Record<string, string>;
  onKeyDown?: (event: KeyboardEvent<HTMLElement>) => void;
  children: ReactNode;
}) {
  const element = useRef<HTMLDetailsElement | null>(null);
  /** What the element was mounted with. Never changes, so React writes it once. */
  const mounted = useRef(preferOpen).current;
  /** What the element *is*, for the mark a test and a stylesheet read. */
  const [open, setOpen] = useState(preferOpen);
  const followed = useRef(preferOpen);

  useEffect(() => {
    if (followed.current === preferOpen) return;
    followed.current = preferOpen;
    const details = element.current;
    if (details !== null && details.open !== preferOpen) details.open = preferOpen;
    setOpen(preferOpen);
  }, [preferOpen]);

  return (
    <section
      className={`panel stack${className === undefined ? "" : ` ${className}`}`}
      aria-label={title}
      data-map-panel={id}
      data-map-panel-open={String(open)}
      {...(onKeyDown === undefined ? {} : { onKeyDown })}
      {...marks}
    >
      <details
        ref={element}
        open={mounted}
        // `onToggle` rather than a click handler on the summary: the element
        // is also toggled by Enter, by Space, and by a browser's own
        // "expand all" find-in-page, and only the toggle event sees all of
        // them. The element is read rather than the event's own payload,
        // because the event is delivered a task late and may describe a state
        // the element has already left.
        onToggle={() => setOpen(element.current?.open === true)}
      >
        <summary className="disclosure__summary">
          <h2 className="panel__title">{title}</h2>
          {summary !== undefined && <span className="faint disclosure__count">{summary}</span>}
        </summary>
        <div className="stack disclosure__body">{children}</div>
      </details>
    </section>
  );
}
