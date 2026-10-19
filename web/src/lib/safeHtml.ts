export async function markdownToSafeHtml(markdown: string): Promise<string> {
  const [{ default: DOMPurify }, { marked }] = await Promise.all([import('dompurify'), import('marked')])
  const container = document.createElement('div')
  container.innerHTML = DOMPurify.sanitize(await marked.parse(markdown, { gfm: true, breaks: false }))
  // Blob print documents and clipboard consumers need absolute image URLs.
  for (const element of container.querySelectorAll('img[src]')) {
    const src = element.getAttribute('src') || ''
    if (src.startsWith('/')) element.setAttribute('src', new URL(src, window.location.origin).href)
  }
  return container.innerHTML
}

export function escapeHtml(text: string): string {
  return text.replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]!))
}
