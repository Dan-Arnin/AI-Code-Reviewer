# coding: utf-8
"""
oci_client.py
Thin wrapper around OCI Generative AI (GenericChatRequest) used by all agents.
"""

import logging
import os
import time
from datetime import datetime

import oci
from logger import get_logger
from config import (
    OCI_COMPARTMENT_ID, OCI_CONFIG_PROFILE, OCI_ENDPOINT,
    OCI_MODEL_ID, OCI_MAX_TOKENS, OCI_TEMPERATURE, OCI_TOP_P, OCI_TOP_K,
    runtime_config,
)

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Dedicated OCI call logger  (prompt + response → separate log file)
# ---------------------------------------------------------------------------
# This logger writes ONLY to logs/oci_calls_<date>.log so the full prompts
# and responses are always preserved but never pollute the console.

_LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(_LOG_DIR, exist_ok=True)

_oci_call_log = logging.getLogger("oci_calls")
_oci_call_log.setLevel(logging.DEBUG)
_oci_call_log.propagate = False   # don't bubble up to root / console

_oci_call_file = os.path.join(_LOG_DIR, f"oci_calls_{datetime.now().strftime('%Y-%m-%d')}.log")
_fh = logging.FileHandler(_oci_call_file, encoding="utf-8")
_fh.setFormatter(logging.Formatter("%(asctime)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
_oci_call_log.addHandler(_fh)

# Global call counter so each OCI call gets a unique ID in the log
_call_counter: int = 0


class OCIGenAIClient:
    """Reusable client for OCI Generative AI chat completions."""

    def __init__(self):
        log.info("Initialising OCI Generative AI client …")
        log.debug(
            "OCI config → profile=%s | endpoint=%s | model=%s",
            OCI_CONFIG_PROFILE, OCI_ENDPOINT, OCI_MODEL_ID,
        )
        try:
            config = oci.config.from_file("~/.oci/config", OCI_CONFIG_PROFILE)
        except Exception as exc:
            log.critical(
                "Failed to load OCI config from ~/.oci/config.\n"
                "  WHAT WENT WRONG : %s\n"
                "  WHAT TO DO      : Ensure ~/.oci/config exists and contains a valid "
                "[%s] profile with user, tenancy, region, key_file, and fingerprint fields. "
                "See https://docs.oracle.com/en-us/iaas/Content/API/Concepts/sdkconfig.htm",
                exc, OCI_CONFIG_PROFILE,
            )
            raise

        try:
            self._client = oci.generative_ai_inference.GenerativeAiInferenceClient(
                config=config,
                service_endpoint=OCI_ENDPOINT,
                retry_strategy=oci.retry.NoneRetryStrategy(),
                timeout=(10, 240),
            )
            self._compartment_id = OCI_COMPARTMENT_ID
            self._model_id = OCI_MODEL_ID
            log.info("OCI client ready.")
        except Exception as exc:
            log.critical(
                "Failed to create OCI GenerativeAiInferenceClient.\n"
                "  WHAT WENT WRONG : %s\n"
                "  WHAT TO DO      : Check that the OCI endpoint (%s) is reachable and "
                "that your API key has the GenerativeAI policy granted in compartment %s.",
                exc, OCI_ENDPOINT, OCI_COMPARTMENT_ID,
            )
            raise

    # Maximum number of retry attempts for transient errors (429, SSL, network)
    _MAX_RETRIES: int = 5
    _RETRY_BASE_DELAY_SECONDS: int = 5  # exponential back-off: 5s, 10s, 20s, 40s …

    def chat(self, prompt: str) -> str:
        """
        Send a single-turn chat message and return the response text.
        Model ID and compartment ID are resolved from runtime_config at call
        time so that Settings changes take effect without a server restart.

        Transient errors (HTTP 429 rate-limit, SSL/network MaxRetryError) are
        automatically retried up to _MAX_RETRIES times with a _RETRY_DELAY_SECONDS
        delay between attempts.

        Args:
            prompt: The full prompt to send to the model.

        Returns:
            The model's response as a plain string.

        Raises:
            RuntimeError: If the OCI API call fails after all retries.
        """
        log.debug("Sending prompt to OCI Gen AI (length=%d chars) …", len(prompt))

        # ── Log the full prompt to the OCI calls file ────────────────────────
        global _call_counter
        _call_counter += 1
        call_id = _call_counter
        _oci_call_log.debug(
            "\n" + "=" * 80 + "\n"
            "OCI CALL #%d  START  |  %s\n"
            + "=" * 80 + "\n"
            "%s\n"
            + "-" * 80,
            call_id,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            prompt,
        )
        log.debug("OCI Call #%d → prompt logged to %s", call_id, _oci_call_file)

        last_exc: Exception | None = None

        for attempt in range(1, self._MAX_RETRIES + 1):
            try:
                content = oci.generative_ai_inference.models.TextContent()
                content.text = prompt

                message = oci.generative_ai_inference.models.Message()
                message.role = "USER"
                message.content = [content]

                chat_request = oci.generative_ai_inference.models.GenericChatRequest()
                chat_request.api_format = (
                    oci.generative_ai_inference.models.BaseChatRequest.API_FORMAT_GENERIC
                )
                chat_request.messages = [message]
                chat_request.max_tokens = OCI_MAX_TOKENS
                chat_request.temperature = OCI_TEMPERATURE
                chat_request.top_p = OCI_TOP_P
                chat_request.top_k = OCI_TOP_K

                # Resolve model / compartment from runtime config (override if set)
                effective_model_id       = runtime_config.get("model_id",       self._model_id)
                effective_compartment_id = runtime_config.get("compartment_id", self._compartment_id)

                chat_detail = oci.generative_ai_inference.models.ChatDetails()
                chat_detail.serving_mode = (
                    oci.generative_ai_inference.models.OnDemandServingMode(
                        model_id=effective_model_id
                    )
                )
                chat_detail.chat_request = chat_request
                chat_detail.compartment_id = effective_compartment_id

                response = self._client.chat(chat_detail)

                # Navigate the response structure to extract text
                choices = response.data.chat_response.choices
                if not choices:
                    log.warning(
                        "OCI returned a response with no choices.\n"
                        "  WHAT WENT WRONG : The model returned an empty choices list.\n"
                        "  WHAT TO DO      : This is usually transient. Retry the review. "
                        "If it persists, check OCI service status at https://ocistatus.oraclecloud.com/"
                    )
                    return ""

                raw = choices[0].message.content
                if isinstance(raw, list):
                    result = "\n".join(
                        part.text for part in raw if hasattr(part, "text")
                    )
                else:
                    result = str(raw)

                log.debug("OCI response received (length=%d chars).", len(result))

                # ── Log the full response to the OCI calls file ──────────────────
                _oci_call_log.debug(
                    "OCI CALL #%d  RESPONSE  |  %s\n"
                    + "-" * 80 + "\n"
                    "%s\n"
                    + "=" * 80,
                    call_id,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    result,
                )
                log.debug("OCI Call #%d → response logged to %s", call_id, _oci_call_file)

                return result

            except oci.exceptions.ServiceError as exc:
                # 429 = rate limit → retryable
                if exc.status == 429:
                    last_exc = exc
                    if attempt < self._MAX_RETRIES:
                        delay = self._RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1))
                        log.warning(
                            "OCI rate limit hit (HTTP 429) on call #%d attempt %d/%d.\n"
                            "  WHAT TO DO : Waiting %ds before retry …",
                            call_id, attempt, self._MAX_RETRIES, delay,
                        )
                        time.sleep(delay)
                        continue
                    # Exhausted retries
                    log.error(
                        "OCI rate limit (HTTP 429) persisted after %d retries on call #%d.\n"
                        "  WHAT TO DO : Reduce concurrent requests or request a quota increase "
                        "in the OCI Console under Generative AI → Limits.",
                        self._MAX_RETRIES, call_id,
                    )
                    raise RuntimeError(
                        f"OCI ServiceError {exc.status} ({exc.code}): {exc.message}"
                    ) from exc

                # Other service errors are not retried
                log.error(
                    "OCI Service Error during chat call #%d.\n"
                    "  HTTP STATUS     : %s\n"
                    "  OCI ERROR CODE  : %s\n"
                    "  MESSAGE         : %s\n"
                    "  WHAT TO DO      : %s",
                    call_id, exc.status, exc.code, exc.message,
                    _oci_error_advice(exc.status, exc.code),
                )
                raise RuntimeError(
                    f"OCI ServiceError {exc.status} ({exc.code}): {exc.message}"
                ) from exc

            except Exception as exc:
                # Check if this is a retriable network/SSL error
                exc_str = str(exc)
                is_transient = any(kw in exc_str for kw in (
                    "MaxRetryError", "SSLError", "ConnectionError",
                    "TimeoutError", "UNEXPECTED_EOF", "RemoteDisconnected",
                    "EOF occurred", "Connection reset",
                ))

                if is_transient and attempt < self._MAX_RETRIES:
                    last_exc = exc
                    delay = self._RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1))
                    log.warning(
                        "Transient network/SSL error on OCI call #%d attempt %d/%d.\n"
                        "  WHAT WENT WRONG : %s\n"
                        "  WHAT TO DO      : Recycling OCI client connection pool and "
                        "waiting %ds before retry …",
                        call_id, attempt, self._MAX_RETRIES, exc, delay,
                    )
                    # ── Recreate the client so the stale SSL/TCP connection ──────
                    # pool is discarded. UNEXPECTED_EOF_WHILE_READING is almost
                    # always caused by the server closing a keep-alive connection
                    # that urllib3 was still holding open.
                    try:
                        config = oci.config.from_file("~/.oci/config", OCI_CONFIG_PROFILE)
                        self._client = oci.generative_ai_inference.GenerativeAiInferenceClient(
                            config=config,
                            service_endpoint=OCI_ENDPOINT,
                            retry_strategy=oci.retry.NoneRetryStrategy(),
                            timeout=(10, 240),
                        )
                        log.debug("OCI client recycled for call #%d retry %d.", call_id, attempt + 1)
                    except Exception as reinit_exc:
                        log.warning("Failed to recycle OCI client: %s — will retry with existing client.", reinit_exc)
                    time.sleep(delay)
                    continue

                log.error(
                    "Unexpected error during OCI chat call #%d (attempt %d/%d).\n"
                    "  WHAT WENT WRONG : %s\n"
                    "  WHAT TO DO      : Check your network connection, OCI credentials, "
                    "and that the endpoint %s is reachable.",
                    call_id, attempt, self._MAX_RETRIES, exc, OCI_ENDPOINT,
                )
                raise RuntimeError(f"OCI call failed: {exc}") from exc

        # Should not be reached, but guard against it
        raise RuntimeError(f"OCI call #{call_id} failed after {self._MAX_RETRIES} retries: {last_exc}") from last_exc


def _oci_error_advice(status: int, code: str) -> str:
    """Return a human-readable remediation hint for common OCI error codes."""
    advice = {
        400: "The request was malformed. Check that the model ID and compartment ID are correct.",
        401: "Authentication failed. Verify your OCI API key, fingerprint, and config profile.",
        403: "Authorisation denied. Ensure your OCI user/group has the GenerativeAI policy "
             "('Allow group <g> to use generative-ai-family in compartment <c>').",
        404: "Resource not found. Check that the model OCID and endpoint URL are correct.",
        429: "Rate limit exceeded. Wait a moment and retry, or request a quota increase.",
        500: "OCI internal server error. This is a service-side issue; retry in a few minutes.",
        503: "OCI service unavailable. Check https://ocistatus.oraclecloud.com/ for incidents.",
    }
    return advice.get(status, f"Refer to OCI documentation for error code '{code}'.")


# ---------------------------------------------------------------------------
# Quick connectivity test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    client = OCIGenAIClient()
    reply = client.chat("Say 'OCI connection successful' and nothing else.")
    print("OCI Test Response:", reply)
