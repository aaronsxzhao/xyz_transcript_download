"""
Authentication module for Xiaoyuzhou API.
Supports both public access and authenticated access for private content.
"""

import json
import time
from typing import Optional, Tuple

import requests

from config import (
    TOKENS_FILE,
    DEFAULT_HEADERS,
    DATA_DIR,
)
from logger import get_logger

logger = get_logger("auth")


def browser_login() -> bool:
    """
    Open a browser window for the user to log in and capture tokens.
    Returns True if tokens were captured successfully.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.warning("Playwright not installed. Installing now...")
        import subprocess
        subprocess.run(["pip", "install", "playwright"], check=True)
        subprocess.run(["playwright", "install", "chromium"], check=True)
        from playwright.sync_api import sync_playwright

    logger.info("Opening browser for login...")
    logger.info("Please log in to your 小宇宙 account.")
    logger.info("The window will close automatically after login.")

    tokens_captured = {"access": None, "refresh": None}

    try:
        with sync_playwright() as p:
            # Launch browser (visible to user)
            browser = p.chromium.launch(headless=False)
            context = browser.new_context()
            page = context.new_page()

            # Try xiaoyuzhoufm.com first, fall back to okjike.com
            page.goto("https://www.xiaoyuzhoufm.com/")
            
            # Wait a moment for any redirects
            time.sleep(2)

            logger.info("Waiting for login... (will timeout in 5 minutes)")
            logger.info("Tip: You can scan QR code with 小宇宙 App or use phone number")
            
            max_wait = 300  # 5 minutes
            waited = 0
            
            while waited < max_wait:
                cookies = context.cookies()
                
                for cookie in cookies:
                    if cookie["name"] == "x-jike-access-token":
                        tokens_captured["access"] = cookie["value"]
                    elif cookie["name"] == "x-jike-refresh-token":
                        tokens_captured["refresh"] = cookie["value"]
                
                if tokens_captured["access"] and tokens_captured["refresh"]:
                    logger.info("Login detected! Capturing tokens...")
                    time.sleep(1)  # Wait a moment to ensure cookies are fully set
                    break
                
                time.sleep(1)
                waited += 1

            browser.close()

    except Exception as e:
        logger.error(f"Browser error: {e}")
        return False

    if tokens_captured["access"] and tokens_captured["refresh"]:
        # Save tokens
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        tokens = {
            "x-jike-access-token": tokens_captured["access"],
            "x-jike-refresh-token": tokens_captured["refresh"],
        }
        with open(TOKENS_FILE, "w") as f:
            json.dump(tokens, f, indent=4)
        
        logger.info("Tokens saved successfully!")
        return True
    else:
        logger.warning("Login timed out or tokens not found.")
        return False


class SessionManager:
    """Manages HTTP session for Xiaoyuzhou requests with optional auth."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        self._authenticated = False

    def load_tokens(self) -> bool:
        """Load saved tokens if available."""
        if not TOKENS_FILE.exists():
            return False

        try:
            with open(TOKENS_FILE, "r") as f:
                tokens = json.load(f)
            
            if "x-jike-access-token" in tokens:
                self.session.headers["x-jike-access-token"] = tokens["x-jike-access-token"]
                if "x-jike-refresh-token" in tokens:
                    self.session.headers["x-jike-refresh-token"] = tokens["x-jike-refresh-token"]
                self._authenticated = True
                return True
        except (json.JSONDecodeError, IOError):
            pass

        return False

    def ensure_authenticated(self) -> bool:
        """Ensure we have valid authentication, prompting login if needed."""
        if self._authenticated:
            return True

        if self.load_tokens():
            return True

        # Prompt for login
        logger.warning("This content requires login.")
        response = input("Open browser to log in? (Y/n): ").strip().lower()
        
        if response != 'n':
            if browser_login():
                return self.load_tokens()
        
        return False

    def get_session(self) -> requests.Session:
        """Get the session for making requests."""
        return self.session

    @property
    def is_authenticated(self) -> bool:
        return self._authenticated


# Global session manager instance
_session_manager: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    """Get or create the global SessionManager instance."""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
        _session_manager.load_tokens()  # Try to load existing tokens
    return _session_manager
