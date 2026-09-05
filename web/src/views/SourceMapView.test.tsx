/**
 * The Source Map's journey, in jsdom (`T-256`).
 *
 * jsdom has no WebGL, which is not a limitation of this suite but its subject:
 * the whole reading path — the list of sources, a source's brief, its
 * relationships, and what one of them rests on — is DOM, so a browser that
 * cannot draw a graph loses the picture and nothing else. Every assertion below
 * runs with **no renderer at all**, which is the strongest form of the phase's
 * accessibility clause: not "there is also a list", but "the list is the
 * journey, and the canvas is an enhancement over it".
 *
 * The one thing the fake renderer is used for is the seam a canvas click goes
 * through, because a mark and a row must call the *same* selection.
 */

import { describe, expect, it, vi } from "vitest";
import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";

import { jsonFetch, renderApp } from "../test/render";
import {
  FAIL,
  PARTIAL,
  PASS,
  POST,
  brief,
  detail,
  graphPayload,
  graphResponse,
  neighbourhoodPayload,
  neighbourhoodResponse,
  sourceNode,
  staleBrief,
  summary,
} from "../test/sourceRecords";
import { sizeTheStage } from "../test/mapServer";
import { SourceMapView } from "./SourceMapView";
import { sourceStyle } from "../map/sourceStyle";
import { fakeRenderers } from "../test/mapRenderer";
import type { MapRendererFactory } from "../map/mapSession";
import type { SourceRelationSummary } from "../api/contract";

/** The two-part id in a neighbourhood path, decoded the way the client wrote it. */
function sourceIdIn(url: string): string {
  return decodeURIComponent(url.split("?")[0]?.split("/").pop() ?? "");
}

/**
 * A library with four sources, one gated relationship and three brief states.
 *
 * The same corpus the API's own tests use, so a frontend assertion and a
 * backend one are about the same records.
 */
function corpus(
  options: { relations?: SourceRelationSummary[]; omitted?: number; truncated?: boolean } = {},
): typeof fetch {
  const nodes = [sourceNode(POST), sourceNode(FAIL), sourceNode(PARTIAL), sourceNode(PASS)];
  const relations = options.relations ?? [summary(POST, PASS)];
  return jsonFetch((url) => {
    if (url.includes("/api/source-graph/neighborhood/")) {
      const id = sourceIdIn(url);
      if (id === PASS) {
        return {
          body: neighbourhoodResponse(
            neighbourhoodPayload(sourceNode(PASS), {
              knowledge: brief("PASS"),
              incoming: [detail(POST, PASS)],
              neighbors: [sourceNode(POST)],
            }),
          ),
        };
      }
      if (id === PARTIAL) {
        return {
          body: neighbourhoodResponse(
            neighbourhoodPayload(sourceNode(PARTIAL), { knowledge: brief("PARTIAL", PARTIAL) }),
          ),
        };
      }
      if (id === FAIL) {
        return { body: neighbourhoodResponse(neighbourhoodPayload(sourceNode(FAIL))) };
      }
      return {
        status: 404,
        body: { error: { code: "not_found", message: "No source in the index has that id." } },
      };
    }
    const payload = graphPayload(nodes, relations, {
      relations_omitted: options.omitted ?? 0,
    });
    return { body: graphResponse({ ...payload, truncated: options.truncated ?? false }) };
  });
}

function mount(route = "/map?of=sources", renderer?: MapRendererFactory<SourceRelationSummary>) {
  sizeTheStage();
  return renderApp(<SourceMapView createRenderer={renderer} />, { route });
}

