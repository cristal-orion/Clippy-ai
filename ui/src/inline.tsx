import { Fragment, type ReactNode } from "react";

/** An absolute http(s) URL, or null. Anything else (javascript:, relative) is dropped. */
export function webUrl(value: unknown): string | null {
  if (typeof value !== "string") return null;
  try {
    const url = new URL(value.trim());
    return url.protocol === "http:" || url.protocol === "https:" ? url.href : null;
  } catch {
    return null;
  }
}

// **bold**, `code`, [text](url), *italic*, _italic_ (only between word boundaries)
const TOKEN = /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)\s]+\)|\*[^*\s][^*]*\*|(?<!\w)_[^_\s][^_]*_(?!\w))/g;
const LINK = /^\[([^\]]+)\]\(([^)\s]+)\)$/;

function inlineLine(line: string): ReactNode[] {
  const out: ReactNode[] = [];
  let last = 0;
  let key = 0;
  TOKEN.lastIndex = 0;
  for (let m = TOKEN.exec(line); m; m = TOKEN.exec(line)) {
    if (m.index > last) out.push(line.slice(last, m.index));
    const token = m[0];
    if (token.startsWith("**")) out.push(<strong key={key++}>{token.slice(2, -2)}</strong>);
    else if (token.startsWith("`")) out.push(<code key={key++}>{token.slice(1, -1)}</code>);
    else if (token.startsWith("[")) {
      const [, text, url] = LINK.exec(token) ?? [];
      const href = webUrl(url);
      out.push(
        href ? (
          <a key={key++} href={href} target="_blank" rel="noopener noreferrer">
            {text}
          </a>
        ) : (
          text
        ),
      );
    } else out.push(<em key={key++}>{token.slice(1, -1)}</em>);
    last = m.index + token.length;
  }
  if (last < line.length) out.push(line.slice(last));
  return out;
}

/** Model text with inline Markdown and line breaks, rendered without innerHTML. */
export function inline(value: unknown): ReactNode {
  const text = value == null ? "" : String(value);
  return text.split("\n").map((line, i) => (
    <Fragment key={i}>
      {i > 0 ? <br /> : null}
      {inlineLine(line)}
    </Fragment>
  ));
}
