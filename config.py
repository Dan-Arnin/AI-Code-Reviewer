# coding: utf-8
"""
config.py
Central configuration for the Gen AI Code Review System.
All settings are read from environment variables (loaded from .env).
Runtime overrides are supported via RuntimeConfig (updated by the /api/config endpoint).

Supported AI providers: 'oci' (OCI Generative AI) or 'claude' (Anthropic Claude).
Switch provider via the Settings page or by setting AI_PROVIDER in .env.
"""

import os
import json
from typing import Dict, Any
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Oracle Visual Builder Studio – Git access
# ---------------------------------------------------------------------------
GIT_PAT = os.getenv("GIT_PAT", "")
GIT_USERNAME = os.getenv("GIT_USERNAME", "")          # VBS username / email
VBS_REPO_URL = os.getenv("VBS_REPO_URL", "")          # default repo (optional)

# ---------------------------------------------------------------------------
# AI Provider selection
# ---------------------------------------------------------------------------
# Set to 'oci' to use OCI Generative AI, or 'claude' to use Anthropic Claude.
AI_PROVIDER = os.getenv("AI_PROVIDER", "oci").lower()   # default: oci

# ---------------------------------------------------------------------------
# Anthropic Claude
# ---------------------------------------------------------------------------
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

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
# OCI Object Storage
# ---------------------------------------------------------------------------
OCI_STORAGE_COMPARTMENT_ID = os.getenv(
    "OCI_STORAGE_COMPARTMENT_ID",
    "ocid1.compartment.oc1..aaaaaaaacucsz25cffcab5afedm7qcui5mpdrib2ygolks5vxsfc3wql6tna"
)
OCI_BUCKET_NAME = os.getenv("OCI_BUCKET_NAME", "REVIEW_REPORT_BUCKET")

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
# ---------------------------------------------------------------------------
# CRITICAL rules – agents flag these as CRITICAL or HIGH findings only.
# These are bugs that WILL crash the process, corrupt data, or open a
# direct security hole (SQL injection, eval on user input, etc.).
# DO NOT add style / logging / documentation rules here.
# ---------------------------------------------------------------------------
BEST_PRACTICES = {
    "security": [
        "SQL queries must use parameterised statements — string concatenation in queries allows SQL injection.",
        "Never call eval(), exec(), new Function(), or similar with unsanitised user input — this allows remote code execution.",
        "File paths constructed from user input must be sanitised to prevent directory traversal attacks.",
        # "HTTP client calls to external services must validate SSL/TLS certificates (no verify=False / rejectUnauthorized:false).",
        # "Cryptographic operations must never use deprecated algorithms (MD5, SHA-1, DES) for security-sensitive data.",
    ],
    "logic": [
        "All external API / database / file-system calls MUST have error handling (try/catch or .catch()). Missing error handling will crash the process on failure.",
        "Null / undefined values returned from API calls or object lookups must be checked before use — accessing a property on null throws a runtime error.",
        "Asynchronous functions / Promises must be properly awaited or have a rejection handler — unhandled rejections crash Node.js processes.",
        "Recursive functions must have a clear base case — missing one causes a stack overflow.",
        "Avoid swallowed exceptions (bare except: pass / catch(e) {}) — silent failures hide bugs and make debugging impossible.",
        "Array / collection operations (map, filter, find, forEach) on a value that could be null or undefined must be null-checked first.",
    ],
    "performance": [
        "Database queries or expensive I/O inside a loop WILL cause N+1 problems and timeouts under load — must be refactored to bulk queries.",
        "File handles and database connections must always be closed after use (use context managers / finally blocks) — resource leaks cause pod crashes under load.",
        "Blocking synchronous I/O (fs.readFileSync, sleep) inside an async event loop blocks the entire thread.",
    ],
    "dependency": [
        "Dependencies with known critical CVEs (CVSS ≥ 9.0) must not be introduced.",
        "All new dependencies must be declared in package.json / requirements.txt — undeclared deps cause deploy failures.",
    ],
    "style": [
        "Deeply nested callbacks or promise chains without any error propagation path will silently swallow failures.",
    ],
}