describe("the field, with no renderer at all", () => {
  it("lists every returned source, with its medium", async () => {
    vi.stubGlobal("fetch", corpus());
    mount();
    const outline = await waitFor(() => {
      const found = document.querySelector("[data-source-outline]");
      expect(found?.getAttribute("data-source-outline")).toBe("4");
      return found!;
    });
    expect(outline?.getAttribute("data-source-outline")).toBe("4");
    expect(document.querySelectorAll("[data-source-row]")).toHaveLength(4);
    // The medium is a word, not only a hue.
    expect(document.body.textContent).toContain("YouTube");
    expect(document.body.textContent).toContain("X / Twitter");
  });

  it("states returned, omitted and total separately", async () => {
    vi.stubGlobal("fetch", corpus({ omitted: 2 }));
    mount();
    const counts = await waitFor(() => {
      const found = document.querySelector("[data-source-returned]");
      expect(found).toBeTruthy();
      return found!;
    });
    expect(counts.getAttribute("data-source-returned")).toBe("4");
    expect(counts.getAttribute("data-source-relations-returned")).toBe("1");
    expect(counts.getAttribute("data-source-omitted")).toBe("2");
    expect(counts.getAttribute("data-source-total")).toBe("4");
  });

  it("says on the surface what it will not tell you", async () => {
    vi.stubGlobal("fetch", corpus());
    mount();
    await waitFor(() => expect(document.querySelector(".refusals")).toBeTruthy());
    const refusals = document.querySelector(".refusals")?.textContent ?? "";
    expect(refusals).toContain("no confidence, no score and no rank");
    expect(refusals).toContain("still current");
  });

  it("counts a relationship whose other end is not on this page rather than drawing it", async () => {
    // One node returned, one relation naming two: the second is on a later page.
    vi.stubGlobal(
      "fetch",
      jsonFetch((url) =>
        url.includes("/neighborhood/")
          ? { status: 404, body: { error: { code: "not_found", message: "no" } } }
          : {
              body: graphResponse(graphPayload([sourceNode(POST)], [summary(POST, PASS)])),
            },
      ),
    );
    mount();
    await waitFor(() => expect(document.querySelector("[data-source-offpage]")).toBeTruthy());
    expect(
      document.querySelector("[data-source-offpage]")?.getAttribute("data-source-offpage"),
    ).toBe("1");
    expect(document.querySelector("[data-source-offpage-note]")).toBeTruthy();
  });

  it("says the index is empty rather than that the drawing failed", async () => {
    vi.stubGlobal(
      "fetch",
      jsonFetch(() => ({ body: graphResponse(graphPayload([], [])) })),
    );
    mount();
    await waitFor(() =>
      expect(document.body.textContent).toContain("This is not a drawing that failed"),
    );
  });
});

