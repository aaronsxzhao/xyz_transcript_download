import {authFetch, getVideoProcessingDefaults, parseApiResponseAsJson} from './api'
import {getAuthGeneration} from './auth'

export interface SourceUpdateReport {
  message: string
  new_videos: number
  channels_checked: number
  channels_failed?: number
  channels_skipped?: number
  failures?: {channel:string;platform:string;message:string}[]
  channels_total?: number
  channels_processed?: number
  next_cursor?: string | null
  interrupted?: string
}

/** Each POST checks and saves one source. Never replay an unacknowledged POST. */
export async function checkSources(opts?: {channel?:string;platform?:string}, onProgress?: (report:SourceUpdateReport)=>void): Promise<SourceUpdateReport> {
  const generation = getAuthGeneration()
  const defaults = JSON.stringify(getVideoProcessingDefaults())
  const report:SourceUpdateReport = {message:'Checking sources',new_videos:0,channels_checked:0,channels_failed:0,channels_skipped:0,failures:[]}
  let cursor:string | null = null
  const seen = new Set<string>()
  do {
    if (generation !== getAuthGeneration()) throw new DOMException('Account changed','AbortError')
    const params = new URLSearchParams({paged:'true',...opts})
    // Optional undefined properties must not turn into a literal source filter.
    if (!opts?.channel) params.delete('channel')
    if (!opts?.platform) params.delete('platform')
    if (cursor) params.set('cursor',cursor)
    let page:SourceUpdateReport
    try {
      const res = await authFetch(`/api/video-notes/check-channels?${params}`,{
        method:'POST',headers:{'Content-Type':'application/json'},body:defaults,
      })
      page = await parseApiResponseAsJson<SourceUpdateReport>(res,'Failed to check source updates')
    } catch (error) {
      if (generation !== getAuthGeneration()) throw error
      if (!report.channels_processed) throw error
      report.interrupted = `${error instanceof Error ? error.message : 'Connection interrupted'} Previously found items were saved. Remaining sources were not checked; check updates again.`
      break
    }
    if (generation !== getAuthGeneration()) throw new DOMException('Account changed','AbortError')
    report.new_videos += page.new_videos
    report.channels_checked += page.channels_checked
    report.channels_failed! += page.channels_failed || 0
    report.channels_skipped! += page.channels_skipped || 0
    report.failures!.push(...page.failures || [])
    report.channels_total = page.channels_total
    report.channels_processed = page.channels_processed
    onProgress?.({...report,failures:[...report.failures!]})
    cursor = page.next_cursor || null
    if (cursor && seen.has(cursor)) {
      report.interrupted = 'The server returned a repeated continuation. Previously found items were saved; check updates again.'
      break
    }
    if (cursor) seen.add(cursor)
  } while (cursor)
  report.message = report.interrupted || (report.channels_failed ? `${report.channels_failed} source(s) could not be checked` : report.new_videos ? `Found ${report.new_videos} new item(s)` : 'No new items found')
  return report
}
