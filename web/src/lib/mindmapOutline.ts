import { Lexer, type Token } from "marked";
import { inlineNoteText, prepareNoteMarkdown } from "./noteMarkdown";

export interface MapNode {
  content: string;
  children: MapNode[];
  payload?: { fold?: number };
}
export interface MapOutline {
  root: MapNode;
  count: number;
  limited: boolean;
}
export const MAP_FORMAT = 1;
const MAX_NODES = 220;
const MAX_LABEL = 180;
const escape = (text: string) =>
  text.replace(
    /[&<>"']/g,
    (character) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        character
      ]!,
  );

/** The map is a bounded navigation view; the saved summary remains complete. */
export function buildMapOutline(markdown: string): MapOutline {
  const root: MapNode = { content: "Video summary", children: [] };
  let count = 1,
    limited = false,
    titled = false;
  const stack: { depth: number; node: MapNode }[] = [{ depth: 0, node: root }];
  const label = (text: string) => {
    const clean = text.replace(/\s+/g, " ").trim();
    if (clean.length > MAX_LABEL) limited = true;
    return escape(
      clean.length > MAX_LABEL ? clean.slice(0, MAX_LABEL) + "…" : clean,
    );
  };
  const tokens = Lexer.lex(prepareNoteMarkdown(markdown));
  let remainingHeadings = Math.min(
    MAX_NODES - 1,
    tokens.filter((token) => token.type === "heading").length,
  );
  const add = (parent: MapNode, text: string, heading = false) => {
    if (!text.trim()) return null;
    if (count >= MAX_NODES - (heading ? 0 : remainingHeadings)) {
      limited = true;
      return null;
    }
    const node: MapNode = { content: label(text), children: [] };
    parent.children.push(node);
    count++;
    return node;
  };
  const textOf = (token: Token): string => {
    if (token.type === "image" || token.type === "html") return "";
    if ("tokens" in token && Array.isArray(token.tokens))
      return inlineNoteText(
        token.tokens.filter((item) => item.type !== "image"),
      );
    return "text" in token ? token.text : "";
  };
  const visit = (tokens: Token[], parent: MapNode, depth = 0) => {
    for (const token of tokens) {
      if (token.type === "list") {
        if (depth >= 6) {
          limited = true;
          continue;
        }
        for (const item of token.items) {
          const text = item.tokens
            .filter((part: Token) => part.type !== "list")
            .map(textOf)
            .join(" ");
          const node = add(parent, text);
          if (node)
            visit(
              item.tokens.filter((part: Token) => part.type === "list"),
              node,
              depth + 1,
            );
        }
      } else if (token.type === "paragraph" || token.type === "text")
        add(parent, textOf(token));
    }
  };
  for (const token of tokens) {
    if (token.type === "heading") {
      remainingHeadings = Math.max(0, remainingHeadings - 1);
      const text = textOf(token);
      if (!titled && token.depth === 1) {
        root.content = label(text);
        titled = true;
        continue;
      }
      while (stack.length > 1 && stack[stack.length - 1].depth >= token.depth)
        stack.pop();
      const node = add(stack[stack.length - 1].node, text, true);
      if (node) stack.push({ depth: token.depth, node });
    } else visit([token], stack[stack.length - 1].node);
  }
  return { root, count, limited };
}
