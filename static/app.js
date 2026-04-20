/**
 * app.js — Code Reviewer Dashboard
 * Vanilla JS, no dependencies.
 */

// ─── State ──────────────────────────────────────────────────────────────────
const state = {
  currentView:   "reports",
  reports: {
    items:       [],
    page:        1,
    pageSize:    20,
    totalPages:  1,
    total:       0,
    loading:     false,
    from:        "",
    to:          "",
  },
  config:        null,
  activeAgent:   "security",
  modal: {
    open:       false,
    objectName: "",
  },
};

// ─── DOM helpers ─────────────────────────────────────────────────────────────
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

// ─── Toast ────────────────────────────────────────────────────────────────────
function toast(msg, type = "info", duration = 4000) {
  const icons = { success: "✅", error: "❌", info: "ℹ️" };
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.innerHTML = `<span>${icons[type] || "ℹ️"}</span><span>${msg}</span>`;
  $("#toast-container").appendChild(el);
  setTimeout(() => el.remove(), duration);
}

// ─── View router ──────────────────────────────────────────────────────────────
function navigateTo(view) {
  state.currentView = view;
  $$(".view").forEach(v => v.classList.remove("active"));
  $$(".nav-item").forEach(n => n.classList.remove("active"));
  $(`#view-${view}`)?.classList.add("active");
  $(`[data-view="${view}"]`)?.classList.add("active");

  if (view === "reports") loadReports();
  if (view === "settings") loadConfig();
}

// ─── Reports ──────────────────────────────────────────────────────────────────
async function loadReports(page = null) {
  if (page !== null) state.reports.page = page;
  state.reports.loading = true;
  showReportsLoading(true);

  const params = new URLSearchParams({
    page:      state.reports.page,
    page_size: state.reports.pageSize,
  });
  if (state.reports.from) params.set("from", state.reports.from);
  if (state.reports.to)   params.set("to",   state.reports.to);

  try {
    const res  = await fetch(`/api/reports?${params}`);
    const data = await res.json();

    if (!res.ok) throw new Error(data.error || "Failed to load reports");

    state.reports.items      = data.items || [];
    state.reports.total      = data.total || 0;
    state.reports.totalPages = data.total_pages || 1;
    state.reports.page       = data.page || 1;

    renderReports();
    renderPagination();
  } catch (err) {
    toast(err.message, "error");
    showReportsEmpty("Failed to load from OCI: " + err.message);
  } finally {
    state.reports.loading = false;
    showReportsLoading(false);
  }
}

function showReportsLoading(show) {
  const loading = $("#reports-loading");
  const list    = $("#reports-list");
  if (show) {
    loading?.classList.remove("hidden");
    list?.classList.add("hidden");
  } else {
    loading?.classList.add("hidden");
    list?.classList.remove("hidden");
  }
}

function showReportsEmpty(msg = "No reports found in OCI bucket.") {
  const list = $("#reports-list");
  if (!list) return;
  list.classList.remove("hidden");
  list.innerHTML = `
    <div class="empty-state">
      <div class="empty-icon">📂</div>
      <h3>No Reports Found</h3>
      <p>${msg}</p>
    </div>`;
}

function renderReports() {
  const list = $("#reports-list");
  if (!list) return;

  if (!state.reports.items.length) {
    showReportsEmpty();
    return;
  }

  list.innerHTML = state.reports.items.map(r => reportCardHTML(r)).join("");

  // Bind click handlers
  $$(".report-card", list).forEach(card => {
    card.addEventListener("click", (e) => {
      if (e.target.closest(".btn")) return; // ignore button clicks
      openReport(card.dataset.objectName);
    });
  });
}

