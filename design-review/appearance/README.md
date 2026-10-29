# Appearance switching and visual acceptance

Implemented in the isolated `feat/appearance-switch` worktree, based on `c8d5c5ad5f9e8d61ee7964dd3b272e14f8e2cae0` (latest `origin/main` checked on 2026-10-29). The original working directory and the other agent's backend work were not edited.

## Behavior

- The navigation and auth pages expose **Classic / A · Editorial** and an independent **light / dark** button.
- New browsers default to Classic dark. Device-local preferences survive reloads and synchronize across tabs. Storage failure does not disable the controls.
- Classic retains the existing typography, page structure and cards. Its light skin changes colors only. A scopes its serif typography, featured content and artwork to `data-design="editorial"`.
- Switching does not reset settings drafts or the recent-content filter. Source data, authentication and processing APIs are unchanged.
- Optional skins load before applying the selected appearance. An unavailable skin retains the working appearance and reports that a reload is needed. Core reader styles still render the note if the richer typography stylesheet is unavailable.
- Rich typography retains the existing Tailwind typography rules, loaded with reader routes to stay within the existing 192 KiB startup budget. No dependency or budget limit was changed.

## Acceptance

- `npm test`: **69 files / 436 tests passed**.
- `npm run build`: passed, **191.3 KiB** initial compressed document/assets.
- Four appearances × three viewport widths (320, 390, 1440): **216 page/state checks**, no viewport overflow or runtime errors. Raw reports are `results.json` and `subscription-results.json`.
- Coverage: dashboard, library, podcast platforms, subscriptions, episodes, video platforms, channels, channel videos, add content, video/podcast readers, General / Platform Accounts / Tools & Data settings, sign-in, signup, recovery and password reset.
- After contrast fixes, an additional 36 light-state checks passed (`final-light-results.json`). Screenshot inspection covered the pages and settings below the fold; screenshot-only CSS expands the scroll container without changing production layout.
- Production browser checks passed: default state, all four combinations, saved preferences after reload, preserved filter/settings draft/reader text, mobile navigation, widths 320/390/768/1024/1440.
- Failure injection passed: repeated failed skin loading keeps Classic usable; a blocked rich-typography asset keeps the reading content visible.

These checks use fixture data and do not exercise real account credentials, cookie import, QR authentication, uploads or production mutations. No deployment was performed.