describe("selecting a source", () => {
  it("reads its brief, with every statement naming the units under it", async () => {
    vi.stubGlobal("fetch", corpus());
    mount();
    await waitFor(() => expect(screen.getAllByRole("button")).not.toHaveLength(0));

    const row = await waitFor(() => {
      const found = document.querySelector(`[data-source-row="${PASS}"] button`);
      expect(found).toBeTruthy();
      return found as HTMLElement;
    });
    fireEvent.click(row);

    const card = await waitFor(() => {
      const found = document.querySelector(`[data-source-card="${PASS}"]`);
      expect(found).toBeTruthy();
      return found as HTMLElement;
    });
    // The brief is Persian in both locales, because the record is.
    expect(card.textContent).toContain("این منبعِ آزمایشی");
    // Every narrative element names its knowledge units, drawn as chips.
    expect(within(card).getAllByText("KU-000001").length).toBeGreaterThan(0);
    expect(card.getAttribute("data-source-brief")).toBe("available");
    // A status, because there is a brief to carry one.
    expect(card.textContent).toContain("PASS");
  });

  it("shows a PARTIAL brief as a state rather than hiding it", async () => {
    vi.stubGlobal("fetch", corpus());
    mount();
    const row = await waitFor(() => {
      const found = document.querySelector(`[data-source-row="${PARTIAL}"] button`);
      expect(found).toBeTruthy();
      return found as HTMLElement;
    });
    fireEvent.click(row);
    await waitFor(() =>
      expect(document.querySelector(`[data-source-card="${PARTIAL}"]`)?.textContent).toContain(
        "PARTIAL",
      ),
    );
  });

  it("says a source with no brief has none, and states no status for it", async () => {
    vi.stubGlobal("fetch", corpus());
    mount();
    const row = await waitFor(() => {
      const found = document.querySelector(`[data-source-row="${FAIL}"] button`);
      expect(found).toBeTruthy();
      return found as HTMLElement;
    });
    fireEvent.click(row);
    const card = await waitFor(() => {
      const found = document.querySelector(`[data-source-card="${FAIL}"]`);
      expect(found).toBeTruthy();
      return found as HTMLElement;
    });
    expect(card.getAttribute("data-source-brief")).toBe("unavailable");
    expect(card.textContent).toContain("normal and possibly permanent");
    expect(card.textContent).toContain("no source_knowledge.json");
    // No brief means no status to state: the run has one, this response does not.
    expect(card.textContent).not.toContain("PASS");
    // And its relationships are an honest absence rather than a failure.
    expect(document.querySelector('[data-source-relations="0"]')).toBeTruthy();
  });

  it("carries a stale brief with its state said out loud", async () => {
    vi.stubGlobal(
      "fetch",
      jsonFetch((url) =>
        url.includes("/neighborhood/")
          ? {
              body: neighbourhoodResponse(
                neighbourhoodPayload(sourceNode(PASS), { knowledge: staleBrief() }),
              ),
            }
          : { body: graphResponse(graphPayload([sourceNode(PASS)], [])) },
      ),
    );
    mount();
    const row = await waitFor(() => {
      const found = document.querySelector(`[data-source-row="${PASS}"] button`);
      expect(found).toBeTruthy();
      return found as HTMLElement;
    });
    fireEvent.click(row);
    const card = await waitFor(() => {
      const found = document.querySelector("[data-source-stale]");
      expect(found).toBeTruthy();
      return found as HTMLElement;
    });
    expect(card.textContent).toContain("inputs that have since changed");
    // Carried, not withheld: the brief itself is still on screen.
    expect(document.body.textContent).toContain("این منبعِ آزمایشی");
  });

  it("renders a 404 as an absence rather than as a broken request", async () => {
    vi.stubGlobal("fetch", corpus());
    mount(`/map?of=sources&focus=youtube:never-ingested:source`);
    await waitFor(() => expect(document.querySelector("[data-source-unknown]")).toBeTruthy());
    expect(document.body.textContent).toContain("Absence is an answer");
  });
});

