"""Public, fixed-label summary errors without provider response content."""
DELIVERY_WARNING = "> ⚠️ 部分生成或内容核对未完成，先提供可用结果。未总结的分段会标为原始转写，请结合 Transcript 阅读。"


def delivery_notice(text: str) -> str:
    return text if DELIVERY_WARNING in text else DELIVERY_WARNING + "\n\n" + text


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
    }
    def __init__(self, code):
        self.code = code if code in self.MESSAGES else 'invalid'
        super().__init__(self.MESSAGES[self.code])
