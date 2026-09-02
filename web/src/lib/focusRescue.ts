/**
 * Keep the keyboard journey alive when a control removes itself (D-180).
 *
 * Every control in this app that disappears on activation dropped focus to
 * `<body>`: tab to `Load more`, press it, the final page arrives, the button
 * unmounts with no focus target named -- and `document.activeElement` is the
 * document body, which is nowhere. The keyboard journey ends mid-page, and the
 * reader's next `Tab` restarts from the top of the document. Seven controls did
 * this: both `Load more` buttons on the Map, the Library's and the Reader's,
 * `Stop loading`, and both `Clear search` buttons.
 *
 * The check is made *after* React has committed, and only then: a control that
 * is still on the page and still focused is left alone, because moving focus
 * off a `Load more` a reader means to press again would be its own defect. So
 * this costs nothing on the pages where the button survives, and fires on
 * exactly the render where it does not.
 *
 * Focus lands on the nearest `[data-focus-anchor]`, or on the control's parent
 * when nothing declares one -- the enclosing region, so the next `Tab` resumes
 * where the reader was rather than at the top. The anchor is made
 * programmatically focusable (`tabIndex = -1`) rather than tabbable, so it
 * never joins the tab order itself.
 */

/** Move focus to *anchor* if the control that had it has gone. */
function rescue(anchor: HTMLElement): void {
  const owner = anchor.ownerDocument;
  const active = owner.activeElement;
  if (active !== null && active !== owner.body) return;
  if (!anchor.isConnected) return;
  if (!anchor.hasAttribute("tabindex")) anchor.setAttribute("tabindex", "-1");
  anchor.focus();
}

/**
 * Wrap a click handler so focus survives the control unmounting.
 *
 * `onClick={withFocusRescue(doTheThing)}` -- the action runs exactly as before;
 * the rescue is scheduled after it and does nothing unless focus was lost.
 */
export function withFocusRescue<E extends { currentTarget: HTMLElement }>(
  action: (event: E) => void,
): (event: E) => void {
  return (event: E) => {
    const control = event.currentTarget;
    const anchor =
      control.closest<HTMLElement>("[data-focus-anchor]") ?? control.parentElement;
    action(event);
    if (anchor === null) return;
    // A task, not a microtask: the control unmounts in React's commit, and a
    // microtask can run before it. Nothing here depends on *when* it runs, only
    // on it running after the DOM has settled.
    setTimeout(() => rescue(anchor), 0);
  };
}
