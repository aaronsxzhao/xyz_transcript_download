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
- New `check_dashboard_return.py`: Classic/Editorial × light/dark × 390/820/1440px, in sandboxed Chrome and native macOS WebKit. Five round trips per combination: newly created reading history, a different entry, Continue reading reordering, filtered second page with reader reload, browser Back. It also checks free user scrolling after restoration, page errors, horizontal bounds and zero business writes. All 24 combinations / 120 round trips passed: maximum offset error 0.141px in Chrome and 0.860px in WebKit. All user-scroll, bounds, zero-error and zero-write assertions passed.
- Existing dashboard (390/820/1440px), reader interactions (390/820/1440px), streamed-document recovery and optional-page-boundary checks passed. Eight PNGs were actually inspected: two baseline frames, Chromium phone Classic light and desktop Editorial dark entry/return pairs, and WebKit desktop Editorial dark Continue reading entry/return. Full CI and formal deployment are recorded after observation; neither is implied by these local results.

Local synthetic API/session fixtures are not authenticated production-account coverage. Chromium/WebKit viewport checks are not physical-device tests. No payment, content import, deletion, subscription or model reprocessing is sent to production. Previously closed paid validations are not repeated.

## Evidence

Original-checkout private artifacts: `appearance-checks/nov15-dashboard-return/`. Baseline: `before/`; final browser matrices: `final-chromium/`, `final-webkit/`; existing reader lane: `readers/`. Captured screenshots and actual image review are separate: the final visual-review manifest lists only the images opened by the reviewer. Numerical assertions cover the complete executed matrix.


## Release

- PR: [275](https://github.com/aaronsxzhao/xyz_transcript_download/pull/275), merged as `9a7555e7293adc777ee9cfbd3e7850ebee83a0c3`.
- Final PR head: `8f485c9dc59ebef63b48576b9dd1c94508f91028`; full [CI 43667267390](https://github.com/aaronsxzhao/xyz_transcript_download/actions/runs/43667267390) completed successfully, including both engines in the new return-position lane. The product source is identical to the locally tested `98c894c` tree.
- Concurrent main repair #274 (`ebd2b2422adc33ae9f39cc790f2757868e0dc40f`) was inspected and preserved. It changes backend coverage diagnostics/receipts and separate evidence, with no frontend overlap. It is an ancestor of the deployed candidate; `git diff 8f485c9..9a7555e -- web` is empty.
- Formal [deployment 43669994064](https://github.com/aaronsxzhao/xyz_transcript_download/actions/runs/43669994064): **success**, exact revision `9a7555e7293adc777ee9cfbd3e7850ebee83a0c3`.
- Post-merge [main CI 43669994089](https://github.com/aaronsxzhao/xyz_transcript_download/actions/runs/43669994089): **success, independently confirmed after the release observation**. This is separate from the successful PR gate.
- Independent live health and public frontend delivery: **pass**: HTTP200 health returned the exact deployed revision. All seven public embedded module bodies are byte-identical to the locally tested production build; the observed public recovery URL also has its expected content hash (`b6233791c6834307`)..

Authenticated production-account behavior is not yet claimed: the dedicated credential is now saved in the local macOS Keychain, but normal UI login initially hit server-connection timeouts. Subsequent original-site sign-in API and normal UI sign-in/protected stats checks passed; the actual dashboard return matrix remains incomplete because of saved-summary read and startup transport timeouts. See [local account readiness](2026-11-15-local-browser-test-keychain.md). The completed UI journeys above use controlled local APIs/sessions. Public frontend code delivery and backend revision verification do not replace a real signed-in flow. No paid validation was repeated.

Existing open browser documents must load the new build before the next dashboard entry is captured; refresh the dashboard once. A position that an old build never recorded cannot be recovered retroactively.


Post-release anonymous Chrome 157 on this Mac passed one 390×844 cold start and reload, reversible checkbox interactions and horizontal bounds, with zero business writes and page errors. Its actual login PNG was opened and inspected, bringing actual reviewed images to nine. This is a login/startup check, not a dashboard or authenticated-account claim. Cold/reload complete interaction timings were 14.677s / 29.383s in this run; no latency improvement or transport closure is claimed. The successful normal compressed HTML document was used for code comparison. Separate identity-document (45s, partial 199,348 bytes), identity recovery-file (30s, partial 381,403 bytes) and compressed recovery-file (60s, partial 32,811 bytes) curl attempts timed out and are not counted as successful transfers.
