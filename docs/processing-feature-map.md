# Process 功能清单与实际调用路径

审查日期：2026-11-02。范围为视频、音频、文章和播客从导入到保存的处理链路，以及相关恢复／维护入口。依据是仓库中的入口、调用关系和条件判断，不代表每种平台在生产环境都已实测可用。未使用函数的结论限于仓库内静态调用关系；外部脚本或第三方调用不能据此排除。

## 本次实现的三个并行点

| 改动 | 执行方式 | 保留的约束 |
| --- | --- | --- |
| 原文内容清单提取 | 两批并发，每批拥有独立统计；汇总时按原文顺序分配稳定编号 | 边界上下文、完整原文校验、有限格式／传输重试、检查点均保留；终止性错误后不继续派发剩余批次，已发出的最多两批可能仍需结束 |
| 清单提取与摘要生成重叠 | 同一份原文启动两条分支，清单不读取草稿；真正覆盖匹配前等待清单结果 | 正文核对、补漏和复查仍按依赖顺序执行；生成失败／取消时停止后续清单请求，等待正在运行的有限时请求退出 |
| 视频下载／视觉分析与转写重叠 | 持久任务中，Bilibili／YouTube 在元数据确认后用独立下载器准备视频；其他来源在音频下载完成后开始视觉准备，与转写重叠 | 对依赖同一视频文件提取音频的平台不重复并发写文件；视觉结果参与摘要时先汇合；仅截图用途的视频可继续与摘要生成重叠 |

代码：[清单提取](../coverage_ledger.py)、[摘要主流程](../transcript_reading.py)、[媒体处理](../api/routers/video_notes.py)、[并行工具与请求准入](../processing_parallel.py)。

新增 JSON 摘要／核对和视觉模型请求准入：**单进程最多 4 个模型请求，同一所有者跨任务最多 3 个**。这是进程内保护，不是跨多个容器的分布式配额，也不替代提供方的 RPM／TPM 限额。旧流式模型客户端不在这次准入范围内。视觉截帧缓存改为按源文件路径及文件属性隔离，避免不同视频的相同时间戳图片串用；FFmpeg 仍通过媒体资源闸门执行。

没有修改：生成模式、模型选择、事实校验要求、覆盖匹配／补漏算法、数据库结构、生产数据。并发缩短可重叠的等待，不保证整个任务按并发数同比加速。现有 `model.editor.seconds` 是检查点调用包围的时间，本次会包含模型准入等待，不能当成纯模型推理耗时或与其他并行阶段直接相加。

## 正常入口可达的功能