describe("a relationship and what it rests on", () => {
  it("lists every returned relationship and opens one's basis", async () => {
    vi.stubGlobal("fetch", corpus());
    mount();
    const row = await waitFor(() => {
      const found = document.querySelector(`[data-source-row="${PASS}"] button`);
      expect(found).toBeTruthy();
      return found as HTMLElement;
    });
    fireEvent.click(row);

    const list = await waitFor(() => {
      const found = document.querySelector("[data-source-relations]");
      expect(found).toBeTruthy();
      return found as HTMLElement;
    });
    expect(list.getAttribute("data-source-relations")).toBe("1");
    // The relationship names its type, its scope and its basis as a count.
    expect(list.textContent).toContain("critiques");
    expect(list.textContent).toContain("partial");
    expect(list.textContent).toContain("Knowledge-unit pairs");

    // Its grounds are pairs, and both counts are stated.
    const basis = await waitFor(() => {
      const found = document.querySelector("[data-source-basis]");
      expect(found).toBeTruthy();
      return found as HTMLElement;
    });
    expect(basis.textContent).toContain("KU-000001");
    expect(basis.textContent).toContain("1 of 1");
    // The rationale is the pass's own Persian sentence, rendered as written.
    expect(basis.textContent).toContain("این پستِ آزمایشی");
  });

  it("says when a basis was cut rather than presenting it as the whole", async () => {
    vi.stubGlobal(
      "fetch",
      jsonFetch((url) =>
        url.includes("/neighborhood/")
          ? {
              body: neighbourhoodResponse(
                neighbourhoodPayload(sourceNode(PASS), {
                  knowledge: brief(),
                  incoming: [detail(POST, PASS, { basis_total: 40, basis_returned: 1 })],
                  neighbors: [sourceNode(POST)],
                }),
              ),
            }
          : { body: graphResponse(graphPayload([sourceNode(PASS), sourceNode(POST)], [])) },
      ),
    );
    mount();
    const row = await waitFor(() => {
      const found = document.querySelector(`[data-source-row="${PASS}"] button`);
      expect(found).toBeTruthy();
      return found as HTMLElement;
    });
    fireEvent.click(row);
    await waitFor(() =>
      expect(document.querySelector("[data-source-basis-truncated]")).toBeTruthy(),
    );
    expect(document.body.textContent).toContain("1 of 40");
  });

  it("keeps a relationship the stage had no room for in the list, and marks it", async () => {
    const many = Array.from({ length: 6 }, (_value, index) =>
      detail(POST, PASS, { id: `SR-${index}` }),
    );
    vi.stubGlobal(
      "fetch",
      jsonFetch((url) =>
        url.includes("/neighborhood/")
          ? {
              body: neighbourhoodResponse(
                neighbourhoodPayload(sourceNode(PASS), {
                  knowledge: brief(),
                  incoming: many,
                  neighbors: [sourceNode(POST)],
                }),
              ),
            }
          : { body: graphResponse(graphPayload([sourceNode(PASS), sourceNode(POST)], [])) },
      ),
    );
    mount();
    const row = await waitFor(() => {
      const found = document.querySelector(`[data-source-row="${PASS}"] button`);
      expect(found).toBeTruthy();
      return found as HTMLElement;
    });
    fireEvent.click(row);
    await waitFor(() =>
      expect(document.querySelectorAll("[data-source-relation-row]")).toHaveLength(6),
    );
    // Every one of them is still a row, whatever the stage could hold.
    const placed = [...document.querySelectorAll("[data-source-relation-placed]")].map((node) =>
      node.getAttribute("data-source-relation-placed"),
    );
    expect(placed).toHaveLength(6);
    expect(placed.filter((value) => value === "false").length).toBeGreaterThan(0);
  });

  it("states that a bound cut both directions together", async () => {
    vi.stubGlobal(
      "fetch",
      jsonFetch((url) =>
        url.includes("/neighborhood/")
          ? {
              body: neighbourhoodResponse(
                neighbourhoodPayload(sourceNode(PASS), {
                  knowledge: brief(),
                  incoming: [detail(POST, PASS)],
                  neighbors: [sourceNode(POST)],
                  truncated: true,
                }),
              ),
            }
          : { body: graphResponse(graphPayload([sourceNode(PASS), sourceNode(POST)], [])) },
      ),
    );
    mount();
    const row = await waitFor(() => {
      const found = document.querySelector(`[data-source-row="${PASS}"] button`);
      expect(found).toBeTruthy();
      return found as HTMLElement;
    });
    fireEvent.click(row);
    await waitFor(() =>
      expect(document.querySelector("[data-source-neighbourhood-truncated]")).toBeTruthy(),
    );
    expect(document.body.textContent).toContain("binds both directions together");
  });
});

describe("the mode switch", () => {
  it("is one choice with two values, and says which this is", async () => {
    vi.stubGlobal("fetch", corpus());
    mount();
    const group = await waitFor(() => {
      const found = document.querySelector('[role="radiogroup"]');
      expect(found).toBeTruthy();
      return found as HTMLElement;
    });
    expect(group.getAttribute("data-map-mode")).toBe("sources");
    const options = within(group).getAllByRole("radio");
    expect(options).toHaveLength(2);
    expect(options.filter((option) => option.getAttribute("aria-checked") === "true")).toHaveLength(
      1,
    );
    // Only the selected option is in the tab order: one stop, not two.
    expect(options.filter((option) => option.getAttribute("tabindex") === "0")).toHaveLength(1);
  });
});

