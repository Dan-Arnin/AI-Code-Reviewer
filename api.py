# coding: utf-8
"""
api.py
Flask webhook + frontend API server.

Start with:
    python api.py

Endpoints:
    GET  /                               → Serve frontend dashboard
    GET  /static/<path>                  → Static assets
    POST /review                         → Trigger a code review (uploads report to OCI on success)
    GET  /api/reports                    → List reports from OCI (paginated + date-filtered)
    GET  /api/reports/<path:object_name> → Fetch a report HTML from OCI
    GET  /api/config                     → Get current runtime config
    POST /api/config                     → Update runtime config
    GET  /health                         → Liveness check
"""

import os
from datetime import datetime, timezone
from flask import Flask, request, jsonify, send_from_directory, Response

from logger import get_logger
from git_client import OracleVBSGitClient
from reviewer import CodeReviewer
from report_generator import ReportGenerator
from oci_storage import OCIStorageClient
from config import (
    OCI_MODEL_ID, OCI_STORAGE_COMPARTMENT_ID, OCI_BUCKET_NAME,
    OCI_ENDPOINT, BEST_PRACTICES, SUGGESTION_PRACTICES, AI_PROVIDER, runtime_config,
)

log = get_logger(__name__)
app = Flask(__name__, static_folder="static", static_url_path="/static")

REPORTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")

# ---------------------------------------------------------------------------
# Frontend
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    """Serve the frontend dashboard."""
    return send_from_directory("static", "index.html")


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.route("/health", methods=["GET"])
def health():
    """Simple liveness check."""
    log.debug("Health check request received.")
    return jsonify({"status": "ok"}), 200


# ---------------------------------------------------------------------------
# Review trigger
# ---------------------------------------------------------------------------

