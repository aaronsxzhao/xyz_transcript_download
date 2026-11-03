# Design contract and interaction review — 2026-11-03

Baseline: main `74b4f3cf38c8cb43f663f1eba9bee579ab0b0fc5`, including the other agent's series-card and legacy P1 fixes. No open PRs were present at the start; the baseline was rechecked before commit.

This change adds repository guidance, a design contract, a regression selection table, a report template, a PR checklist and a persisted-theme page matrix in CI. It does not modify application code or authorize new product flows.

Fresh local production-build checks:
- `check_ui_page_matrix.py`: 9 pages × 4 appearances × 3 widths (390/820/1440), 108 states; no page overflow or JS errors. Includes original articles and Transcript.
- `check_series_theme_browser.py`: 12 combinations; cold-start/reload/theme round trip, ordinary/series alignment and pagination.
- `check_bilibili_parts_browser.py`: 12 combinations; directory, selection feedback and horizontal boundaries.
- `check_processing_progress.py --widths 390 820 1440`: parallel stream updates, fast completion and simulated client clock skew.
- `check_global_feedback.py`: four appearances at 320/820px; notification visibility and keyboard interaction.
- `check_auth_forms.py --widths 390 820 1440`: sign-in, signup, recovery and reset, with pending/failure/retry feedback.
- Production build: 197.6 KiB within the unchanged 197.75 KiB budget. Script compiles; workflow YAML parses; all 25 documented regression script paths exist.

No new product defect was confirmed within this scope. No product fix or deployment is needed for this documentation/test-only change. No workflow or large-design issue is claimed from missing evidence.

All checks used Chromium and controlled API fixtures. Representative screenshots were inspected; the full matrix is automatically captured/asserted, not manually reviewed frame by frame. This run does not claim live-site, real provider, cross-device persistence or physical-device acceptance. Existing CI still supplies WebKit regressions; the new page matrix runs in Chromium and uploads its evidence as `ui-page-matrix`.
