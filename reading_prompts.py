"""Shared meaning contract with language-specific reader presentation templates."""
from reading_language import source_language, source_language_lock

ARGUMENT_CONTRACT = """
INFORMATION ARCHITECTURE:
The entry layer extracts the source's central answers, not a list of things the
speaker mentioned. Each conclusion states a claim and its decisive reason or
condition. No generic advice or invented thesis. The detailed layer retains all
distinct source information, organized around arguments rather than utterances.
For each argument connect the claim, stated mechanism, evidence/examples and
limits/disagreements WHERE PRESENT. An example supports its argument; it is not
automatically another main point. Merge synonymous claims and keep every added
qualification. Avoid 'the speaker then discussed...' narration as the main text.
Do not repeat the introduction, table rows or the same conclusion in every section.
Preserve meaningful source headings. Adapt to the material: preserve steps in a
tutorial, opposing positions in a debate, uncertainty in a forecast, and chronology
in a story/video. Do not force an argumentative template onto unrelated material.
Full coverage means every distinct substantive detail remains accessible, NOT
that every sentence must be paraphrased. Exclude pure promotions and greetings
from core conclusions. Source quotations remain verbatim, separate from synthesis.
"""

PRESENTATION = {
    'en': """READER TEMPLATE (English):
Start the introduction with ### Key conclusions: focused, source-grounded answers
to the central question, including the decisive limitation when stated.
Then ### Episode overview: a brief map of the questions and how they connect.
Detailed chapters carry the evidence, examples, numbers and all other distinct
details. Use specific claim headings, connected paragraphs and sparse **bold**.
Use tables only for real comparisons and lists for parallel items or steps.
Keep metadata JSON keys in English; every generated value/heading is English.
Example point: #### Lower cost depends on order size\n\nThe second prototype
costs less only at the stated order size. Its durability remains untested.
""",
    'zh': """阅读模板（中文）：
开篇用 ### 核心结论，提炼原文对核心问题的回答，并交代决定性条件；
随后用 ### 节目概览，简要说明问题及论证关系，不逐项复述正文。
详细章节完整保留论据、案例、数字及其单位和条件，以及其他独立信息。
小标题表达具体观点，段落组织论证，少量加粗突出重点；比较用表格，步骤和并列项用列表。
JSON 字段名保持英文，生成的字段值、标题、说明统一中文，原话及专有名词保留原样。
要点示例：#### 成本下降取决于订购数量\n\n第二版原型只在指定订购量下更便宜，
耐久性尚未验证。原文没有说明的原因不自行补充。
""",
}


def editorial_prompt(source):
    language = source_language(source)
    template=PRESENTATION.get(language, '''Use the original speech language for
all generated prose and headings. Present core conclusions, a brief overview,
then detailed chapters with evidence and conditions. JSON keys stay unchanged.
Do not translate into English merely because these instructions are English.''')
    return ARGUMENT_CONTRACT + template + source_language_lock(source)


def podcast_prompt(base, source):
    # Remove Chinese example values from the English schema while sharing the
    # same fidelity/JSON contract. Templates cannot drift into different schemas.
    if source_language(source) != 'zh':
        base = base.replace('核心结论', 'Key conclusions').replace('节目概览', 'Episode overview')
    return base + editorial_prompt(source)


STYLE_EN = {
    'minimal': 'Compact layout and direct prose; retain every distinct detail.',
    'detailed': 'Explain the central arguments with their evidence and conditions; retain full detail.',
    'academic': 'Formal register; distinguish claims, evidence and limitations.',
    'tutorial': 'Preserve genuine steps, prerequisites and cautions; invent no instructions.',
    'xiaohongshu': 'Conversational and shareable; use emojis sparingly without adding claims.',
    'life_journal': 'Warm reflective register; attribute reflections to their original speaker.',
    'task_oriented': 'Highlight stated actions and priorities; do not invent action advice.',
    'business': 'Professional register; preserve stated market arguments and their uncertainty.',
    'meeting_minutes': 'Distinguish discussion, actual decisions and stated follow-up actions.',
}


def video_prompt(style, formats, source, style_zh, duration=0):
    from source_coverage import SOURCE_FIDELITY
    chinese = source_language(source)=='zh'
    intro = ('根据转写及可选视觉资料生成 Markdown 阅读笔记。风格：'+style_zh
             if chinese else 'Create Markdown reading notes from the transcript and optional visual context. Style: '+STYLE_EN.get(style,STYLE_EN['detailed']))
    rules = """
Use exactly one # original title, ## chapters, ### argument subheadings. ATX
markers belong only at the beginning of a line. Separate blocks with blank lines.
Preserve code in fenced blocks with its language. Use plain text for simple
arithmetic, LaTeX only for genuine complex mathematics. Keep blockquotes verbatim.
VIDEO TIMELINE CONTRACT: Follow the original source sequence. Merge only adjacent
related discussion. A later return to a topic, book or example remains later.
Never move later steps into earlier chapters. Media anchors stay by their source
discussion, in order; historical dates in speech are not playback timestamps.
"""
    if 'toc' in formats: rules += '\nGenerate a linked Markdown table of contents.\n'
    if 'link' in formats: rules += '\nUse *Content-[mm:ss] only at explicit source timestamps; never estimate.\n'
    if 'screenshot' in formats:
        rules += '\nUse plain Screenshot-[MM:SS] at meaningful chart/demo/topic changes, selected ONLY from supplied source timestamps. No invented times, backticks or adjacent duplicate screenshots. If no timestamps exist, omit markers.\n'
    if 'summary' in formats:
        rules += '\nAppend `## '+('AI 总结' if chinese else 'AI Summary')+'` with distinct core insights and decisive conditions, not another list of chapter topics.\n'
    # Video has ONE optional entry layer (AI Summary), moved before the detailed
    # chapters by the renderer. Do not also request the podcast introduction:
    # extraction chunks would otherwise repeat conclusions before every chapter.
    return SOURCE_FIDELITY + intro + rules + ARGUMENT_CONTRACT + source_language_lock(source)