function reportCardHTML(r) {
  const name     = r.name.replace(/^reports\//, "");
  const created  = r.time_created || "Unknown";
  const sizeKb   = r.size_bytes ? (r.size_bytes / 1024).toFixed(1) + " KB" : "";

  // Try to detect status from name
  const status  = guessStatusFromName(name);
  const badgeCls = statusBadge(status);

  return `
    <div class="report-card" data-object-name="${r.name}">
      <div class="report-icon">📄</div>
      <div class="report-body">
        <div class="report-name" title="${r.name}">${name}</div>
        <div class="report-meta">
          <span class="report-meta-item">🕐 ${created}</span>
          ${sizeKb ? `<span class="report-meta-item">📦 ${sizeKb}</span>` : ""}
          <span class="badge badge-oci">☁ OCI</span>
        </div>
      </div>
      <div class="report-actions">
        ${badgeCls ? `<span class="badge ${badgeCls}">${status}</span>` : ""}
        <button class="btn btn-sm btn-secondary" onclick="openReport('${r.name}')">
          View ↗
        </button>
      </div>
    </div>`;
}

function guessStatusFromName(name) {
  // Reports don't embed status in filename — return empty for now
  // Could be enriched by parsing a metadata sidecar in the future
  return "";
}

function statusBadge(status) {
  const map = {
    "BLOCKED":         "badge-blocked",
    "NEEDS WORK":      "badge-needs",
    "REVIEW REQUIRED": "badge-review",
    "APPROVED":        "badge-approved",
  };
  return map[status] || "";
}

function renderPagination() {
  const container = $("#pagination");
  if (!container) return;

  const { page, totalPages, total, pageSize } = state.reports;
  if (totalPages <= 1) { container.innerHTML = ""; return; }

  const startItem = (page - 1) * pageSize + 1;
  const endItem   = Math.min(page * pageSize, total);

  let btns = "";

  // Prev
  btns += `<button class="page-btn" ${page === 1 ? "disabled" : ""} onclick="loadReports(${page - 1})">‹ Prev</button>`;

  // Page numbers
  const range = pageRange(page, totalPages);
  range.forEach(p => {
    if (p === "…") {
      btns += `<span class="page-info">…</span>`;
    } else {
      btns += `<button class="page-btn ${p === page ? "active" : ""}" onclick="loadReports(${p})">${p}</button>`;
    }
  });

  // Next
  btns += `<button class="page-btn" ${page === totalPages ? "disabled" : ""} onclick="loadReports(${page + 1})">Next ›</button>`;

  container.innerHTML = `
    <div class="page-info">${startItem}–${endItem} of ${total} reports</div>
    ${btns}`;
}

function pageRange(current, total) {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);
  const pages = [1];
  if (current > 3) pages.push("…");
  for (let p = Math.max(2, current - 1); p <= Math.min(total - 1, current + 1); p++) {
    pages.push(p);
  }
  if (current < total - 2) pages.push("…");
  pages.push(total);
  return pages;
}

// ─── Report Modal ─────────────────────────────────────────────────────────────
function openReport(objectName) {
  const modal    = $("#report-modal");
  const iframe   = $("#report-iframe");
  const titleEl  = $("#modal-title");
  const name     = objectName.replace(/^reports\//, "");

  titleEl.textContent  = name;
  iframe.src           = `/api/reports/${objectName}`;
  state.modal.open     = true;
  state.modal.objectName = objectName;
  modal.classList.add("open");
  document.body.style.overflow = "hidden";
}

function closeModal() {
  const modal  = $("#report-modal");
  const iframe = $("#report-iframe");
  iframe.src   = "about:blank";
  modal.classList.remove("open");
  state.modal.open = false;
  document.body.style.overflow = "";
}

// ─── AI Provider toggle ───────────────────────────────────────────────────────
/**
 * Called when the user clicks an OCI / Claude button.
 * Immediately updates the button UI and the topbar badge.
 * Does NOT save — user still needs to click "Save Settings".
 */
function selectProvider(provider) {
  $$(".provider-btn").forEach(btn => btn.classList.remove("active"));
  $(`#btn-provider-${provider}`)?.classList.add("active");
  updateProviderUI(provider, false);
}

/**
 * Sync the topbar badge and the hint text to the given provider.
 * @param {string}  provider  'oci' | 'claude'
 * @param {boolean} save      if true, also persist via POST /api/config
 */
function updateProviderUI(provider, save = false) {
  const badge     = $("#provider-badge");
  const hintName  = $("#provider-hint-name");

  if (provider === "claude") {
    if (badge) {
      badge.textContent = "✦ Claude Sonnet";
      badge.className   = "provider-badge provider-claude";
    }
    if (hintName) hintName.textContent = "Anthropic Claude Sonnet";
  } else {
    if (badge) {
      badge.textContent = "⚙ OCI Gen AI";
      badge.className   = "provider-badge provider-oci";
    }
    if (hintName) hintName.textContent = "OCI Gen AI";
  }

  if (save) {
    fetch("/api/config", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ ai_provider: provider }),
    })
      .then(r => r.json())
      .then(d => { if (d.status === "ok") toast(`Switched to ${provider === "claude" ? "Claude Sonnet" : "OCI Gen AI"}`, "success"); })
      .catch(err => toast("Failed to update provider: " + err.message, "error"));
  }
}

