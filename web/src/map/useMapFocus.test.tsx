/**
 * Focus history (`T-206`, D-133, ADR 0005 invariant 14).
 *
 * The claim under test is not "the URL changes". It is the one a user makes
 * with their thumb: **Back restores the previous focus, and the Map is still
 * there** -- not reloaded, not re-fetched, not rebuilt. So the probe route
 * counts its own mounts, and every traversal below asserts that count has not
 * moved. A Map that unmounted and remounted would still show the right
 * selection and would have thrown away its accumulated graph to do it.
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { useEffect } from "react";
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";

import { useMapFocus } from "./useMapFocus";

const KU1 = "youtube:pqlWNihgdjI:KU-000001";
const KU2 = "youtube:pqlWNihgdjI:KU-000002";

/**
 * How many times the Map route has mounted in this test.
 *
 * Module scope on purpose: a counter held in the component would start again
 * at zero on a remount and would report "1" for the very failure it exists to
 * catch.
 */
let mounts = 0;
beforeEach(() => {
  mounts = 0;
});

/**
 * The Map, reduced to the two things this hook is about: the selection, and
 * the fact that the route stayed mounted while the selection changed.
 */
function MapProbe() {
  const { state, focus, filters, focusEntity, clearFocus, setFilters } = useMapFocus();
  const location = useLocation();
  const navigate = useNavigate();
  useEffect(() => {
    mounts += 1;
  }, []);

  return (
    <div>
      <output data-focus>{focus ?? ""}</output>
      <output data-search>{location.search}</output>
      <output data-filters>{JSON.stringify(filters)}</output>
      <output data-state>{JSON.stringify(state)}</output>
      {/* The keyboard-operable path: a real button, activated by the platform. */}
      <button type="button" onClick={() => focusEntity(KU1)}>
        focus one
      </button>
      <button type="button" onClick={() => focusEntity(KU2)}>
        focus two
      </button>
      {/* The pointer path a Sigma `clickNode` handler stands in for: the same
          function, reached from a surface that has no keyboard semantics. */}
      <div data-canvas role="presentation" onClick={() => focusEntity(KU1)}>
        canvas
      </div>
      <button type="button" onClick={clearFocus}>
        clear
      </button>
      <button type="button" onClick={() => setFilters({ provenance: "derived" })}>
        filter derived
      </button>
      <button type="button" onClick={() => navigate(-1)}>
        back
      </button>
    </div>
  );
}

function mountMap(initial = "/map") {
  return render(
    <MemoryRouter initialEntries={[initial]}>
      <Routes>
        <Route path="/map" element={<MapProbe />} />
        <Route path="/" element={<p>the library</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

const readFocus = () => document.querySelector("[data-focus]")?.textContent ?? "";
const readSearch = () => document.querySelector("[data-search]")?.textContent ?? "";
const readMounts = () => mounts;

describe("useMapFocus", () => {
  it("reads a valid URL", () => {
    const { container } = mountMap(
      `/map?focus=${encodeURIComponent(KU1)}&provenance_class=derived`,
    );
    expect(container.querySelector("[data-focus]")?.textContent).toBe(KU1);
    expect(container.querySelector("[data-filters]")?.textContent).toBe(
      JSON.stringify({ provenance_class: "derived" }),
    );
  });

  it("invents nothing out of a malformed URL", () => {
    // Nothing selected and nothing filtered, rather than a plausible guess at
    // what the link meant (D-119).
    const { container } = mountMap("/map?focus=KU-000001&provenance_class=derivd");
    expect(container.querySelector("[data-focus]")?.textContent).toBe("");
    expect(container.querySelector("[data-filters]")?.textContent).toBe("{}");
  });

  it("pushes a history entry that Back restores, without leaving the Map", () => {
    mountMap();
    expect(readFocus()).toBe("");
    expect(readMounts()).toBe(1);

    fireEvent.click(screen.getByText("focus one"));
    expect(readFocus()).toBe(KU1);
    expect(readSearch()).toBe(`?focus=${encodeURIComponent(KU1)}`);

    fireEvent.click(screen.getByText("focus two"));
    expect(readFocus()).toBe(KU2);

    fireEvent.click(screen.getByText("back"));
    expect(readFocus()).toBe(KU1);

    fireEvent.click(screen.getByText("back"));
    expect(readFocus()).toBe("");

    // The whole point: three focus states were traversed and the route was
    // mounted once. Nothing was rebuilt, so an accumulated graph would have
    // survived every one of them.
    expect(readMounts()).toBe(1);
    expect(screen.queryByText("the library")).toBeNull();
  });

  it("resolves the same id from the pointer path and the keyboard path", () => {
    mountMap();
    const button = screen.getByText("focus one");
    // A real `<button>`: Enter and Space activate it through the platform, so
    // the keyboard path is the same click handler rather than a second one
    // that could resolve a different identity (W3C G202).
    expect(button.tagName).toBe("BUTTON");
    fireEvent.click(button);
    const fromKeyboardCapableControl = readSearch();

    fireEvent.click(screen.getByText("clear"));
    expect(readFocus()).toBe("");

    fireEvent.click(document.querySelector("[data-canvas]") as Element);
    expect(readSearch()).toBe(fromKeyboardCapableControl);
    expect(readFocus()).toBe(KU1);
  });

  it("does not push an entry for a selection that is already the selection", () => {
    mountMap();
    fireEvent.click(screen.getByText("focus one"));
    fireEvent.click(screen.getByText("focus two"));
    fireEvent.click(screen.getByText("focus two"));
    fireEvent.click(screen.getByText("focus two"));

    // Three clicks, one entry: Back reaches the first selection rather than
    // appearing to do nothing twice.
    fireEvent.click(screen.getByText("back"));
    expect(readFocus()).toBe(KU1);
  });

  it("keeps the selection when a filter changes, and states both", () => {
    mountMap();
    fireEvent.click(screen.getByText("focus one"));
    fireEvent.click(screen.getByText("filter derived"));

    expect(readFocus()).toBe(KU1);
    expect(readSearch()).toBe(`?focus=${encodeURIComponent(KU1)}&provenance_class=derived`);
    expect(document.querySelector("[data-filters]")?.textContent).toBe(
      JSON.stringify({ provenance_class: "derived" }),
    );

    // And a filter change is undoable for the same reason a focus change is:
    // it replaced the snapshot.
    fireEvent.click(screen.getByText("back"));
    expect(readSearch()).toBe(`?focus=${encodeURIComponent(KU1)}`);
    expect(readMounts()).toBe(1);
  });

  it("clears the focus without clearing the filters", () => {
    mountMap(`/map?focus=${encodeURIComponent(KU1)}&provenance_class=source`);
    fireEvent.click(screen.getAllByText("clear")[0] as HTMLElement);
    expect(readSearch()).toBe("?provenance_class=source");
    expect(readFocus()).toBe("");
  });
});
