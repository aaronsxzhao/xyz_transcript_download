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

it('preserves Markdown escapes and character references while exporting private images',()=>{
 const source='![Chart](/data/screenshots/chart.jpg?expires=1&amp;signature=abc "Source chart")\n\n![Reference][chart]\n\n[chart]: </data/screenshots/chart\\(1\\).jpg?expires=1&amp;signature=def> "Chart title"'
 const expected=source.replaceAll('/data/screenshots/','https://aipodcastsummary.online/data/screenshots/')
 expect(portableMarkdown(source,'https://aipodcastsummary.online')).toBe(expected)
})

it('locates the image destination after nested and escaped labels without rewriting alt text',()=>{
 const source='![Nested [label] and escaped \\](/data/screenshots/example)](</data/screenshots/chart.jpg?expires=1&amp;signature=abc> "Caption")'
 expect(portableMarkdown(source,'https://aipodcastsummary.online')).toBe(source.replace('(</data/','(<https://aipodcastsummary.online/data/'))
})

it('keeps multiline image destinations inside nested quotations and lists in their original containers',()=>{
 const source='> > ![Chart](\n> >   /data/screenshots/a.png?x=1&amp;y=2)\n\n> [cover]:\n>   </data/thumbnails/cover\\(1\\).webp?x=1&amp;y=2> "Cover"\n\n- ![List](\n    /data/screenshots/list.png)'
 expect(portableMarkdown(source,'https://aipodcastsummary.online')).toBe(source.replaceAll('/data/','https://aipodcastsummary.online/data/'))
})

it('exports stable article image sources while leaving literal code untouched',()=>{
 const image='![Chart](/api/article-image?url=https%3A%2F%2Fblog.example%2Fchart.png&expires=1&signature=abc&size=article)'
 const result=portableMarkdown(image+'\n\n```md\n'+image+'\n```','https://notes.example')
 expect(result).toBe('![Chart](https://blog.example/chart.png)\n\n```md\n'+image+'\n```')
})
