"""
Centralized logging configuration for the Xiaoyuzhou podcast tool.
Provides structured logging with console, file, and Discord webhook output.
"""

import logging
import sys
import threading
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional
import json

import requests

from config import DATA_DIR, DISCORD_WEBHOOK_URL


# Create logs directory
LOGS_DIR = DATA_DIR / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)


class ColoredFormatter(logging.Formatter):
    """Formatter that adds colors to console output."""

    COLORS = {
        'DEBUG': '\033[36m',     # Cyan
        'INFO': '\033[32m',      # Green
        'WARNING': '\033[33m',   # Yellow
        'ERROR': '\033[31m',     # Red
        'CRITICAL': '\033[35m',  # Magenta
    }
    RESET = '\033[0m'
    SYMBOLS = {
        'DEBUG': '🔍',
        'INFO': '✓',
        'WARNING': '⚠',
        'ERROR': '✗',
        'CRITICAL': '💥',
    }

    def format(self, record):
        # Add color and symbol for console
        color = self.COLORS.get(record.levelname, '')
        symbol = self.SYMBOLS.get(record.levelname, '')
        
        # Format the message
        record.symbol = symbol
        record.color = color
        record.reset = self.RESET
        
        return super().format(record)


class DiscordWebhookHandler(logging.Handler):
    """
    Logging handler that sends log messages to a Discord webhook.
    Sends asynchronously to avoid blocking the main thread.
    """
    
    LEVEL_COLORS = {
        'DEBUG': 0x36393F,     # Gray
        'INFO': 0x3498DB,      # Blue
        'WARNING': 0xF39C12,   # Orange
        'ERROR': 0xE74C3C,     # Red
        'CRITICAL': 0x9B59B6,  # Purple
    }
    
    LEVEL_EMOJIS = {
        'DEBUG': '🔍',
        'INFO': 'ℹ️',
        'WARNING': '⚠️',
        'ERROR': '❌',
        'CRITICAL': '💥',
    }
    
    def __init__(self, webhook_url: str, level: int = logging.WARNING):
        super().__init__(level)
        self.webhook_url = webhook_url
        self._session = None
    
    @property
    def session(self):
        """Lazy-load requests session."""
        if self._session is None:
            self._session = requests.Session()
        return self._session
    
    def emit(self, record):
        """Send log record to Discord webhook asynchronously."""
        try:
            # Format the log message
            msg = self.format(record)
            
            # Build Discord embed
            embed = {
                "title": f"{self.LEVEL_EMOJIS.get(record.levelname, '📝')} {record.levelname}",
                "description": msg[:4000] if len(msg) > 4000 else msg,  # Discord limit
                "color": self.LEVEL_COLORS.get(record.levelname, 0x36393F),
                "fields": [
                    {"name": "Module", "value": record.name, "inline": True},
                    {"name": "Function", "value": record.funcName, "inline": True},
                ],
                "timestamp": datetime.utcnow().isoformat(),
                "footer": {"text": "Podcast Tool Logs"}
            }
            
            # Add exception info if present
            if record.exc_info:
                import traceback
                tb = ''.join(traceback.format_exception(*record.exc_info))
                if len(tb) > 1000:
                    tb = tb[:1000] + "..."
                embed["fields"].append({
                    "name": "Exception",
                    "value": f"```\n{tb}\n```",
                    "inline": False
                })
            
            payload = {
                "embeds": [embed]
            }
            
            # Send asynchronously to avoid blocking
            thread = threading.Thread(
                target=self._send_webhook,
                args=(payload,),
                daemon=True
            )
            thread.start()
            
        except Exception:
            self.handleError(record)
    
    def _send_webhook(self, payload: dict):
        """Actually send the webhook request."""
        try:
            self.session.post(
                self.webhook_url,
                json=payload,
                timeout=10
            )
        except Exception:
            pass  # Silently fail - don't want logging to crash the app


def setup_logging(
    level: str = "INFO",
    log_file: Optional[str] = None,
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
) -> logging.Logger:
    """
    Set up the logging configuration.
    
    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional log file name (defaults to xyz_{date}.log)
        max_bytes: Max size of log file before rotation
        backup_count: Number of backup files to keep
        
    Returns:
        Configured logger instance
    """
    # Get the root logger for our application
    logger = logging.getLogger("xyz")
    
    # Only configure once
    if logger.handlers:
        return logger
    
    # Set log level
    log_level = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(log_level)
    
    # Console handler with colors
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_format = ColoredFormatter(
        "%(color)s%(symbol)s %(message)s%(reset)s"
    )
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)
    
    # File handler with rotation
    if log_file is None:
        log_file = f"xyz_{datetime.now().strftime('%Y%m%d')}.log"
    
    log_path = LOGS_DIR / log_file
    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)  # Log everything to file
    file_format = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_format)
    logger.addHandler(file_handler)
    
    # Discord webhook handler (for warnings and errors)
    if DISCORD_WEBHOOK_URL:
        discord_handler = DiscordWebhookHandler(
            webhook_url=DISCORD_WEBHOOK_URL,
            level=logging.WARNING  # Only send warnings and above
        )
        discord_format = logging.Formatter(
            "**%(name)s** in `%(funcName)s` (line %(lineno)d)\n%(message)s"
        )
        discord_handler.setFormatter(discord_format)
        logger.addHandler(discord_handler)
    
    # Prevent propagation to root logger
    logger.propagate = False
    
    return logger