# ---------------------------------------------------------------------------
# SUGGESTION rules – shown only in the Suggestions tab, never as blocking
# findings. These are code-quality improvements, NOT bugs.
# ---------------------------------------------------------------------------
SUGGESTION_PRACTICES = {
    "security": [
        "Hardcoded credentials or API keys in source code should be moved to environment variables.",
        "Sensitive data (PII, tokens) ideally should not appear in log output even at debug level.",
        "OCI / cloud config paths should be loaded from environment variables for portability.",
    ],
    "style": [
        "Code should follow PEP-8 / ESLint conventions (indentation, line length, naming).",
        "Commented-out code blocks should be removed.",
        "Unused imports or variables should be cleaned up.",
        "Type hints (Python) or JSDoc annotations (JS) improve IDE support and readability.",
        "Magic numbers should be replaced with named constants.",
        "Complex logic should have inline comments.",
    ],
    "logic": [
        "Repeated expensive computations (e.g. moment() parsing inside sort comparators) should be cached.",
        "Boolean flags used as poor state machines could be replaced with explicit state enums.",
        "Mutable default arguments in Python functions can cause surprising bugs.",
    ],
    "performance": [
        "HTTP connections should be reused via session/agent objects where possible.",
        "Large datasets should use generators or streams instead of loading fully into memory.",
        "String concatenation in tight loops should use join() or a buffer.",
        "Logging inside tight loops should be avoided or guarded by a level check.",
    ],
    "dependency": [
        "Avoid adding large libraries for trivial tasks.",
        "Version constraints should not be overly broad (e.g. requests>=2).",
        "Dependency licences should be compatible with the project licence.",
    ],
}


# ---------------------------------------------------------------------------
# Runtime config  (in-memory overrides – updated via POST /api/config)
# ---------------------------------------------------------------------------

_RUNTIME_CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".runtime_config.json")


def _get_storage_auth() -> Dict[str, Any]:
    """Returns auth configuration exclusively from Environment Variables for the Object Storage linkage."""
    import oci
    auth_method = os.getenv("OCI_STORAGE_AUTH_METHOD", "instance_principal")
    if auth_method == "instance_principal":
        signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
        cfg = {}
        region = os.getenv("OCI_STORAGE_REGION")
        if region:
            cfg["region"] = region
        return {"signer": signer, "config": cfg}
    elif auth_method == "keys":
        key_content = os.getenv("OCI_STORAGE_KEY_CONTENT", "")
        if r"\n" in key_content:
            key_content = key_content.replace(r"\n", "\n")
        cfg = {
            "user": os.getenv("OCI_STORAGE_USER", ""),
            "key_content": key_content,
            "fingerprint": os.getenv("OCI_STORAGE_FINGERPRINT", ""),
            "tenancy": os.getenv("OCI_STORAGE_TENANCY", ""),
            "region": os.getenv("OCI_STORAGE_REGION", "")
        }
        oci.config.validate_config(cfg)
        return {"config": cfg}
    else:
        cfg = oci.config.from_file("~/.oci/config", os.getenv("OCI_STORAGE_CONFIG_PROFILE", "DEFAULT"))
        return {"config": cfg}

