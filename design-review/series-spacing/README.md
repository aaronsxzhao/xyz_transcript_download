# Series row spacing — 2026-11-04

Baseline: bb3f9f145284db84acdaeeac208da85ebd827998. No open PRs at start; isolated fix/series-row-spacing worktree.

Matched-title browser fixtures confirmed extra vertical space in all three surfaces:
- Dashboard: series used Library footer padding plus a 44px disclosure line, and different heading/source spacing. Editorial desktop: 195.23px vs ordinary 164.83px; Classic phone: 165.03px vs 123.64px.
- Library list: the disclosure inflated the footer by 26–28px. Editorial desktop: 173.59px vs 146.09px.
- Video list: the disclosure was nested inside the text column instead of using the existing sibling actions slot. Desktop: 139px vs 106px; tablet: 155px vs 133.5px.

Fix: use each surface's existing text/footer spacing; retain a real 44px disclosure hit target inside existing padding; use the existing video action slot and metadata row. No fixed row heights, clipping, navigation, default-open or processing changes. Different title lengths may still legitimately create different row heights.

Regression: scripts/check_series_spacing.py compares matched-content row heights and footer positions and exercises keyboard disclosure in Classic/Editorial, light/dark, 390/820/1440px. It is wired into CI for Chromium and WebKit. Existing series cold-start/pagination, disclosure/error retry and multipart overflow tests also pass locally. Production build and bundle budget pass.

Local evidence: /workspace/reviews/ui-20261104-series-spacing. Before/after Dashboard and Library screenshots manually inspected; video list phone, tablet and desktop inspected. Synthetic APIs only; no user content processed. Local Chromium passes; local WebKit runtime is absent, so WebKit is delegated to CI. Production-site proxy access remains blocked (CONNECT 403); local evidence is not a live visual acceptance claim.
