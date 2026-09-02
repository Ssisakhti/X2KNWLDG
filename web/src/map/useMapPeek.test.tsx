/**
 * Peek (`T-206`, D-133, ADR 0005 invariants 13 and 14).
 *
 * Four claims, and every one of them is a thing that goes wrong in a hover UI:
 * a Peek that outlives the pointer, two Peeks on stage at once, a Peek for a
 * node whose record never arrived, and a hover that fills the back stack.
 *
 * The history test runs inside a real router and watches the location itself,
 * because "writes no history" cannot be proved by reading this module -- it is
 * proved by hovering and finding the URL exactly where it was.
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { describe, expect, it } from "vitest";

import type { EntityRef } from "../api/contract";
import { concept, unit } from "../test/graphRecords";
import { recordLookup } from "./useMapSearch";
import { createMapGraph, nodeAttributes } from "./graphProjection";
import { useMapPeek } from "./useMapPeek";

const KU1 = unit("KU-000001");
const KU2 = unit("KU-000002");
const C1 = concept("C-000001");
const ABSENT = "youtube:pqlWNihgdjI:KU-999999";

function graphOf(records: readonly EntityRef[]) {
  const graph = createMapGraph();
  for (const record of records) graph.addNode(record.global_id, nodeAttributes(record));
  return graph;
}

/** The rail and the canvas, reduced to two rows that share one Peek binding. */
function PeekProbe({ records }: { records: readonly EntityRef[] }) {
  const peek = useMapPeek(recordLookup(graphOf(records)));
  const location = useLocation();
  return (
    <div>
      <output data-peek>{peek.peek?.globalId ?? ""}</output>
      <output data-origin>{peek.peek?.origin ?? ""}</output>
      <output data-statement>{peek.peek?.record.label ?? ""}</output>
      <output data-url>{`${location.pathname}${location.search}`}</output>
      <output data-cards>{peek.peek === null ? 0 : 1}</output>
      <button type="button" {...peek.handlers(KU1.global_id)}>
        row one
      </button>
      <button type="button" {...peek.handlers(KU2.global_id)}>
        row two
      </button>
      <button type="button" {...peek.handlers(C1.global_id)}>
        row concept
      </button>
      <button type="button" {...peek.handlers(ABSENT)}>
        row absent
      </button>
      <button type="button" onClick={() => peek.close()}>
        dismiss
      </button>
    </div>
  );
}

function mountPeek(records: readonly EntityRef[] = [KU1, KU2, C1]) {
  return render(
    <MemoryRouter initialEntries={["/map?focus=youtube:pqlWNihgdjI:KU-000001"]}>
      <PeekProbe records={records} />
    </MemoryRouter>,
  );
}

const peeked = () => document.querySelector("[data-peek]")?.textContent ?? "";
const origin = () => document.querySelector("[data-origin]")?.textContent ?? "";
const url = () => document.querySelector("[data-url]")?.textContent ?? "";

describe("useMapPeek", () => {
  it("opens on pointer hover and on keyboard focus, over the same node", () => {
    mountPeek();
    const row = screen.getByText("row one");

    fireEvent.mouseEnter(row);
    expect(peeked()).toBe(KU1.global_id);
    expect(origin()).toBe("pointer");
    fireEvent.mouseLeave(row);
    expect(peeked()).toBe("");

    // The keyboard path is not a second lookup: same node, same record, and
    // the only difference recorded is how it was reached.
    fireEvent.focus(row);
    expect(peeked()).toBe(KU1.global_id);
    expect(origin()).toBe("keyboard");
    expect(document.querySelector("[data-statement]")?.textContent).toBe(KU1.label);
  });

  it("shows the record the Map holds, verbatim", () => {
    mountPeek();
    fireEvent.focus(screen.getByText("row concept"));
    expect(document.querySelector("[data-statement]")?.textContent).toBe(C1.label);
  });

  it("keeps at most one Peek, whatever order the events arrive in", () => {
    mountPeek();
    fireEvent.mouseEnter(screen.getByText("row one"));
    fireEvent.mouseEnter(screen.getByText("row two"));
    expect(peeked()).toBe(KU2.global_id);
    expect(document.querySelector("[data-cards]")?.textContent).toBe("1");
  });

  it("does not let a stale leave close the Peek that replaced it", () => {
    // Pointers emit `leave` for the node they left *after* `enter` for the one
    // they arrived at. An unconditional close would blank the card the reader
    // is looking at, at the moment they arrive on it.
    mountPeek();
    fireEvent.mouseEnter(screen.getByText("row one"));
    fireEvent.mouseEnter(screen.getByText("row two"));
    fireEvent.mouseLeave(screen.getByText("row one"));
    expect(peeked()).toBe(KU2.global_id);

    fireEvent.mouseLeave(screen.getByText("row two"));
    expect(peeked()).toBe("");
  });

  it("opens no Peek for a node the Map has not loaded", () => {
    // There is nothing to show. An empty card, or one carrying only an id, is
    // the blind choice the card exists to remove -- and filling it in would be
    // client-authored knowledge (D-131).
    mountPeek();
    fireEvent.mouseEnter(screen.getByText("row absent"));
    expect(peeked()).toBe("");
  });

  it("closes rather than attributing one node's statement to another", () => {
    mountPeek();
    fireEvent.mouseEnter(screen.getByText("row one"));
    fireEvent.mouseEnter(screen.getByText("row absent"));
    expect(peeked()).toBe("");
  });

  it("writes no history and no selection", () => {
    // Invariant 14's first half, watched from the location rather than
    // inferred from the code: eight hovers, one URL, unchanged -- including
    // the focus the URL already carried.
    mountPeek();
    const before = url();
    for (const label of ["row one", "row two", "row concept", "row one"]) {
      fireEvent.mouseEnter(screen.getByText(label));
      fireEvent.focus(screen.getByText(label));
    }
    expect(peeked()).toBe(KU1.global_id);
    expect(url()).toBe(before);
    expect(url()).toContain("focus=youtube:pqlWNihgdjI:KU-000001");
  });

  it("closes on demand, for the keyboard path that has no leave", () => {
    mountPeek();
    fireEvent.focus(screen.getByText("row one"));
    fireEvent.click(screen.getByText("dismiss"));
    expect(peeked()).toBe("");
  });
});
