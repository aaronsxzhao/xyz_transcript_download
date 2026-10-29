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
