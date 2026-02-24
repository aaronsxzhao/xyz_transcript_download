"""
Note generation with configurable styles and format options.
Builds on the existing summarizer patterns but generates Markdown notes
with support for TOC, timestamped links, screenshot markers, and AI summaries.
"""

import json
import re
from typing import List, Optional

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from config import (
    LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, MAX_RETRIES,
)
from logger import get_logger

logger = get_logger("note_summarizer")

NOTE_CHUNK_CHARS = 10000

NOTE_STYLES = {
    "minimal": {
        "name": "精简",
        "prompt": "请生成精简笔记，只保留最关键的要点和核心观点。使用简洁的语言，避免冗余。",
    },
    "detailed": {
        "name": "详细",
        "prompt": "请生成详细笔记，全面覆盖视频中的每个知识点、案例和讨论。保留重要细节和上下文。",
    },
    "academic": {
        "name": "学术",
        "prompt": "请以学术论文风格生成笔记。使用正式语言，结构严谨，包含论点、论据和结论。适当标注引用。",
    },
    "tutorial": {
        "name": "教程",
        "prompt": "请以教程/步骤指南风格生成笔记。将内容组织为分步骤的操作指南，突出关键步骤和注意事项。",
    },
    "xiaohongshu": {
        "name": "小红书",
        "prompt": (
            "请以小红书笔记风格生成内容。使用轻松活泼的语气，适当使用emoji表情，"
            "提取关键词标签，突出实用性和分享价值。"
        ),
    },
    "life_journal": {
        "name": "生活向",
        "prompt": "请以生活日记风格生成笔记。使用感性、温暖的语言，关注情感共鸣和个人感悟。",
    },
    "task_oriented": {
        "name": "任务导向",
        "prompt": "请以任务导向风格生成笔记。提取所有可操作的行动项、目标和待办事项，按优先级组织。",
    },
    "business": {
        "name": "商业风格",
        "prompt": "请以商业报告风格生成笔记。使用专业术语，聚焦于商业洞察、市场分析和战略建议。",
    },
    "meeting_minutes": {
        "name": "会议纪要",
        "prompt": "请以会议纪要风格生成笔记。包含议题、讨论要点、决议事项和后续跟进计划。",
    },
}


