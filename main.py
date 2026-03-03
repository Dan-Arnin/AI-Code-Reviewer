# coding: utf-8
"""
main.py
CLI entry point for manual / local review runs (no Flask required).

Usage:
    python main.py \
        --repo https://vbs.example.com/org/project.git \
        --source feature/my-feature \
        --target main \
        [--pr-id 42]

The HTML report is written to the reports/ directory.
"""

import argparse
import os
import sys
from datetime import datetime

# Logger must be imported first so logging is active before any other imports
from logger import get_logger
from git_client import OracleVBSGitClient
from reviewer import CodeReviewer
from report_generator import ReportGenerator

log = get_logger(__name__)

REPORTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="OCI Gen AI Code Review – CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--repo",    required=True, help="Oracle VBS git repo HTTPS URL")
    parser.add_argument("--source",  required=True, help="Source / feature branch name")
    parser.add_argument("--target",  required=True, help="Target / production branch name")
    parser.add_argument("--pr-id",   default="",    help="Optional merge-request / PR ID")
    parser.add_argument("--out-dir", default=REPORTS_DIR,
                        help=f"Directory to write the HTML report (default: {REPORTS_DIR})")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    log.info("=" * 60)
    log.info("OCI Gen AI – Code Review System  (CLI mode)")
    log.info("=" * 60)
    log.info("Repo   : %s", args.repo)
    log.info("Source : %s", args.source)
    log.info("Target : %s", args.target)
    log.info("PR ID  : %s", args.pr_id or "N/A")
    log.info("-" * 60)

    # ── Step 1: Fetch diff ───────────────────────────────────────────────────
    log.info("STEP 1/3 → Cloning repository and computing diff …")
    try:
        git_client = OracleVBSGitClient(repo_url=args.repo)
        diff_result = git_client.get_diff(
            source_branch=args.source,
            target_branch=args.target,
            pr_id=args.pr_id or None,
        )
    except ValueError as exc:
        log.error(
            "Configuration error — cannot start review.\n"
            "  WHAT WENT WRONG : %s\n"
            "  WHAT TO DO      : Fix the value(s) in your .env file and retry.",
            exc,
        )
        sys.exit(1)
    except Exception as exc:
        log.error(
            "Failed to fetch diff from repository.\n"
            "  WHAT WENT WRONG : %s\n"
            "  WHAT TO DO      : See the error details above. Check your network "
            "connection, credentials, branch names, and repository URL.",
            exc,
        )
        sys.exit(1)

    meta = diff_result.metadata
    log.info(
        "Diff ready → %d file(s) changed | %d commit(s) | %d diff lines.",
        len(diff_result.changed_files),
        meta.commit_count,
        len(diff_result.full_diff.splitlines()),
    )

    # ── Step 2: Run agents ───────────────────────────────────────────────────
    log.info("-" * 60)
    log.info("STEP 2/3 → Running AI review agents (parallel) …")
    try:
        reviewer = CodeReviewer()
        report = reviewer.review(diff_result)
    except Exception as exc:
        log.error(
            "Review pipeline failed unexpectedly.\n"
            "  WHAT WENT WRONG : %s\n"
            "  WHAT TO DO      : Check the log file in logs/ for the full stack trace. "
            "Verify OCI credentials and connectivity.",
            exc,
            exc_info=True,
        )
        sys.exit(1)

    log.info("-" * 60)
    log.info("STEP 2/3 → Results summary:")
    log.info("  Overall status : %s", report.overall_status)
    log.info("  Total findings : %d", report.total_findings)
    for sev, count in report.severity_totals.items():
        if count:
            log.info("    %-10s : %d", sev, count)
    log.info("  Elapsed        : %.2fs", report.elapsed_seconds)

    # ── Step 3: Write report ─────────────────────────────────────────────────
    log.info("-" * 60)
    log.info("STEP 3/3 → Generating HTML report …")
    os.makedirs(args.out_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = args.pr_id or f"{args.source.replace('/', '_')}_{timestamp}"
    report_path = os.path.join(args.out_dir, f"review_{slug}.html")

    try:
        generator = ReportGenerator()
        generator.generate(report, report_path)
    except Exception as exc:
        log.error(
            "Failed to generate HTML report.\n"
            "  WHAT WENT WRONG : %s\n"
            "  WHAT TO DO      : Ensure the output directory (%s) is writable.",
            exc, args.out_dir,
        )
        sys.exit(1)

    log.info("Report saved → %s", report_path)
    log.info("=" * 60)


if __name__ == "__main__":
    main()
