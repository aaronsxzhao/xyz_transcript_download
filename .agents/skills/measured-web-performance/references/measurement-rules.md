# Measurement rules for this project

## Baseline validity

Use the same machine/runner and browser build for before/after comparisons. Alternate baseline/candidate runs to reduce drift. Recreate browser contexts for cold runs; document service-worker/cache clearing separately from warm-up. Avoid concurrent benchmark jobs on the same runner. Preserve every sample and record exclusions with reasons.

Start with at least 10 paired runs per scenario for exploration, increase if noise dominates. This is a local protocol, not a guarantee of statistical significance. Report median, p75, p95, sample count, spread and failures. A p95 from 10 runs is effectively an extreme observation: label it exploratory and collect more data before gating tails. Use intervals/resampling or more runs if an apparent improvement is close to noise. Do not discard slow successful runs, compare different fixture sizes, mix browser cohorts or compute a global percentile from percentile averages.

Report milliseconds saved as well as percentage. Do not subtract unrelated aggregate client/server percentiles. Account for timeouts and missing samples rather than making the page appear faster by excluding failures.

## Select measurements by bottleneck

- Network: request count, transferred bytes, duplicate requests, critical dependency chain, server timings and resource timing. A smaller bundle can still delay a required module.
- React: profiler commits/renders for an exact interaction, store selector fan-out and derived-data recomputation. Development StrictMode counts are not a production benchmark.
- Browser: trace main-thread tasks, style/layout work, unexpected region displacement, DOM size and event-to-paint. Exclude intended scrolling/disclosure from layout regressions; report unexpected movement after data/font/image arrival.
- Pure computation: a deterministic fixture plus operation counters where possible. Optional instruction profiling requires pinned runtime/toolchain and repeatability checks; never assume an unavailable profiler or compare counts across architectures.
- Long reader/streaming/progress: input responsiveness, worst stalls, frame-time distribution, work per update, duplicate subscriptions and memory growth. Distinguish server-event cadence from animation cadence. rAF timestamps alone do not prove display refresh or physical-device smoothness; verify hardware before claiming 120 Hz.

A reduced count is only a useful proxy if the same scenario also improves end-to-end timing without incorrect output or displaced work. Count metrics can become reproducible CI gates after repeated stability checks; wall-clock values need noise-aware limits. Both remain observations, not guarantees.

## Budget record

For each proven budget, store metric name/unit, exact start/end, fixture/version and size, runtime/browser, baseline/candidate SHAs, raw evidence location, allowed ceiling or range, calibration variance and rationale. Reduce ceilings only after repeated validated improvement. Runtime or fixture upgrades need an explicit recalibration record, not an unexplained baseline overwrite.

Use the existing bundle and correctness gates immediately. New call-count/render/layout budgets require measurement first; this skill deliberately contains no fabricated target counts. Do not increase request volume, polling frequency, background CPU or memory merely to improve a visible latency metric.

## Stop conditions

Stop an experiment when correctness fails, benefit is below measured noise, complexity outweighs the result, or the next change crosses the user's workflow/architecture boundary. Retain the evidence and report the next decision. Keep speed, accessibility, data integrity and maintainability as separate acceptance criteria.
