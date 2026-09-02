/**
 * The `T-202` gate's renderer lifecycle: create, layout, update, resize,
 * select, tear down -- and do it repeatedly without leaking.
 *
 * The renderer is reached through `GateRenderer`/`RendererFactory` rather than
 * by constructing `Sigma` inline. Two reasons, both practical:
 *
 * 1. WebGL does not exist in jsdom, so the *sequence* -- that a second create
 *    kills the first, that teardown kills exactly once, that a killed session
 *    refuses to keep operating -- can only be asserted against an injected
 *    fake. The real renderer is then exercised in a real browser, which is the
 *    only place the question this gate asks can actually be answered.
 * 2. If the gate finds a blocking v4 defect, the fallback is one pinned stable
 *    v3 and no compatibility layer for both (D-117). This seam is the small
 *    surface where that substitution happens -- it is a test boundary, not an
 *    abstraction over two renderer APIs.
 *
 * The layout pass is measured rather than assumed. The canvas plan permits a
 * ForceAtlas2 worker; the task says to use it only if measurement shows the
 * synchronous pass blocks interaction, so this module reports the milliseconds
 * it spent and leaves the decision to the recorded number.
 */

import forceAtlas2 from "graphology-layout-forceatlas2";

import type { GraphPayload } from "../../api/contract";
import { GATE_NODE_SIZE, type GateGraph, type GateGraphReport, buildGateGraph } from "./gateGraph";

/**
 * The part of the renderer this gate uses. Sigma satisfies it structurally;
 * nothing here reaches for anything wider.
 */
export interface GateRenderer {
  resize(force?: boolean): unknown;
  refresh(): unknown;
  kill(): unknown;
  on(event: "clickNode", handler: (payload: { node: string }) => void): unknown;
}

export type RendererFactory = (graph: GateGraph, container: HTMLElement) => GateRenderer;

/** How many ForceAtlas2 iterations the gate runs, and reports the cost of. */
export const GATE_LAYOUT_ITERATIONS = 200;

/** Presentation-only sizes the update and selection passes toggle between. */
const UPDATED_SIZE = GATE_NODE_SIZE + 4;
const SELECTED_SIZE = GATE_NODE_SIZE * 2;

export interface LayoutMeasurement {
  nodes: number;
  edges: number;
  iterations: number;
  milliseconds: number;
}

export interface GateSessionOptions {
  container: HTMLElement;
  createRenderer: RendererFactory;
  /** Where the walk's observations are written. The page renders them. */
  log: (message: string) => void;
  /** Called with the `global_id` of a clicked node. */
  onSelect?: (nodeId: string) => void;
  /** Injected for tests; `performance.now` in the browser. */
  now?: () => number;
}

export class GateSession {
  private readonly options: GateSessionOptions;
  private readonly now: () => number;
  private renderer: GateRenderer | null = null;
  private graph: GateGraph | null = null;
  private selected: string | null = null;
  private updated = false;

  /** Every create and every kill, counted, so a leak shows up as a mismatch. */
  public creates = 0;
  public kills = 0;

  constructor(options: GateSessionOptions) {
    this.options = options;
    this.now = options.now ?? (() => performance.now());
  }

  get live(): boolean {
    return this.renderer !== null;
  }

  /**
   * Build the graph, seed it, lay it out, and hand it to the renderer.
   *
   * A create over a live session tears the old one down first. Leaving both
   * alive is how a WebGL context leaks, and the browser answers a leak by
   * losing the *oldest* context -- so the symptom appears far from the cause.
   */
  create(payload: GraphPayload): { report: GateGraphReport; layout: LayoutMeasurement } {
    if (this.renderer !== null) this.teardown();

    const { graph, report } = buildGateGraph(payload);
    this.graph = graph;
    this.options.log(
      `graph: ${report.nodesDrawn}/${report.nodesReturned} nodes, ` +
        `${report.edgesDrawn}/${report.edgesReturned} edges, ` +
        `${report.edgesWithMissingEndpoint} edge(s) with an endpoint off this page, ` +
        `${report.selfLoops} self-loop(s), truncated=${report.truncated}`,
    );

    const layout = this.runLayout(graph);
    this.options.log(
      `layout: ${layout.iterations} ForceAtlas2 iterations over ` +
        `${layout.nodes} nodes / ${layout.edges} edges in ` +
        `${layout.milliseconds.toFixed(1)} ms (synchronous)`,
    );

    const renderer = this.options.createRenderer(graph, this.options.container);
    this.renderer = renderer;
    this.creates += 1;
    renderer.on("clickNode", ({ node }) => {
      this.select(node);
      this.options.onSelect?.(node);
    });
    this.options.log(`create: renderer #${this.creates} attached`);
    return { report, layout };
  }

