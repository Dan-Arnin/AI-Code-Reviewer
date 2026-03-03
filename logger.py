# coding: utf-8
"""
logger.py
Centralized logging for the OCI Gen AI Code Review System.

Features:
  - Console handler  : colored output by level (INFO → ✅, WARNING → ⚠, ERROR → ✗)
  - File handler     : full structured logs written to logs/code_reviewer_<date>.log
  - One call to get_logger() returns a pre-configured logger for any module.

Usage:
    from logger import get_logger
    log = get_logger(__name__)

    log.info("Cloning repository …")
    log.warning("Diff is very large; chunking into %d pieces", n)
    log.error("OCI call failed: %s", exc)
"""

import logging
import os
import sys
from datetime import datetime

# ---------------------------------------------------------------------------
# ANSI colour codes (console only)
# ---------------------------------------------------------------------------
_RESET  = "\033[0m"
_BOLD   = "\033[1m"
_GREY   = "\033[90m"
_CYAN   = "\033[96m"
_GREEN  = "\033[92m"
_YELLOW = "\033[93m"
_RED    = "\033[91m"
_BRED   = "\033[1;91m"   # bold red

_LEVEL_COLOURS = {
    logging.DEBUG:    _GREY,
    logging.INFO:     _GREEN,
    logging.WARNING:  _YELLOW,
    logging.ERROR:    _RED,
    logging.CRITICAL: _BRED,
}

_LEVEL_ICONS = {
    logging.DEBUG:    "·",
    logging.INFO:     "✓",
    logging.WARNING:  "⚠",
    logging.ERROR:    "✗",
    logging.CRITICAL: "✗✗",
}


# ---------------------------------------------------------------------------
# Custom formatters
# ---------------------------------------------------------------------------

class ConsoleFormatter(logging.Formatter):
    """Coloured, human-friendly console output."""

    FMT = "{colour}{icon} [{name}] {msg}{reset}"

    def format(self, record: logging.LogRecord) -> str:
        colour = _LEVEL_COLOURS.get(record.levelno, "")
        icon   = _LEVEL_ICONS.get(record.levelno, "-")
        # Shorten the logger name to the last segment (e.g. "agents.base_agent" → "base_agent")
        short_name = record.name.split(".")[-1]
        msg = super().format(record)
        return f"{colour}{icon} [{short_name}] {record.getMessage()}{_RESET}"


class FileFormatter(logging.Formatter):
    """Structured, machine-readable file output."""

    FMT = "%(asctime)s | %(levelname)-8s | %(name)-30s | %(message)s"
    DATEFMT = "%Y-%m-%d %H:%M:%S"

    def __init__(self):
        super().__init__(fmt=self.FMT, datefmt=self.DATEFMT)


# ---------------------------------------------------------------------------
# Module-level setup (runs once)
# ---------------------------------------------------------------------------

def _setup_root_logger() -> None:
    """Configure the root logger with console + file handlers."""
    root = logging.getLogger("code_reviewer")
    if root.handlers:
        return  # Already configured (e.g. in tests)

    root.setLevel(logging.DEBUG)

    # ── Console handler (INFO and above) ──────────────────────────────────
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(ConsoleFormatter())
    root.addHandler(console)

    # ── File handler (DEBUG and above) ────────────────────────────────────
    log_dir = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "logs"
    )
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(
        log_dir, f"code_reviewer_{datetime.now().strftime('%Y-%m-%d')}.log"
    )
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(FileFormatter())
    root.addHandler(file_handler)

    root.info("Logging initialised → %s", log_file)


_setup_root_logger()


def get_logger(name: str) -> logging.Logger:
    """
    Return a logger scoped under the 'code_reviewer' namespace.

    Args:
        name: Typically ``__name__`` of the calling module.

    Returns:
        A configured :class:`logging.Logger`.
    """
    # Strip leading package path so names stay clean
    short = name.replace("agents.", "").strip(".")
    return logging.getLogger(f"code_reviewer.{short}")
