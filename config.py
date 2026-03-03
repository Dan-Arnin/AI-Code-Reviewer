# coding: utf-8
"""
config.py
Central configuration for the OCI Gen AI Code Review System.
All settings are read from environment variables (loaded from .env).
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Oracle Visual Builder Studio – Git access
# ---------------------------------------------------------------------------
GIT_PAT = os.getenv("GIT_PAT", "")
GIT_USERNAME = os.getenv("GIT_USERNAME", "")          # VBS username / email
VBS_REPO_URL = os.getenv("VBS_REPO_URL", "")          # default repo (optional)

# ---------------------------------------------------------------------------
# OCI Generative AI
# ---------------------------------------------------------------------------
OCI_COMPARTMENT_ID = os.getenv(
    "OCI_COMPARTMENT_ID",
    "ocid1.tenancy.oc1..aaaaaaaahqvb2kliqi35z57qalhpr4dyqbjprclszdcoar2wgc7q6nl36aba"
)
OCI_CONFIG_PROFILE = os.getenv("OCI_CONFIG_PROFILE", "DEFAULT")
OCI_ENDPOINT = os.getenv(
    "OCI_ENDPOINT",
    "https://inference.generativeai.us-chicago-1.oci.oraclecloud.com"
)
OCI_MODEL_ID = os.getenv(
    "OCI_MODEL_ID",
    "ocid1.generativeaimodel.oc1.us-chicago-1.amaaaaaask7dceyat2iycf2rksgjhlmrmsxakcyjbpxurwmfguxjzptogvqa"
)
OCI_MAX_TOKENS = 20000
OCI_TEMPERATURE = 1
OCI_TOP_P = 1
OCI_TOP_K = 0

# ---------------------------------------------------------------------------
# Agent orchestration
# ---------------------------------------------------------------------------
# Maximum number of lines of diff sent to a single AI agent call.
# Large diffs are chunked automatically.
MAX_DIFF_LINES_PER_CHUNK = 300

# ---------------------------------------------------------------------------
# Best-practices checklist
# Each agent uses a subset of these rules in its system prompt.
# ---------------------------------------------------------------------------
BEST_PRACTICES = {
    "security": [
        "No hardcoded credentials, API keys, passwords or tokens in source code.",
        "All user inputs must be validated and sanitised before use.",
        "SQL queries must use parameterised statements; no string concatenation.",
        "Sensitive data must never be logged in plain text.",
        "Authentication tokens must not be stored in cookies without HttpOnly/Secure flags.",
        "File paths constructed from user input must be sanitised to prevent path traversal.",
        "Third-party libraries should be pinned to specific versions.",
        "Avoid use of eval(), exec(), or dynamic code execution with untrusted input.",
        "HTTP requests to external services must validate SSL certificates.",
        "Secrets must be loaded from environment variables or a secrets vault, not config files.",
    ],
    "style": [
        "Code must follow PEP-8 conventions (indentation, line length ≤ 120 chars, naming).",
        "All public functions, classes and modules must have docstrings.",
        "Variable and function names must be descriptive and in snake_case.",
        "No commented-out code blocks left in the codebase.",
        "No unused imports or variables.",
        "Type hints should be used for all function signatures.",
        "Magic numbers must be replaced with named constants.",
        "Complex logic must be accompanied by inline comments.",
        "Files must end with a single newline character.",
        "Avoid deeply nested code; prefer early returns to reduce nesting.",
    ],
    "logic": [
        "All external API / DB calls must have error handling (try/except).",
        "Edge cases (empty list, None, zero, negative numbers) must be handled.",
        "Recursive functions must have a clear base case to prevent infinite recursion.",
        "Asynchronous code must properly await all coroutines.",
        "No swallowed exceptions (bare except: pass).",
        "Return values from functions must not be silently ignored where they signal errors.",
        "Boolean flags should not replace proper state machines for complex workflows.",
        "List comprehensions must not have side effects.",
        "Thread-shared state must be protected with appropriate locks.",
        "Avoid mutable default arguments in function definitions.",
    ],
    "performance": [
        "Database queries inside loops must be refactored to bulk queries.",
        "Large data sets must be processed with generators or streams, not loaded fully into memory.",
        "Repeated expensive computations should be cached.",
        "Avoid creating large temporary lists when a generator suffices.",
        "HTTP connections should be reused via session objects.",
        "File handles must always be closed (use context managers).",
        "Avoid unnecessary deep copying of large objects.",
        "String concatenation in loops must use join() or a buffer.",
        "Logging inside tight loops must be avoided or guarded by a level check.",
        "Blocking I/O must not be performed in async event loops.",
    ],
    "dependency": [
        "All new dependencies must be listed in requirements.txt / pyproject.toml.",
        "Avoid adding large libraries for trivial tasks (e.g. six, requests for one-line use).",
        "License of new dependencies must be compatible with the project license.",
        "Dependencies must not have known critical CVEs.",
        "Version constraints must not be overly broad (e.g. requests>=2 is too broad).",
    ],
}
