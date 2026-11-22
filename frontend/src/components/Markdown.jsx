import { Fragment } from "react";

// Minimal, safe markdown renderer for chat replies: headings, bold, italic,
// inline code, bullet/ordered lists, and pipe tables. No HTML is injected —
// everything is built as React elements.

const INLINE_RE = /(\*\*[^*\n]+\*\*|\*[^*\n]+\*|`[^`\n]+`|\[[^\]\n]+\]\([^)\s]+\))/g;

function renderInline(text, keyPrefix) {
  const nodes = [];
  let last = 0;
  let m;
  INLINE_RE.lastIndex = 0;
  let i = 0;
  while ((m = INLINE_RE.exec(text)) !== null) {
    if (m.index > last) nodes.push(text.slice(last, m.index));
    const tok = m[0];
    if (tok.startsWith("**")) {
      nodes.push(<strong key={`${keyPrefix}-b${i}`}>{tok.slice(2, -2)}</strong>);
    } else if (tok.startsWith("*")) {
      nodes.push(<em key={`${keyPrefix}-i${i}`}>{tok.slice(1, -1)}</em>);
    } else if (tok.startsWith("`")) {
      nodes.push(<code key={`${keyPrefix}-c${i}`}>{tok.slice(1, -1)}</code>);
    } else {
      const lm = tok.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
      if (lm) {
        nodes.push(
          <a key={`${keyPrefix}-a${i}`} href={lm[2]} target="_blank" rel="noreferrer">
            {lm[1]}
          </a>
        );
      } else {
        nodes.push(tok);
      }
    }
    last = m.index + tok.length;
    i += 1;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes.map((n, idx) => <Fragment key={idx}>{n}</Fragment>);
}

const isTableSep = (line) => /^\s*\|[\s:|-]+\|\s*$/.test(line) && line.includes("-");
const isTableRow = (line) => /^\s*\|.*\|\s*$/.test(line);

function splitRow(line) {
  return line
    .trim()
    .replace(/^\||\|$/g, "")
    .split("|")
    .map((c) => c.replace(/<br\s*\/?>/gi, " ").trim());
}

function parseBlocks(text) {
  const lines = String(text || "").split("\n");
  const blocks = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {
      i += 1;
      continue;
    }
    // Pipe table: header row + separator row + body rows
    if (isTableRow(line) && i + 1 < lines.length && isTableSep(lines[i + 1])) {
      const header = splitRow(line);
      i += 2;
      const rows = [];
      while (i < lines.length && isTableRow(lines[i])) {
        rows.push(splitRow(lines[i]));
        i += 1;
      }
      blocks.push({ type: "table", header, rows });
      continue;
    }
    // Heading
    const h = line.match(/^\s{0,3}(#{1,6})\s+(.*)$/);
    if (h) {
      blocks.push({ type: "heading", level: h[1].length, text: h[2] });
      i += 1;
      continue;
    }
    // Unordered list
    if (/^\s*[-*•]\s+/.test(line)) {
      const items = [];
      while (i < lines.length && /^\s*[-*•]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*[-*•]\s+/, ""));
        i += 1;
      }
      blocks.push({ type: "ul", items });
      continue;
    }
    // Ordered list
    if (/^\s*\d+[.)]\s+/.test(line)) {
      const items = [];
      while (i < lines.length && /^\s*\d+[.)]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*\d+[.)]\s+/, ""));
        i += 1;
      }
      blocks.push({ type: "ol", items });
      continue;
    }
    // Paragraph: gather until blank line or a block starter
    const para = [];
    while (
      i < lines.length &&
      lines[i].trim() &&
      !isTableRow(lines[i]) &&
      !/^\s{0,3}#{1,6}\s/.test(lines[i]) &&
      !/^\s*[-*•]\s+/.test(lines[i]) &&
      !/^\s*\d+[.)]\s+/.test(lines[i])
    ) {
      para.push(lines[i]);
      i += 1;
    }
    blocks.push({ type: "p", text: para.join("\n").replace(/<br\s*\/?>/gi, "\n") });
  }
  return blocks;
}

export default function Markdown({ text }) {
  const blocks = parseBlocks(text);
  return (
    <div className="md">
      {blocks.map((b, idx) => {
        if (b.type === "table") {
          return (
            <div className="md-table-wrap" key={idx}>
              <table className="md-table">
                <thead>
                  <tr>{b.header.map((c, j) => <th key={j}>{renderInline(c, `h${idx}-${j}`)}</th>)}</tr>
                </thead>
                <tbody>
                  {b.rows.map((r, j) => (
                    <tr key={j}>{r.map((c, k) => <td key={k}>{renderInline(c, `r${idx}-${j}-${k}`)}</td>)}</tr>
                  ))}
                </tbody>
              </table>
            </div>
          );
        }
        if (b.type === "heading") {
          const Tag = b.level <= 2 ? "strong" : "em";
          return <Tag key={idx} className="md-heading">{renderInline(b.text, `hd${idx}`)}</Tag>;
        }
        if (b.type === "ul" || b.type === "ol") {
          const Tag = b.type === "ul" ? "ul" : "ol";
          return (
            <Tag key={idx} className="md-list">
              {b.items.map((it, j) => <li key={j}>{renderInline(it, `li${idx}-${j}`)}</li>)}
            </Tag>
          );
        }
        return <p key={idx} className="md-p">{renderInline(b.text, `p${idx}`)}</p>;
      })}
    </div>
  );
}
