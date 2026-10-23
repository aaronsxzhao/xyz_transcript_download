// @vitest-environment jsdom
import { expect, it } from "vitest";
import { portableMarkdown } from "../src/lib/markdownDownload";

it("makes generated screenshot and reference image URLs usable outside the website", () => {
  const source =
    "# Notes\n\n![Chart](/data/screenshots/task_00-01.jpg?expires=123&signature=abc)\n\n![Cover][cover]\n\n[cover]: /data/thumbnails/task.webp?expires=456&signature=def\n";
  const result = portableMarkdown(source, "https://aipodcastsummary.online");
  expect(result).toContain(
    "](https://aipodcastsummary.online/data/screenshots/task_00-01.jpg?expires=123&signature=abc)",
  );
  expect(result).toContain(
    "[cover]: https://aipodcastsummary.online/data/thumbnails/task.webp?expires=456&signature=def",
  );
  expect(result.replaceAll("https://aipodcastsummary.online", "")).toBe(source);
});
it("preserves inline code, fenced source, external images and ordinary links", () => {
  const source =
    "`![example](/data/screenshots/example.jpg)`\n\n```md\n![sample](/data/screenshots/sample.jpg)\n```\n\n![external](https://example.com/image.jpg)\n\n[source](/viewer/one)\n";
  expect(portableMarkdown(source, "https://aipodcastsummary.online")).toBe(
    source,
  );
});
