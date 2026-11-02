import {useRef,type ReactNode} from 'react'
import {useOutsideInteraction} from '../lib/outsideInteraction'

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

/** One outside-interaction listener per list, regardless of its item count. */
export function useItemActionList() {
  const list=useRef<HTMLDivElement>(null)
  useOutsideInteraction(target=>{
    list.current?.querySelectorAll<HTMLDetailsElement>('details[open]').forEach(menu=>{
      if(!menu.contains(target))menu.open=false
    })
  })
  return list
}
