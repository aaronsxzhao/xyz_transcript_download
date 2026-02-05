"""
Custom log formatter that redacts sensitive data from access logs.
"""
import re
from uvicorn.logging import AccessFormatter


class RedactedAccessFormatter(AccessFormatter):
    """
    Custom access log formatter that redacts tokens from URLs.
    
    This prevents JWT tokens from appearing in server logs when
    passed as query parameters.
    """
    
    # Pattern to match token query parameter
    TOKEN_PATTERN = re.compile(r'token=[^&\s"]+')
    
    def formatMessage(self, record):
        # First get the standard formatted message
        message = super().formatMessage(record)
        
        # Redact any token parameters
        message = self.TOKEN_PATTERN.sub('token=[REDACTED]', message)
        
        return message