// ─── Config / Settings ────────────────────────────────────────────────────────
async function loadConfig() {
  try {
    const res  = await fetch("/api/config");
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Failed to load config");
    state.config = data;
    populateConfigForm(data);
    // Sync provider badge in topbar
    if (data.ai_provider) updateProviderUI(data.ai_provider, false);
  } catch (err) {
    toast("Could not load config: " + err.message, "error");
  }
}

function populateConfigForm(cfg) {
  const set = (id, val) => { const el = $(id); if (el) el.value = val || ""; };
  set("#cfg-model-id",      cfg.model_id);
  set("#cfg-compartment",   cfg.compartment_id);
  set("#cfg-bucket",        cfg.bucket_name);
  set("#cfg-endpoint",      cfg.endpoint);

  // Provider toggle buttons
  if (cfg.ai_provider) {
    $$("#provider-toggle-group .provider-btn").forEach(btn => btn.classList.remove("active"));
    $(`#btn-provider-${cfg.ai_provider}`)?.classList.add("active");
  }

  // Active agents (Settings tab)
  if (cfg.enabled_agents) {
    ALL_AGENTS.forEach(agent => {
      const cb = $(`#agent-${agent}`);
      const chip = $(`#chip-${agent}`);
      if (cb && chip) {
        cb.checked = cfg.enabled_agents.includes(agent);
        chip.classList.toggle("active", cb.checked);
      }
    });
    // This function exists from the toggles setup
    if (typeof updateAgentCountHint === "function") {
      updateAgentCountHint();
    }
  }

  // Prompts
  if (cfg.prompts) {
    Object.entries(cfg.prompts).forEach(([agent, text]) => {
      const ta = $(`#prompt-${agent}`);
      if (ta) ta.value = text;
    });
  }
}

