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

## iPad controls and video cards (2026-10-29)

The supplied iPad screenshot exposed two gaps not caught by the prior empty-list/phone checks: the native select could render shorter than the theme button, and video actions squeezed the title at intermediate widths. Appearance controls now use explicit border-box heights, a styled native select with a shared ChevronDown icon, and 44px touch targets (including the mobile navigation toggle). Video lists use a container query: at 600–1000px available list width, artwork keeps its original size and actions occupy a second row beneath the title/metadata. Wider desktop rows and small-screen stacking retain their existing layout.

`check_tablet_controls.py` uses logged-in touch contexts with actual video cards, checks four appearances across 320/390/640/744/768/820/834/1024/1180/1366px, equal control heights, fully visible/unobscured header hit targets, title width, and More/View interactions. WebKit runs at 744/820/1024px in both PR and scheduled CI. In the 820px fixture, title width is 594px and select/theme controls are 44px high. Screenshots wait for color transitions and loaded artwork.

Local validation: 444 unit tests, the touch matrix and existing appearance/state/failure regression passed. The initial compressed document increased from about 191.9 KiB to 192.1 KiB; the enforced budget is explicitly adjusted by 0.5 KiB to 192.5 KiB for these control/layout rules. Other performance and startup checks remain unchanged. WebKit and the full suite run in CI. This is emulated browser evidence; it is not a physical iPad test.

## Complete thumbnails and consistent button corners (2026-10-29)

Video-list thumbnails now use contain fitting. In the constrained two-row layout they span both rows, center vertically, and use the loaded image's natural height (capped at 128px), instead of retaining a cropped 128×72 box aligned only with the first row.

Standard rectangular controls use `--ui-radius`: Classic 8px and Editorial 4px. Appearance controls, collection actions, reader actions, standard rounded workspace buttons and auth form controls use this token. More already uses the shared `ui-button` component class; its competing radius/background overrides were removed, so it has the same secondary-button treatment. Navigation tabs and pill-shaped controls retain their intentional shapes.

The touch regression now asserts image contain fitting, vertical centering across the card rows, and consistent 1px borders/theme radii for the appearance and card controls. Local production checks cover all four appearances and ten viewport widths. The preview uses synthetic content and licensed fixture artwork.

## Reader interaction and stalled-tool review (2026-10-30)

Reviewed the library/reader, shared dialogs, optional-module loading, account/navigation state, progress updates and backend request/pagination code. Three defects were fixed:

- Selecting a reader menu action with the keyboard removed the focused control and left focus on the document body. Menu actions now return focus to their disclosure when the action has not deliberately moved it elsewhere.
- A failed regeneration-confirmation module showed generic retry controls outside its modal focus trap. Recovery is now rendered inside the dialog, with retry, cancel and restored opener focus; retry does not regenerate a note by itself.
- Optional tools wrapped in Suspense could wait indefinitely for a stalled module. Their pending fallback now expires after 15 seconds and enters the existing tool-specific failure state. The screenshot fallback retains the original image and Close control. Successfully loaded tools cancel their deadline.

Validation uses synthetic API fixtures and Chromium. `check_reader_recovery.py` intercepts actual confirmation/gallery module requests at 390px and 1440px, verifies keyboard download focus, modal retry/Tab/cancel, and original-image fallback without summary mutations. CI runs this separately. Reader interaction checks cover filtering/pagination, export, reading-position restoration, account changes and screenshot controls; mobile-control checks cover 390/820/1440px. Authentication checks cover four appearances and sign-in/sign-up/recovery/reset states at 390/820px. Progress checks cover parallel streams and fast completion with unavailable detail responses. All 464 frontend and 1,372 backend tests pass. Production build is 194.0 KiB compressed; the initial-transfer ceiling increases by 0.5 KiB to 194.5 KiB for bounded tool recovery.

Current-run screenshots and machine-readable results are stored outside the repository at `/workspace/reviews/ui-20261030/`. The required Product Design Browser interface is unavailable; this is source review plus automated browser evidence, not a complete live-account design/accessibility audit. No production notes were rewritten, and physical-device/WebKit verification was not performed locally in this run.

## Subscription concurrency and navigation review (2026-10-30, second pass)

This pass inspected subscription/episode state, background form completion, cache reconciliation, and navigation under persistent notifications. Reproductions exposed four additional defects:

- Concurrent subscription refreshes/deletions shared one pending ID; finishing one operation re-enabled another operation's controls. Per-subscription locks and pending state now preserve independent progress, prevent duplicate submissions before React renders, and exclude conflicting bulk checks. Buttons also identify their subscription to assistive technology.
- A late episode-page snapshot could replace a newly confirmed summary with its old unprocessed state, or remove a newly uploaded episode. Page-local confirmed changes now reconcile with read/cache snapshots, retain unrelated response rows, and reset when the podcast route changes.
- A Spotify import or audio upload could finish after the user navigated away and redirect them back to the imported episode. Automatic navigation now requires the original route instance/key to remain active.
- On phones, the persistent import notification covered the expanded navigation's Library link. Notifications now sit below the header only while mobile navigation is expanded. The real browser reproduction initially failed because pointer events were intercepted; the final check clicks the link normally, without forced clicks or notification dismissal.

Validation: 470 frontend tests and the production build pass; initial compressed transfer is 194.3 KiB within the existing 194.5 KiB limit. `check_podcast_actions.py` verifies independent pending states and background-import navigation across 390/820px and all four appearances; it is included in CI. Existing subscription/upload form checks pass across the same matrix, including failure/retry and retained drafts. Mobile-control checks at 390/820px pass. Current-run synthetic screenshots/logs are at `/workspace/reviews/ui-20261030-pass2/`. Backend/model execution and production notes are unchanged; this pass does not claim live-account or physical-device validation.
