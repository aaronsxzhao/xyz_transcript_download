"""Public, fixed-label summary errors without provider response content."""
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
