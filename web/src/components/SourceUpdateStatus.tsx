import type {SourceUpdateReport} from '../lib/sourceUpdateCheck'

export default function SourceUpdateStatus({progress,report}:{progress?:SourceUpdateReport|null;report?:SourceUpdateReport|null}) {
  return <>
    {progress && <p role="status" className="text-sm text-gray-400">Checked {progress.channels_processed} / {progress.channels_total} sources · {progress.new_videos} new items saved</p>}
    {report?.interrupted && <p role="alert" className="reader-utility-panel text-amber-300 [overflow-wrap:anywhere]">{report.interrupted}</p>}
    {!!report?.failures?.length && <details open className="reader-utility-panel"><summary>Some sources could not be checked · {report.failures.length}</summary><ul className="mt-2 space-y-2 text-sm [overflow-wrap:anywhere]">{report.failures.map((item,index)=><li key={index}><strong>{item.channel}</strong>: {item.message}</li>)}</ul></details>}
  </>
}
