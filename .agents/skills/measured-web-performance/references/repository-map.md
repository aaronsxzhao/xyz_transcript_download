# Repository integration

Verified against main `d415f1676d60bd166a874aa5d04b7955982de82b` on 2026-11-04. Recheck paths and CLI arguments on each invocation; these are pointers, not immutable interfaces. At creation, open PR #229 touches processing performance and reader subscriptions: inspect its current status before duplicating that work.

## Stack and evidence already available

- React 18, Vite, TypeScript, Zustand, React Router; Python API.
- `PERFORMANCE_REVIEW.md`: read prior findings before proposing work. It explicitly distinguishes US-runner results from the user's company network in China. Record network geography and test the relevant route when available; do not substitute a fast US fixture run for that experience.
- `web/src/startup.js`, `web/src/lib/startupReads.ts`: startup and read coordination.
- `api/routers/performance.py`, `api/performance_store.py`: account-scoped page timings. Existing fields include page, stage, navigation, cached, elapsed/document/API/server time, first paint, errors and module counts. Inspect collection semantics and retention before trusting aggregates.
- Existing percentile helper reports **p50 and p95**, not p75. Do not relabel p95 or average per-page percentiles. Computing p75 requires suitable raw samples or an explicitly scoped telemetry change.
- Current timing schema does not expose a release-revision field. Exact release attribution and device/network cohort coverage must be verified or added before claiming field improvements. The existence of telemetry does not prove a complete RUM dashboard.
- `web/scripts/check-bundle-budget.mjs` and `web/package.json`: production build and compressed initial asset budget. Read the current ceiling; do not bake a stale value into the skill or silently relax it.

## Candidate journeys (hypotheses, not measured rankings)

| Journey | Start → useful result | Relevant existing checks |
| --- | --- | --- |
| Open Dashboard | Document navigation → content and intended control respond | `check_first_paint.py`, `check_document_startup.py`, `check_dashboard_recent.py` |
| Search/browse Library and series | Input/navigation/disclosure → matching rows or episodes displayed and usable | `check_library_browser.py`, `check_series_browser.py`, `check_series_theme_browser.py`, `check_series_spacing.py` |
| Open summary/article/Transcript | Select saved item/tab → readable content and controls ready | `check_reader_interactions.py`, `check_unified_readers.py`, `check_reader_recovery.py`, `check_reader_layout.py` |
| Observe active tasks | Accepted status event → consistent visible status and percentage | `check_processing_progress.py`, `check_progress_motion.py`, `check_task_workspace.py` |
| Return after a failed load | Restore connectivity/retry → requested content ready with state retained | `check_network_resilience.py`, `check_page_loading.py`, `check_page_boundaries.py` |

Select priority using actual frequency × delay × affected users, plus tail pain and implementation risk. Without usage data, label the ranking provisional. Do not assume these journeys account for any particular percentage of traffic.

## Repeatable local baseline setup

Run from the repository root. Resolve `BASELINE_SHA` to the observed main commit first and choose a new, unused baseline directory. Do not overwrite existing worktrees or artifacts.

```sh
git worktree add --detach /tmp/xyz-perf-baseline BASELINE_SHA
npm --prefix /tmp/xyz-perf-baseline/web ci
npm --prefix /tmp/xyz-perf-baseline/web run build
npm --prefix web ci
npm --prefix web run build
python scripts/check_library_browser.py --baseline-dist /tmp/xyz-perf-baseline/web/dist --current-dist web/dist --browser-path /usr/bin/chromium
python scripts/check_document_startup.py --baseline-dist /tmp/xyz-perf-baseline/web/dist --browser-path /usr/bin/chromium
python scripts/check_first_paint.py --baseline-dist /tmp/xyz-perf-baseline/web/dist --browser-path /usr/bin/chromium --output /tmp/xyz-perf-first-paint
```

These fixtures verify specific boundaries; running a script once is not a statistically valid latency comparison. Check its fixture, metric endpoints and `--help` first. Use the available Playwright browser path; do not pass unsupported flags to every script. API/DB investigations may require their own applicable skill and tests.

`.github/workflows/continuous-testing.yml` defines CI; `.github/workflows/deploy-oracle.yml` and `scripts/verify_deployment.py` define release verification. A skill/documentation-only change does not need an application deployment. Do not add recurring jobs merely by invoking this skill.