class _RuntimeConfig:
    """
    Singleton that holds live config overrides.
    Values here take precedence over the module-level constants above.
    Persisted to OCI Object Storage if OCI_BUCKET_NAME is set, otherwise a local JSON file.
    """

    _DEFAULTS: Dict[str, Any] = {}

    def __init__(self) -> None:
        self._data: Dict[str, Any] = {}
        self._load()

    def _get_storage_client(self):
        import oci
        auth_dict = _get_storage_auth()
        kw = {"config": auth_dict.get("config", {})}
        if "signer" in auth_dict:
            kw["signer"] = auth_dict["signer"]
        return oci.object_storage.ObjectStorageClient(**kw)

    def _load(self) -> None:
        self._data = {}
        bucket = os.getenv("OCI_BUCKET_NAME", "")
        if bucket:
            try:
                import json
                client = self._get_storage_client()
                namespace = client.get_namespace().data
                obj_name = os.getenv("OCI_CONFIG_JSON_OBJECT_NAME", "config/runtime_config.json")
                resp = client.get_object(namespace, bucket, obj_name)
                self._data = json.loads(resp.data.content.decode("utf-8"))
            except Exception as e:
                print(f"Failed to load config from OCI Storage: {e}")
                pass
        else:
            if os.path.exists(_RUNTIME_CONFIG_FILE):
                try:
                    import json
                    with open(_RUNTIME_CONFIG_FILE, "r", encoding="utf-8") as fh:
                        self._data = json.load(fh)
                except Exception:
                    pass

    def _save(self) -> None:
        bucket = os.getenv("OCI_BUCKET_NAME", "")
        if bucket:
            try:
                import json
                client = self._get_storage_client()
                namespace = client.get_namespace().data
                obj_name = os.getenv("OCI_CONFIG_JSON_OBJECT_NAME", "config/runtime_config.json")
                content = json.dumps(self._data, indent=2).encode("utf-8")
                client.put_object(namespace, bucket, obj_name, content)
            except Exception as e:
                print(f"Failed to save config to OCI Storage: {e}")
                pass
        else:
            try:
                import json
                with open(_RUNTIME_CONFIG_FILE, "w", encoding="utf-8") as fh:
                    json.dump(self._data, fh, indent=2)
            except Exception:
                pass

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
        self._save()

    def update(self, updates: Dict[str, Any]) -> None:
        self._data.update(updates)
        self._save()

    def as_dict(self) -> Dict[str, Any]:
        return dict(self._data)

runtime_config = _RuntimeConfig()

def _extract_region_from_url(url: str) -> str | None:
    """
    Extracts the OCI region from a provided endpoint URL.
    Example: https://inference.generativeai.us-chicago-1.oci.oraclecloud.com -> us-chicago-1
    """
    import re
    if not url:
        return None
    # Standard OCI region pattern: [a-z]{2,}-[a-z]+-[0-9]
    # We look for it between dots and preceding the oracle domain suffixes.
    match = re.search(r"\.([a-z]{2,}-[a-z]+-[0-9])\.(?:oci\.customer-oci\.com|oraclecloud\.com)", url)
    if match:
        return match.group(1)
    
    # Fallback for simple formats like 'us-phoenix-1.oraclecloud.com'
    match = re.search(r"([a-z]{2,}-[a-z]+-[0-9])", url)
    if match:
        return match.group(1)
        
    return None

def get_oci_auth(service: str = None) -> Dict[str, Any]:
    """
    Returns the OCI authentication credentials dictated by the config override.
    If service is 'genai', it uses the region extracted from the endpoint URL.
    Returns:
        A dict with either:
          {"config": <config_dict>}
        Or:
          {"signer": <instance_principal_signer>, "config": {}}
    """
    if service == "storage":
        return _get_storage_auth()

    import oci
    auth_method = runtime_config.get("oci_auth_method", "config_file")
    endpoint = runtime_config.get("endpoint", "")
    extracted_region = _extract_region_from_url(endpoint)
    
    # Use the extracted region only for Gen AI, or as a global fallback if no other region exists
    target_region = runtime_config.get("oci_region", "")
    if service in ["genai", "generativeai"]:
        target_region = extracted_region or target_region
    
    if auth_method == "instance_principal":
        signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
        cfg = {}
        if target_region:
            cfg["region"] = target_region
        return {"signer": signer, "config": cfg}
    elif auth_method == "keys":
        cfg = {
            "user": runtime_config.get("oci_user_ocid", ""),
            "key_content": runtime_config.get("oci_private_key", ""),
            "fingerprint": runtime_config.get("oci_fingerprint", ""),
            "tenancy": runtime_config.get("oci_tenancy_ocid", ""),
            "region": target_region
        }
        oci.config.validate_config(cfg)
        return {"config": cfg}
    else:
        # Default config file behavior
        cfg = oci.config.from_file("~/.oci/config", OCI_CONFIG_PROFILE)
        if target_region:
            cfg["region"] = target_region
        return {"config": cfg}

