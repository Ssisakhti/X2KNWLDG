/**
 * The canonical report, rendered as React nodes.
 *
 * There is no `dangerouslySetInnerHTML` here and there must never be one:
 * every leaf goes through React as text, so raw HTML inside a report renders
 * as the characters the author wrote. That satisfies canvas plan §14's
 * sanitisation requirement by construction rather than by a filter that has to
 * be kept ahead of attackers.
 *
 * Links are the one outbound affordance, and canvas plan §14 requires opening
 * an external URL to be an explicit, visible action: only `http`, `https` and
 * `mailto` become anchors, they open in a new context with `noopener`, and any
 * other scheme is left as plain text with its target visible.
 */

import type { ReactNode } from "react";

import { isSafeHref, parseMarkdown, type Block, type Inline } from "../lib/markdown";

function renderInline(nodes: readonly Inline[], keyPrefix: string): ReactNode[] {
  return nodes.map((node, index) => {
    const key = `${keyPrefix}.${index}`;
    switch (node.type) {
      case "text":
        return <span key={key}>{node.text}</span>;
      case "code":
        return <code key={key}>{node.text}</code>;
      case "strong":
        return <strong key={key}>{renderInline(node.children, key)}</strong>;
      case "em":
        return <em key={key}>{renderInline(node.children, key)}</em>;
      case "break":
        return <br key={key} />;
      case "link":
        return isSafeHref(node.href) ? (
          <a key={key} href={node.href} target="_blank" rel="noopener noreferrer">
            {renderInline(node.children, key)}
          </a>
        ) : (
          <span key={key}>
            {renderInline(node.children, key)} ({node.href})
          </span>
        );
    }
  });
}

function renderBlock(block: Block, key: string): ReactNode {
  switch (block.type) {
    case "heading": {
      const level = Math.min(6, Math.max(1, block.level));
      const Tag = `h${level}` as "h1" | "h2" | "h3" | "h4" | "h5" | "h6";
      return (
        <Tag key={key} dir="auto">
          {renderInline(block.children, key)}
        </Tag>
      );
    }
    case "paragraph":
      return (
        <p key={key} dir="auto">
          {renderInline(block.children, key)}
        </p>
      );
    case "code":
      return (
        <pre key={key}>
          <code>{block.text}</code>
        </pre>
      );
    case "quote":
      return (
        <blockquote key={key} dir="auto">
          {renderInline(block.children, key)}
        </blockquote>
      );
    case "rule":
      return <hr key={key} />;
    case "list": {
      const Tag = block.ordered ? "ol" : "ul";
      return (
        <Tag key={key} dir="auto">
          {block.items.map((item, index) => (
            <li key={`${key}.${index}`}>{renderInline(item, `${key}.${index}`)}</li>
          ))}
        </Tag>
      );
    }
  }
}

export function Markdown({ source }: { source: string }) {
  const blocks = parseMarkdown(source);
  return (
    <div className="markdown">{blocks.map((block, index) => renderBlock(block, `b${index}`))}</div>
  );
}
