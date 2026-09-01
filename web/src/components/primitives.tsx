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
}: {
  children: ReactNode;
  className?: string;
  as?: "span" | "p" | "div" | "blockquote";
}) {
  const props: { className?: string } = {};
  if (className !== undefined) props.className = className;
  return (
    <Tag dir="auto" style={{ unicodeBidi: "isolate" }} {...props}>
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
