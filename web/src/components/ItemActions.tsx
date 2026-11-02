import type {ReactNode} from 'react'

/** Keep destructive choices identical for episodes and videos. */
export default function ItemActions({title, kind, busy, hasSummary, onDeleteSummary, onDeleteItem, children}: {
  title:string; kind:'episode'|'video'; busy:boolean; hasSummary:boolean
  onDeleteSummary:()=>void; onDeleteItem:()=>void; children?:ReactNode
}) {
  return <details className="task-more" onKeyDown={event=>{
    if(event.key==='Escape'){event.currentTarget.open=false;event.currentTarget.querySelector('summary')?.focus()}
  }}>
    <summary className="ui-button" aria-label={`More actions for ${title}`}>More</summary>
    <div>
      {children}
      <button className="ui-button ui-button-danger" disabled={busy || !hasSummary}
        onClick={onDeleteSummary}>Delete summary only</button>
      <button className="ui-button ui-button-danger" disabled={busy} title={`Delete ${kind}`}
        onClick={onDeleteItem}>Delete {kind}</button>
    </div>
  </details>
}
