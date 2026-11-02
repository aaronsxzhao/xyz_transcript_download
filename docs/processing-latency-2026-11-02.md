# Long-video processing investigation — 2026-11-02

Read-only inspection of the reporting account's durable processing metrics; no transcript or summary text is included here.

| Completed sample | Media duration | Processing wall time | Created → completed | Model calls / cumulative time | Transcription calls / cumulative time |
| --- | --- | --- | --- | --- | --- |
| A | 48m 08s | 48m 07s | 56m 13s | 81 / 45m 23s | 5 / 34s |
| B | 46m 19s | 51m 42s | 66m 02s | 107 / 47m 04s | 5 / 31s |

Both completed with one queue attempt. The difference between processing wall time and created-to-completed time is approximately 8m and 14m, respectively; it includes queue/lifecycle overhead, not a directly instrumented queue-only timer. A prior 43m 53s video completed in 3m 31s with 11 model calls, so video length alone does not determine this latency.

`processing_execution.Execution` measures actual model/checkpoint calls and accumulated worker wall time. Stage totals may overlap and should not be added to derive elapsed time. `generation.wall_seconds` describes the recorded generation session and is not the entire task timer.

The final coverage reports recorded 47 and 64 requests, eight and nine source inventory batches, and one unresolved-item recovery round each. They still reported two and seven unresolved coverage items. `coverage_ledger.py` inventories source batches sequentially, then processes eight coverage items at a time through matching, source validation, repair, and verification. Repairs mutate the shared draft, so those passes cannot simply be run concurrently without redesigning validation.

Conclusion: the reported 30+ minute wait is real, and these samples took longer. Model generation and repeated coverage/repair work dominate; transcription is a small fraction. Batch-importing a multipart course also queues later chapters behind these long tasks.

Recommended follow-up: instrument model calls by semantic phase and first-result/verification completion; parallelize only independent inventory work with a shared provider concurrency cap; evaluate less repetitive matching against fixed draft snapshots before changing dependent repair passes. Benchmark representative long videos for elapsed time, calls, coverage failures, source grounding and cancellation/resume behavior. Do not silently remove source checks, reduce coverage requirements, or promise a new runtime without measurements. This change leaves the generation algorithm untouched.

Multipart UX changes: channel video lists group by validated Bilibili video identity (not titles), keep page order and per-part actions, and label counts as the loaded/filtered subset. The reader displays collection status and previous/next navigation, with a collapsible directory, shorter chapter titles and a current-page indicator. The Library feed remains unchanged: its existing API does not expose source identity, and grouping by similar titles would incorrectly merge unrelated videos.
