# coding: utf-8
"""
claude_client.py
Thin wrapper around the Anthropic Claude API used by all review agents.
Provides the same chat() interface as OCIGenAIClient so the agents are
provider-agnostic.
"""

import logging
import os
import time
from datetime import datetime

import anthropic
from logger import get_logger
from config import runtime_config

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Dedicated call logger (prompt + response → separate log file)
# ---------------------------------------------------------------------------
_LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(_LOG_DIR, exist_ok=True)

_claude_call_log = logging.getLogger("claude_calls")
_claude_call_log.setLevel(logging.DEBUG)
_claude_call_log.propagate = False

_claude_call_file = os.path.join(
    _LOG_DIR, f"claude_calls_{datetime.now().strftime('%Y-%m-%d')}.log"
)
_fh = logging.FileHandler(_claude_call_file, encoding="utf-8")
_fh.setFormatter(
    logging.Formatter("%(asctime)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
)
_claude_call_log.addHandler(_fh)

_call_counter: int = 0

# Default Claude model
CLAUDE_MODEL = "claude-sonnet-4-6"
CLAUDE_MAX_TOKENS = 8096
CLAUDE_MAX_RETRIES = 5
CLAUDE_RETRY_BASE_DELAY = 5  # seconds; exponential back-off


class ClaudeClient:
    """Reusable client for Anthropic Claude chat completions."""

    def __init__(self):
        log.info("Initialising Anthropic Claude client …")
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. "
                "Add it to the .env file or your environment variables."
            )
        self._client = anthropic.Anthropic(api_key=api_key)
        log.info("Claude client ready (model=%s).", CLAUDE_MODEL)

    def chat(self, prompt: str) -> str:
        """
        Send a single-turn message to Claude and return the response text.

        Args:
            prompt: The full prompt to send to the model.

        Returns:
            The model's response as a plain string.

        Raises:
            RuntimeError: If the Claude API call fails after all retries.
        """
        global _call_counter
        _call_counter += 1
        call_id = _call_counter

        log.debug(
            "Sending prompt to Claude (length=%d chars, call_id=%d) …",
            len(prompt), call_id,
        )

        _claude_call_log.debug(
            "\n" + "=" * 80 + "\n"
            "CLAUDE CALL #%d  START  |  %s\n" + "=" * 80 + "\n"
            "%s\n" + "-" * 80,
            call_id,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            prompt,
        )

        last_exc: Exception | None = None

        for attempt in range(1, CLAUDE_MAX_RETRIES + 1):
            try:
                message = self._client.messages.create(
                    model=CLAUDE_MODEL,
                    max_tokens=CLAUDE_MAX_TOKENS,
                    messages=[{"role": "user", "content": prompt}],
                )

                result = ""
                for block in message.content:
                    if hasattr(block, "text"):
                        result += block.text

                log.debug(
                    "Claude response received (length=%d chars, call_id=%d).",
                    len(result), call_id,
                )

                _claude_call_log.debug(
                    "CLAUDE CALL #%d  RESPONSE  |  %s\n"
                    + "-" * 80 + "\n"
                    "%s\n" + "=" * 80,
                    call_id,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    result,
                )

                return result

            except anthropic.RateLimitError as exc:
                last_exc = exc
                if attempt < CLAUDE_MAX_RETRIES:
                    delay = CLAUDE_RETRY_BASE_DELAY * (2 ** (attempt - 1))
                    log.warning(
                        "Claude rate limit hit on call #%d attempt %d/%d. "
                        "Waiting %ds before retry …",
                        call_id, attempt, CLAUDE_MAX_RETRIES, delay,
                    )
                    time.sleep(delay)
                    continue
                raise RuntimeError(
                    f"Claude rate limit persisted after {CLAUDE_MAX_RETRIES} retries: {exc}"
                ) from exc

            except anthropic.APIStatusError as exc:
                log.error(
                    "Claude API error on call #%d: HTTP %s — %s",
                    call_id, exc.status_code, exc.message,
                )
                raise RuntimeError(
                    f"Claude APIStatusError {exc.status_code}: {exc.message}"
                ) from exc

            except Exception as exc:
                exc_str = str(exc)
                is_transient = any(
                    kw in exc_str
                    for kw in (
                        "ConnectionError", "TimeoutError", "RemoteDisconnected",
                        "EOF occurred", "Connection reset", "SSLError",
                    )
                )
                if is_transient and attempt < CLAUDE_MAX_RETRIES:
                    last_exc = exc
                    delay = CLAUDE_RETRY_BASE_DELAY * (2 ** (attempt - 1))
                    log.warning(
                        "Transient network error on Claude call #%d attempt %d/%d: %s. "
                        "Waiting %ds …",
                        call_id, attempt, CLAUDE_MAX_RETRIES, exc, delay,
                    )
                    time.sleep(delay)
                    continue
                log.error(
                    "Unexpected error during Claude call #%d: %s", call_id, exc
                )
                raise RuntimeError(f"Claude call failed: {exc}") from exc

        raise RuntimeError(
            f"Claude call #{call_id} failed after {CLAUDE_MAX_RETRIES} retries: {last_exc}"
        ) from last_exc


# ---------------------------------------------------------------------------
# Quick connectivity test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    client = ClaudeClient()
    reply = client.chat("Say 'Claude connection successful' and nothing else.")
    print("Claude Test Response:", reply)
