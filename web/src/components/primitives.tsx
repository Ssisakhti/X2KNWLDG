/**
 * The three atoms every view needs, and the reason each exists.
 *
 * `Missing` is the one that matters: a value the canonical data does not state
 * renders as a visible absence rather than as a blank, a zero, or a dash that
 * could be mistaken for content. Every optional field in this UI goes through
 * it.
 */

import type { ReactNode } from "react";

import { useI18n } from "../i18n";
import { isSafeHref } from "../lib/markdown";
import type { MessageKey } from "../i18n";

/** A value the canonical files do not state. Visible, never filled in. */
export function Missing({ reason = "common.notStated" }: { reason?: MessageKey }) {
  const { t } = useI18n();
  return <span className="missing">{t(reason)}</span>;
}

/**
 * Content text, rendered in its own direction.
 *
 * Extracted knowledge is Persian or English regardless of the UI language, so
 * content carries `dir="auto"` and paragraph-level bidi isolation: a Persian
 * excerpt inside an English page is laid out as Persian, and neither one
 * reorders the other (D-012).
 */
export function Bidi({
  children,
  className,
  as: Tag = "span",
  marks,
}: {
  children: ReactNode;
  className?: string;
  as?: "span" | "p" | "div" | "blockquote";
  /**
   * `data-*` attributes to put on the element itself.
   *
   * Passed explicitly rather than spread from the rest of the props, because
   * TypeScript does not check a hyphenated JSX attribute against a component's
   * props at all: `data-thing="x"` on a component that does not forward it
   * compiles cleanly and renders nothing, which is a test asserting on an
   * attribute that was never there. `MapLegend`'s `Row` already takes its
   * marks this way (`T-205`).
   */
  marks?: Record<string, string>;
}) {
  const props: { className?: string } = {};
  if (className !== undefined) props.className = className;
  return (
    <Tag dir="auto" style={{ unicodeBidi: "isolate" }} {...props} {...marks}>
      {children}
    </Tag>
  );
}

/** An identifier or path: monospace, always laid out left to right. */
export function Mono({ children }: { children: ReactNode }) {
  return <span className="mono">{children}</span>;
}

export interface Definition {
  label: string;
  value: ReactNode;
}

/** A label/value grid. A `null` value renders as `Missing`, never as blank. */
export function DefinitionList({ entries }: { entries: readonly Definition[] }) {
  return (
    <dl className="definitions">
      {entries.map((entry) => (
        <div key={entry.label} style={{ display: "contents" }}>
          <dt>{entry.label}</dt>
          <dd>{entry.value === null || entry.value === undefined ? <Missing /> : entry.value}</dd>
        </div>
      ))}
    </dl>
  );
}

/**
 * An external link, rendered as a link only when its href is safe to follow.
 *
 * D-105: five sites rendered an API-supplied URL -- `hit.source_url`,
 * `source.url`, `artifact.url` -- straight into `href`, with `target` and
 * `rel` repeated at each one and no scheme check, while the markdown path a
 * few lines away had used `isSafeHref` all along. React 19 neutralises
 * `javascript:` but passes `data:` and `vbscript:` through verbatim; browsers
 * block top-level `data:` navigation, so this was never more than latent --
 * and "the browser refuses it" is not a check the application performed.
 *
 * A refused href keeps the label as text with the URL beside it, the same
 * shape `Markdown` already uses: the reader still sees what the record said,
 * and nothing is quietly dropped.
 */
export function ExternalLink({
  href,
  children,
  label,
}: {
  href: string | null | undefined;
  children: ReactNode;
  label?: string;
}) {
  if (typeof href !== "string" || href === "") return <>{children}</>;
  if (!isSafeHref(href)) {
    return (
      <span>
        {children} ({href})
      </span>
    );
  }
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" aria-label={label}>
      {children}
    </a>
  );
}