@app.route("/review", methods=["POST"])
def review():
    """
    Trigger a code review for a merge request.

    Body (JSON):
        repo_url, source_branch, target_branch, pr_id (optional)

    Returns:
        JSON with status, report OCI object name, and summary stats.
    """
    data = request.get_json(silent=True) or {}
    request_time = datetime.now().isoformat()

    log.info("=" * 60)
    log.info("Review request received at %s", request_time)

    # ── Validate input ────────────────────────────────────────────────
    is_single_branch = data.get("is_single_branch", False)
    
    required = ["repo_url", "source_branch"]
    if not is_single_branch:
        required.append("target_branch")
        
    missing = [f for f in required if not data.get(f)]
    if missing:
        log.warning("Request rejected — missing fields: %s", missing)
        return jsonify({
            "status": "error",
            "error":  f"Missing required fields: {', '.join(missing)}",
        }), 400

    repo_url      = data["repo_url"]
    source_branch = data["source_branch"]
    target_branch = data.get("target_branch", "")
    pr_id         = data.get("pr_id", "")
    git_pat       = data.get("git_pat")
    git_username  = data.get("git_username")

    # Agents the user enabled from global settings — default to all five if not set
    _all_agents     = ["security", "logic", "performance", "dependency", "style"]
    enabled_agents  = runtime_config.get("enabled_agents")
    
    if not isinstance(enabled_agents, list) or not enabled_agents:
        enabled_agents = _all_agents
    else:
        # filter to valid agents only
        enabled_agents = [a for a in enabled_agents if a in _all_agents]

    # guard: never let an empty list slip through
    enabled_agents = enabled_agents or _all_agents

    log.info("  Repo   : %s", repo_url)
    log.info("  Source : %s", source_branch)
    if not is_single_branch:
        log.info("  Target : %s", target_branch)
    else:
        log.info("  Mode   : Single Branch")
    log.info("  PR ID  : %s", pr_id or "N/A")
    log.info("  Agents : %s", ", ".join(enabled_agents))

    try:
        # ── Step 1: Fetch diff ────────────────────────────────────────
        git_client_kwargs = {"repo_url": repo_url}
        if git_pat and git_username:
            git_client_kwargs["pat"] = git_pat
            git_client_kwargs["username"] = git_username
            
        git_client = OracleVBSGitClient(**git_client_kwargs)
        
        if is_single_branch:
            log.info("STEP 1/4 → Cloning repository and extracting single branch …")
            diff_result = git_client.get_single_branch(branch=source_branch)
        else:
            log.info("STEP 1/4 → Cloning repository and computing diff …")
            diff_result = git_client.get_diff(
                source_branch=source_branch,
                target_branch=target_branch,
                pr_id=pr_id or None,
            )
            
        log.info(
            "Data ready → %d file(s) changed/found | %d commit(s).",
            len(diff_result.changed_files), diff_result.metadata.commit_count,
        )

        # ── Step 2: Run review agents ─────────────────────────────────
        log.info("STEP 2/4 → Running AI review agents (%s) …", ", ".join(enabled_agents))
        reviewer = CodeReviewer()
        report   = reviewer.review(diff_result, enabled_agents=enabled_agents)
        log.info(
            "Review complete → status: %s | findings: %d | elapsed: %.2fs",
            report.overall_status, report.total_findings, report.elapsed_seconds,
        )

        # ── Step 3: Write HTML report locally ─────────────────────────
        log.info("STEP 3/4 → Writing HTML report …")
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        repo_name = repo_url.rstrip('/').split('/')[-1]
        if repo_name.endswith('.git'):
            repo_name = repo_name[:-4]
        
        safe_repo = repo_name.replace("/", "_").replace(" ", "_").replace("-", "_")
        safe_source = source_branch.replace("/", "_").replace(" ", "_")
        
        if is_single_branch:
            report_filename = f"{safe_repo}_{safe_source}_{timestamp}.html"
        else:
            safe_target = target_branch.replace("/", "_").replace(" ", "_")
            report_filename = f"{safe_repo}_{safe_source}_{safe_target}_{timestamp}.html"
            
        report_path = os.path.join(REPORTS_DIR, report_filename)

        os.makedirs(REPORTS_DIR, exist_ok=True)
        generator = ReportGenerator()
        generator.generate(report, report_path)
        log.info("Report saved locally → %s", report_path)

        # ── Step 4: Upload to OCI Object Storage ──────────────────────
        log.info("STEP 4/4 → Uploading report to OCI Object Storage …")
        oci_object_name = f"reports/{report_filename}"
        oci_uploaded    = False
        try:
            storage = OCIStorageClient()
            oci_uploaded = storage.upload(report_path, oci_object_name)
        except Exception as oci_exc:
            log.error(
                "OCI upload failed (report is still saved locally).\n"
                "  WHAT WENT WRONG : %s", oci_exc,
            )

        log.info("=" * 60)

        return jsonify({
            "status":          "success",
            "report_path":     report_path,
            "report_filename": report_filename,
            "oci_object":      oci_object_name if oci_uploaded else None,
            "oci_uploaded":    oci_uploaded,
            "summary": {
                "overall_status":  report.overall_status,
                "total_findings":  report.total_findings,
                "severity_counts": report.severity_totals,
                "elapsed_seconds": report.elapsed_seconds,
            },
        }), 200

    except ValueError as exc:
        log.error(
            "Configuration error during review.\n"
            "  WHAT WENT WRONG : %s\n"
            "  WHAT TO DO      : Fix GIT_USERNAME or GIT_PAT in the .env file.",
            exc,
        )
        return jsonify({"status": "error", "error": str(exc)}), 400

    except Exception as exc:
        log.error(
            "Unexpected error processing review request.\n"
            "  WHAT WENT WRONG : %s\n"
            "  WHAT TO DO      : Check logs/ for the full stack trace.",
            exc, exc_info=True,
        )
        return jsonify({"status": "error", "error": str(exc)}), 500


# ---------------------------------------------------------------------------
# Local report (for inline viewer immediately after a review completes)
# ---------------------------------------------------------------------------

