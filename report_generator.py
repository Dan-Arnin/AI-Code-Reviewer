# coding: utf-8
"""
report_generator.py
Generates a single, self-contained HTML report from a ReviewReport.
Premium, spacious layout with pastel colours and tabbed sections.
"""

import os
from datetime import datetime
from typing import Dict, List

from reviewer import ReviewReport
from agents.base_agent import AgentResult, Finding

# ---------------------------------------------------------------------------
# Severity config – pastel palette
# ---------------------------------------------------------------------------
SEVERITY_COLORS: Dict[str, str] = {
    "CRITICAL": "#FF6B6B",
    "HIGH":     "#FF9F7F",
    "MEDIUM":   "#FFD166",
    "LOW":      "#74C7EC",
    "INFO":     "#A8D8A8",
}

SEVERITY_BG: Dict[str, str] = {
    "CRITICAL": "#FFF0F0",
    "HIGH":     "#FFF5EE",
    "MEDIUM":   "#FFFBEE",
    "LOW":      "#EEF8FF",
    "INFO":     "#F0FAF0",
}

SEVERITY_BORDER: Dict[str, str] = {
    "CRITICAL": "#FFB3B3",
    "HIGH":     "#FFCBB3",
    "MEDIUM":   "#FFE599",
    "LOW":      "#B3DFF7",
    "INFO":     "#C5E5C5",
}

SEVERITY_ORDER = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]

STATUS_COLORS: Dict[str, str] = {
    "BLOCKED":         "#FF6B6B",
    "NEEDS WORK":      "#FF9F7F",
    "REVIEW REQUIRED": "#FFD166",
    "APPROVED":        "#69D4A0",
}

STATUS_BG: Dict[str, str] = {
    "BLOCKED":         "#FFF0F0",
    "NEEDS WORK":      "#FFF5EE",
    "REVIEW REQUIRED": "#FFFBEE",
    "APPROVED":        "#EEFAF4",
}

AGENT_ICONS = {
    "Security":    "🔒",
    "Style":       "🎨",
    "Logic":       "🧠",
    "Performance": "⚡",
    "Dependency":  "📦",
}


# ---------------------------------------------------------------------------
# CSS – all inlined for a single self-contained file
# ---------------------------------------------------------------------------
_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

:root {
  --bg:        #F8F9FB;
  --surface:   #FFFFFF;
  --surface2:  #F4F5F7;
  --border:    #E8EDF3;
  --text:      #1E2433;
  --text-muted:#6B7A99;
  --text-dim:  #ACB5CC;
  --accent:    #6B7AFF;
  --radius:    12px;
  --radius-sm: 8px;
  --shadow:    0 2px 12px rgba(30,36,51,0.07);
  --shadow-md: 0 4px 24px rgba(30,36,51,0.10);
  --font:      'Inter', system-ui, -apple-system, sans-serif;
  --font-mono: 'JetBrains Mono', 'Fira Code', monospace;
}

html { scroll-behavior: smooth; }
body {
  font-family: var(--font);
  background: var(--bg);
  color: var(--text);
  font-size: 14px;
  line-height: 1.7;
  padding: 0;
  min-height: 100vh;
}

/* ── Page shell ── */
.page-wrapper {
  max-width: 1100px;
  margin: 0 auto;
  padding: 40px 32px 80px;
}

/* ── Header hero ── */
.report-hero {
  background: linear-gradient(135deg, #6B7AFF 0%, #A78BFA 100%);
  border-radius: 20px;
  padding: 40px 44px;
  margin-bottom: 36px;
  color: #fff;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  flex-wrap: wrap;
  gap: 20px;
  box-shadow: 0 8px 40px rgba(107,122,255,0.30);
}
.report-hero h1 {
  font-size: 28px;
  font-weight: 800;
  letter-spacing: -0.02em;
  margin-bottom: 6px;
}
.report-hero .subtitle {
  font-size: 14px;
  opacity: 0.8;
}

/* ── Status pill ── */
.status-pill {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 22px;
  border-radius: 100px;
  font-size: 14px;
  font-weight: 700;
  letter-spacing: 0.04em;
  border: 2px solid;
  white-space: nowrap;
}

/* ── Section card ── */
.section-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 32px 36px;
  margin-bottom: 28px;
  box-shadow: var(--shadow);
}
.section-card + .section-card { margin-top: 0; }

