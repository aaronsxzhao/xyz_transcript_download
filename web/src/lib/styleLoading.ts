/** Cosmetic assets must not leave startup or navigation waiting indefinitely. */
export function withStyleTimeout<T>(load: Promise<T>, stylesheet?: string): Promise<T> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      // WebKit can keep rendering blocked by a pending stylesheet even after
      // our promise times out. Detach only this optional, still-unloaded skin.
      if (stylesheet) document.querySelectorAll<HTMLLinkElement>(`link[rel="stylesheet"][href*="/${stylesheet}-"]`).forEach(link => {
        if (!link.sheet) link.remove()
      })
      reject(new Error('Appearance loading timed out'))
    }, 8000)
    load.then(resolve, reject).finally(() => clearTimeout(timer))
  })
}

/** Share loads. Named CSS imports need a reload after failure because Vite
 * remembers their preload URL even when its pending link was removed. */
export function retryableStyleLoad(load: () => Promise<unknown>, stylesheet?: string) {
  let pending: Promise<unknown> | undefined
  return () => {
    if (!pending) {
      pending = withStyleTimeout(Promise.resolve().then(load), stylesheet).catch(error => {
        if (!stylesheet) pending = undefined
        throw error
      })
    }
    return pending
  }
}
