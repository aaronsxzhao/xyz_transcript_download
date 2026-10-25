import { fromMarkdown } from "mdast-util-from-markdown";

/** Locate the destination after the balanced label without decoding source bytes. */
function destinationOffset(raw: string, image: boolean): number {
  let depth = 1, index = image ? 2 : 1;
  for (; index < raw.length; index++) {
    if (raw[index] === '\\') { index++; continue; }
    if (raw[index] === '[') depth++;
    if (raw[index] === ']' && --depth === 0) break;
  }
  if (raw[index + 1] !== (image ? '(' : ':')) return -1;
  index += 2;
  let continued = false;
  while (index < raw.length) {
    if (raw[index] === '\n' || raw[index] === '\r') continued = true;
    if (/\s/.test(raw[index]) || (continued && raw[index] === '>')) index++;
    else break;
  }
  return raw[index] === '<' ? index + 1 : index;
}

/** AST URLs are decoded; measure the original spelling before replacing it. */
function destinationEnd(raw: string, start: number): number {
  const angle = raw[start - 1] === '<';
  let depth = 0;
  for (let index = start; index < raw.length; index++) {
    const char = raw[index];
    if (char === '\\') { index++; continue; }
    if (angle) { if (char === '>') return index; }
    else {
      if (/\s/.test(char) || (char === ')' && depth === 0)) return index;
      if (char === '(') depth++;
      if (char === ')') depth--;
    }
  }
  return raw.length;
}

/** Preserve source formatting and code while making generated media portable. */
export function portableMarkdown(source: string, origin: string): string {
  const edits: { start: number; end: number; text: string }[] = [];
  const visit = (node: any) => {
    if (
      (node.type === 'image' || node.type === 'definition') &&
      typeof node.url === 'string' && node.url.startsWith('/api/article-image?')
    ) {
      const original = new URL(node.url, origin).searchParams.get('url');
      const start=node.position?.start.offset, end=node.position?.end.offset;
      if(original && /^https?:\/\//i.test(original) && typeof start==='number' && typeof end==='number'){
        const raw=source.slice(start,end), index=destinationOffset(raw,node.type==='image');
        if(index>=0){
          const angle=raw[index-1]==='<';
          const destination=original.replace(/&(?=(?:#\d+|#x[\da-f]+|[a-z][\da-z]+);)/gi,'&amp;')
            .replace(/[\s<>]/g,char=>encodeURIComponent(char))
            .replace(angle?/\\/g:/[\\()]/g,char=>'\\'+char);
          edits.push({start:start+index,end:start+destinationEnd(raw,index),text:destination});
        }
      }
    } else if (
      (node.type === "image" || node.type === "definition") &&
      typeof node.url === "string" &&
      /^\/data\/(screenshots|thumbnails)\//.test(node.url)
    ) {
      const start = node.position?.start.offset,
        end = node.position?.end.offset;
      if (typeof start === "number" && typeof end === "number") {
        const raw = source.slice(start, end);
        const index = destinationOffset(raw, node.type === 'image');
        if (index >= 0)
          edits.push({
            start: start + index,
            end: start + index,
            text: new URL(node.url, origin).origin,
          });
      }
    }
    node.children?.forEach(visit);
  };
  visit(fromMarkdown(source));
  for (const edit of edits.sort((a, b) => b.start - a.start))
    source = source.slice(0, edit.start) + edit.text + source.slice(edit.end);
  return source;
}

export function downloadMarkdown(
  source: string,
  title: string,
  origin = location.origin,
) {
  const blob = new Blob([portableMarkdown(source, origin)], {
    type: "text/markdown;charset=utf-8",
  });
  const url = URL.createObjectURL(blob),
    link = document.createElement("a");
  link.href = url;
  link.download =
    (title
      .replace(/[\\/:*?"<>|\u0000-\u001f]/g, "_")
      .trim()
      .slice(0, 160) || "notes") + ".md";
  document.body.append(link);
  link.click();
  setTimeout(() => {
    link.remove();
    URL.revokeObjectURL(url);
  }, 1000);
}
