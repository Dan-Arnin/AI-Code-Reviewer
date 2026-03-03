# coding: utf-8
"""
api.py
Flask webhook server.

Start with:
    python api.py

POST /review
Body (JSON):
    {
        "repo_url":      "https://vbs.example.com/org/project.git",
        "source_branch": "feature/my-feature",
        "target_branch": "main",
        "pr_id":         "42"          (optional)
    }

Returns (JSON):
    {
        "status":       "success" | "error",
        "report_path":  "/absolute/path/to/reports/review_<pr_id>.html",
        "summary": {
            "overall_status": "APPROVED" | "NEEDS WORK" | "BLOCKED" | "REVIEW REQUIRED",
            "total_findings": 12,
            "severity_counts": {...},
            "elapsed_seconds": 18.4
        },
        "error": "..." (only on error)
    }
"""

import os
from datetime import datetime
from flask import Flask, request, jsonify

from logger import get_logger
from git_client import OracleVBSGitClient
from reviewer import CodeReviewer
from report_generator import ReportGenerator

log = get_logger(__name__)
app = Flask(__name__)

REPORTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")


@app.route("/health", methods=["GET"])
def health():
    """Simple liveness check."""
    log.debug("Health check request received.")
    return jsonify({"status": "ok"}), 200


@app.route("/review", methods=["POST"])
def review():
    """
    Trigger a code review for a merge request.
    See module docstring for request/response shapes.
    """
    data = request.get_json(silent=True) or {}
    request_time = datetime.now().isoformat()

    log.info("=" * 60)
    log.info("Review request received at %s", request_time)

    # ── Validate input ───────────────────────────────────────────────────────
    required = ["repo_url", "source_branch", "target_branch"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        log.warning(
            "Request rejected — missing required fields: %s\n"
            "  WHAT TO DO : Ensure your webhook payload includes all required fields: "
            "repo_url, source_branch, target_branch (and optionally pr_id).",
            missing,
        )
        return jsonify({
            "status": "error",
            "error": f"Missing required fields: {', '.join(missing)}",
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
        # ── Fetch diff ───────────────────────────────────────────────────────
        log.info("STEP 1/3 → Cloning repository and computing diff …")
        git_client = OracleVBSGitClient(repo_url=repo_url)
        diff_result = git_client.get_diff(
            source_branch=source_branch,
            target_branch=target_branch,
            pr_id=pr_id or None,
        )
        log.info(
            "Diff ready → %d file(s) changed | %d commit(s).",
            len(diff_result.changed_files), diff_result.metadata.commit_count,
        )

        # ── Run review agents ────────────────────────────────────────────────
        log.info("STEP 2/3 → Running AI review agents …")
        reviewer = CodeReviewer()
        report = reviewer.review(diff_result)
        log.info(
            "Review complete → status: %s | findings: %d | elapsed: %.2fs",
            report.overall_status, report.total_findings, report.elapsed_seconds,
        )

        # ── Write HTML report ────────────────────────────────────────────────
        log.info("STEP 3/3 → Writing HTML report …")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        slug = pr_id or f"{source_branch.replace('/', '_')}_{timestamp}"
        report_filename = f"review_{slug}.html"
        report_path = os.path.join(REPORTS_DIR, report_filename)

        os.makedirs(REPORTS_DIR, exist_ok=True)
        generator = ReportGenerator()
        generator.generate(report, report_path)
        log.info("Report saved → %s", report_path)
        log.info("=" * 60)

        return jsonify({
            "status": "success",
            "report_path": report_path,
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
            "  WHAT TO DO      : Fix GIT_USERNAME or GIT_PAT in the .env file on the server.",
            exc,
        )
        return jsonify({"status": "error", "error": str(exc)}), 400

    except Exception as exc:
        log.error(
            "Unexpected error processing review request.\n"
            "  WHAT WENT WRONG : %s\n"
            "  WHAT TO DO      : Check the log file in logs/ for the full stack trace. "
            "Verify connectivity to Oracle VBS and OCI.",
            exc,
            exc_info=True,
        )
        return jsonify({"status": "error", "error": str(exc)}), 500


if __name__ == "__main__":
    os.makedirs(REPORTS_DIR, exist_ok=True)
    log.info("OCI Gen AI Code Review API starting …")
    log.info("Reports directory : %s", REPORTS_DIR)
    log.info("Listening on http://0.0.0.0:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)
