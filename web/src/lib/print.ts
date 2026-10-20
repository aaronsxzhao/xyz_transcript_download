/** Keep preparation pending until the print document and its images have loaded. */
export function printHtml(html: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(new Blob([html], { type: 'text/html' }))
    const previous = document.activeElement as HTMLElement | null
    const frame = document.createElement('iframe')
    frame.title = 'Print preview'
    frame.setAttribute('aria-hidden', 'true')
    frame.setAttribute('sandbox', 'allow-same-origin allow-modals')
    Object.assign(frame.style, { position: 'fixed', left: '-10000px', width: '1px', height: '1px', border: '0' })
    let loadTimer: ReturnType<typeof setTimeout>
    let cleanupTimer: ReturnType<typeof setTimeout> | undefined
    let printTimer: ReturnType<typeof setTimeout> | undefined
    const cleanup = () => {
      clearTimeout(loadTimer); clearTimeout(cleanupTimer); clearTimeout(printTimer)
      const focused = document.activeElement === frame
      frame.remove(); URL.revokeObjectURL(url)
      if (focused) requestAnimationFrame(() => previous?.focus())
    }
    const fail = () => { cleanup(); reject(new Error('Could not prepare the PDF. Please retry or download Markdown.')) }
    frame.onerror = fail
    frame.onload = () => {
      clearTimeout(loadTimer)
      // Let the browser finish layout after its image load events.
      printTimer = setTimeout(() => {
        try {
          const target = frame.contentWindow
          if (!target) { fail(); return }
          target.addEventListener('afterprint', cleanup, { once: true })
          cleanupTimer = setTimeout(cleanup, 120000)
          target.focus(); target.print()
          resolve()
        } catch { fail() }
      }, 100)
    }
    loadTimer = setTimeout(fail, 30000)
    frame.src = url
    document.body.appendChild(frame)
  })
}