[Review screenshots in ChatGPT Pages](https://chatgpt.com/space/page_dc168877478081919732ae8c86dba665)

## Reproduce browser checks

Install the web dependencies, plus Playwright and Chromium for the browser harness. The scripts expect `/usr/bin/chromium`; adapt that executable path for another machine.

Run Vite dev on port 5180 for `visual-check.cjs` and `subscription-check.cjs`; run the production preview on port 5181 for `production-check.cjs` and `failure-check.cjs`. Execute these scripts with Node from the repository. All API calls are intercepted by `fixtures.cjs`; no production credentials are required.

The fixture artwork was taken from the MIT-licensed Start Bootstrap Clean Blog example (`StartBootstrap/startbootstrap-clean-blog`, `dist/assets/img/{post,home,about}-bg.jpg`). Product code always uses the existing source thumbnails; these assets are only for local review.

## Follow-up interaction audit (2026-10-29)

Rebased the isolated branch onto the newer `origin/main` commit `7c6a8a6` before this review. Fixed defects discovered beyond the initial overflow checks:

- Editorial mobile/tablet readers incorrectly retained a desktop outline column, squeezing a 390px viewport's reading content to 150px. The core 1170px breakpoint now gives the content the full 350px available width. Regression checks assert actual reading width, not just absence of horizontal overflow.
- Stalled optional stylesheet requests could keep startup, switching or reader navigation waiting indefinitely. All are bounded to eight seconds; failed skins retain the working appearance and reader typography falls back to core styles. The control reports loading to assistive technology.
- Escape closes mobile navigation and now restores focus to its trigger.
- Muted light text, dark platform-account status labels and the QR action needed additional contrast. Changes are scoped to the affected skin/components.
- Broad substring selectors incorrectly treated disabled background variants as active tint classes, affecting the editorial login submit button and formatted reader container. Exact class-token matching now distinguishes selected options from primary buttons and prose variants.

Validation: **438 tests / 70 files passed**, production build **191.6 KiB**. **56** actual reader-width checks (two reader routes, four appearances, seven widths) plus font-size/width and transcript switching passed. **22** header layouts and hit targets passed, together with Escape focus, mobile navigation, cross-tab sync and retained login drafts. Production smoke and failed/stalled asset tests passed. Two accessibility passes cover **60** mobile pages and expanded desktop states, with no WCAG 2 A/AA or 2.1 AA violations reported by axe after fixes. This is scoped automated evidence, not a claim of universal accessibility or real-account end-to-end correctness.

Additional reproducible scripts: `interaction-check.cjs`, `reader-layout-check.cjs`, `stalled-style-check.cjs`, `accessibility-check.cjs`, `accessibility-states.cjs`. Accessibility scripts additionally require `axe-core` (or an absolute package path via `AXE_CORE`). The production preview is required for the stalled-style check. Reports are in `accessibility-results.json` and `accessibility-states.json`. Existing screenshot/fixture limitations still apply; production account mutations were not performed.

## Keyboard continuation check (2026-10-29)

Found a second focus defect in the appearance controls: when an uncached skin disabled the native select, Chromium blurred the select to the document body. A keyboard user could lose their place after changing the design. The control now restores the original focus after rendering the completed state, only when focus remains on the body; it does not steal focus from another control chosen while loading. A visible ellipsis also indicates the pending change.

`focus-check.cjs` tests the actual production CSS request with a deliberate delay and asserts interception. All three cases passed: successful load restores the select, failed load restores the select while retaining Classic, and moving focus to mobile navigation during loading is respected. The initial development-mode failure-injection attempt did not intercept the actual stylesheet and was rejected as evidence; the retained script uses the production asset URL and explicitly verifies interception.

Validation: all 438 unit tests passed; production build passed at 191.6 KiB; diff checks passed. No production deployment or real-account operations occurred. The remote main branch was checked and remained at `7c6a8a6`.

The Product Design screenshot-audit workflow was unavailable in this run: the required in-app browser execution interface was not exposed. This round provides code and automated browser-regression evidence, not a completed new screenshot-based design audit. The earlier screenshots are historical evidence only.

## Classic layout restoration (2026-10-29)

Compared the merged appearance implementation against pre-appearance main `665bb2e` using identical fixtures, at 390px and 1440px. The earlier checks did not verify layout equivalence and missed these regressions:

- Dashboard: the extra container removed the original 24px gap before Recently added. Restore that gap in Classic only; keep the wrapper stable so switching does not remount forms or recent filters.
- Video reader: the extracted Tailwind typography sheet lacked theme references, so spacing utilities such as blockquote padding were not generated. The fixture's body was 32px shorter. Reference the existing theme without duplicating it in the document.
- Login: the new controls displaced the original centered form by 30px on desktop and 34px on mobile. Login and password reset now use an out-of-flow, expandable appearance entry. Escape closes it and returns focus.
- Scope the remaining plain `html` rule in the light stylesheet to Classic light. The measured round-trip layout did not reproduce a global color leak; this is stylesheet isolation cleanup.

`classic-layout-check.cjs` compares positions, dimensions, typography and colors for key blocks on nine routes, then cycles Classic dark → Classic light → Editorial light → Editorial dark → Classic dark. All 18 route/viewport comparisons and return trips passed. `classic-layout-before.json` and `classic-layout-after.json` record the measurements. These checks exclude top navigation positioning because its requested appearance controls are new. They do not constitute exhaustive pixel equality or real-account testing.

Run the original revision's Vite server on 5183 and the candidate on 5180, then run the script with Playwright available through NODE_PATH. BASELINE_URL and CURRENT_URL override those origins. Screenshot files are generated locally.

## Continuous appearance regression (2026-10-29)

`python scripts/check_appearance.py --browser-path /usr/bin/chromium` validates the production build using synthetic authenticated/anonymous fixtures. It covers seven workspace routes at 390px and 1440px, four appearance combinations, return-to-Classic geometry, retained recent filters/settings drafts, reload persistence, cross-tab synchronization, auth draft/focus/geometry, blocked skin loading, stalled switching, and stalled startup. `--webkit --widths 390` runs the same checks in WebKit. Failures retain diagnostic screenshots in `appearance-checks/`; successful runs emit structured results.

The main CI now runs these checks on PRs and pushes. A separate job also runs them on the existing 30-minute schedule (which previously skipped frontend checks) and on manual workflow dispatch. Scheduled checks build current main and use fixtures; they do not exercise real credentials, mutate live subscriptions, or establish complete visual/accessibility correctness. Real service availability remains covered separately by the existing API health job.

This review found no new reproducible interaction regression in the exercised flows; production UI was left unchanged. Local validation: 444 unit tests, production build, the Chromium appearance matrix, and the existing production/failure/stall/focus scripts passed. WebKit validation runs in CI. The Product Design screenshot-audit workflow remains unavailable because its browser execution interface is not exposed; this is automated regression evidence, not a completed live screenshot audit.
