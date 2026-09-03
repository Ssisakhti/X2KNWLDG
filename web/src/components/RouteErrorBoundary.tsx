/**
 * The one thing between a render error and a blank page (D-179).
 *
 * There was no error boundary anywhere in `web/src` -- no `ErrorBoundary`, no
 * `componentDidCatch`, no `getDerivedStateFromError`, and no `onCaughtError` or
 * `onUncaughtError` on the root. React's behaviour without one is to unmount
 * the whole tree, so any uncaught render error anywhere gave the reader a blank
 * document with no retry and no statement of what happened.
 *
 * On the Map that is worse than a blank page. ADR 0005 names "an error throw"
 * as a path invariant 10 must survive -- one renderer created, one alive, none
 * leaked -- and a root that unmounts *does* run effect cleanups, but nothing
 * observes that they ran. A boundary here keeps the tree mounted, so the
 * unmount of the route beneath it is an ordinary one whose cleanup the session
 * tests already cover, and `data-error-boundary` gives the browser gate
 * something to assert against.
 *
 * A class component because that is the only thing React gives this capability
 * to; it holds no other state and does nothing else.
 *
 * Reset is by key, not by mutation: `retry` bumps a counter that re-keys the
 * children, so a retried view is a fresh subtree rather than the failed one
 * asked to try again with whatever state it died holding. A **navigation**
 * changes the same key, for the same reason: see `resetKey` below.
 */

import { Component } from "react";
import type { ErrorInfo, ReactNode } from "react";

import { useI18n } from "../i18n";

interface Props {
  children: ReactNode;
  /**
   * Changed on retry *and* on navigation, so the children remount rather than
   * resume.
   *
   * A string rather than a counter, because two things change it: `App`'s
   * retry attempt and the location. It used to be the attempt alone and
   * nothing bumped it on navigation, so a reader who hit a thrown view stayed
   * looking at the fallback on every other route until a reload — while
   * D-179's whole argument for putting this boundary inside `Shell` is that
   * they are "one click from somewhere that works".
   */
  resetKey: number | string;
  onRetry: () => void;
}

interface State {
  error: Error | null;
}

class Boundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidUpdate(previous: Props): void {
    if (previous.resetKey !== this.props.resetKey && this.state.error !== null) {
      this.setState({ error: null });
    }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // The console is the only channel here on purpose: this project sends
    // nothing anywhere, and a reader who opens the console should find the
    // stack rather than a summary of it.
    console.error("A view threw and was taken down by its boundary", error, info);
  }

  render(): ReactNode {
    if (this.state.error === null) return this.props.children;
    return <Fallback error={this.state.error} onRetry={this.props.onRetry} />;
  }
}

function Fallback({ error, onRetry }: { error: Error; onRetry: () => void }) {
  const { t } = useI18n();
  return (
    <div className="notice notice--internal" role="alert" data-error-boundary="caught">
      <strong>{t("error.boundary.title")}</strong>
      <p>{t("error.boundary.body")}</p>
      <p className="faint" dir="auto">
        {error.message}
      </p>
      <p>
        <button type="button" className="button" onClick={onRetry}>
          {t("error.boundary.retry")}
        </button>
      </p>
    </div>
  );
}

export { Boundary as RouteErrorBoundary };