describe("the canvas", () => {
  it("selects through the same call a row does", async () => {
    vi.stubGlobal("fetch", corpus());
    const harness = fakeRenderers<SourceRelationSummary>();
    mount("/map?of=sources", harness.factory);
    await waitFor(() => expect(harness.latest()).not.toBeNull());

    // The seam a mark's click goes through. It calls the same selection a row
    // calls, which is the whole point of the assertion below.
    act(() => harness.latest()?.fireNode("clickNode", `${PASS}:source`));

    await waitFor(() =>
      expect(document.querySelector(`[data-source-card="${PASS}"]`)).toBeTruthy(),
    );
  });

  it("deselects on a second click of the same mark, and does not stack history", async () => {
    /*
     * The defect: the session's `onSelectNode` closed over `focusSource`, and
     * the effect that builds the session has `[projection, createRenderer]` for
     * deps — `projection` is one fetch and never changes identity, so the
     * closure was frozen at `focus.focus === null` for the life of the route.
     * The second click therefore compared the clicked id against a stale
     * `null`, re-selected instead of deselecting, and pushed a duplicate
     * history entry, leaving Back with nothing to do.
     */
    vi.stubGlobal("fetch", corpus());
    const harness = fakeRenderers<SourceRelationSummary>();
    mount("/map?of=sources", harness.factory);
    await waitFor(() => expect(harness.latest()).not.toBeNull());

    act(() => harness.latest()?.fireNode("clickNode", `${PASS}:source`));
    await waitFor(() =>
      expect(document.querySelector(`[data-source-card="${PASS}"]`)).toBeTruthy(),
    );

    // The same mark again: the reader is putting the selection down.
    act(() => harness.latest()?.fireNode("clickNode", `${PASS}:source`));
    await waitFor(() =>
      expect(document.querySelector(`[data-source-card="${PASS}"]`)).toBeNull(),
    );
  });

  it("never lights a previous selection's neighbours around a new one", async () => {
    /*
     * `useAsync` keeps the previous `data` while the next request is in flight.
     * The drawer is masked by a `loading` branch; the style table was not, so
     * `setView` drew the marks of one source's neighbours around a *different*
     * source — a false relatedness claim on the canvas. The endpoint echoes
     * `center_id` back so a client can refuse a stale answer, which is what the
     * view now does.
     *
     * The window is only open while the second request is unresolved, so this
     * test holds PARTIAL's neighbourhood open deliberately. Resolving it first
     * and asserting afterwards is the shape that passes with the bug present.
     */
    const held: { release: () => void } = { release: () => {} };
    const partialHeld = new Promise<void>((resolve) => {
      held.release = resolve;
    });
    const underlying = corpus();
    vi.stubGlobal("fetch", (async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/api/source-graph/neighborhood/") && sourceIdIn(url) === PARTIAL) {
        await partialHeld;
      }
      return underlying(input, init);
    }) as typeof fetch);

    const harness = fakeRenderers<SourceRelationSummary>();
    mount("/map?of=sources", harness.factory);
    await waitFor(() => expect(harness.latest()).not.toBeNull());

    act(() => harness.latest()?.fireNode("clickNode", `${PASS}:source`));
    // PASS really does have POST as a neighbour, so the table is populated.
    await waitFor(() => expect(sourceStyle.view.neighbourNodes.has(`${POST}:source`)).toBe(true));

    // Select PARTIAL, whose answer is still in flight. Until it lands, nothing
    // may be drawn as PARTIAL's neighbour — least of all POST, which is the
    // previous selection's.
    act(() => harness.latest()?.fireNode("clickNode", `${PARTIAL}:source`));
    await waitFor(() => expect(sourceStyle.view.selectedNode).toBe(`${PARTIAL}:source`));
    expect(sourceStyle.view.neighbourNodes.has(`${POST}:source`)).toBe(false);

    held.release();
    // And PARTIAL carries no relationships at all, so it stays empty after.
    await waitFor(() =>
      expect(document.querySelector(`[data-source-card="${PARTIAL}"]`)).toBeTruthy(),
    );
    expect(sourceStyle.view.neighbourNodes.size).toBe(0);
  });

  it("shows no brief for a focus that names a unit rather than a source", async () => {
    /*
     * `focusedSourceId` is `sourceIdOf(focus.focus)`, which drops the third
     * segment — so `youtube:abc:KU-000001` and `youtube:abc:source` both ask
     * the endpoint for `youtube:abc`. A stale bookmark or a hand-typed link
     * carrying a unit id would therefore have filled the drawer with that
     * unit's *source* brief while `focus.focus` matched no node on the field,
     * leaving the drawer saying a source was selected and the list saying
     * nothing was — two selection identities derived from one, which is what
     * `MapView`'s §8.6 doctrine exists to forbid.
     *
     * The centre-id guard closes it: the answer's own `centre.global_id` is
     * `…:source` and the focus is not, so the answer is refused as not being
     * about this selection.
     */
    vi.stubGlobal("fetch", corpus());
    mount(`/map?of=sources&focus=${PASS}:KU-000001`);
    await waitFor(() => expect(document.querySelector("[data-source-outline]")).toBeTruthy());
    expect(document.querySelector(`[data-source-card="${PASS}"]`)).toBeNull();
  });

  it("leaves the shared style table empty when the route unmounts", async () => {
    // `sourceStyle` is a module singleton: a selection left in it dims every
    // mark on the next mount, around a selection that no longer exists.
    vi.stubGlobal("fetch", corpus());
    const harness = fakeRenderers<SourceRelationSummary>();
    const view = mount("/map?of=sources", harness.factory);
    await waitFor(() => expect(harness.latest()).not.toBeNull());

    act(() => harness.latest()?.fireNode("clickNode", `${PASS}:source`));
    await waitFor(() => expect(sourceStyle.view.selectedNode).toBe(`${PASS}:source`));

    view.unmount();
    expect(sourceStyle.view.selectedNode).toBeNull();
    expect(sourceStyle.view.neighbourNodes.size).toBe(0);
  });

  it("is not announced as an image while there is no picture", async () => {
    vi.stubGlobal("fetch", corpus());
    mount();
    await waitFor(() => expect(document.querySelector("[data-map-stage]")).toBeTruthy());
    const stage = document.querySelector("[data-map-stage]");
    // No renderer was injected and jsdom has none, so there is nothing to label.
    expect(stage?.getAttribute("role")).toBeNull();
    expect(stage?.getAttribute("aria-hidden")).toBe("true");
  });
});