def _build_system_prompt(style: str, formats: List[str], duration: float = 0) -> str:
    """Build the system prompt based on style and format options."""
    style_info = NOTE_STYLES.get(style, NOTE_STYLES["detailed"])
    style_instruction = style_info["prompt"]

    format_instructions = []
    if "toc" in formats:
        format_instructions.append(
            "在笔记开头生成目录（Table of Contents），使用 Markdown 链接格式指向各章节。"
        )
    if "link" in formats:
        format_instructions.append(
            "在关键内容处插入原片跳转标记，格式为 `*Content-[mm:ss]`，"
            "其中 mm:ss 是对应的视频时间戳。"
        )
    if "screenshot" in formats:
        if duration > 0:
            duration_min = duration / 60
            if duration_min <= 5:
                screenshot_count = "3-5"
            elif duration_min <= 15:
                screenshot_count = "5-8"
            elif duration_min <= 30:
                screenshot_count = "8-12"
            elif duration_min <= 60:
                screenshot_count = "10-15"
            else:
                screenshot_count = "15-20"
        else:
            screenshot_count = "5-10"

        format_instructions.append(
            "转录文本中每行前面有 [MM:SS] 时间戳，表示该段内容在视频中的实际时间位置。\n"
            "请在内容发生视觉变化（如切换话题、展示图表、演示操作、出现新场景）的位置插入截图标记。\n"
            "格式严格为 Screenshot-[MM:SS]（纯文本，不要用反引号包裹，不要加 * 号），"
            "其中 MM:SS 必须从转录文本中的时间戳中选取，不要自行编造时间戳。\n"
            "不要用 H:MM:SS 格式。\n"
            f"根据视频时长，建议插入约 {screenshot_count} 个截图，"
            "均匀分布在笔记各段落中，优先选择以下时刻：\n"
            "  - 话题切换或章节转折处\n"
            "  - 出现重要图表、数据、代码、公式等视觉内容时\n"
            "  - 关键操作步骤演示时\n"
            "  - 讨论重点结论时\n"
            "不要在相邻位置连续插入截图，保持合理间距。"
        )
    if "summary" in formats:
        format_instructions.append(
            "在笔记最后添加一个 `## AI 总结` 段落，用3-5句话概括视频的核心观点和价值。"
        )

    format_text = "\n".join(f"- {inst}" for inst in format_instructions) if format_instructions else ""

    return f"""你是一个专业的视频内容笔记助手。你的任务是根据视频的转录文本（和可选的视觉分析）生成高质量的、结构清晰的 Markdown 格式笔记。

风格要求:
{style_instruction}

格式要求:
{format_text if format_text else "- 使用标准 Markdown 格式，结构清晰"}

Markdown 结构规范（严格遵守）:
- 使用 `# 标题` 作为笔记主标题（仅一个）
- 使用 `## 二级标题` 划分主要章节/话题
- 使用 `### 三级标题` 划分子话题
- 每个章节之间用空行分隔，保证视觉层次
- 关键观点用 **加粗** 强调
- 使用 `>` 引用块来突出重要金句、核心论点或原话
- 使用有序列表 `1. 2. 3.` 表示步骤或排序内容
- 使用无序列表 `- ` 表示并列要点
- 适当使用分隔线 `---` 分隔大的内容板块
- 如果视频涉及代码，使用带语言标记的代码块 (```python 等)
- 对于简单数字和计算（如 450,000 / 250 ≈ 1,800），直接用纯文本书写，不要用 LaTeX
- 仅在复杂数学公式（如积分、求和、矩阵）时才使用 LaTeX（$...$ 行内，$$...$$ 块级）
- LaTeX 中数字不要加反斜杠（写 1800 不要写 \\1800），使用正确的 LaTeX 语法
- 绝对不要把所有内容都写成平铺直叙的纯文本段落

内容规则:
- 使用中文撰写笔记（除非原视频是英文，则保留关键术语的英文）
- 确保内容准确，不要编造视频中没有的信息
- 按照视频时间顺序组织内容
- 每个要点要有实质内容，不要只写标题没有展开

输出示例结构:
```
# 视频标题笔记

## 第一部分：主题名
> 核心论点引用

### 1.1 子话题
- 要点一：具体内容说明
- 要点二：具体内容说明
  - 补充细节

### 1.2 子话题
**关键概念**：详细解释...

---

## 第二部分：主题名
...

## AI 总结
概括性总结...
```"""


def _build_user_prompt(
    title: str,
    transcript_text: str,
    visual_context: str = "",
    tags: List[str] = None,
    extras: str = "",
    chunk_info: str = "",
) -> str:
    """Build the user prompt with video content."""
    parts = [f"## 视频标题\n{title}\n"]

    if chunk_info:
        parts.append(f"## 当前片段\n{chunk_info}\n")

    if tags:
        parts.append(f"## 标签\n{', '.join(tags)}\n")

    if visual_context:
        parts.append(f"## 视觉分析\n{visual_context}\n")

    parts.append(f"## 转录文本\n{transcript_text}\n")

    if extras:
        parts.append(f"## 额外要求\n{extras}\n")

    parts.append(
        "请根据以上内容生成结构清晰的笔记。"
        "直接输出 Markdown 格式内容（不要用代码块包裹）。"
        "必须使用 # ## ### 标题层级、**加粗**、> 引用块、列表等 Markdown 元素来组织内容，"
        "不要输出纯文本段落。确保笔记有清晰的视觉层次和段落间距。"
    )

    return "\n".join(parts)


