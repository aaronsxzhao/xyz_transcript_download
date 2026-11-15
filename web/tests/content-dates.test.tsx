// @vitest-environment jsdom
import React from 'react'
import {renderToStaticMarkup} from 'react-dom/server'
import {expect, it} from 'vitest'
import ContentDates from '../src/components/ContentDates'

it('distinguishes a source publication date from a later import, without timezone shifts', () => {
  const html = renderToStaticMarkup(<ContentDates published="2024-12-25T23:30:00-08:00" imported="2026-10-21T10:00:00Z" />)
  expect(html).toContain('Published 2024-12-25')
  expect(html).toContain('Imported 2026-10-21')
})
it('does not imply import is publication when source date is missing or invalid', () => {
  for (const published of ['', '2024-02-30', 'unknown']) {
    const html = renderToStaticMarkup(<ContentDates published={published} imported="2026-10-21" />)
    expect(html).toContain('Publication date unavailable')
    expect(html).toContain('Imported 2026-10-21')
    expect(html).not.toContain('Published 2026')
  }
})
it('keeps both dates even when imported on publication day and treats local media as uploaded', () => {
  expect(renderToStaticMarkup(<ContentDates published="20241025" imported="2024-10-25" />)).toContain('Published 2024-10-25')
  const html = renderToStaticMarkup(<ContentDates local published="2024-10-25" imported="2026-10-21" />)
  expect(html).toContain('Uploaded 2026-10-21')
  expect(html).not.toContain('Published')
  expect(html).not.toContain('unavailable')
})

it('keeps the import date without repeating missing publication notices in compact rows', () => {
 const html = renderToStaticMarkup(<ContentDates imported="2026-10-30T12:00:00Z" compact />)
 expect(html).toContain('Imported 2026-10-30')
 expect(html).not.toContain('Publication date unavailable')
})

it('keeps an old source publication separate from a new library import', () => {
 const html = renderToStaticMarkup(<ContentDates published="2005-04-24" imported="2026-11-09T05:51:46.372982+00:00" />)
 expect(html).toContain('Published 2005-04-24')
 expect(html).toContain('Imported 2026-11-09')
 expect(html).not.toContain('4/24/2005')
})
