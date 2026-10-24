# Social content import

Paste a link in Dashboard → Add content or Videos & social → Add content.
Completed imports appear in Library and use the existing reader, Markdown/PDF
export, copy, Notion export, versions and reading-history features.

## Content behavior

- X/Twitter posts: original text, photos/alt text, quoted-post text, author,
  publication time and source link. Long Articles included in a post use their
  full structured body, not the preview.
- Direct X Article links: import the full body when the public page exposes it.
  Otherwise show an actionable source error and suggest the associated post link.
- Substack articles: headings, paragraphs, lists, code, tables, images and links.
  Substack Notes use the public reader response and retain text and attachments.
- Substack publication custom domains with `/p/...` links use the publication's
  public post API. App/share links resolve through public redirects/canonical URLs.
- Text and image posts are stored as **Original text** with no transcription or
  LLM call. Reading does not run generated-note cleanup on source text.
- Audio/video attachments use the existing transcription and summary providers.
  Original post text is retained after the generated note. Multiple attachments
  are processed in source order; their combined timeline is used for screenshots.
  Audio-only posts do not request screenshots or video understanding.

## Access and completeness

Public access is required. Private/deleted posts, subscription-only articles,
missing Article bodies, rate limits and incomplete previews are reported clearly.
Profiles, searches, live X Spaces and automatic account/timeline synchronization
are not imported. Posting a link does not bypass a subscription or sign-in wall.

The X public-data adapter uses the documented FxEmbed API
(`https://api.fxtwitter.com/2/status/{id}`); its availability and completeness
depend on that service and X. Only the public post ID is sent, without account
cookies or credentials. Substack reads use the publication's public post API and
`/api/v1/reader/comment/{id}` for Notes. These interfaces can change upstream;
failures preserve the source reason rather than silently storing a preview.

Source fetches validate public DNS destinations and every redirect, enforce time
and size limits, and never silently truncate oversized responses. Media download
hosts are restricted to platform CDNs and recognized publication media endpoints.
New imports reuse the owner-scoped task storage and atomic final-save operation;
no schema migration is needed.

## Validation

Synthetic tests cover URL normalization, safe destinations/redirects, long text,
Articles versus previews, Notes, paywalls, source formatting, ordered media,
zero-model text imports, atomic storage, admission, media generation and reader
behavior. Browser checks use synthetic records, not private platform content.
