/** Cosmetic assets must not leave startup or navigation waiting indefinitely. */
export function withStyleTimeout<T>(load: Promise<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('Appearance loading timed out')), 8000)
    load.then(resolve, reject).finally(() => clearTimeout(timer))
  })
}
