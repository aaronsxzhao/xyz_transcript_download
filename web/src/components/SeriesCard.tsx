import {lazy, Suspense} from 'react'
import type {LibrarySeries} from '../lib/librarySeries'

const SeriesCardContent = lazy(() => import('./SeriesCardContent'))

/** Load the episode directory only when a series is present on this page. */
export default function SeriesCard(props: {group: LibrarySeries; priority?: boolean}) {
  return <Suspense fallback={<article aria-busy="true"><h2>{props.group.title}</h2><p role="status">Loading episodes…</p></article>}>
    <SeriesCardContent {...props}/>
  </Suspense>
}