def get_logger(name: str = "xyz") -> logging.Logger:
    """
    Get a logger instance.
    
    Args:
        name: Logger name (will be prefixed with 'xyz.')
        
    Returns:
        Logger instance
    """
    if name == "xyz":
        logger = logging.getLogger(name)
    else:
        logger = logging.getLogger(f"xyz.{name}")
    
    # Ensure root logger is configured
    if not logging.getLogger("xyz").handlers:
        setup_logging()
    
    return logger


# Convenience functions for quick logging
def debug(msg: str, *args, **kwargs):
    """Log a debug message."""
    get_logger().debug(msg, *args, **kwargs)


def info(msg: str, *args, **kwargs):
    """Log an info message."""
    get_logger().info(msg, *args, **kwargs)


def warning(msg: str, *args, **kwargs):
    """Log a warning message."""
    get_logger().warning(msg, *args, **kwargs)


def error(msg: str, *args, **kwargs):
    """Log an error message."""
    get_logger().error(msg, *args, **kwargs)


def critical(msg: str, *args, **kwargs):
    """Log a critical message."""
    get_logger().critical(msg, *args, **kwargs)


def exception(msg: str, *args, **kwargs):
    """Log an exception with traceback."""
    get_logger().exception(msg, *args, **kwargs)


# =============================================================================
# Discord Event Notifications
# =============================================================================

class DiscordNotifier:
    """
    Send specific event notifications to Discord.
    Unlike the log handler, this sends notifications for specific events
    regardless of log level.
    """
    
    # Event types with their colors and emojis
    EVENT_TYPES = {
        "startup": {"color": 0x2ECC71, "emoji": "🚀"},      # Green - API started
        "shutdown": {"color": 0x95A5A6, "emoji": "🛑"},     # Gray - API stopped
        "success": {"color": 0x3498DB, "emoji": "✅"},      # Blue - Processing complete
        "transcript": {"color": 0x9B59B6, "emoji": "📝"},   # Purple - Transcript ready
        "summary": {"color": 0xE91E63, "emoji": "📋"},      # Pink - Summary ready
        "new_episode": {"color": 0x00BCD4, "emoji": "🎙️"},  # Cyan - New episode detected
        "health": {"color": 0xF39C12, "emoji": "💓"},       # Orange - Health status
        "info": {"color": 0x3498DB, "emoji": "ℹ️"},         # Blue - General info
    }
    
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url
        self._session = None
    
    @property
    def session(self):
        if self._session is None:
            self._session = requests.Session()
        return self._session
    
    def notify(
        self,
        title: str,
        message: str,
        event_type: str = "info",
        fields: Optional[list] = None,
        url: Optional[str] = None,
    ):
        """
        Send a notification to Discord.
        
        Args:
            title: Notification title
            message: Main message body
            event_type: One of: startup, shutdown, success, transcript, summary, 
                       new_episode, health, info
            fields: Optional list of {"name": str, "value": str, "inline": bool}
            url: Optional URL to link in the embed
        """
        if not self.webhook_url:
            return
        
        event_config = self.EVENT_TYPES.get(event_type, self.EVENT_TYPES["info"])
        
        embed = {
            "title": f"{event_config['emoji']} {title}",
            "description": message[:4000] if len(message) > 4000 else message,
            "color": event_config["color"],
            "timestamp": datetime.utcnow().isoformat(),
            "footer": {"text": "Podcast Tool"}
        }
        
        if fields:
            embed["fields"] = fields[:25]  # Discord limit
        
        if url:
            embed["url"] = url
        
        payload = {"embeds": [embed]}
        
        # Send asynchronously
        thread = threading.Thread(
            target=self._send,
            args=(payload,),
            daemon=True
        )
        thread.start()
    
    def _send(self, payload: dict):
        try:
            self.session.post(self.webhook_url, json=payload, timeout=10)
        except Exception:
            pass  # Silently fail


# Global notifier instance
_discord_notifier: Optional[DiscordNotifier] = None


def get_discord_notifier() -> Optional[DiscordNotifier]:
    """Get the Discord notifier instance (creates one if needed)."""
    global _discord_notifier
    if _discord_notifier is None and DISCORD_WEBHOOK_URL:
        _discord_notifier = DiscordNotifier(DISCORD_WEBHOOK_URL)
    return _discord_notifier


def notify_discord(
    title: str,
    message: str,
    event_type: str = "info",
    fields: Optional[list] = None,
    url: Optional[str] = None,
):
    """
    Send a Discord notification for important events.
    
    This is separate from logging - use this for specific events you want
    to always notify about, regardless of log level.
    
    Args:
        title: Notification title (e.g., "Processing Complete")
        message: Message body (e.g., "Episode 'My Podcast' has been transcribed")
        event_type: One of: startup, shutdown, success, transcript, summary, 
                   new_episode, health, info
        fields: Optional additional fields for the embed
        url: Optional URL to include
    
    Example:
        notify_discord(
            "Transcript Ready",
            "Episode 'Tech Talk #42' has been transcribed successfully",
            event_type="transcript",
            fields=[{"name": "Duration", "value": "45 min", "inline": True}]
        )
    """
    notifier = get_discord_notifier()
    if notifier:
        notifier.notify(title, message, event_type, fields, url)
