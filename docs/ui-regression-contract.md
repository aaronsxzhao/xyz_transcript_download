# UI regression contract

## Before editing

Record current main SHA, relevant open PRs and the last report. Use an isolated worktree. Capture the observed failure before changing code. The standard matrix is Classic/Editorial × light/dark × 390px phone / 820px tablet / 1440px desktop. Add 320/430px phones and 744/1024px tablets for navigation or toolbar changes. Chromium and WebKit are engine checks, not physical iPhone/iPad acceptance.

## Required checks by change

| Surface/change | Existing executable regression | What it protects |
| --- | --- | --- |
| All page presentation | `check_ui_page_matrix.py`, `check_appearance.py`, `check_editorial_components.py` | Cold starts, page bounds, saved themes, retained state, controls and composited contrast |
| Header, toolbar, responsive spacing | `check_mobile_controls.py`, `check_tablet_controls.py`, `check_editorial_fonts.py` | Touch targets, mobile title, fonts, narrow layouts |
| Dashboard / Library / series | `check_dashboard_recent.py`, `check_series_theme_browser.py`, `check_series_browser.py`, `check_series_spacing.py`, `check_library_browser.py` | Grouping, pagination, search, list/grid alignment, matched-title row/footer height and disclosure hit targets, fallback and no duplicate base CSS |
| Channel / multipart reader | `check_unassigned_channels.py`, `check_bilibili_parts_browser.py` and relevant collection unit/API tests | Source identity, numeric order, current/ready/selected states, expanded reader directory, legacy parts |
| Summary / article / Transcript | `check_currency_math.py`, `check_summary_theme.py`, `check_unified_readers.py`, `check_reader_themes.py`, `check_reader_layout.py`, `check_reader_interactions.py`, `check_article_media_controls.py` | Native audio controls before/after loading and errors; original article vs summary, tabs, lists, images, copy/export, retained reading position |
| Task progress and notifications | `check_processing_progress.py`, `check_progress_motion.py`, `check_global_feedback.py` | Parallel updates, late snapshots, completion, motion, duplicate feedback and keyboard dismissal |
| Authentication | `check_auth_forms.py` | Pending inputs, duplicate submission prevention, failure/retry, retained drafts, recovery |
| Subscriptions / uploads | `check_podcast_forms.py`, `check_podcast_actions.py` | Pending/selected feedback, concurrent actions, drafts and background navigation |
| Startup, CSS or lazy assets | `check_document_startup.py`, `check_page_boundaries.py`, `check_page_loading.py`, `check_series_theme_browser.py` | Production startup, blocked optional assets, CSS ordering, navigation readiness |

Settings tabs, custom model fields, platform accounts and tools/data controls are covered by `check_editorial_components.py`; add focused tests for any business logic change. Read a script's `--help` and fixtures before running it. Browser test names alone do not imply all themes/widths: record the actual arguments. `check_reader_themes.py`, for example, currently covers 390/1280px; the page matrix adds 820/1440px visual bounds.

## Execution

```sh
npm --prefix web ci
npm --prefix web test
npm --prefix web run build
python -m pip install playwright
python -m playwright install chromium webkit
python scripts/check_ui_page_matrix.py --output appearance-checks/page-matrix
python scripts/check_series_theme_browser.py
python scripts/check_series_theme_browser.py --webkit
```

Use `--browser-path /usr/bin/chromium` for scripts that support it when that is the installed browser. Run relevant lanes from the table; do not rerun unrelated expensive checks after they pass unless a new change or unresolved failure warrants it. Full CI is defined in `.github/workflows/continuous-testing.yml`; maintain it with this table. Build-time compressed-size checks keep their existing budget. Tests with mocked APIs are local/CI checks, not production service validation.

For each affected component, exercise normal, hover, keyboard focus, selected, disabled, loading, empty, error and retry states where applicable. Cover persisted-theme cold start and reload, not only runtime switching. Include missing artwork, long text, mixed ordinary/series data, multiple pages and out-of-order task updates when relevant. Never send a production write merely to test a visual state.

## Evidence and release

- Capture the built UI before and after a confirmed fix. Inspect screenshots; record which are manually reviewed versus only captured/asserted.
- Save SHA, commands, engine, viewport/theme coverage, results and screenshots in a dated review folder. Use `docs/ui-review-template.md` for the report.
- Every confirmed bug gets a regression at its actual failure boundary. Do not change an assertion to bless a regression; if the product behavior was explicitly changed, document why the expectation changes.
- Default/hover contrast checks do not prove accessibility compliance. Synthetic failure/retry tests do not prove provider integration or cross-device persistence.
- Report workflow changes separately during minor-only audits. No confirmed defect means no product patch and no unnecessary release.
- If a product fix is authorized for release: PR, relevant passing checks, merge, existing deployment workflow, exact deployed SHA and health verification. Clearly label live UI verification as completed or blocked. A merged PR is not proof of deployment.

## Historical regression cases that must stay covered

1. Lazy series components reloaded base CSS after Editorial, restoring blue panels and purple tabs.
2. A page of twelve parts collapsed to one title while other content remained behind pagination.
3. Series and ordinary cards differed in artwork, typography, metadata and action alignment.
4. Reader/table/numbered-list content caused horizontal drift on narrow screens.
5. Current/processed parts were indistinguishable from selectable parts; selection lacked visual feedback.
6. Task progress could regress after stale polling/stream updates or leak across runs.
7. Repeated failure notifications and dismissed messages needed state-aware behavior; test the implemented semantics without silently changing them.

These are regression scenarios, not claims that all possible production cases are solved.

## Managed cloud browser capability

Use `python scripts/check_cloud_browser.py --output appearance-checks/cloud-browser/RUN-ID/anonymous`
for the secure shell Chromium capability and anonymous responsive smoke lane.
See [cloud browser inspection](cloud-browser-inspection.md) for host permissions,
explicit authenticated coverage, private artifacts and mandatory separate image
inspection. Missing built-in Browser tools alone is not a browser-test blocker.