class NoteSummarizer:
    """Generates Markdown notes from video transcripts with configurable styles."""

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "",
        model: str = "",
    ):
        self.api_key = api_key or LLM_API_KEY
        self.base_url = base_url or LLM_BASE_URL
        self.model = model or LLM_MODEL

        if not self.api_key:
            raise ValueError("LLM API key is required for note generation")

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=600.0,
            max_retries=MAX_RETRIES,
        )
        logger.info(f"NoteSummarizer initialized: model={self.model}")

    def generate_note(
        self,
        title: str,
        transcript_text: str,
        style: str = "detailed",
        formats: Optional[List[str]] = None,
        visual_context: str = "",
        tags: Optional[List[str]] = None,
        extras: str = "",
        progress_callback=None,
        duration: float = 0,
    ) -> Optional[str]:
        """
        Generate a Markdown note from a transcript.
        Automatically chunks long transcripts (> NOTE_CHUNK_CHARS) and merges results.
        """
        if formats is None:
            formats = []

        transcript_len = len(transcript_text)
        logger.info(
            f"Generating note: style={style}, formats={formats}, "
            f"transcript={transcript_len} chars"
        )

        try:
            if transcript_len > NOTE_CHUNK_CHARS:
                result = self._generate_chunked(
                    title, transcript_text, style, formats,
                    visual_context, tags, extras, progress_callback,
                    duration=duration,
                )
            else:
                result = self._generate_single(
                    title, transcript_text, style, formats,
                    visual_context, tags, extras, progress_callback,
                    duration=duration,
                )

            if result:
                ratio = len(result) / transcript_len if transcript_len > 0 else 1
                if ratio < 0.05:
                    logger.warning(
                        f"Output may be too sparse: {len(result)} chars output "
                        f"for {transcript_len} chars input (ratio={ratio:.3f})"
                    )

            return result
        except Exception as e:
            if "cancel" in type(e).__name__.lower() or "cancel" in str(e).lower():
                raise
            logger.error(f"Note generation failed: {e}")
            return None

    def _generate_single(
        self,
        title: str,
        transcript_text: str,
        style: str,
        formats: List[str],
        visual_context: str = "",
        tags: Optional[List[str]] = None,
        extras: str = "",
        progress_callback=None,
        duration: float = 0,
    ) -> Optional[str]:
        """Generate notes from a single (short) transcript."""
        system_prompt = _build_system_prompt(style, formats, duration=duration)
        user_prompt = _build_user_prompt(title, transcript_text, visual_context, tags, extras)
        return self._call_llm(system_prompt, user_prompt, progress_callback)

    def _generate_chunked(
        self,
        title: str,
        transcript_text: str,
        style: str,
        formats: List[str],
        visual_context: str = "",
        tags: Optional[List[str]] = None,
        extras: str = "",
        progress_callback=None,
        duration: float = 0,
    ) -> Optional[str]:
        """Split a long transcript into chunks, generate notes for each, and merge."""
        chunks = self._split_transcript(transcript_text)
        num_chunks = len(chunks)
        logger.info(f"Chunked transcript into {num_chunks} parts ({len(transcript_text):,} chars total)")

        chunk_formats = [f for f in formats if f != "toc"]
        chunk_formats_no_summary = [f for f in chunk_formats if f != "summary"]

        chunk_results = []
        total_chars = 0
        accumulated_text = f"# {title}\n\n"

        for i, chunk_text in enumerate(chunks):
            is_last = (i == num_chunks - 1)
            these_formats = chunk_formats if is_last else chunk_formats_no_summary
            chunk_info = (
                f"这是视频的第 {i + 1}/{num_chunks} 部分。请为本部分生成详细笔记，不要生成总标题（# 标题），直接从 ## 二级标题开始。"
                "二级标题请使用描述性名称（如 ## 市场分析），不要自行编号（如 ## 第一部分：市场分析），编号会在后期统一处理。"
            )

            system_prompt = _build_system_prompt(style, these_formats, duration=duration)
            user_prompt = _build_user_prompt(
                title, chunk_text, visual_context if i == 0 else "",
                tags, extras, chunk_info=chunk_info,
            )

            logger.info(f"Generating chunk {i + 1}/{num_chunks} ({len(chunk_text):,} chars)")

            prefix = accumulated_text
            chunk_idx = i
            def chunk_progress(chars, partial_text="", _ci=chunk_idx, _prefix=prefix):
                if progress_callback:
                    full_text = _prefix + partial_text if partial_text else _prefix
                    progress_callback(total_chars + chars, full_text, _ci + 1, num_chunks)

            if progress_callback:
                progress_callback(total_chars, accumulated_text, i + 1, num_chunks)

            try:
                result = self._call_llm(system_prompt, user_prompt, chunk_progress)
            except Exception as e:
                if "cancel" in type(e).__name__.lower() or "cancel" in str(e).lower():
                    raise
                logger.error(f"Chunk {i + 1}/{num_chunks} failed: {e}")
                continue

            if result:
                chunk_results.append(result)
                total_chars += len(result)
                accumulated_text += result + "\n\n---\n\n"

        if not chunk_results:
            return None

        return self._merge_chunk_notes(title, chunk_results, "toc" in formats)

    def _split_transcript(self, text: str) -> List[str]:
        """Split transcript text into chunks at sentence boundaries."""
        if len(text) <= NOTE_CHUNK_CHARS:
            return [text]

        chunks = []
        start = 0
        while start < len(text):
            end = start + NOTE_CHUNK_CHARS
            if end >= len(text):
                chunks.append(text[start:])
                break

            split_at = end
            for sep in ["。", ".", "\n\n", "\n", "，", ", ", " "]:
                pos = text.rfind(sep, start + NOTE_CHUNK_CHARS // 2, end)
                if pos != -1:
                    split_at = pos + len(sep)
                    break

            chunks.append(text[start:split_at])
            start = split_at

        return chunks

    def _merge_chunk_notes(self, title: str, chunk_results: List[str], add_toc: bool) -> str:
        """Merge chunk note results into a single document with sequential heading numbers."""
        merged_sections = []
        ai_summary = ""

        for result in chunk_results:
            lines = result.strip().split("\n")
            filtered = []
            in_summary = False
            summary_lines = []

            for line in lines:
                stripped = line.strip()
                if stripped.startswith("# ") and not stripped.startswith("## "):
                    continue
                if stripped.startswith("## AI 总结") or stripped.startswith("## AI总结"):
                    in_summary = True
                    continue
                if in_summary:
                    if stripped.startswith("## "):
                        in_summary = False
                        filtered.append(line)
                    else:
                        summary_lines.append(line)
                    continue
                filtered.append(line)

            merged_sections.append("\n".join(filtered).strip())
            if summary_lines:
                ai_summary = "\n".join(summary_lines).strip()

        body = "\n\n---\n\n".join(merged_sections)

        body = self._renumber_headings(body)

        if add_toc:
            toc = self._generate_toc(body)
            final = f"# {title}\n\n{toc}\n\n---\n\n{body}"
        else:
            final = f"# {title}\n\n{body}"

        if ai_summary:
            final += f"\n\n---\n\n## AI 总结\n\n{ai_summary}"

        return final

    @staticmethod
    def _renumber_headings(markdown: str) -> str:
        """Sequentially number ## headings and their ### sub-headings across the whole document."""
        lines = markdown.split("\n")
        result = []
        h2_counter = 0
        h3_counter = 0

        strip_num = re.compile(r"^(#{2,3}\s+)(?:第?[一二三四五六七八九十\d]+[部章节]分?[：:\s]*|[\d]+(?:[.、．][\d]+)*[.、．\s]\s*)")

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("## ") and not stripped.startswith("### "):
                h2_counter += 1
                h3_counter = 0
                cleaned = strip_num.sub(r"\1", line)
                heading_text = cleaned.lstrip("#").strip()
                result.append(f"## {h2_counter}. {heading_text}")
            elif stripped.startswith("### "):
                h3_counter += 1
                cleaned = strip_num.sub(r"\1", line)
                heading_text = cleaned.lstrip("#").strip()
                result.append(f"### {h2_counter}.{h3_counter} {heading_text}")
            else:
                result.append(line)

        return "\n".join(result)

    def _generate_toc(self, markdown: str) -> str:
        """Generate a table of contents from ## headings in markdown."""
        toc_lines = ["## 目录\n"]
        slug_counts: dict[str, int] = {}
        for match in re.finditer(r"^(#{2,3})\s+(.+)$", markdown, re.MULTILINE):
            level = len(match.group(1))
            heading = match.group(2).strip()
            anchor = self._github_slug(heading, slug_counts)
            indent = "  " * (level - 2)
            toc_lines.append(f"{indent}- [{heading}](#{anchor})")
        return "\n".join(toc_lines)

    @staticmethod
    def _github_slug(text: str, counts: dict[str, int]) -> str:
        """Replicate github-slugger's algorithm used by rehype-slug."""
        slug = text.lower()
        slug = re.sub(r"[^\w\u4e00-\u9fff\u3400-\u4dbf\U00020000-\U0002a6df\s-]", "", slug, flags=re.UNICODE)
        slug = slug.strip().replace(" ", "-")
        slug = re.sub(r"-+", "-", slug)
        base = slug
        n = counts.get(base, 0)
        if n > 0:
            slug = f"{base}-{n}"
        counts[base] = n + 1
        return slug

    @retry(
        stop=stop_after_attempt(MAX_RETRIES),
        wait=wait_exponential(multiplier=2, min=1, max=60),
        reraise=True,
    )
    def _call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        progress_callback=None,
    ) -> str:
        """Call the LLM with retry and optional streaming progress."""
        params = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.4,
        }

        if progress_callback:
            stream = self.client.chat.completions.create(**params, stream=True)
            collected = []
            char_count = 0
            finish_reason = None
            for chunk in stream:
                choice = chunk.choices[0]
                if choice.delta.content:
                    collected.append(choice.delta.content)
                    char_count += len(choice.delta.content)
                    partial_text = "".join(collected)
                    progress_callback(char_count, partial_text)
                if choice.finish_reason:
                    finish_reason = choice.finish_reason
            result = "".join(collected)
            if finish_reason and finish_reason != "stop":
                logger.warning(f"LLM stream ended with finish_reason={finish_reason} ({len(result)} chars)")
        else:
            response = self.client.chat.completions.create(**params)
            result = response.choices[0].message.content or ""
            finish_reason = response.choices[0].finish_reason
            if finish_reason and finish_reason != "stop":
                logger.warning(f"LLM response finish_reason={finish_reason} ({len(result)} chars)")
            if hasattr(response, "usage") and response.usage:
                logger.info(
                    f"Token usage: prompt={response.usage.prompt_tokens}, "
                    f"completion={response.usage.completion_tokens}, "
                    f"total={response.usage.total_tokens}"
                )

        result = self._clean_markdown(result)
        logger.info(f"Note generated: {len(result)} chars")
        return result

    @staticmethod
    def _clean_markdown(text: str) -> str:
        """Strip code fence wrappers that LLMs sometimes add despite instructions."""
        stripped = text.strip()
        if stripped.startswith("```"):
            first_newline = stripped.find("\n")
            if first_newline != -1:
                stripped = stripped[first_newline + 1:]
        if stripped.endswith("```"):
            stripped = stripped[:-3]
        return stripped.strip()


_note_summarizer: Optional[NoteSummarizer] = None


def get_note_summarizer(model: str = "") -> NoteSummarizer:
    """Get or create a NoteSummarizer instance, reusing the existing LLM config."""
    global _note_summarizer
    if model:
        return NoteSummarizer(model=model)
    if _note_summarizer is None:
        _note_summarizer = NoteSummarizer()
    return _note_summarizer


def get_available_styles() -> dict:
    """Return all available note styles with their display names."""
    return {k: v["name"] for k, v in NOTE_STYLES.items()}
