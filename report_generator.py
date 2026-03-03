# coding: utf-8
"""
report_generator.py
Generates a single, self-contained HTML report from a ReviewReport.
"""

import os
from datetime import datetime
from typing import Dict, List

from reviewer import ReviewReport
from agents.base_agent import AgentResult, Finding

# ---------------------------------------------------------------------------
# Severity styling
# ---------------------------------------------------------------------------
SEVERITY_COLORS: Dict[str, str] = {
    "CRITICAL": "#ff2d2d",
    "HIGH":     "#ff7e2d",
    "MEDIUM":   "#f5c518",
    "LOW":      "#4db6ff",
    "INFO":     "#9e9e9e",
}

SEVERITY_ORDER = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]

STATUS_COLORS: Dict[str, str] = {
    "BLOCKED":          "#ff2d2d",
    "NEEDS WORK":       "#ff7e2d",
    "REVIEW REQUIRED":  "#f5c518",
    "APPROVED":         "#2dcc70",
}


# ---------------------------------------------------------------------------
# Report generator
# ---------------------------------------------------------------------------

class ReportGenerator:
    """Converts a ReviewReport into a single self-contained HTML file."""

    def generate(self, report: ReviewReport, output_path: str) -> str:
        """
        Write the HTML report to *output_path*.

        Args:
            report:      The aggregated ReviewReport.
            output_path: Absolute path where the .html file will be saved.

        Returns:
            Absolute path to the written file.
        """
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        html = self._render_html(report)
        with open(output_path, "w", encoding="utf-8") as fh:
            fh.write(html)
        return output_path

    # ------------------------------------------------------------------
    # HTML rendering helpers
    # ------------------------------------------------------------------

    def _render_html(self, report: ReviewReport) -> str:
        meta = report.diff_result.metadata
        status = report.overall_status
        status_color = STATUS_COLORS.get(status, "#9e9e9e")
        generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        agent_sections = "\n".join(
            self._render_agent_section(r) for r in report.agent_results
        )

        summary_table = self._render_summary_table(report)
        severity_bar = self._render_severity_bar(report)

        changed_files_html = self._render_changed_files(report)

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Code Review Report – {meta.source_branch} → {meta.target_branch}</title>
<style>
  :root {{
    --bg: #0f1117; --surface: #1a1d27; --surface2: #22263a;
    --border: #2e3250; --text: #e8eaf6; --muted: #7a7f9d;
    --accent: #5c6bc0; --radius: 8px; --font: 'Segoe UI', system-ui, sans-serif;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg); color: var(--text); font-family: var(--font);
          font-size: 14px; line-height: 1.6; padding: 24px; }}
  h1 {{ font-size: 22px; font-weight: 700; margin-bottom: 4px; }}
  h2 {{ font-size: 16px; font-weight: 600; margin: 20px 0 10px; color: var(--accent); }}
  h3 {{ font-size: 14px; font-weight: 600; margin: 12px 0 6px; }}
  .card {{ background: var(--surface); border: 1px solid var(--border);
           border-radius: var(--radius); padding: 16px; margin-bottom: 16px; }}
  .meta-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px,1fr));
                gap: 12px; margin: 12px 0; }}
  .meta-item {{ background: var(--surface2); border-radius: var(--radius);
                padding: 10px 14px; }}
  .meta-item label {{ display: block; font-size: 11px; color: var(--muted);
                      text-transform: uppercase; letter-spacing: .05em; }}
  .meta-item span {{ font-size: 13px; font-weight: 600; }}
  .status-badge {{
    display: inline-block; padding: 6px 18px; border-radius: 20px;
    font-weight: 700; font-size: 13px; letter-spacing: .05em;
    background: {status_color}22; color: {status_color};
    border: 1.5px solid {status_color};
  }}
  /* Summary table */
  table {{ width: 100%; border-collapse: collapse; }}
  th, td {{ text-align: left; padding: 8px 12px; border-bottom: 1px solid var(--border); }}
  th {{ font-size: 11px; text-transform: uppercase; color: var(--muted); }}
  tr:hover td {{ background: var(--surface2); }}
  /* Severity badges */
  .sev {{ display: inline-block; padding: 2px 8px; border-radius: 12px;
          font-size: 11px; font-weight: 700; }}
  .sev-CRITICAL {{ background: #ff2d2d22; color: #ff2d2d; border: 1px solid #ff2d2d; }}
  .sev-HIGH     {{ background: #ff7e2d22; color: #ff7e2d; border: 1px solid #ff7e2d; }}
  .sev-MEDIUM   {{ background: #f5c51822; color: #f5c518; border: 1px solid #f5c518; }}
  .sev-LOW      {{ background: #4db6ff22; color: #4db6ff; border: 1px solid #4db6ff; }}
  .sev-INFO     {{ background: #9e9e9e22; color: #9e9e9e; border: 1px solid #9e9e9e; }}
  /* Severity bar */
  .bar-wrap {{ height: 10px; border-radius: 5px; overflow: hidden; display: flex;
               margin: 10px 0; background: var(--surface2); }}
  .bar-seg {{ height: 100%; transition: width .3s; }}
  /* Agent sections */
  details {{ background: var(--surface); border: 1px solid var(--border);
             border-radius: var(--radius); margin-bottom: 10px; overflow: hidden; }}
  summary {{ padding: 12px 16px; cursor: pointer; font-weight: 600;
             display: flex; justify-content: space-between; align-items: center;
             background: var(--surface2); }}
  summary:hover {{ background: var(--surface); }}
   .finding {{ background: var(--surface2); border-radius: 6px; padding: 12px;
              margin: 8px 16px; border-left: 3px solid var(--border); }}
  .finding-header {{ display: flex; align-items: center; gap: 10px; margin-bottom: 6px; }}
  .file-path {{ font-family: monospace; font-size: 12px; color: var(--muted); }}
  .desc {{ margin: 4px 0; font-weight: 600; }}
  .explanation {{ margin: 6px 0; font-size: 13px; color: var(--text); background: var(--surface); padding: 8px; border-radius: 4px; border: 1px solid var(--border); }}
  .best-practice {{ font-size: 12px; color: var(--accent); margin-top: 8px; font-weight: 600; display: inline-block; padding: 2px 6px; background: rgba(92,107,192,0.1); border-radius: 4px; border: 1px solid rgba(92,107,192,0.2); }}
  .suggestion {{ color: #2dcc70; font-size: 13px; margin-top: 8px; font-weight: 600; }}
  /* Changed files */
  .file-list {{ list-style: none; }}
  .file-list li {{ padding: 4px 0; font-family: monospace; font-size: 12px;
                   color: var(--muted); border-bottom: 1px solid var(--border); }}
  .file-list li:last-child {{ border: none; }}
  .change-A {{ color: #2dcc70; }} .change-M {{ color: #4db6ff; }}
  .change-D {{ color: #ff2d2d; }} .change-R {{ color: #f5c518; }}
  /* Diff block */
  pre {{ background: #0a0c14; border-radius: 6px; padding: 12px; overflow-x: auto;
         font-size: 11px; line-height: 1.5; border: 1px solid var(--border);
         max-height: 400px; overflow-y: auto; }}
  .diff-add {{ color: #2dcc70; }} .diff-del {{ color: #ff4d4d; }}
  .diff-hunk {{ color: var(--accent); }}
  footer {{ margin-top: 32px; text-align: center; font-size: 11px; color: var(--muted); }}
</style>
</head>
<body>

<!-- ===== Header ===== -->
<div class="card">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:12px;">
    <div>
      <h1>🔍 Code Review Report</h1>
      <p style="color:var(--muted);margin-top:4px;">
        Auto-generated by OCI Gen AI Code Reviewer &nbsp;·&nbsp; {generated_at}
      </p>
    </div>
    <div class="status-badge">{status}</div>
  </div>

  <div class="meta-grid">
    <div class="meta-item">
      <label>Repository</label>
      <span title="{meta.repo_url}">{meta.repo_url.split('/')[-1].replace('.git','')}</span>
    </div>
    <div class="meta-item">
      <label>Source Branch (MR)</label>
      <span>{meta.source_branch}</span>
    </div>
    <div class="meta-item">
      <label>Target Branch (Prod)</label>
      <span>{meta.target_branch}</span>
    </div>
    <div class="meta-item">
      <label>Commits</label>
      <span>{meta.commit_count}</span>
    </div>
    <div class="meta-item">
      <label>Total Findings</label>
      <span>{report.total_findings}</span>
    </div>
    <div class="meta-item">
      <label>Analysis Time</label>
      <span>{report.elapsed_seconds}s</span>
    </div>
  </div>
</div>

<!-- ===== Severity Overview ===== -->
<div class="card">
  <h2>📊 Severity Overview</h2>
  {severity_bar}
  {summary_table}
</div>

<!-- ===== Agent Results ===== -->
<h2>🤖 Agent Findings</h2>
{agent_sections}

<!-- ===== Changed Files ===== -->
{changed_files_html}

<footer>Generated by OCI Gen AI Code Review System &nbsp;·&nbsp; {generated_at}</footer>
</body>
</html>"""

    def _render_severity_bar(self, report: ReviewReport) -> str:
        totals = report.severity_totals
        grand_total = max(sum(totals.values()), 1)
        segments = []
        for sev in SEVERITY_ORDER:
            count = totals.get(sev, 0)
            if count:
                pct = count / grand_total * 100
                color = SEVERITY_COLORS[sev]
                segments.append(
                    f'<div class="bar-seg" title="{sev}: {count}" '
                    f'style="width:{pct:.1f}%;background:{color};"></div>'
                )
        inner = "\n".join(segments) if segments else '<div class="bar-seg" style="width:100%;background:var(--surface2);"></div>'
        return f'<div class="bar-wrap">{inner}</div>'

    def _render_summary_table(self, report: ReviewReport) -> str:
        rows = []
        for agent_result in report.agent_results:
            counts = agent_result.severity_counts
            badges = " ".join(
                f'<span class="sev sev-{sev}">{sev[0]} {counts[sev]}</span>'
                for sev in SEVERITY_ORDER if counts.get(sev, 0) > 0
            ) or '<span style="color:var(--muted)">none</span>'
            rows.append(
                f"<tr><td>{agent_result.agent_name}</td>"
                f"<td>{badges}</td>"
                f"<td style='color:var(--muted);font-size:12px;'>{agent_result.summary}</td></tr>"
            )
        return f"""<table>
  <thead><tr><th>Agent</th><th>Findings</th><th>Summary</th></tr></thead>
  <tbody>{"".join(rows)}</tbody>
</table>"""

    def _render_agent_section(self, result: AgentResult) -> str:
        counts = result.severity_counts
        total = sum(counts.values())
        badge_color = (
            SEVERITY_COLORS["CRITICAL"] if counts.get("CRITICAL")
            else SEVERITY_COLORS["HIGH"] if counts.get("HIGH")
            else SEVERITY_COLORS["MEDIUM"] if counts.get("MEDIUM")
            else SEVERITY_COLORS["LOW"] if counts.get("LOW")
            else "#2dcc70"
        )
        findings_html = (
            "\n".join(self._render_finding(f) for f in result.findings)
            if result.findings
            else '<p style="color:var(--muted);padding:12px 16px;">No issues found.</p>'
        )
        return f"""<details>
  <summary>
    <span>{result.agent_name}</span>
    <span style="color:{badge_color};font-size:12px;">{total} issue(s)</span>
  </summary>
  <p style="padding:10px 16px;color:var(--muted);font-size:12px;">{result.summary}</p>
  {findings_html}
</details>"""

    def _render_finding(self, finding: Finding) -> str:
        sev = finding.severity
        
        explanation_html = f'<div class="explanation"><strong>Explanation:</strong> {finding.explanation}</div>' if finding.explanation else ''
        best_practice_html = f'<div class="best-practice">🎯 {finding.best_practice}</div>' if finding.best_practice else ''
        
        return f"""<div class="finding" style="border-left-color:{SEVERITY_COLORS.get(sev,'#9e9e9e')};">
  <div class="finding-header">
    <span class="sev sev-{sev}">{sev}</span>
    <span class="file-path">{finding.file_path or 'general'} {finding.line_reference}</span>
  </div>
  <p class="desc">{finding.description}</p>
  {explanation_html}
  <p class="suggestion">💡 {finding.suggestion}</p>
  {best_practice_html}
</div>"""

    def _render_changed_files(self, report: ReviewReport) -> str:
        files = report.diff_result.changed_files
        if not files:
            return ""

        items = []
        for f in files:
            type_class = f"change-{f.change_type}"
            type_label = {"A": "+ Added", "D": "- Deleted", "M": "~ Modified", "R": "⇒ Renamed"}.get(
                f.change_type, f.change_type
            )
            items.append(
                f'<li><span class="{type_class}">{type_label}</span>&nbsp;&nbsp;{f.path}</li>'
            )

        # Render the full unified diff in a diff-highlighted block
        diff_lines = []
        for line in report.diff_result.full_diff.splitlines()[:500]:
            escaped = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            if line.startswith("+") and not line.startswith("+++"):
                diff_lines.append(f'<span class="diff-add">{escaped}</span>')
            elif line.startswith("-") and not line.startswith("---"):
                diff_lines.append(f'<span class="diff-del">{escaped}</span>')
            elif line.startswith("@@"):
                diff_lines.append(f'<span class="diff-hunk">{escaped}</span>')
            else:
                diff_lines.append(escaped)
        diff_html = "\n".join(diff_lines)
        truncation_note = (
            '<p style="color:var(--muted);font-size:11px;padding:4px 0;">'
            '(diff truncated at 500 lines)</p>'
            if len(report.diff_result.full_diff.splitlines()) > 500
            else ""
        )

        return f"""<div class="card">
  <h2>📁 Changed Files ({len(files)})</h2>
  <ul class="file-list">{"".join(items)}</ul>
  <h3 style="margin-top:14px;">Full Diff</h3>
  {truncation_note}
  <pre><code>{diff_html}</code></pre>
</div>"""
