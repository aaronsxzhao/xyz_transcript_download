/** Cosmetic assets must not leave startup or navigation waiting indefinitely. */
export function withStyleTimeout<T>(load: Promise<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('Appearance loading timed out')), 8000)
    load.then(resolve, reject).finally(() => clearTimeout(timer))
  })
}

/** Share in-flight/successful loads, but a rejected load must be retryable. */
export function retryableStyleLoad(load: () => Promise<unknown>) {
  let pending: Promise<unknown> | undefined
  return () => {
    if (!pending) {
      pending = withStyleTimeout(Promise.resolve().then(load)).catch(error => {
        pending = undefined
        throw error
      })
    }
    return pending
  }
}
