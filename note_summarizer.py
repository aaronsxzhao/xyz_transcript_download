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
    SUMMARIZER_MAX_OUTPUT_TOKENS,
)
from summarizer import extract_json_from_response
from logger import get_logger

logger = get_logger("note_summarizer")

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


def _build_system_prompt(style: str, formats: List[str]) -> str:
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
        format_instructions.append(
            "在适当位置插入截图标记，格式为 `*Screenshot-[mm:ss]`，"
            "其中 mm:ss 是建议截取的视频时间戳。每个主要段落可插入1-2个截图标记。"
        )
    if "summary" in formats:
        format_instructions.append(
            "在笔记最后添加一个 `## AI 总结` 段落，用3-5句话概括视频的核心观点和价值。"
        )

    format_text = "\n".join(f"- {inst}" for inst in format_instructions) if format_instructions else ""

    return f"""你是一个专业的视频内容笔记助手。你的任务是根据视频的转录文本（和可选的视觉分析）生成高质量的 Markdown 格式笔记。

风格要求:
{style_instruction}

格式要求:
{format_text if format_text else "- 使用标准 Markdown 格式，结构清晰"}

通用规则:
- 使用中文撰写笔记
- 使用 Markdown 格式，包括标题 (##)、列表、引用块等
- 支持 LaTeX 数学公式（使用 $...$ 和 $$...$$）
- 保持逻辑清晰、层次分明
- 确保内容准确，不要编造视频中没有的信息
- 按照视频时间顺序组织内容
- 如果视频涉及代码，使用代码块展示"""


def _build_user_prompt(
    title: str,
    transcript_text: str,
    visual_context: str = "",
    tags: List[str] = None,
    extras: str = "",
) -> str:
    """Build the user prompt with video content."""
    parts = [f"## 视频标题\n{title}\n"]

    if tags:
        parts.append(f"## 标签\n{', '.join(tags)}\n")

    if visual_context:
        parts.append(f"## 视觉分析\n{visual_context}\n")

    parts.append(f"## 转录文本\n{transcript_text}\n")

    if extras:
        parts.append(f"## 额外要求\n{extras}\n")

    parts.append("请根据以上内容生成笔记。直接输出 Markdown 格式的笔记内容，不要用代码块包裹。")

    return "\n".join(parts)


class NoteSummarizer:
    """Generates Markdown notes from video transcripts with configurable styles."""

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "",
        model: str = "",
        max_output_tokens: int = 0,
    ):
        self.api_key = api_key or LLM_API_KEY
        self.base_url = base_url or LLM_BASE_URL
        self.model = model or LLM_MODEL
        self.max_output_tokens = max_output_tokens or SUMMARIZER_MAX_OUTPUT_TOKENS

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
    ) -> Optional[str]:
        """
        Generate a Markdown note from a transcript.

        Args:
            title: Video title.
            transcript_text: Full transcript text.
            style: Note style key (one of NOTE_STYLES).
            formats: List of format options ("toc", "link", "screenshot", "summary").
            visual_context: Optional visual analysis text.
            tags: Optional list of tags.
            extras: Optional extra instructions from user.
            progress_callback: Optional callback(chars_generated).

        Returns:
            Markdown string or None on failure.
        """
        if formats is None:
            formats = []

        system_prompt = _build_system_prompt(style, formats)
        user_prompt = _build_user_prompt(title, transcript_text, visual_context, tags, extras)

        try:
            logger.info(
                f"Generating note: style={style}, formats={formats}, "
                f"transcript={len(transcript_text)} chars"
            )
            return self._call_llm(system_prompt, user_prompt, progress_callback)
        except Exception as e:
            logger.error(f"Note generation failed: {e}")
            return None

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
            "max_tokens": self.max_output_tokens,
        }

        if progress_callback:
            stream = self.client.chat.completions.create(**params, stream=True)
            collected = []
            char_count = 0
            for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    collected.append(delta)
                    char_count += len(delta)
                    progress_callback(char_count)
            result = "".join(collected)
        else:
            response = self.client.chat.completions.create(**params)
            result = response.choices[0].message.content or ""

        logger.info(f"Note generated: {len(result)} chars")
        return result


_note_summarizer: Optional[NoteSummarizer] = None


def get_note_summarizer(
    model: str = "",
    max_output_tokens: int = 0,
) -> NoteSummarizer:
    """Get or create a NoteSummarizer instance, reusing the existing LLM config."""
    global _note_summarizer
    if model or max_output_tokens:
        return NoteSummarizer(model=model, max_output_tokens=max_output_tokens)
    if _note_summarizer is None:
        _note_summarizer = NoteSummarizer()
    return _note_summarizer


def get_available_styles() -> dict:
    """Return all available note styles with their display names."""
    return {k: v["name"] for k, v in NOTE_STYLES.items()}
