# Dashboard → reader → dashboard position — 2026-11-15

Baseline: current main `1c92f966e801fee7fd16ddea74af9460b792d586`. No open PRs existed at the start. Work is isolated on `codex/dashboard-return-position` in the existing worktree. User explicitly requested that returning from a summary preserve the exact dashboard entry position.

## Confirmed failure

In secure macOS Chrome 157 with a production build and controlled local APIs, scrolling Recently added to Summary 3, opening it, reading down 2,600px and using Go back returned the dashboard scroller to zero. The entry card moved from y=348.34 to y=1418.48: a 1,070.14px displacement. Both baseline PNGs were opened and inspected.

The shared main scroller survived routes, but Dashboard did not register a saved reading position. Reader code reset/restored that same scroller. In addition, the newly recorded Continue reading card changed the height above Recently added. Restoring only an absolute scroll number would not preserve the entry card's position. DashboardRecent also reset the content filter and replaced paginated data with its first page on remount.

## Repair

Dashboard now uses the existing account-scoped, tab-local position hook. A capture-phase click saves the actual reader link, its source section, its viewport offset, current scroll position, content filter and loaded-note count before navigation changes the shared scroller. On return the hook aligns that same card; it retries after content resize and child-list changes, including asynchronous reading-history verification. User wheel/touch/pointer/scroll-key navigation stops automatic correction. A new entry replaces the previous snapshot. Reader offsets and return-origin URLs retain their existing behavior.

DashboardRecent restores the selected filter and revalidates the previously loaded window instead of collapsing to page one. It retains full cached pages during verification, persists them outside render, and passes the original account owner to cache writes. A failed revalidation can retry the complete saved window. The existing grouped-page helper accepts an explicit minimum window for this case; ordinary callers retain their five-read bound and cursor/abort/account guards.

The layout, theme tokens, import entry, visible statistics and expanded reader collection directory are unchanged. To keep this repair within the existing compressed document budget, generated embedded-module import URLs are re-minified after rewriting. Page controllers stay embedded; no navigation helper is deferred and no budget is raised. Document gzip: 202,489 bytes against the unchanged 202,496-byte ceiling.

## Verification

- Frontend: 83 files / 559 tests pass, including dashboard filter/window retry, capture before DOM clamp, account isolation, restored windows beyond five ordinary pages and existing reader position cases.
- Production build passes the unchanged size check.
- New `check_dashboard_return.py`: Classic/Editorial × light/dark × 390/820/1440px, in sandboxed Chrome and native macOS WebKit. Five round trips per combination: newly created reading history, a different entry, Continue reading reordering, filtered second page with reader reload, browser Back. It also checks free user scrolling after restoration, page errors, horizontal bounds and zero business writes. Final results are recorded after the run completes.
- Existing dashboard, reader interactions and startup checks are recorded after completion. Full PR/main CI and formal deployment are recorded after observation; none is implied by this draft.

Local synthetic API/session fixtures are not authenticated production-account coverage. Chromium/WebKit viewport checks are not physical-device tests. No payment, content import, deletion, subscription or model reprocessing is sent to production. Previously closed paid validations are not repeated.

## Evidence

Original-checkout private artifacts: `appearance-checks/nov15-dashboard-return/`. Baseline: `before/`; final browser matrices: `final-chromium/`, `final-webkit/`; existing reader lane: `readers/`. Captured screenshots and actual image review are separate: the final visual-review manifest lists only the images opened by the reviewer. Numerical assertions cover the complete executed matrix.