@app.route("/api/local-report/<path:filename>", methods=["GET"])
def get_local_report(filename: str):
    """
    Serve a report HTML file from the local reports/ directory.
    Used by the inline viewer right after a review completes so the user
    doesn't have to wait for OCI Object Storage propagation.
    """
    import re
    # Safety: only allow safe filenames (no directory traversal)
    if not re.match(r'^[\w\-]+\.html$', filename):
        return jsonify({"status": "error", "error": "Invalid filename."}), 400
    try:
        return send_from_directory(REPORTS_DIR, filename, mimetype="text/html; charset=utf-8")
    except Exception as exc:
        log.error("Failed to serve local report '%s': %s", filename, exc)
        return jsonify({"status": "error", "error": str(exc)}), 404


# ---------------------------------------------------------------------------
# Reports API — OCI-backed
# ---------------------------------------------------------------------------

@app.route("/api/reports", methods=["GET"])
def list_reports():
    """
    List review reports from OCI Object Storage.

    Query params:
        page      (int, default 1)
        page_size (int, default 20)
        from      (str, YYYY-MM-DD, optional)
        to        (str, YYYY-MM-DD, optional)
        repo      (str, optional)
        branch    (str, optional)
    """
    try:
        page      = max(1, int(request.args.get("page", 1)))
        page_size = max(1, min(100, int(request.args.get("page_size", 20))))

        from_date = None
        to_date   = None

        from_str = request.args.get("from", "")
        to_str   = request.args.get("to", "")
        repo_filter   = request.args.get("repo", "").lower()
        branch_filter = request.args.get("branch", "").lower()

        if from_str:
            from_date = datetime.strptime(from_str, "%Y-%m-%d").replace(tzinfo=None)
        if to_str:
            # Inclusive: add 1 day's worth of seconds so "to=2026-03-04" includes that whole day
            to_date = datetime.strptime(to_str, "%Y-%m-%d").replace(
                hour=23, minute=59, second=59, tzinfo=None
            )

        storage = OCIStorageClient()
        result  = storage.list_objects(
            page=1, # We filter locally, so fetch all then slice
            page_size=10000,
            from_date=from_date,
            to_date=to_date,
            prefix="reports/",
        )
        
        filtered_items = []
        for item in result["items"]:
            # item["name"] format: reports/Repo_SourceBranch_[TargetBranch_]YYYY...
            name_lower = item["name"].lower()
            if repo_filter and repo_filter not in name_lower:
                continue
            if branch_filter and branch_filter not in name_lower:
                continue
            filtered_items.append(item)
            
        total = len(filtered_items)
        total_pages = max(1, -(-total // page_size))
        start = (page - 1) * page_size
        page_items = filtered_items[start:start + page_size]
        
        result.update({
            "items": page_items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        })
        
        return jsonify(result), 200

    except Exception as exc:
        log.error("Failed to list OCI reports: %s", exc)
        return jsonify({"status": "error", "error": str(exc)}), 500


@app.route("/api/reports/<path:object_name>", methods=["GET"])
def get_report(object_name: str):
    """
    Fetch a report's HTML content from OCI and proxy it to the browser.
    object_name: the OCI object key (e.g. 'reports/review_xyz.html')
    """
    try:
        # If the caller omits the 'reports/' prefix, add it
        if not object_name.startswith("reports/"):
            object_name = f"reports/{object_name}"

        storage = OCIStorageClient()
        content = storage.get_object_content(object_name)
        return Response(content, mimetype="text/html; charset=utf-8")

    except Exception as exc:
        log.error("Failed to fetch report '%s' from OCI: %s", object_name, exc)
        return jsonify({"status": "error", "error": str(exc)}), 500


# ---------------------------------------------------------------------------
# Config API
# ---------------------------------------------------------------------------

@app.route("/api/config", methods=["GET"])
def get_config():
    """Return the current runtime configuration (merged with defaults)."""
    import config as cfg

    # Effective values: runtime overrides take precedence
    effective = {
        "ai_provider":    runtime_config.get("ai_provider",    AI_PROVIDER),
        "model_id":       runtime_config.get("model_id",       cfg.OCI_MODEL_ID),
        "compartment_id": runtime_config.get("compartment_id", cfg.OCI_STORAGE_COMPARTMENT_ID),
        "bucket_name":    runtime_config.get("bucket_name",    cfg.OCI_BUCKET_NAME),
        "endpoint":       runtime_config.get("endpoint",       cfg.OCI_ENDPOINT),
        "enabled_agents": runtime_config.get("enabled_agents", ["security", "logic", "performance", "dependency", "style"]),
        "prompts": {
            agent: runtime_config.get(f"prompt_{agent}", "\n".join(rules))
            for agent, rules in BEST_PRACTICES.items()
        },
        "saved_repos":    runtime_config.get("saved_repos", []),
        "saved_pats":     runtime_config.get("saved_pats", []),
        "oci_auth_method": runtime_config.get("oci_auth_method", "config_file"),
        "oci_user_ocid":   runtime_config.get("oci_user_ocid", ""),
        "oci_fingerprint": runtime_config.get("oci_fingerprint", ""),
        "oci_tenancy_ocid": runtime_config.get("oci_tenancy_ocid", ""),
        "oci_region":      runtime_config.get("oci_region", ""),
        "oci_private_key": runtime_config.get("oci_private_key", ""),
        
        "_overrides": runtime_config.as_dict(),
    }
    return jsonify(effective), 200


@app.route("/api/config", methods=["POST"])
def update_config():
    """
    Update runtime configuration.

    Accepted fields (all optional):
        model_id, compartment_id, bucket_name, endpoint,
        prompts: { security, style, logic, performance, dependency }
    """
    data = request.get_json(silent=True) or {}
    updates = {}

    # AI provider toggle
    if "ai_provider" in data and data["ai_provider"] in ("oci", "claude"):
        updates["ai_provider"] = data["ai_provider"]

    for field in ("model_id", "compartment_id", "bucket_name", "endpoint"):
        if field in data and data[field]:
            updates[field] = data[field]

    if "enabled_agents" in data and isinstance(data["enabled_agents"], list):
        updates["enabled_agents"] = [
            a for a in data["enabled_agents"]
            if a in ("security", "style", "logic", "performance", "dependency")
        ]

    if "saved_repos" in data and isinstance(data["saved_repos"], list):
        updates["saved_repos"] = data["saved_repos"]

    if "saved_pats" in data and isinstance(data["saved_pats"], list):
        updates["saved_pats"] = data["saved_pats"]

    for field in ("oci_auth_method", "oci_user_ocid", "oci_fingerprint", "oci_tenancy_ocid", "oci_region", "oci_private_key"):
        if field in data:
            updates[field] = data[field]

    if "prompts" in data and isinstance(data["prompts"], dict):
        for agent, text in data["prompts"].items():
            if agent in BEST_PRACTICES:
                updates[f"prompt_{agent}"] = text

    if not updates:
        return jsonify({"status": "error", "error": "No valid fields to update."}), 400

    runtime_config.update(updates)
    log.info("Runtime config updated: %s", list(updates.keys()))
    return jsonify({"status": "ok", "updated": list(updates.keys())}), 200


# ---------------------------------------------------------------------------
# Git API (Utilities)
# ---------------------------------------------------------------------------

@app.route("/api/git/branches", methods=["POST"])
def get_git_branches():
    """
    Fetch remote branches for a repository using git ls-remote.
    
    Body (JSON):
        repo_url, git_pat, git_username
    """
    data = request.get_json(silent=True) or {}
    repo_url = data.get("repo_url")
    pat = data.get("git_pat")
    username = data.get("git_username")
    
    if not repo_url or not pat or not username:
        return jsonify({"status": "error", "error": "Missing repo_url, git_pat, or git_username"}), 400
        
    try:
        from git_client import OracleVBSGitClient
        client = OracleVBSGitClient(repo_url=repo_url, pat=pat, username=username)
        branches = client.get_remote_branches()
        return jsonify({"status": "success", "branches": branches}), 200
    except Exception as exc:
        log.error("Failed to fetch branches: %s", exc)
        return jsonify({"status": "error", "error": str(exc)}), 500


# ---------------------------------------------------------------------------
# OCI API (Resource Fetching)
# ---------------------------------------------------------------------------

@app.route("/api/oci/compartments", methods=["GET"])
def get_oci_compartments():
    try:
        import oci
        from config import get_oci_auth
        auth = get_oci_auth(service="identity")
        kw = {"config": auth.get("config", {})}
        if "signer" in auth:
            kw["signer"] = auth["signer"]
            
        # Get tenancy from config or signer
        tenancy_id = kw["config"].get("tenancy")
        if not tenancy_id and "signer" in kw:
            tenancy_id = kw["signer"].tenancy_id
            
        client = oci.identity.IdentityClient(**kw)
        resp = client.list_compartments(
            compartment_id=tenancy_id,
            compartment_id_in_subtree=True,
            access_level="ACCESSIBLE",
            limit=200
        )
        # Use .items if it's a collection object, else use .data directly
        data_list = resp.data.items if hasattr(resp.data, 'items') and not isinstance(resp.data, list) else resp.data
        return jsonify({"status": "success", "compartments": [{"id": c.id, "name": c.name} for c in data_list]}), 200
    except Exception as exc:
        return jsonify({"status": "error", "error": str(exc)}), 500

@app.route("/api/oci/buckets", methods=["GET"])
def get_oci_buckets():
    try:
        import oci
        from config import get_oci_auth
        compartment_id = request.args.get("compartment_id")
        if not compartment_id:
            return jsonify({"status": "error", "error": "compartment_id query param required"}), 400
            
        auth = get_oci_auth(service="storage")
        kw = {"config": auth.get("config", {})}
        if "signer" in auth:
            kw["signer"] = auth["signer"]
            
        client = oci.object_storage.ObjectStorageClient(**kw)
        namespace = client.get_namespace().data
        resp = client.list_buckets(namespace_name=namespace, compartment_id=compartment_id, limit=200)
        data_list = resp.data.items if hasattr(resp.data, 'items') and not isinstance(resp.data, list) else resp.data
        return jsonify({"status": "success", "buckets": [{"name": b.name} for b in data_list]}), 200
    except Exception as exc:
        return jsonify({"status": "error", "error": str(exc)}), 500

@app.route("/api/oci/models", methods=["GET"])
def get_oci_models():
    try:
        import oci
        from config import get_oci_auth
        compartment_id = request.args.get("compartment_id")
        if not compartment_id:
            return jsonify({"status": "error", "error": "compartment_id query param required"}), 400
            
        auth = get_oci_auth(service="genai")
        kw = {"config": auth.get("config", {})}
        if "signer" in auth:
            kw["signer"] = auth["signer"]
            
        client = oci.generative_ai.GenerativeAiClient(**kw)
        resp = client.list_models(compartment_id=compartment_id, sort_order="ASC", sort_by="timeCreated")
        # GenerativeAi models are returned in a ModelCollection which has an 'items' list
        data_list = resp.data.items if hasattr(resp.data, 'items') else resp.data
        return jsonify({"status": "success", "models": [{"id": m.id, "name": m.display_name} for m in data_list]}), 200
    except Exception as exc:
        return jsonify({"status": "error", "error": str(exc)}), 500


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    os.makedirs(REPORTS_DIR, exist_ok=True)
    log.info("OCI Gen AI Code Review API starting …")
    log.info("Reports directory : %s", REPORTS_DIR)
    log.info("Listening on http://0.0.0.0:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)
