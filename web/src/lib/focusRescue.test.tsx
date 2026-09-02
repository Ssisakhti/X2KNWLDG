/**
 * D-180: a control that removes itself must not take the keyboard with it.
 *
 * Every control in this app that disappears on activation dropped focus to
 * `<body>` — tab to `Load more`, press it, the last page arrives, the button
 * unmounts with nothing named as the next focus, and the reader's next `Tab`
 * restarts at the top of the document. Seven controls did it and
 * `MapView.access.test.tsx` covered none of them, because a walk that clicks
 * with a pointer never notices where focus went.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import { withFocusRescue } from "./focusRescue";

function Vanishing({ rescue }: { rescue: boolean }) {
  const [gone, setGone] = useState(false);
  const go = () => setGone(true);
  return (
    <section data-focus-anchor data-testid="region">
      <button type="button">before</button>
      {!gone && (
        <button type="button" onClick={rescue ? withFocusRescue(go) : go}>
          vanishing
        </button>
      )}
    </section>
  );
}

function Staying() {
  const [count, setCount] = useState(0);
  return (
    <section data-focus-anchor>
      <button type="button" onClick={withFocusRescue(() => setCount((n) => n + 1))}>
        stays {count}
      </button>
    </section>
  );
}

describe("a control that removes itself on activation", () => {
  it("drops focus to the body without the rescue — the defect, stated", async () => {
    render(<Vanishing rescue={false} />);
    const button = screen.getByText("vanishing");
    button.focus();
    expect(document.activeElement).toBe(button);

    fireEvent.click(button);
    await waitFor(() => expect(screen.queryByText("vanishing")).toBeNull());
    expect(document.activeElement).toBe(document.body);
  });

  it("leaves focus inside the page with it", async () => {
    render(<Vanishing rescue />);
    const button = screen.getByText("vanishing");
    button.focus();

    fireEvent.click(button);
    await waitFor(() => expect(screen.queryByText("vanishing")).toBeNull());
    await waitFor(() => {
      expect(document.activeElement).toBe(screen.getByTestId("region"));
    });
    // Focusable programmatically, never tabbable: the anchor must not join the
    // tab order it exists to preserve.
    expect(screen.getByTestId("region").getAttribute("tabindex")).toBe("-1");
  });

  it("leaves a surviving control focused, because a reader may press it again", async () => {
    render(<Staying />);
    const button = screen.getByText(/stays/);
    button.focus();

    fireEvent.click(button);
    await waitFor(() => expect(screen.getByText("stays 1")).not.toBeNull());
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(document.activeElement).toBe(screen.getByText("stays 1"));
  });

  it("runs the action exactly once, and first", () => {
    const calls: string[] = [];
    const handler = withFocusRescue(() => calls.push("action"));
    const anchor = document.createElement("div");
    document.body.append(anchor);
    const button = document.createElement("button");
    anchor.append(button);
    handler({ currentTarget: button } as never);
    expect(calls).toEqual(["action"]);
    anchor.remove();
  });
});
