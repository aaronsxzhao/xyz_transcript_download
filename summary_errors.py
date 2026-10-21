"""Public, fixed-label summary errors without provider response content."""
class SummaryOutputError(RuntimeError):
    MESSAGES = {
        'length': 'The model reached its summary output limit. Your transcript is saved; retry summary generation.',
        'empty': 'The model returned an empty summary. Your transcript is saved; retry summary generation.',
        'invalid': 'The model returned an invalid summary format. Your transcript is saved; retry summary generation.',
        'content_filter': 'The model declined to generate this summary. Try another summary model.',
    }
    def __init__(self, code):
        self.code = code if code in self.MESSAGES else 'invalid'
        super().__init__(self.MESSAGES[self.code])
