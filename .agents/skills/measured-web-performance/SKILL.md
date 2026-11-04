---
name: measured-web-performance
description: Diagnose and improve a website's loading speed, interaction latency, reader responsiveness, list rendering, or progress smoothness using reproducible measurements and regression budgets. Use for performance audits, slow-page investigations, and measured optimizations; not for visual redesigns or speculative rewrites.
---

# Measured web performance

## Start here

This skill works across repositories. Resolve the current project root and read its `AGENTS.md` plus existing design, test and performance guidance when present. Missing project-specific documentation is not a blocker. Discover the actual stack, build commands, test runners, instrumentation and release process before issuing commands; do not assume React, Python or any particular provider.

Only when working in `aaronsxzhao/xyz_transcript_download`, read [repository map](references/repository-map.md) and its design/regression contracts. In other projects, treat that file as an example, not applicable instructions. Map the user's journeys to the current project's components and tests. Resolve bundled reference/template links relative to this skill directory, and project paths relative to the current repository. This skill is a procedure, not permission to modify product workflows or deploy outside the user's authorized scope.

For a request to **create or install this skill**, deliver the skill only. Do not silently start an optimization campaign, schedule monitoring, install paid telemetry, or publish product changes.

For an optimization request:
1. Fetch current main, inspect open PRs, and use an isolated branch/worktree. Identify overlapping changes before editing.
2. Pick one user journey. Record the symptom, data size, device, cache state, and expected visible result in [experiment record](assets/experiment.md).
3. Classify the work: investigation; behavior-preserving optimization; or workflow/architecture change requiring a separate decision. Honor authorization already given; do not ask again for authorized minor fixes.

## Measure the actual experience

Define start and end before collecting results. A route change ends when its content and controls are usable, not when a request finishes or a skeleton appears. Separate request latency, server work, JS initialization, rendering, and image readiness. Avoid double-counting overlapping work.

Use a production build. Record commit, lockfile, browser/version, hardware/runner, CPU/network profile, viewport, theme, fixture size, and whether service workers and caches are active. Compare cold document loads separately from warm navigation. Separate active processing from idle sessions.

Capture a browser trace, network waterfall, and before screenshot/recording. Keep unredacted traces containing tokens or user content out of the repository. Reuse synthetic data and authenticated read-only access where authorized; never test real payment, deletion or user-content reprocessing.

If the site or required browser is inaccessible, record the actual failure. Continue useful local diagnosis, but label it local. A health check is not a visual test or evidence of faster user interactions.

## Run one bounded experiment

Write a falsifiable hypothesis: “Removing duplicate collection derivation will reduce calculations per task update while preserving episode order.” Identify the hot function/component from a trace before changing it.

- Make a correctness test fail at the observed boundary first. Add a performance measurement for the same workload.
- Hold fixture size, outputs and instrumentation constant. Check identical episode membership/order, rendered text, selected state, focus and scroll position.
- Prefer existing caches, selectors and lazy boundaries when the trace supports them. Profile their invalidation, account isolation, error paths and memory impact; do not introduce a second state system casually.
- Make the smallest cohesive fix. Do not split a workflow change into “minor” patches or hide content to improve a score.
- For progress, measure event-to-paint latency and main-thread work. Preserve task/run identity, authoritative percentages and completion semantics. A smoother animation is not faster processing.

See [measurement rules](references/measurement-rules.md) for paired runs, proxy metrics and acceptable gates. Reject the hypothesis if the controlled results do not support it. Do not keep complexity merely because a benchmark number fell.

## Validate and retain the result

Run the affected checks from the current project's test guidance; include persisted-theme cold load/reload for lazy asset changes. Cover the project's supported themes and phone/tablet/desktop sizes for affected presentation. For xyz_transcript_download this includes Classic/Editorial × light/dark. Add narrow widths where relevant. Confirm keyboard/touch access, reduced motion, error/retry and stale-event behavior where affected.

Show before/after traces and user-visible results. Keep valid improvements behind a tested budget with fixture and runtime provenance. Do not raise an existing ceiling to pass the new code. A legitimate new requirement needs a separately explained budget change and user authorization where applicable.

If release is authorized, open a focused PR with evidence, run required checks, follow the existing deployment pipeline, and verify the exact revision plus health. If the change needs staged exposure, use an existing rollout/rollback mechanism; document a plan if none exists rather than inventing one during a minor fix. Do not revert another agent's changes.

Field validation requires comparable windows/cohorts, sufficient samples and error rates. If telemetry cannot associate observations with the release, say so; do not invent attribution. Regressions or inconclusive results require investigation, not tighter budgets. Record follow-up candidates, but keep the next experiment within the user's task scope.

## Required output

Use the experiment record. Report: confirmed bottleneck; change or rejected hypothesis; reproducible commands; raw evidence; before/after absolute values and sample sizes; correctness/regression coverage; PR/release revision; field evidence or its absence; unresolved risks and report-only workflow proposals. Never promise a fixed speedup or claim physical-device verification from viewport simulation.

## Basis

Inspired by the measurement/optimization/release feedback cycle in [How we made claude.ai 3x faster in two weeks](https://claude.dev/blog/how-we-made-claude-ai-faster/) (2026-09-23, read 2026-11-04). The transferable principle is to select important journeys, reproduce bottlenecks, validate an optimization, check its field effect, and protect proven improvements. The repository-specific instructions here are our adaptation, not Anthropic's internal skill or an endorsement. Their reported gains do not predict this site's results.
