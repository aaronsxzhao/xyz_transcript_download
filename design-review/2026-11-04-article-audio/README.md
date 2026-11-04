# UI / loading audit — 2026-11-04

- Baseline: `545dbdeedc263f91635518d966e0d666dc4cb163`; isolated `audit/ui-loading-nov04`; no open PRs at start or pre-delivery check.
- Scope: minor presentation and loading regressions only; existing layouts, entry points, processing and media-loading behavior retained.
- Evidence: local production build, Chromium, controlled API/media fixtures. Production CONNECT is rejected with HTTP 403 by the environment proxy; no live visual acceptance or physical-device testing is claimed.

## Confirmed and fixed

Native article audio controls had height **0px**: the shared image/video/audio CSS applied `height:auto` to audio. Reproduced across Classic/Editorial, light/dark and 390/820/1440px. The new browser regression fails on baseline before media is loaded.

Keep responsive auto-height for images/video only; audio retains the browser's native controls height. No new player, loading rule, retry or navigation change. Regression covers keyboard focus, no audio download before explicit loading, valid WAV metadata, unavailable-media feedback, and page bounds. Added Chromium/WebKit runs to CI and the regression contract.

## Verification

- Production build and unchanged compressed entry budget: 197.7 KiB / 197.75 KiB.
- Frontend unit tests: 79 files, 539 tests passed.
- Baseline broad scan: 108 page/theme/viewport combinations; Dashboard, Library, videos, summary, article, subscriptions, tasks, settings, login. No overflow or JS exceptions.
- Classic and Editorial component/contrast sweeps: both light/dark, 2,126 controls per theme. Separate auth and subscription fixtures at 390/820/1440px passed; no real writes/payments/reprocessing.
- Series spacing across Dashboard/Library/videos, multipart selection/overflow, progress at 390/820/1440px passed. Same synthetic series geometry compared with ordinary rows.
- Patched native-media regression: all 12 theme/viewport combinations passed including deferred loading, loaded and error states.
- Loading/backlog checks: bounded channel pages (40 then 80), server filtering, persisted IndexedDB and failure-cache expiry passed. First-paint and document-startup recovery checks passed. Timing samples are local fixture measurements, not an overall speedup or production benchmark.
- Screenshots/logs: `/workspace/reviews/ui-20261104-loading-audit/`. Manually inspected Editorial light mobile audio before/after and Editorial dark mobile Dashboard; additional screenshots captured with geometry/contrast assertions, not individually visually reviewed.
- Local WebKit unavailable; CI runs Chromium and WebKit. Deployment/revision results are recorded in the PR/workflow and final report.

## Report-only

No additional confirmed flow issue or major redesign recommendation from this run. Real production latency, authenticated live content and physical iOS behavior remain unverified due the access/environment limits above. No speculative optimization or workflow patch was made.