/**
 * What `T-256` deferred and `T-257` closed.
 *
 * `UnitReaderLink` existed, was exported, and was rendered by nothing — its own
 * comment said so and handed the journey to this task. These are the assertions
 * that make drawing it a claim rather than a change: both ends of a pair resolve,
 * and they resolve to *different* sources, which is the one thing that would
 * still pass if both were resolved against a single endpoint.
 */
describe("from a basis to the units it names", () => {
  it("opens each end of a pair in the Reader of the source that owns it", async () => {
    vi.stubGlobal("fetch", corpus());
    mount();
    const row = await waitFor(() => {
      const found = document.querySelector(`[data-source-row="${PASS}"] button`);
      expect(found).toBeTruthy();
      return found as HTMLElement;
    });
    fireEvent.click(row);

    const basis = await waitFor(() => {
      const found = document.querySelector("[data-source-basis]");
      expect(found).toBeTruthy();
      return found as HTMLElement;
    });

    // One row per pair, and the row names the pair it is.
    const pairs = [...basis.querySelectorAll("[data-source-basis-pair]")];
    expect(pairs).toHaveLength(1);
    expect(pairs[0]?.getAttribute("data-source-basis-pair")).toBe("KU-000001->KU-000001");

    // Two links, one per end. The relation runs POST -> PASS, so `from_ku_id`
    // belongs to the X post and `to_ku_id` to the video — and the two hrefs
    // must therefore differ even though the two unit ids are identical, which
    // is exactly the case a single-endpoint resolution would get wrong.
    const links = [...basis.querySelectorAll("[data-source-unit-link]")];
    expect(links.map((link) => link.getAttribute("data-source-unit-link"))).toEqual([
      `${POST}:KU-000001`,
      `${PASS}:KU-000001`,
    ]);
    const hrefs = links.map((link) => link.getAttribute("href"));
    expect(new Set(hrefs).size).toBe(2);
    for (const href of hrefs) expect(href).toContain("tab=units");

    // The accessible name distinguishes them from each other by the unit id,
    // rather than reading the same words twice.
    for (const link of links) expect(link.textContent).toContain("KU-000001");
  });

  it("names the supporting units of every narrative element it draws", async () => {
    vi.stubGlobal("fetch", corpus());
    // The widest tier, so the whole brief is drawn rather than counted: the
    // clause is about every element the card shows, and a card that hides two
    // key points is a weaker witness for it than one that shows them.
    sizeTheStage({ width: 2100, height: 900 });
    renderApp(<SourceMapView />, { route: "/map?of=sources" });
    const row = await waitFor(() => {
      const found = document.querySelector(`[data-source-row="${PASS}"] button`);
      expect(found).toBeTruthy();
      return found as HTMLElement;
    });
    fireEvent.click(row);

    const card = await waitFor(() => {
      const found = document.querySelector(`[data-source-card="${PASS}"]`);
      expect(found).toBeTruthy();
      return found as HTMLElement;
    });

    // The thesis and both key points, each with its own `based_on` group, and
    // nothing counted away: three groups is the acceptance clause said as a
    // number rather than as "some chips were rendered".
    const groups = [...card.querySelectorAll("[data-source-basedon]")];
    expect(groups).toHaveLength(3);
    expect(card.querySelector("[data-source-points-hidden]")).toBeNull();
    for (const group of groups) {
      expect(Number(group.getAttribute("data-source-basedon"))).toBeGreaterThan(0);
      expect(group.querySelectorAll("[data-source-ku]").length).toBe(
        Number(group.getAttribute("data-source-basedon")),
      );
    }
    // The chip carries the id itself, so a gate compares sets rather than counts.
    expect(
      [...card.querySelectorAll("[data-source-ku]")].map((chip) =>
        chip.getAttribute("data-source-ku"),
      ),
    ).toEqual(["KU-000001", "KU-000001", "KU-000001"]);
  });

  it("counts the elements a narrower card did not draw, rather than dropping them", async () => {
    vi.stubGlobal("fetch", corpus());
    // The same brief at `compact`: one key point drawn, one counted. What must
    // not happen is a statement drawn *without* its support, so the invariant
    // asserted here is per drawn element rather than per record element.
    mount();
    const row = await waitFor(() => {
      const found = document.querySelector(`[data-source-row="${PASS}"] button`);
      expect(found).toBeTruthy();
      return found as HTMLElement;
    });
    fireEvent.click(row);

    const card = await waitFor(() => {
      const found = document.querySelector(`[data-source-card="${PASS}"]`);
      expect(found).toBeTruthy();
      return found as HTMLElement;
    });
    const groups = [...card.querySelectorAll("[data-source-basedon]")];
    // The thesis plus each key point the card drew, and no more.
    expect(groups).toHaveLength(1 + card.querySelectorAll(".sourcecard__points li").length);
    for (const group of groups) {
      expect(group.querySelectorAll("[data-source-ku]").length).toBeGreaterThan(0);
    }
    // And the rest is a number on the card, not an omission in silence.
    expect(card.querySelector("[data-source-points-hidden]")?.getAttribute("data-source-points-hidden")).toBe("1");
  });
});
