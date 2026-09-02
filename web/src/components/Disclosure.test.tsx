/**
 * `T-208`: a panel may be put away, and may not go quiet.
 *
 * Three claims, and the second is the one that makes a collapsed Map usable
 * rather than a row of doors: the summary keeps stating what the panel holds.
 */

import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Disclosure } from "./Disclosure";
import { renderApp } from "../test/render";

function panel(id: string): HTMLElement {
  const found = document.querySelector<HTMLElement>(`[data-map-panel='${id}']`);
  if (found === null) throw new Error(`no panel named ${id}`);
  return found;
}

function details(id: string): HTMLDetailsElement {
  const found = panel(id).querySelector("details");
  if (found === null) throw new Error("a disclosure that is not a `<details>`");
  return found as HTMLDetailsElement;
}

describe("a disclosure panel", () => {
  it("is the platform's own disclosure, with the heading as its toggle", () => {
    renderApp(
      <Disclosure id="related" title="Related knowledge" summary="8 related entities" preferOpen>
        <p>a neighbour</p>
      </Disclosure>,
    );
    // A labelled region with a real heading, so the document outline is
    // unchanged by the panel being collapsible.
    expect(screen.getByRole("region", { name: "Related knowledge" })).toBeDefined();
    expect(screen.getByRole("heading", { name: "Related knowledge", level: 2 })).toBeDefined();
    const summary = details("related").querySelector("summary");
    expect(summary).not.toBeNull();
    expect(summary?.querySelector("h2")).not.toBeNull();
  });

  it("states what it holds while it is closed", () => {
    renderApp(
      <Disclosure
        id="related"
        title="Related knowledge"
        summary="8 related entities"
        preferOpen={false}
      >
        <p>a neighbour</p>
      </Disclosure>,
    );
    expect(details("related").open).toBe(false);
    // The count is outside the folded body, which is the whole point: putting
    // a panel away must not hide that there is something in it.
    expect(screen.getByText("8 related entities")).toBeDefined();
    expect(panel("related").dataset.mapPanelOpen).toBe("false");
  });

  it("follows the journey when the step changes", () => {
    const { rerender } = renderApp(
      <Disclosure id="quickread" title="Quick Read" preferOpen={false}>
        <p>the record</p>
      </Disclosure>,
    );
    expect(details("quickread").open).toBe(false);
    rerender(
      <Disclosure id="quickread" title="Quick Read" preferOpen>
        <p>the record</p>
      </Disclosure>,
    );
    expect(details("quickread").open).toBe(true);
    expect(panel("quickread").dataset.mapPanelOpen).toBe("true");
  });

  it("keeps the reader's own choice through a re-render that changes nothing", () => {
    // The failure this guards is a panel forced open on every render, which
    // reopens itself the moment anything above it re-renders -- and on this
    // route something above it re-renders on every accumulated page.
    const { rerender } = renderApp(
      <Disclosure id="search" title="Search this Map" summary="nothing searched yet" preferOpen>
        <p>the form</p>
      </Disclosure>,
    );
    const element = details("search");
    element.open = false;
    fireEvent(element, new Event("toggle"));
    expect(panel("search").dataset.mapPanelOpen).toBe("false");

    rerender(
      <Disclosure id="search" title="Search this Map" summary="1 loaded nodes match" preferOpen>
        <p>the form</p>
      </Disclosure>,
    );
    expect(details("search").open).toBe(false);
    // And the summary still updated while folded.
    expect(screen.getByText("1 loaded nodes match")).toBeDefined();
  });

  it("carries the marks a test reads without a component forwarding them by hand", () => {
    renderApp(
      <Disclosure
        id="outline"
        title="What this Map holds"
        preferOpen
        marks={{ "data-map-outline": "4" }}
      >
        <p>rows</p>
      </Disclosure>,
    );
    expect(panel("outline").dataset.mapOutline).toBe("4");
  });
});