/* ── Section header ── */
.section-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 24px;
  padding-bottom: 16px;
  border-bottom: 2px solid var(--border);
}
.section-icon {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  background: linear-gradient(135deg, #EFF0FF, #E0E2FF);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 19px;
  flex-shrink: 0;
}
.section-title {
  font-size: 17px;
  font-weight: 700;
  color: var(--text);
  letter-spacing: -0.01em;
}
.section-subtitle {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 2px;
}

/* ── Meta grid ── */
.meta-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 14px;
}
.meta-tile {
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 16px 20px;
}
.meta-tile .tile-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.07em;
  margin-bottom: 6px;
}
.meta-tile .tile-value {
  font-size: 20px;
  font-weight: 800;
  color: var(--text);
  letter-spacing: -0.01em;
  line-height: 1.2;
}
.meta-tile .tile-value.mono {
  font-size: 13px;
  font-family: var(--font-mono);
  font-weight: 500;
}

/* ── Severity bar ── */
.sev-bar-wrap {
  height: 12px;
  border-radius: 100px;
  background: var(--surface2);
  overflow: hidden;
  display: flex;
  margin-bottom: 20px;
  border: 1px solid var(--border);
}
.sev-bar-seg { height: 100%; transition: width 0.4s; }

.sev-legend {
  display: flex;
  gap: 18px;
  flex-wrap: wrap;
  margin-bottom: 4px;
}
.sev-legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-muted);
}
.sev-dot {
  width: 10px;
  height: 10px;
  border-radius: 3px;
  flex-shrink: 0;
}

/* ── Summary table ── */
.summary-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  margin-top: 8px;
}
.summary-table th {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.07em;
  color: var(--text-muted);
  padding: 10px 16px;
  background: var(--surface2);
  border-bottom: 1px solid var(--border);
  text-align: left;
}
.summary-table th:first-child { border-radius: 8px 0 0 0; }
.summary-table th:last-child  { border-radius: 0 8px 0 0; }
.summary-table td {
  padding: 14px 16px;
  border-bottom: 1px solid var(--border);
  vertical-align: middle;
  font-size: 13px;
}
.summary-table tr:last-child td { border-bottom: none; }
.summary-table tr:hover td { background: #FAFBFF; }
.agent-name-cell {
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 8px;
}
.agent-icon-sm {
  font-size: 16px;
}

/* ── Severity badges ── */
.sev-badge {
  display: inline-flex;
  align-items: center;
  padding: 3px 10px;
  border-radius: 100px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.04em;
  border: 1.5px solid;
  white-space: nowrap;
  margin-right: 4px;
  margin-bottom: 3px;
}

/* ── Tab bar ── */
.tab-bar {
  display: flex;
  gap: 4px;
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 5px;
  margin-bottom: 24px;
  width: fit-content;
}
.tab-btn {
  padding: 9px 22px;
  border-radius: 9px;
  border: none;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  font-size: 13.5px;
  font-family: var(--font);
  font-weight: 600;
  transition: all 0.2s;
  white-space: nowrap;
}
.tab-btn:hover { color: var(--text); background: rgba(255,255,255,0.7); }
.tab-btn.active {
  background: var(--surface);
  color: var(--accent);
  box-shadow: 0 1px 8px rgba(30,36,51,0.08);
}
.tab-panel { display: none; }
.tab-panel.active { display: block; }

/* ── Notice banners ── */
.notice {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 14px 18px;
  border-radius: var(--radius);
  font-size: 13px;
  font-weight: 500;
  margin-bottom: 24px;
}
.notice-blocking {
  background: #FFF5F0;
  border: 1.5px solid #FFCBB3;
  color: #C45A1E;
}
.notice-suggestions {
  background: #F0F7FF;
  border: 1.5px solid #B3D4FF;
  color: #1E5FAA;
}
.notice-success {
  background: #F0FAF5;
  border: 1.5px solid #B3E5CC;
  color: #1A7A48;
}
.notice-icon { font-size: 18px; flex-shrink: 0; margin-top: 1px; }

/* ── Agent finding card ── */
.agent-section {
  background: var(--surface);
  border: 1.5px solid var(--border);
  border-radius: 14px;
  margin-bottom: 20px;
  overflow: hidden;
  box-shadow: var(--shadow);
}
.agent-section-header {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 18px 24px;
  background: var(--surface2);
  border-bottom: 1px solid var(--border);
  cursor: pointer;
  user-select: none;
}
.agent-section-header:hover { background: #EEEFFE; }
.agent-header-icon {
  width: 36px;
  height: 36px;
  border-radius: 9px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 17px;
  background: var(--surface);
  border: 1px solid var(--border);
  flex-shrink: 0;
}
.agent-header-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--text);
  flex: 1;
}
.agent-header-summary {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 2px;
}
.agent-count-chip {
  padding: 4px 12px;
  border-radius: 100px;
  font-size: 12px;
  font-weight: 700;
  border: 1.5px solid;
  white-space: nowrap;
}
.agent-toggle-icon {
  font-size: 14px;
  color: var(--text-dim);
  transition: transform 0.2s;
}
.agent-body { padding: 20px 24px; }