async function saveConfig() {
  const btn = $("#save-config-btn");
  btn.disabled = true;
  btn.textContent = "Saving…";

  const prompts = {};
  ["security", "style", "logic", "performance", "dependency"].forEach(agent => {
    const ta = $(`#prompt-${agent}`);
    if (ta) prompts[agent] = ta.value;
  });

  // Determine selected provider from the active button
  const activeProviderBtn = $("#provider-toggle-group .provider-btn.active");
  const selectedProvider  = activeProviderBtn?.id?.replace("btn-provider-", "") || "oci";

  const payload = {
    ai_provider:    selectedProvider,
    model_id:       $("#cfg-model-id")?.value.trim(),
    compartment_id: $("#cfg-compartment")?.value.trim(),
    bucket_name:    $("#cfg-bucket")?.value.trim(),
    endpoint:       $("#cfg-endpoint")?.value.trim(),
    enabled_agents: getEnabledAgents(),
    prompts,
  };

  try {
    const res  = await fetch("/api/config", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Save failed");
    toast(`Config saved: ${data.updated?.join(", ")}`, "success");
    updateProviderUI(selectedProvider, false);
  } catch (err) {
    toast(err.message, "error");
  } finally {
    btn.disabled    = false;
    btn.textContent = "Save Settings";
  }
}

// ─── Agent Toggles ───────────────────────────────────────────────────────────
const ALL_AGENTS = ["security", "logic", "performance", "dependency", "style"];

function initAgentToggles() {
  ALL_AGENTS.forEach(agent => {
    const chip = $(`#chip-${agent}`);
    const cb   = $(`#agent-${agent}`);
    if (!chip || !cb) return;

    chip.addEventListener("click", (e) => {
      e.preventDefault(); // prevent double-fire from label+input
      cb.checked = !cb.checked;
      chip.classList.toggle("active", cb.checked);
      updateAgentCountHint();
    });
  });
  updateAgentCountHint();
}

function updateAgentCountHint() {
  const active = ALL_AGENTS.filter(a => $(`#agent-${a}`)?.checked).length;
  const hint   = $("#agent-count-hint");
  if (hint) hint.textContent = `${active} of ${ALL_AGENTS.length} agents active`;
}

function getEnabledAgents() {
  return ALL_AGENTS.filter(a => $(`#agent-${a}`)?.checked);
}

// ─── Run Review ───────────────────────────────────────────────────────────────
async function runReview() {
  const btn      = $("#run-review-btn");
  const progress = $("#review-progress");
  const resultEl = $("#review-result");
  const bar      = $("#review-bar");

  const payload = {
    repo_url:       $("#review-repo")?.value.trim(),
    source_branch:  $("#review-source")?.value.trim(),
    target_branch:  $("#review-target")?.value.trim(),
    pr_id:          $("#review-pr-id")?.value.trim(),
  };

  if (!payload.repo_url || !payload.source_branch || !payload.target_branch) {
    toast("Please fill in Repo URL, Source Branch, and Target Branch.", "error");
    return;
  }

  btn.disabled          = true;
  btn.innerHTML         = `<span class="spinner"></span> Running…`;
  progress?.classList.remove("hidden");
  resultEl.innerHTML    = "";
  resultEl.className    = "review-result";
  bar?.classList.add("indeterminate");

  try {
    const res  = await fetch("/review", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify(payload),
    });
    const data = await res.json();

    bar?.classList.remove("indeterminate");

    if (!res.ok || data.status === "error") {
      throw new Error(data.error || "Review failed");
    }

    const s = data.summary;
    const severities = Object.entries(s.severity_counts || {})
      .filter(([, v]) => v > 0)
      .map(([k, v]) => `<span class="stat-chip ${k.toLowerCase()}">${k}: ${v}</span>`)
      .join("");

    resultEl.className = "review-result success";
    resultEl.innerHTML = `
      <div class="flex items-center gap-12" style="margin-bottom:12px;">
        <span style="font-size:22px;">✅</span>
        <div>
          <div style="font-weight:700;font-size:15px;">Review Complete</div>
          <div class="text-muted" style="font-size:12px;">Elapsed: ${s.elapsed_seconds}s</div>
        </div>
        <span class="badge ${statusBadge(s.overall_status)} ml-auto">${s.overall_status}</span>
      </div>
      <div class="stat-chips">
        <span class="stat-chip"><strong>Total:</strong> ${s.total_findings} findings</span>
        ${severities}
      </div>
      ${data.oci_uploaded ? `<div class="mt-8 text-muted" style="font-size:12px;">☁ Uploaded to OCI: <span class="font-mono">${data.oci_object}</span></div>` : ""}
    `;

    toast("Review complete! Loading report inline…", "success", 5000);

    // ── Show the report inline on the same page ──────────────────────
    if (data.report_filename) {
      showInlineReport(data.report_filename);
    }

    // Refresh reports list if on that tab
    if (state.currentView === "reports") {
      loadReports(1);
    }

  } catch (err) {
    bar?.classList.remove("indeterminate");
    resultEl.className = "review-result error";
    resultEl.innerHTML = `<span style="font-size:20px;">❌</span> <strong>Error:</strong> ${err.message}`;
    toast(err.message, "error");
  } finally {
    btn.disabled      = false;
    btn.innerHTML     = "🚀 Run Review";
    if (bar) bar.style.width = "100%";
    setTimeout(() => progress?.classList.add("hidden"), 1000);
  }
}