  /**
   * The synchronous layout pass, measured.
   *
   * `inferSettings` is the library's own advice for a graph of this order; the
   * gate does not hand-tune it, because a tuned number measured once would
   * describe the tuning rather than the renderer.
   */
  private runLayout(graph: GateGraph): LayoutMeasurement {
    const started = this.now();
    forceAtlas2.assign(graph, {
      iterations: GATE_LAYOUT_ITERATIONS,
      settings: forceAtlas2.inferSettings(graph),
    });
    const milliseconds = this.now() - started;
    const measurement: LayoutMeasurement = {
      nodes: graph.order,
      edges: graph.size,
      iterations: GATE_LAYOUT_ITERATIONS,
      milliseconds,
    };
    return measurement;
  }

  /**
   * Mutate the graph the renderer is holding.
   *
   * Presentation attributes only, and only on nodes the API really returned:
   * adding a node here would put an entity on the canvas that no source
   * carries, which is the one thing a gate is not allowed to teach the Map to
   * do. Toggling `size` across every node is enough to exercise Sigma's live
   * update path, which is what the gate is measuring.
   */
  update(): number {
    const graph = this.requireGraph();
    this.updated = !this.updated;
    const started = this.now();
    graph.forEachNode((node) => {
      graph.setNodeAttribute(node, "size", this.updated ? UPDATED_SIZE : GATE_NODE_SIZE);
    });
    if (this.selected !== null && graph.hasNode(this.selected)) {
      graph.setNodeAttribute(this.selected, "size", SELECTED_SIZE);
    }
    this.renderer?.refresh();
    const milliseconds = this.now() - started;
    this.options.log(
      `update: size toggled on ${graph.order} nodes in ${milliseconds.toFixed(1)} ms`,
    );
    return milliseconds;
  }

  /** Resize the container and let the renderer pick the new dimensions up. */
  resize(width: number, height: number): void {
    const renderer = this.requireRenderer();
    this.options.container.style.width = `${width}px`;
    this.options.container.style.height = `${height}px`;
    renderer.resize(true);
    this.options.log(`resize: container set to ${width}x${height}`);
  }

  /**
   * Select one node by id.
   *
   * The gate selects through the same path a pointer click takes, so a
   * keyboard-driven selection and a click cannot diverge -- which is the
   * property `T-208` has to hold and would be expensive to retrofit.
   */
  select(nodeId: string): boolean {
    const graph = this.requireGraph();
    if (!graph.hasNode(nodeId)) {
      this.options.log(`select: no node ${nodeId} on this page -- refused`);
      return false;
    }
    if (this.selected !== null && graph.hasNode(this.selected)) {
      graph.setNodeAttribute(this.selected, "size", this.updated ? UPDATED_SIZE : GATE_NODE_SIZE);
    }
    this.selected = nodeId;
    graph.setNodeAttribute(nodeId, "size", SELECTED_SIZE);
    this.renderer?.refresh();
    this.options.log(`select: ${nodeId} (${graph.getNodeAttribute(nodeId, "label")})`);
    return true;
  }

  get selection(): string | null {
    return this.selected;
  }

  /**
   * Kill the renderer and release the graph.
   *
   * Idempotent, and the counters are the point: `creates` and `kills` must
   * finish equal after any sequence of operations. A double kill would be as
   * much of a defect as a missed one -- Sigma's second `kill` on v3 was a
   * throw, and this gate is here to find out what v4 does.
   */
  teardown(): void {
    const renderer = this.renderer;
    this.renderer = null;
    this.graph = null;
    this.selected = null;
    if (renderer === null) {
      this.options.log("teardown: nothing live");
      return;
    }
    renderer.kill();
    this.kills += 1;
    this.options.container.replaceChildren();
    this.options.log(`teardown: renderer killed (${this.kills} of ${this.creates} creates)`);
  }

  private requireRenderer(): GateRenderer {
    if (this.renderer === null) throw new Error("The gate session has no live renderer.");
    return this.renderer;
  }

  private requireGraph(): GateGraph {
    if (this.graph === null) throw new Error("The gate session has no graph.");
    return this.graph;
  }
}
