"""
Retry utilities using tenacity for resilient API calls.
"""

import logging
from typing import Tuple, Type

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
    after_log,
)
import requests

from config import MAX_RETRIES, RETRY_BACKOFF, REQUEST_TIMEOUT_CONNECT, REQUEST_TIMEOUT_READ


# Get logger
logger = logging.getLogger("xyz.retry")


# Exceptions that should trigger a retry
RETRYABLE_EXCEPTIONS: Tuple[Type[Exception], ...] = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    requests.exceptions.ChunkedEncodingError,
)


def is_retryable_status_code(response: requests.Response) -> bool:
    """Check if response status code warrants a retry."""
    return response.status_code in [429, 500, 502, 503, 504]


def create_retry_decorator(
    max_attempts: int = MAX_RETRIES,
    backoff_factor: int = RETRY_BACKOFF,
):
    """
    Create a retry decorator with configurable settings.
    
    Args:
        max_attempts: Maximum number of retry attempts
        backoff_factor: Exponential backoff multiplier
        
    Returns:
        Configured retry decorator
    """
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=backoff_factor, min=1, max=60),
        retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        after=after_log(logger, logging.DEBUG),
        reraise=True,
    )


# Default retry decorator
default_retry = create_retry_decorator()


def get_request_timeout() -> Tuple[int, int]:
    """Get the default request timeout tuple (connect, read)."""
    return (REQUEST_TIMEOUT_CONNECT, REQUEST_TIMEOUT_READ)


class RetryableSession:
    """A requests session with built-in retry logic."""
    
    def __init__(self, headers: dict = None):
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
        
        self.session = requests.Session()
        if headers:
            self.session.headers.update(headers)
        
        # Configure retry strategy
        retry_strategy = Retry(
            total=MAX_RETRIES,
            backoff_factor=RETRY_BACKOFF,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "POST", "PUT", "DELETE"],
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
    
    def get(self, url: str, **kwargs) -> requests.Response:
        """GET request with timeout."""
        kwargs.setdefault("timeout", get_request_timeout())
        return self.session.get(url, **kwargs)
    
    def post(self, url: str, **kwargs) -> requests.Response:
        """POST request with timeout."""
        kwargs.setdefault("timeout", get_request_timeout())
        return self.session.post(url, **kwargs)
    
    def head(self, url: str, **kwargs) -> requests.Response:
        """HEAD request with timeout."""
        kwargs.setdefault("timeout", get_request_timeout())
        return self.session.head(url, **kwargs)
