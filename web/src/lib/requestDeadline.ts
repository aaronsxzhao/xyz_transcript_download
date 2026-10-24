const transientStatus = (status: number) => [408, 502, 503, 504].includes(status)

export async function bufferResponse(response: Response): Promise<Response> {
  return new Response([204,205,304].includes(response.status) ? null : await response.text(),
    {status:response.status, headers:response.headers})
}

/** Bound headers and body together. Only safe reads may reconnect once. */
export async function requestWithDeadline<T>(
  read: (signal: AbortSignal) => Promise<T>,
  {signal, timeout = 10000, retry = false, message = 'Loading timed out. Please retry.'}:
  {signal?: AbortSignal | null; timeout?: number; retry?: boolean; message?: string} = {},
): Promise<T> {
  for (let attempt = 0; ; attempt++) {
    if (signal?.aborted) throw new DOMException('Navigation cancelled', 'AbortError')
    const controller = new AbortController()
    let timedOut = false
    let timer: ReturnType<typeof setTimeout>
    let cancel = () => {}
    const deadline = new Promise<never>((_, reject) => {
      cancel = () => { reject(new DOMException('Navigation cancelled', 'AbortError')); controller.abort() }
      signal?.addEventListener('abort', cancel, {once:true})
      timer = setTimeout(() => {
        timedOut = true
        reject(new Error(message))
        controller.abort()
      }, timeout)
    })
    try {
      const result = await Promise.race([read(controller.signal), deadline])
      if (retry && !attempt && result instanceof Response && transientStatus(result.status)) continue
      return result
    } catch (error) {
      if (signal?.aborted) throw new DOMException('Navigation cancelled', 'AbortError')
      const detail = error as {status?:number; retryable?:boolean}
      if (!retry || attempt || detail?.retryable === false || !(timedOut || error instanceof TypeError || transientStatus(detail?.status || 0))) throw error
    } finally {
      clearTimeout(timer!)
      signal?.removeEventListener('abort', cancel)
    }
  }
}
