"""Public, fixed-label summary errors without provider response content."""
DELIVERY_WARNING = "> ⚠️ 部分生成或内容核对未完成，先提供可用结果。未总结的分段会标为原始转写，请结合 Transcript 阅读。"


GENERATION_WARNING = "> ⚠️ 部分分段未能生成摘要，已保留原始转写；请结合 Transcript 阅读。"
AUDIT_WARNING = "> ℹ️ 摘要已生成，但全文覆盖核对未完成；完整性尚未验证，可对照 Transcript 阅读。"
COVERAGE_GAP_WARNING = "> ℹ️ 核对提示部分内容可能未覆盖，已附对应原文供对照阅读。"
FORMAT_WARNING = "> ℹ️ 生成内容已保留，但未能完整整理为结构化格式。"
MERGE_WARNING = "> ℹ️ 各分段正文已保留，但全文概览未能合并。"
PROVENANCE_WARNING = "> ℹ️ 部分截图引用未通过来源校验，已跳过对应截图。"
_EN_NOTICES = {
    'generation': "> ⚠️ Some sections could not be summarized and are included as original transcript. See Transcript for the full source.",
    'audit': "> ℹ️ Notes were generated, but the full-source coverage review did not complete. Completeness is unverified; compare with Transcript.",
    'coverage_gap': "> ℹ️ The review flagged potentially uncovered content. Corresponding source passages are included for comparison.",
    'format': "> ℹ️ Generated content is preserved, but could not be fully organized into structured fields.",
    'merge': "> ℹ️ All available section notes are preserved, but the episode overview could not be merged.",
    'provenance': "> ℹ️ Some screenshot references failed source validation and were skipped.",
}
_NOTICES = (DELIVERY_WARNING, GENERATION_WARNING, AUDIT_WARNING, COVERAGE_GAP_WARNING, FORMAT_WARNING, MERGE_WARNING, PROVENANCE_WARNING, *_EN_NOTICES.values())


def delivery_notice(text: str, reason: str = 'generation', source: str = '') -> str:
    from reading_language import chinese_source
    chinese = not source or chinese_source(source)
    notice = ({'generation': GENERATION_WARNING, 'audit': AUDIT_WARNING, 'coverage_gap': COVERAGE_GAP_WARNING, 'format': FORMAT_WARNING, 'merge': MERGE_WARNING, 'provenance': PROVENANCE_WARNING}[reason]
              if chinese else _EN_NOTICES[reason])
    return text if notice in text else notice + "\n\n" + text


def _leading_notices(text: str):
    notices = []
    while True:
        body = text.lstrip('\r\n')
        notice = next((value for value in _NOTICES if body == value or body.startswith(value + '\n')), None)
        if notice is None:
            return notices, text.strip('\r\n')
        notices.append(notice)
        text = body[len(notice):]


def strip_delivery_notices(text: str) -> str:
    # Remove generated prefixes only; quotations/code in the body are source.
    return _leading_notices(text)[1]


def merge_delivery_notices(text: str, sources) -> str:
    notices = list(dict.fromkeys(notice for source in sources for notice in _leading_notices(source)[0]))
    return "\n\n".join([*notices, strip_delivery_notices(text)]) if notices else text


def is_cancellation(error: Exception) -> bool:
    return isinstance(error, ProcessingCancelledError) or "cancel" in type(error).__name__.lower()


class ProcessingCancelledError(Exception):
    """A requested stop must propagate without provider retries."""


class SummaryOutputError(RuntimeError):
    MESSAGES = {
        'coverage': 'The source coverage check could not be verified. The previous note was kept. Please retry generation.',
        'length': 'The model reached its summary output limit. Please retry summary generation.',
        'empty': 'The model returned an empty summary. Please retry summary generation.',
        'invalid': 'The model returned an invalid summary format. Please retry summary generation.',
        'content_filter': 'The model declined to generate this summary. Try another summary model.',
        'capacity': 'The full transcript exceeds the model context capacity. Choose segmented generation or a larger-context model, then retry.',
    }
    def __init__(self, code):
        self.code = code if code in self.MESSAGES else 'invalid'
        super().__init__(self.MESSAGES[self.code])
