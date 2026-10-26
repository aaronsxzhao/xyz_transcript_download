import ReadableMarkdown from './ReadableMarkdown'

/** Fully formatted note even when optional rich enhancements cannot load. */
export default function PlainNote({markdown,preserveSource=false}:{markdown:string;preserveSource?:boolean}) {
  // The first two previews load asynchronously; later images remain lazy.
  // An artificial timer delays screenshots without protecting text rendering.
  return <article data-rendering="plain" aria-label="Readable note" className="note-prose prose prose-invert max-w-none"><ReadableMarkdown markdown={markdown} omitToc={!preserveSource}/></article>
}
