/** Copy normal per-tab login storage, then sever the opener before navigation. */
export function openSummaryExport(eid: string): boolean {
  const tab = window.open('about:blank', '_blank')
  if (!tab) return false
  tab.opener = null
  tab.location.replace(`/exports/summaries/${encodeURIComponent(eid)}`)
  return true
}