// ─── Inline Report Viewer ────────────────────────────────────────────────────
/**
 * Load the freshly-generated report into the inline iframe panel.
 * Uses the local-report endpoint so the user doesn't have to wait for OCI.
 * @param {string} filename  bare filename, e.g. "review_PR42_20260312_161812.html"
 */
function showInlineReport(filename) {
  const panel    = $("#inline-report-panel");
  const iframe   = $("#inline-report-iframe");
  const titleEl  = $("#inline-report-title");
  const tabLink  = $("#inline-report-open-tab");

  if (!panel || !iframe) return;

  const url = `/api/local-report/${encodeURIComponent(filename)}`;
  titleEl.textContent    = `📄 ${filename}`;
  tabLink.href           = url;
  iframe.src             = url;

  panel.classList.remove("hidden");

  // Smooth scroll so the user sees the report without manual scrolling
  setTimeout(() => panel.scrollIntoView({ behavior: "smooth", block: "start" }), 150);
}

function closeInlineReport() {
  const panel  = $("#inline-report-panel");
  const iframe = $("#inline-report-iframe");
  if (iframe) iframe.src = "about:blank";
  panel?.classList.add("hidden");
}

// ─── Filter handlers ──────────────────────────────────────────────────────────
function applyFilters() {
  state.reports.from = $("#filter-from")?.value || "";
  state.reports.to   = $("#filter-to")?.value || "";
  loadReports(1);
}

function clearFilters() {
  if ($("#filter-from")) $("#filter-from").value = "";
  if ($("#filter-to"))   $("#filter-to").value   = "";
  state.reports.from = "";
  state.reports.to   = "";
  loadReports(1);
}

// ─── Agent prompt tab switcher ────────────────────────────────────────────────
function switchAgentTab(agent) {
  state.activeAgent = agent;
  $$(".agent-tab").forEach(t => t.classList.remove("active"));
  $$(".agent-prompt-panel").forEach(p => p.classList.remove("active"));
  $(`[data-agent="${agent}"]`)?.classList.add("active");
  $(`#agent-panel-${agent}`)?.classList.add("active");
}

// ─── Bootstrap ───────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {

  // Navigation
  $$(".nav-item").forEach(item => {
    item.addEventListener("click", () => navigateTo(item.dataset.view));
  });

  // Modal close
  $("#modal-close")?.addEventListener("click", closeModal);
  $("#report-modal")?.addEventListener("click", (e) => {
    if (e.target === e.currentTarget) closeModal();
  });

  // Keyboard shortcut: Escape closes modal
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && state.modal.open) closeModal();
  });

  // Filter form
  $("#filter-apply")?.addEventListener("click", applyFilters);
  $("#filter-clear")?.addEventListener("click", clearFilters);
  // Support pressing Enter on date inputs
  ["filter-from", "filter-to"].forEach(id => {
    $(`#${id}`)?.addEventListener("keydown", (e) => { if (e.key === "Enter") applyFilters(); });
  });

  // Agent prompt tabs
  $$(".agent-tab").forEach(tab => {
    tab.addEventListener("click", () => switchAgentTab(tab.dataset.agent));
  });

  // Save config
  $("#save-config-btn")?.addEventListener("click", saveConfig);

  // Run review
  $("#run-review-btn")?.addEventListener("click", runReview);

  // Agent toggle chips
  initAgentToggles();

  // Page size change
  $("#page-size-select")?.addEventListener("change", (e) => {
    state.reports.pageSize = parseInt(e.target.value, 10);
    loadReports(1);
  });

  // Initial load
  navigateTo("reports");
});