| 功能 | 实际入口／调用路径 | 状态与边界 |
| --- | --- | --- |
| 视频 URL 生成 | `video_notes.generate` / `generate-json` → `process_video_note_sync` | 当前主流程 |
| Bilibili、YouTube、抖音、快手、本地视频 | `video_downloader.get_downloader` | 平台下载器仍接入；具体站点受 Cookie、网络、源文件可用性约束 |
| X/Twitter、Substack、通用网页与直接媒体链接 | `resolve_content` / `resolve_social_content` → 媒体处理或原文保存 | 有媒体时转写并生成；纯文章保存原文，不自动调用摘要模型 |
| 本地媒体上传／分块上传／断点续传 | `/upload`、`/upload/init`、`chunk`、`complete`、`status` | 已有接口与前端上传流程 |
| Bilibili 多 P 发现、单 P 与整套导入 | `resolve_parts` → `prepare_parts`；`/collections/{id}/parts` | 各 P 独立任务、转写、摘要、时间轴；重复入队有去重 |
| 优先使用平台字幕 | `get_subtitles`，无字幕才下载音频并转写 | 当前有效的跳过音频下载／转写路径 |
| 复用已保存转写 | 视频重试检查保存转写及 P 身份；播客检查转写完整性 | 避免无必要的重新下载和转写 |
| 转写 API／自定义兼容 API | `get_transcriber` → `APITranscriber` | 云端默认走 API；支持账户自定义模型与端点 |
| 长音频分片转写 | `APITranscriber` 分片 → `parallel_map` | 持久任务已有两路并发；逐片完整性校验和结果按时间合并 |
| 整篇／分段摘要 | `generate_note` 或 `Summarizer.summarize` → `transcript_reading.generate` | 设置中可选择，默认整篇；本次未把分段生成改成并发 |
| 摘要风格 | `NOTE_STYLES` 提供 9 个选项；当前生成 payload 传入 `style` | 精简、详细、学术、教程、小红书、生活向、任务导向、商业、会议纪要；当前路径并不逐一套用旧 `NOTE_STYLES[*].prompt`，见后面的旧路径说明 |
| 阅读长度预算／原文语言约束 | `generation_session` → `reading_budget` / `reading_language` | 当前有效；精简模式预算有所区别，长度是建议，不截断原文 |
| 额外要求、标签、视觉上下文 | 视频生成 payload 的 `additional_requirements`、`tags`、`visual_context` | 当前有效；与字幕／转写一起作为生成输入 |
| 总结开头／目录／时间链接／截图 | `formats` → `transcript_reading.render` 及媒体后处理 | 开头总结、目录与原文时间锚点独立选项；截图使用生成后的有效时间点 |
| 视频画面理解 | `extract_frame_grids` → `analyze_grids` | 用户选项；当前最多将 5 张网格图放入一次视觉模型请求；不是每张网格逐个调用模型。Groq 兼容配置下明确拒绝该模式 |
| 下载视频画质／抽帧间隔／网格尺寸 | 视频任务参数 | 影响截图与视觉输入，不改变原文覆盖校验要求 |
| 来源准确性核对 | `validate_sections` / `validate_review` | 校验来源编号、范围、正文支持；不支持的文字退回原文并标记 |
| 独立内容清单与覆盖核对 | `coverage_ledger.audit` | 提取清单、匹配、核实缺口、补漏、验证、一次剩余项恢复；未解决时保留警告 |
| 只续跑已保存摘要的覆盖核对 | `/tasks/{id}/review-coverage` → `review_saved_note` → `review_document` | 前端已接入；使用固定摘要与转写快照、独立检查点；不是整篇重新生成 |
| 重试／重新生成／取消／任务确认 | 视频任务接口、播客 `/jobs` 接口 | 当前有效；重新生成时保留此前已保存的内容，成功后形成新版本 |
| 摘要版本与按需读取转写 | `/tasks/{id}/versions/{version}`、`/transcript` | 当前有效，和生成过程分别读取 |
| 持久队列、租约、部署暂停、恢复与检查点 | `execution_store` → `api.worker` → `processing_execution` | 环境启用时走持久执行；任务默认两个槽位，与“单个任务内部模型并发”不是同一个限制 |
| 非持久执行兼容路径 | `process_video_note_async` / `process_episode_async` → executor | 持久执行未启用时仍有效；本次媒体提前准备主要针对持久任务，兼容路径保留同步行为 |
| 播客单集／批量处理／重新总结 | `/process`、`/batch`、`/episodes/{id}/resummarize` | 当前有效；最终也走同一套 `transcript_reading.generate`，因此受益于本次清单并行 |
| 频道发现／订阅检查／收藏夹导入 | 频道更新、Bilibili 收藏夹相关入口 | 发现内容后再入队；频道更新已有有界并发，并非每次摘要都同步扫描频道 |
| 截图修复、转写维护、诊断与导出 | 独立维护／导出入口、前端工具、`scripts/repair_*` | 与主生成链分离；不能全部归类为“未使用” |

## 条件启用或接口存在、常规界面不明显的功能

