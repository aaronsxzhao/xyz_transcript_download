function day(value?: string): string {
  const match = value?.match(/^(\d{4})-?(\d{2})-?(\d{2})(?:T| |$)/)
  if (!match) return ''
  const date = `${match[1]}-${match[2]}-${match[3]}`
  const parsed = new Date(`${date}T00:00:00Z`)
  return Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 10) === date ? date : ''
}

/** Keep source dates distinct from the time content was added to this app. */
export default function ContentDates({published, imported, local = false}: {published?: string; imported?: string; local?: boolean}) {
  const source = day(published), added = day(imported)
  if (local) return added ? <time dateTime={added}>Uploaded {added}</time> : null
  return <>
    {source ? <time dateTime={source}>Published {source}</time> : <span title="The source has not provided a publication date. Import time is shown separately.">Publication date unavailable</span>}
    {added && <time className="text-gray-500" dateTime={added}>Imported {added}</time>}
  </>
}