/* ── Finding card ── */
.finding-card {
  border: 1.5px solid var(--border);
  border-radius: 12px;
  margin-bottom: 16px;
  overflow: hidden;
  transition: box-shadow 0.2s;
}
.finding-card:last-child { margin-bottom: 0; }
.finding-card:hover { box-shadow: var(--shadow-md); }
.finding-card-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 20px;
  border-bottom: 1px solid var(--border);
}
.finding-card-body {
  padding: 18px 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.finding-description {
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
  line-height: 1.5;
}
.finding-location {
  font-size: 12px;
  font-family: var(--font-mono);
  color: var(--text-muted);
  background: var(--surface2);
  padding: 2px 8px;
  border-radius: 5px;
  border: 1px solid var(--border);
  margin-left: auto;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 260px;
}

/* ── Sub-blocks ── */
.finding-block {
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 12px 16px;
}
.finding-block-label {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-dim);
  margin-bottom: 5px;
}
.finding-block-text {
  font-size: 13px;
  color: var(--text);
  line-height: 1.6;
}
.finding-block.fix {
  background: #F0FAF5;
  border-color: #B3E5CC;
}
.finding-block.fix .finding-block-label { color: #1A7A48; }
.finding-block.fix .finding-block-text  { color: #1A4A30; font-weight: 500; }
.finding-block.rule {
  background: #F4F0FF;
  border-color: #C9B3FF;
}
.finding-block.rule .finding-block-label { color: #5A3AAA; }
.finding-block.rule .finding-block-text  { color: #3A226A; }

/* ── Changed files ── */
.file-list { list-style: none; }
.file-list li {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 0;
  border-bottom: 1px solid var(--border);
  font-family: var(--font-mono);
  font-size: 12.5px;
  color: var(--text-muted);
}
.file-list li:last-child { border-bottom: none; }
.file-change-type {
  display: inline-flex;
  align-items: center;
  padding: 2px 9px;
  border-radius: 100px;
  font-size: 11px;
  font-weight: 700;
  flex-shrink: 0;
}
.change-A { background: #F0FAF5; color: #1A7A48; border: 1px solid #B3E5CC; }
.change-M { background: #EFF2FF; color: #3B4FD4; border: 1px solid #B3BEFF; }
.change-D { background: #FFF0F0; color: #C42A2A; border: 1px solid #FFBBBB; }
.change-R { background: #FFFBEE; color: #A07A00; border: 1px solid #FFE599; }

/* ── Diff block (Legacy) ── */
.diff-block {
  background: #1A1D27;
  border-radius: var(--radius);
  padding: 20px;
  overflow-x: auto;
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.7;
  border: 1px solid #2E3250;
  max-height: 440px;
  overflow-y: auto;
  margin-top: 18px;
}

/* ── Side-by-Side Diff ── */
.diff-container {
  background: #ffffff;
  border: 1px solid #000000;
  border-radius: 4px;
  overflow-x: auto;
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.5;
  max-height: 500px;
  overflow-y: auto;
  margin-top: 18px;
  color: #000;
}
.sbs-diff-table {
  width: 100%;
  border-spacing: 0;
  border-collapse: collapse;
}
.sbs-diff-table td {
  padding: 0 4px;
  vertical-align: top;
  white-space: pre-wrap;
}
.sbs-diff-table .ln {
  width: 40px;
  color: #666;
  background: #f5f5f5;
  text-align: right;
  padding-right: 8px;
  user-select: none;
  border-right: 1px solid #ddd;
  border-left: 1px solid #ddd;
}
.sbs-diff-table .diff-add { background: #e6ffec; color: #000; border-right: 1px solid #ddd; }
.sbs-diff-table .diff-del { background: #ffebe9; color: #000; border-right: 1px solid #ddd; }
.sbs-diff-table .diff-ctx { color: #000; border-right: 1px solid #ddd; }
.sbs-diff-table .diff-empty { background: #fafafa; border-right: 1px solid #ddd; }
.sbs-diff-table .diff-file-header { background: #000; color: #fff; font-weight: bold; padding: 6px 8px; border: 1px solid #000; }
.sbs-diff-table .diff-hunk-header { background: #e0e0e0; color: #000; font-style: italic; padding: 4px 8px; border: 1px solid #ccc; }

/* Single view mode code block */
.single-branch-code {
  background: #ffffff;
  color: #000000;
  border: 1px solid #000;
  padding: 15px;
  overflow-x: auto;
  overflow-y: auto;
  max-height: 500px;
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.5;
  white-space: pre;
}

/* ── Footer ── */
.report-footer {
  margin-top: 48px;
  text-align: center;
  font-size: 12px;
  color: var(--text-dim);
  padding-bottom: 20px;
}
.report-footer strong { color: var(--text-muted); }

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #D0D5E8; border-radius: 3px; }
"""

_JS = """
function switchTab(id) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  document.getElementById('tab-btn-' + id).classList.add('active');
  document.getElementById('tab-panel-' + id).classList.add('active');
}
function toggleAgent(id) {
  const body = document.getElementById(id);
  const icon = document.getElementById(id + '-icon');
  if (!body) return;
  const open = body.style.display !== 'none';
  body.style.display = open ? 'none' : 'block';
  if (icon) icon.style.transform = open ? 'rotate(0deg)' : 'rotate(180deg)';
}
"""


# ---------------------------------------------------------------------------
# Report generator
# ---------------------------------------------------------------------------

class ReportGenerator:
    """Converts a ReviewReport into a single self-contained HTML file."""

    def generate(self, report: ReviewReport, output_path: str) -> str:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        html = self._render_html(report)
        with open(output_path, "w", encoding="utf-8") as fh:
            fh.write(html)
        return output_path

    # ------------------------------------------------------------------
    # Top-level renderer
    # ------------------------------------------------------------------

    def _render_html(self, report: ReviewReport) -> str:
        meta         = report.diff_result.metadata
        status       = report.overall_status
        status_color = STATUS_COLORS.get(status, "#9E9E9E")
        status_bg    = STATUS_BG.get(status, "#F5F5F5")
        generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        repo_name    = meta.repo_url.split("/")[-1].replace(".git", "")

        total_blocking   = sum(len(r.findings)    for r in report.agent_results)
        total_suggestions= sum(len(r.suggestions) for r in report.agent_results)

        sev_bar   = self._render_severity_bar(report)
        sev_legend= self._render_severity_legend(report)
        sum_table = self._render_summary_table(report)
        meta_grid = self._render_meta_grid(meta, report, total_blocking, total_suggestions)

        # Tab content
        blocking_html     = self._render_tab_blocking(report, total_blocking)
        suggestions_html  = self._render_tab_suggestions(report, total_suggestions)
        changed_files_html= self._render_changed_files(report)

        if meta.target_branch:
            page_title = f"Code Review — {meta.source_branch} → {meta.target_branch}"
            subtitle_text = f"{repo_name} &nbsp;·&nbsp; {meta.source_branch} → {meta.target_branch} &nbsp;·&nbsp; {generated_at}"
        else:
            page_title = f"Code Review — {meta.source_branch}"
            subtitle_text = f"{repo_name} &nbsp;·&nbsp; {meta.source_branch} &nbsp;·&nbsp; {generated_at}"

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{page_title}</title>
<style>{_CSS}</style>
<script>{_JS}</script>
</head>
<body>

<div class="page-wrapper">

  <!-- ═══ Hero ═══ -->
  <div class="report-hero">
    <div>
      <h1>🔍 Code Review Report</h1>
      <div class="subtitle">{subtitle_text}</div>
    </div>
    <div class="status-pill" style="background:{status_bg};color:{status_color};border-color:{status_color};">
      {self._status_icon(status)} {status}
    </div>
  </div>

  <!-- ═══ Meta tiles ═══ -->
  <div class="section-card">
    <div class="section-header">
      <div class="section-icon">📋</div>
      <div>
        <div class="section-title">Review Summary</div>
        <div class="section-subtitle">Key metrics for this review run</div>
      </div>
    </div>
    {meta_grid}
  </div>

  <!-- ═══ Severity Overview ═══ -->
  <div class="section-card">
    <div class="section-header">
      <div class="section-icon">📊</div>
      <div>
        <div class="section-title">Severity Breakdown</div>
        <div class="section-subtitle">Distribution across all agents</div>
      </div>
    </div>
    {sev_legend}
    {sev_bar}
    {sum_table}
  </div>

  <!-- ═══ Findings Tabs ═══ -->
  <div class="section-card">
    <div class="section-header">
      <div class="section-icon">🤖</div>
      <div>
        <div class="section-title">Agent Findings</div>
        <div class="section-subtitle">Expand each agent to see individual findings</div>
      </div>
    </div>

    <div class="tab-bar">
      <button class="tab-btn active" id="tab-btn-blocking"     onclick="switchTab('blocking')">🚨 Critical Issues ({total_blocking})</button>
      <button class="tab-btn"        id="tab-btn-suggestions"  onclick="switchTab('suggestions')">💡 Suggestions ({total_suggestions})</button>
    </div>

    <div class="tab-panel active" id="tab-panel-blocking">
      {blocking_html}
    </div>
    <div class="tab-panel" id="tab-panel-suggestions">
      {suggestions_html}
    </div>
  </div>

  <!-- ═══ Changed Files ═══ -->
  {changed_files_html}

</div><!-- /page-wrapper -->

<div class="report-footer">
  Generated by <strong>AI Code Review System</strong> &nbsp;·&nbsp; {generated_at}<br/>
  <span style="opacity:0.7;">Powered by OCI Generative AI / Anthropic Claude</span>
</div>

</body>
</html>"""

    # ------------------------------------------------------------------
    # Meta grid
    # ------------------------------------------------------------------

    def _render_meta_grid(self, meta, report, total_blocking, total_suggestions) -> str:
        repo_name = meta.repo_url.split("/")[-1].replace(".git", "")
        tiles = [
            ("Repository",      repo_name,                     "mono", ""),
            ("Source Branch",   meta.source_branch,            "mono", ""),
            ("Target Branch",   meta.target_branch if meta.target_branch else "N/A (Single Branch)",            "mono", ""),
            ("Commits",         str(meta.commit_count),        "",     ""),
            ("Files Changed",   str(len(report.diff_result.changed_files)), "", ""),
            ("Blocking Issues", str(total_blocking),           "",     "#FF9F7F"),
            ("Suggestions",     str(total_suggestions),        "",     "#74C7EC"),
            ("Analysis Time",   f"{report.elapsed_seconds}s", "",     ""),
        ]
        items = []
        for label, value, extra_cls, color in tiles:
            style = f'style="color:{color};"' if color else ""
            items.append(
                f'<div class="meta-tile">'
                f'<div class="tile-label">{label}</div>'
                f'<div class="tile-value {extra_cls}" {style}>{value}</div>'
                f'</div>'
            )
        return f'<div class="meta-grid">{"".join(items)}</div>'

    # ------------------------------------------------------------------
    # Severity bar & legend
    # ------------------------------------------------------------------

    def _render_severity_legend(self, report: ReviewReport) -> str:
        totals = report.severity_totals
        items = []
        for sev in SEVERITY_ORDER:
            count = totals.get(sev, 0)
            color = SEVERITY_COLORS[sev]
            items.append(
                f'<div class="sev-legend-item">'
                f'<div class="sev-dot" style="background:{color};"></div>'
                f'{sev} ({count})'
                f'</div>'
            )
        return f'<div class="sev-legend">{"".join(items)}</div>'

    def _render_severity_bar(self, report: ReviewReport) -> str:
        totals    = report.severity_totals
        grand_tot = max(sum(totals.values()), 1)
        segs = []
        for sev in SEVERITY_ORDER:
            count = totals.get(sev, 0)
            if count:
                pct   = count / grand_tot * 100
                color = SEVERITY_COLORS[sev]
                segs.append(
                    f'<div class="sev-bar-seg" title="{sev}: {count}" '
                    f'style="width:{pct:.1f}%;background:{color};"></div>'
                )
        inner = "\n".join(segs) if segs else \
            '<div class="sev-bar-seg" style="width:100%;background:#E8EDF3;"></div>'
        return f'<div class="sev-bar-wrap">{inner}</div>'

    # ------------------------------------------------------------------
    # Summary table
    # ------------------------------------------------------------------

    def _render_summary_table(self, report: ReviewReport) -> str:
        rows = []
        for ar in report.agent_results:
            counts = ar.severity_counts
            badges = " ".join(
                f'<span class="sev-badge" style="background:{SEVERITY_BG[sev]};'
                f'color:{SEVERITY_COLORS[sev]};border-color:{SEVERITY_BORDER[sev]};">'
                f'{sev} {counts[sev]}</span>'
                for sev in SEVERITY_ORDER if counts.get(sev, 0) > 0
            ) or f'<span style="color:var(--text-dim);font-size:12px;">None</span>'

            icon = AGENT_ICONS.get(ar.agent_name, "🤖")
            rows.append(
                f"<tr>"
                f"<td><div class='agent-name-cell'><span class='agent-icon-sm'>{icon}</span>{ar.agent_name}</div></td>"
                f"<td>{badges}</td>"
                f"<td style='color:var(--text-muted);font-size:12.5px;max-width:340px;'>{ar.summary}</td>"
                f"</tr>"
            )
        return f"""
<div style="overflow-x:auto;border:1px solid var(--border);border-radius:var(--radius);margin-top:12px;">
<table class="summary-table">
  <thead><tr><th>Agent</th><th>Findings</th><th>Summary</th></tr></thead>
  <tbody>{"".join(rows)}</tbody>
</table>
</div>"""

    # ------------------------------------------------------------------
    # Tabs
    # ------------------------------------------------------------------

    def _render_tab_blocking(self, report: ReviewReport, total: int) -> str:
        if total == 0:
            return self._notice(
                "success",
                "✅",
                "No critical or high-severity issues found.",
                "All CRITICAL and HIGH checks passed. Review suggestions for optional improvements."
            )
        notice = self._notice(
            "blocking",
            "🚨",
            f"{total} blocking issue(s) found — review required before merge.",
            "Only CRITICAL and HIGH severity findings are shown here (max 10 per agent). These must be addressed."
        )
        agent_blocks = "".join(
            self._render_agent_block(ar, use_suggestions=False)
            for ar in report.agent_results
            if ar.findings
        )
        return notice + agent_blocks

    def _render_tab_suggestions(self, report: ReviewReport, total: int) -> str:
        if total == 0:
            return self._notice(
                "success",
                "💡",
                "No suggestions.",
                "No MEDIUM, LOW, or INFO findings were raised by any agent."
            )
        notice = self._notice(
            "suggestions",
            "💡",
            f"{total} suggestion(s) — optional improvements.",
            "These are MEDIUM, LOW, and INFO findings. They are not required for merge but are worth considering."
        )
        agent_blocks = "".join(
            self._render_agent_block(ar, use_suggestions=True)
            for ar in report.agent_results
            if ar.suggestions
        )
        return notice + agent_blocks

    @staticmethod
    def _notice(kind: str, icon: str, title: str, body: str) -> str:
        return (
            f'<div class="notice notice-{kind}">'
            f'<span class="notice-icon">{icon}</span>'
            f'<div><strong>{title}</strong><br/><span style="opacity:0.85;">{body}</span></div>'
            f'</div>'
        )

    # ------------------------------------------------------------------
    # Agent block (collapsible)
    # ------------------------------------------------------------------

    def _render_agent_block(self, ar: AgentResult, use_suggestions: bool) -> str:
        findings_list = ar.suggestions if use_suggestions else ar.findings
        count         = len(findings_list)
        icon          = AGENT_ICONS.get(ar.agent_name, "🤖")
        label         = "suggestion(s)" if use_suggestions else "issue(s)"
        uid           = f"agent-{ar.agent_name.lower().replace(' ', '-')}-{'sug' if use_suggestions else 'blk'}"

        # Determine chip colour
        if not use_suggestions and count > 0:
            has_crit = any(f.severity == "CRITICAL" for f in findings_list)
            chip_color  = SEVERITY_COLORS["CRITICAL"] if has_crit else SEVERITY_COLORS["HIGH"]
            chip_bg     = SEVERITY_BG["CRITICAL"]     if has_crit else SEVERITY_BG["HIGH"]
            chip_border = SEVERITY_BORDER["CRITICAL"] if has_crit else SEVERITY_BORDER["HIGH"]
        else:
            chip_color  = SEVERITY_COLORS["LOW"]
            chip_bg     = SEVERITY_BG["LOW"]
            chip_border = SEVERITY_BORDER["LOW"]

        findings_html = (
            "".join(self._render_finding_card(f) for f in findings_list)
            if findings_list
            else f'<p style="color:var(--text-dim);font-size:13px;padding:8px 0;">No {label} found.</p>'
        )

        return f"""
<div class="agent-section">
  <div class="agent-section-header" onclick="toggleAgent('{uid}')">
    <div class="agent-header-icon">{icon}</div>
    <div style="flex:1;">
      <div class="agent-header-title">{ar.agent_name}</div>
      <div class="agent-header-summary">{ar.summary}</div>
    </div>
    <span class="agent-count-chip"
          style="background:{chip_bg};color:{chip_color};border-color:{chip_border};">
      {count} {label}
    </span>
    <span class="agent-toggle-icon" id="{uid}-icon" style="transform:rotate(180deg);">▾</span>
  </div>
  <div class="agent-body" id="{uid}">
    {findings_html}
  </div>
</div>"""

    # ------------------------------------------------------------------
    # Finding card
    # ------------------------------------------------------------------

    def _render_finding_card(self, f: Finding) -> str:
        sev     = f.severity
        color   = SEVERITY_COLORS.get(sev, "#9E9E9E")
        bg      = SEVERITY_BG.get(sev, "#F5F5F5")
        border  = SEVERITY_BORDER.get(sev, "#E0E0E0")
        loc     = f"{f.file_path or 'general'}  {f.line_reference}".strip()

        explanation_block = (
            f'<div class="finding-block">'
            f'<div class="finding-block-label">Why this matters</div>'
            f'<div class="finding-block-text">{f.explanation}</div>'
            f'</div>'
        ) if f.explanation else ""

        fix_block = (
            f'<div class="finding-block fix">'
            f'<div class="finding-block-label">💚 Suggested Fix</div>'
            f'<div class="finding-block-text">{f.suggestion}</div>'
            f'</div>'
        ) if f.suggestion else ""

        rule_block = (
            f'<div class="finding-block rule">'
            f'<div class="finding-block-label">📐 Best Practice</div>'
            f'<div class="finding-block-text">{f.best_practice}</div>'
            f'</div>'
        ) if f.best_practice else ""

        return f"""
<div class="finding-card" style="border-color:{border};">
  <div class="finding-card-header" style="background:{bg};">
    <span class="sev-badge"
          style="background:{bg};color:{color};border-color:{border};">
      {sev}
    </span>
    <span class="finding-description">{f.description}</span>
    <span class="finding-location" title="{loc}">{loc}</span>
  </div>
  <div class="finding-card-body">
    {explanation_block}
    {fix_block}
    {rule_block}
  </div>
</div>"""

    # ------------------------------------------------------------------
    # Changed files
    # ------------------------------------------------------------------

    def _render_changed_files(self, report: ReviewReport) -> str:
        files = report.diff_result.changed_files
        if not files:
            return ""

        items = []
        for f in files:
            label = {"A": "+ Added", "D": "− Deleted", "M": "~ Modified", "R": "⇒ Renamed"}.get(
                f.change_type, f.change_type
            )
            items.append(
                f'<li><span class="file-change-type change-{f.change_type}">{label}</span>{f.path}</li>'
            )

        # Determine if single branch mode
        is_single_branch = not bool(report.diff_result.metadata.target_branch)

        diff_lines_raw = report.diff_result.full_diff.splitlines()
        trunc_msg = ""
        if len(diff_lines_raw) > 2000:
            diff_lines_raw = diff_lines_raw[:2000]
            trunc_msg = '<p style="color:var(--text-dim);font-size:11px;margin-top:8px;">⚠ Code truncated at 2000 lines</p>'

        if is_single_branch:
            # Single column pure code
            clean_lines = []
            for line in diff_lines_raw:
                # Strip leading '+' from single branch simulation
                if line.startswith('+++') or line.startswith('---'): continue
                if line.startswith('@@'): continue
                val = line[1:] if line.startswith('+') else line
                clean_lines.append(val.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
            
            code_html = "\n".join(clean_lines)
            viewer_html = f'<div class="single-branch-code">{code_html}</div>'
            viewer_title = "Source Code"
        else:
            # Side-by-side diff
            html_rows = []
            html_rows.append('<table class="sbs-diff-table">')
            left_ln = 0
            right_ln = 0
            
            for line in diff_lines_raw:
                if line.startswith('---') or line.startswith('+++'):
                    esc = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    html_rows.append(f'<tr><td colspan="4" class="diff-file-header">{esc}</td></tr>')
                    continue
                if line.startswith('@@'):
                    esc = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    html_rows.append(f'<tr><td colspan="4" class="diff-hunk-header">{esc}</td></tr>')
                    # Hunk parsing could reset lines here if needed, keeping simple for now
                    continue
                
                content = line[1:] if len(line) > 0 else ""
                esc = content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                
                if line.startswith('-'):
                    left_ln += 1
                    html_rows.append(f'<tr><td class="ln">{left_ln}</td><td class="diff-del">{esc}</td><td class="ln"></td><td class="diff-empty"></td></tr>')
                elif line.startswith('+'):
                    right_ln += 1
                    html_rows.append(f'<tr><td class="ln"></td><td class="diff-empty"></td><td class="ln">{right_ln}</td><td class="diff-add">{esc}</td></tr>')
                else:
                    left_ln += 1
                    right_ln += 1
                    # context uses full line in traditional diffs (space prefixed)
                    ctx_esc = line[1:].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    html_rows.append(f'<tr><td class="ln">{left_ln}</td><td class="diff-ctx">{ctx_esc}</td><td class="ln">{right_ln}</td><td class="diff-ctx">{ctx_esc}</td></tr>')
            
            html_rows.append('</table>')
            viewer_html = f'<div class="diff-container">{"".join(html_rows)}</div>'
            viewer_title = "Side-by-Side Diff"

        return f"""
<div class="section-card">
  <div class="section-header">
    <div class="section-icon">📁</div>
    <div>
      <div class="section-title">Changed Files ({len(files)})</div>
      <div class="section-subtitle">Files modified in this merge request</div>
    </div>
  </div>
  <ul class="file-list">{"".join(items)}</ul>

  <div style="margin-top:24px;">
    <div class="section-header" style="margin-bottom:12px;padding-bottom:12px;">
      <div class="section-icon" style="font-size:15px;">📄</div>
      <div>
        <div class="section-title" style="font-size:14px;">{viewer_title}</div>
        <div class="section-subtitle">Code Viewer</div>
      </div>
    </div>
    {viewer_html}
    {trunc_msg}
  </div>
</div>"""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _status_icon(status: str) -> str:
        return {
            "BLOCKED":         "🚫",
            "NEEDS WORK":      "⚠️",
            "REVIEW REQUIRED": "🔍",
            "APPROVED":        "✅",
        }.get(status, "🔍")