| 功能 | 可达条件 | 结论 |
| --- | --- | --- |
| 只转写、不生成摘要 | 播客 `ProcessRequest` / `BatchProcessRequest.transcribe_only`；前端 API wrapper 有 `transcribeOnly` 参数，但本次未找到 TSX 界面调用传入该选项 | 后端可用，当前常规界面没有明确入口；不是死代码 |
| 强制重新处理 | `force`、重新总结／重试入口 | 跳过部分复用逻辑；是有效控制参数 |
| faster-whisper / MLX 本地转写 | `WHISPER_MODE=local`，再按本地 backend 选择 | 环境条件功能，云端默认 API 路径不会使用 |
| 压缩音频快速结果＋原音频后台精修 | 播客非 API 模式、成功生成不同的压缩文件、非“只转写” | `_background_refinement` 仍有调用；API 模式明确关闭。注释称后台精修不显示在普通前台任务进度中，应单独评估其取消、租约及可见性，不在本次自动启用 |
| 保存摘要的补漏工具 | `scripts/complete_saved_coverage.py` | 同时被维护脚本和当前 `saved_note_review.py` 引用，不能因位于 scripts 目录就删除 |
| 旧排版整理器 | `NoteSummarizer._finish_presentation` | 当前日常生成不经过，但 `scripts/repair_note_presentation.py` 会调用，仍是维护功能 |
| 旧单次生成探针 | `NoteSummarizer._generate_single` | 当前网页主流程不调用，但 `scripts/probe_summary_language.py` 仍使用；探针不能代表网页当前实际生成质量 |

## 当前主入口不再调用的旧实现

以下为仓库中识别出的旧生成／整理路径，保留了部分内部相互调用与测试。不能把其中的并行或校验逻辑当成当前网页已经启用的能力。本次没有删除这些代码。

| 旧实现 | 当前情况 |
| --- | --- |
| `NoteSummarizer._generate_chunked`、`_split_transcript`、`_merge_chunk_notes` | 旧分段 Markdown 生成／合并；其中已有两路并行，但当前 `generate_note` 不走这里 |
| `NoteSummarizer._generate_single` → `_audit_note` → `_audit_note_verified` | 旧单次生成＋全文审核路径；保留探针用途，网页主流程已换入口 |
| `NoteSummarizer._edit_reading`、`_complete_overview` | 旧正文重编排／开头总结；当前主入口不调用 |
| `Summarizer._summarize_single`、`_summarize_long_transcript` | 旧播客 JSON 分段摘要路径；当前 `summarize` 转到统一阅读生成器 |
| `Summarizer._audit_summary`、`_merge_summaries`、`_merge_summaries_verified` | 旧播客模型核对／合并链；由旧函数内部调用，当前公共生成入口不走这些链路 |
| `Summarizer._edit_reading`、`_localize_summary` | 旧后置编辑／语言整理；当前公共生成入口不调用 |
| `note_summarizer._build_system_prompt`、`_build_user_prompt` 以及 `NOTE_STYLES` 的旧详细提示词 | 旧生成器使用；当前新生成器使用自己的提示词并传 style 标识，不能认为新旧风格提示完全相同 |

注意：`NoteSummarizer._generate_toc`、`_renumber_headings` 等渲染辅助函数仍被新生成器调用；模块级 `summarizer.merge_summaries` 仍被后台精修使用，和类里的 `_merge_summaries` 不是同一个函数。它们不在可删除名单中。

## 后续处理建议（未在本次实施）

1. 给探针明确标注 legacy，增加走真实公共入口的质量检查，避免验证错路径。
2. 为条件功能补齐可见状态；尤其是后台精修，不应靠阅读源码才能知道是否发生。
3. 逐个确认旧函数的脚本用途和外部调用后，再决定迁移或删除；本次只列出，不混入并行改动。
4. 如果未来扩成多 worker 进程／多容器，补分布式模型配额；当前进程内闸门不能声称是跨集群限流。
5. 单独基准测试长视频，比较首次可读时间、总耗时、请求数量、限流、遗漏和引用错误。当前测试证明并行关系与恢复行为，不等于已经测得生产提速比例。
