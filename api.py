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
    OCI_ENDPOINT, BEST_PRACTICES, runtime_config,
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
    required = ["repo_url", "source_branch", "target_branch"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        log.warning("Request rejected — missing fields: %s", missing)
        return jsonify({
            "status": "error",
            "error":  f"Missing required fields: {', '.join(missing)}",
        }), 400

    repo_url      = data["repo_url"]
    source_branch = data["source_branch"]
    target_branch = data["target_branch"]
    pr_id         = data.get("pr_id", "")

    log.info("  Repo   : %s", repo_url)
    log.info("  Source : %s", source_branch)
    log.info("  Target : %s", target_branch)
    log.info("  PR ID  : %s", pr_id or "N/A")

    try:
        # ── Step 1: Fetch diff ────────────────────────────────────────
        log.info("STEP 1/4 → Cloning repository and computing diff …")
        git_client  = OracleVBSGitClient(repo_url=repo_url)
        diff_result = git_client.get_diff(
            source_branch=source_branch,
            target_branch=target_branch,
            pr_id=pr_id or None,
        )
        log.info(
            "Diff ready → %d file(s) changed | %d commit(s).",
            len(diff_result.changed_files), diff_result.metadata.commit_count,
        )

        # ── Step 2: Run review agents ─────────────────────────────────
        log.info("STEP 2/4 → Running AI review agents …")
        reviewer = CodeReviewer()
        report   = reviewer.review(diff_result)
        log.info(
            "Review complete → status: %s | findings: %d | elapsed: %.2fs",
            report.overall_status, report.total_findings, report.elapsed_seconds,
        )

        # ── Step 3: Write HTML report locally ─────────────────────────
        log.info("STEP 3/4 → Writing HTML report …")
        timestamp       = datetime.now().strftime("%Y%m%d_%H%M%S")
        slug            = pr_id or f"{source_branch.replace('/', '_')}_{timestamp}"
        report_filename = f"review_{slug}.html"
        report_path     = os.path.join(REPORTS_DIR, report_filename)

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
            "status":      "success",
            "report_path": report_path,
            "oci_object":  oci_object_name if oci_uploaded else None,
            "oci_uploaded": oci_uploaded,
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
    """
    try:
        page      = max(1, int(request.args.get("page", 1)))
        page_size = max(1, min(100, int(request.args.get("page_size", 20))))

        from_date = None
        to_date   = None

        from_str = request.args.get("from", "")
        to_str   = request.args.get("to", "")

        if from_str:
            from_date = datetime.strptime(from_str, "%Y-%m-%d").replace(tzinfo=None)
        if to_str:
            # Inclusive: add 1 day's worth of seconds so "to=2026-03-04" includes that whole day
            to_date = datetime.strptime(to_str, "%Y-%m-%d").replace(
                hour=23, minute=59, second=59, tzinfo=None
            )

        storage = OCIStorageClient()
        result  = storage.list_objects(
            page=page,
            page_size=page_size,
            from_date=from_date,
            to_date=to_date,
            prefix="reports/",
        )
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
        "model_id":       runtime_config.get("model_id",       cfg.OCI_MODEL_ID),
        "compartment_id": runtime_config.get("compartment_id", cfg.OCI_STORAGE_COMPARTMENT_ID),
        "bucket_name":    runtime_config.get("bucket_name",    cfg.OCI_BUCKET_NAME),
        "endpoint":       runtime_config.get("endpoint",       cfg.OCI_ENDPOINT),
        "prompts": {
            agent: runtime_config.get(f"prompt_{agent}", "\n".join(rules))
            for agent, rules in BEST_PRACTICES.items()
        },
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

    for field in ("model_id", "compartment_id", "bucket_name", "endpoint"):
        if field in data and data[field]:
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
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    os.makedirs(REPORTS_DIR, exist_ok=True)
    log.info("OCI Gen AI Code Review API starting …")
    log.info("Reports directory : %s", REPORTS_DIR)
    log.info("Listening on http://0.0.0.0:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)
