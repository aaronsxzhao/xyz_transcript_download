import { expect, it } from "vitest";
import { buildMapOutline } from "../src/lib/mindmapOutline";
it("keeps chapter structure while excluding navigation, screenshots and untrusted HTML", () => {
  const outline = buildMapOutline(
    "# Trading\n\n## 目录\n- [Market](#market)\n\n## Market\n\nA conditional argument.\n\n![Chart](https://image.test/chart.jpg)\n\n- A signal\n  - Its condition\n\n<script>alert(1)</script>",
  );
  expect(outline.root.content).toBe("Trading");
  const text = JSON.stringify(outline);
  expect(text).toContain("Market");
  expect(text).toContain("Its condition");
  expect(text).not.toContain("目录");
  expect(text).not.toContain("https://image.test");
  expect(text).not.toContain("<script>");
  expect(
    outline.root.children[0].children.some(
      (child) =>
        child.content === "A signal" &&
        child.children[0].content === "Its condition",
    ),
  ).toBe(true);
});
it("bounds diagram size and label length for very large saved notes without modifying the source", () => {
  const markdown =
    "# Long note\n\n" +
    Array.from(
      { length: 600 },
      (_, i) => `## Chapter ${i}\n\n${"Argument ".repeat(400)}`,
    ).join("\n\n");
  const outline = buildMapOutline(markdown);
  expect(outline.count).toBeLessThanOrEqual(220);
  expect(outline.limited).toBe(true);
  const lengths: number[] = [];
  const visit = (node: typeof outline.root) => {
    lengths.push(node.content.length);
    node.children.forEach(visit);
  };
  visit(outline.root);
  expect(Math.max(...lengths)).toBeLessThanOrEqual(181);
  expect(markdown).toContain("Chapter 599");
});
it("escapes text rather than emitting executable markup or image URLs", () => {
  const outline = buildMapOutline(
    "# Safe\n\n`<img src=x onerror=alert(1)>`\n\n[link](javascript:alert)",
  );
  expect(JSON.stringify(outline)).toContain("&lt;img");
  expect(JSON.stringify(outline)).not.toContain("<img");
  expect(JSON.stringify(outline)).not.toContain("javascript:");
});

it("reserves space for later chapters before filling the map with paragraph details", () => {
  const markdown =
    "# All chapters\n\n" +
    Array.from(
      { length: 90 },
      (_, i) =>
        `## Chapter ${i}\n\n${Array.from({ length: 12 }, () => "- Supporting detail").join("\n")}`,
    ).join("\n\n");
  const outline = buildMapOutline(markdown);
  expect(
    outline.root.children.filter((node) => node.content.startsWith("Chapter")),
  ).toHaveLength(90);
  expect(outline.count).toBeLessThanOrEqual(220);
  expect(outline.limited).toBe(true);
});
