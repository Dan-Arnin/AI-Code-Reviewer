/**
 * app.js — CodeSpectre Dashboard
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
    from:        "",
    to:          "",
    repo:        "",
    branch:      "",
  },
  config: {
    saved_pats: [],
    saved_repos: []
  },
  activeAgent:   "security",
  modal: {
    open:       false,
    objectName: "",
  },
};

// ─── DOM helpers ─────────────────────────────────────────────────────────────
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

// ─── Particles & Theme ───────────────────────────────────────────────────────
function initTheme() {
  const toggle = $("#theme-toggle");
  if (!toggle) return;
  const isDark = !document.documentElement.classList.contains("light");
  
  toggle.addEventListener("click", () => {
    document.documentElement.classList.toggle("dark");
    document.documentElement.classList.toggle("light");
    const nowDark = document.documentElement.classList.contains("dark");
    toggle.textContent = nowDark ? "🌙" : "☀️";
  });
}

function initParticles() {
    try {
        if (window.tsParticles) {
            tsParticles.load("tsparticles", {
                preset: "stars",
                background: { color: "transparent" },
                particles: {
                    number: { value: 80 },
                    color: { value: ["#06b6d4", "#a855f7", "#ffffff"] },
                    opacity: { value: 0.5, animation: { enable: true, minimumValue: 0.1, speed: 1, sync: false } },
                    size: { value: 2, random: true },
                    move: { enable: true, speed: 0.5, direction: "none", random: true, straight: false, outModes: "out" }
                }
            });
        }
    } catch (e) {
        console.warn("Could not load particles:", e);
    }
}

// ─── Toast ────────────────────────────────────────────────────────────────────
function toast(msg, type = "info", duration = 4000) {
  const icons = { success: "✅", error: "❌", info: "ℹ️" };
  const el = document.createElement("div");
  el.className = `toast toast-${type}`;
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
  if (view === "run-review") populateReviewFormOptions();
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
  if (state.reports.repo) params.set("repo", state.reports.repo);
  if (state.reports.branch) params.set("branch", state.reports.branch);

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
    <div class="empty-state card glass flex flex-col items-center gap-12" style="text-align:center; padding: 40px;">
      <div style="font-size: 3rem; margin-bottom: 15px;">📂</div>
      <h3 class="neon-text">No Reports Found</h3>
      <p class="text-muted">${msg}</p>
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

  $$(".report-item", list).forEach(card => {
    card.addEventListener("click", (e) => {
      if (e.target.closest(".btn")) return;
      openReport(card.dataset.objectName);
    });
  });
}

function reportCardHTML(r) {
  const name     = r.name.replace(/^reports\//, "");
  const created  = r.time_created || "Unknown";
  const sizeKb   = r.size_bytes ? (r.size_bytes / 1024).toFixed(1) + " KB" : "";

  return `
    <div class="report-item" data-object-name="${r.name}">
      <div>
        <div class="report-item-title" title="${r.name}">${name}</div>
        <div class="report-item-date">
          <span>🕐 ${created}</span>
          ${sizeKb ? `<span style="margin-left:8px;">📦 ${sizeKb}</span>` : ""}
          <span style="margin-left:8px;" class="neon-text-cyan">☁ OCI</span>
        </div>
      </div>
      <div>
        <button class="btn btn-sm btn-secondary ghost-btn" onclick="openReport('${r.name}')">
          View ↗
        </button>
      </div>
    </div>`;
}

function renderPagination() {
  const container = $("#pagination");
  if (!container) return;

  const { page, totalPages, total, pageSize } = state.reports;
  if (totalPages <= 1) { container.innerHTML = ""; return; }

  const startItem = (page - 1) * pageSize + 1;
  const endItem   = Math.min(page * pageSize, total);

  let btns = "";
  btns += `<button class="btn btn-sm ghost-btn" ${page === 1 ? "disabled" : ""} onclick="loadReports(${page - 1})">‹ Prev</button>`;
  
  const range = pageRange(page, totalPages);
  range.forEach(p => {
    if (p === "…") {
      btns += `<span class="page-info text-muted">…</span>`;
    } else {
      btns += `<button class="btn btn-sm ${p === page ? "neon-btn" : "ghost-btn"}" onclick="loadReports(${p})">${p}</button>`;
    }
  });

  btns += `<button class="btn btn-sm ghost-btn" ${page === totalPages ? "disabled" : ""} onclick="loadReports(${page + 1})">Next ›</button>`;

  container.innerHTML = `
    <div class="page-info text-muted text-xs" style="margin-bottom:8px;">${startItem}–${endItem} of ${total} reports</div>
    <div class="flex gap-8">${btns}</div>`;
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
  modal.classList.remove("hidden");
  document.body.style.overflow = "hidden";
}

function closeModal() {
  const modal  = $("#report-modal");
  const iframe = $("#report-iframe");
  iframe.src   = "about:blank";
  modal.classList.add("hidden");
  state.modal.open = false;
  document.body.style.overflow = "";
}

// ─── AI Provider toggle ───────────────────────────────────────────────────────
function selectProvider(provider) {
  $$(".provider-btn").forEach(btn => btn.classList.remove("active"));
  $(`#btn-provider-${provider}`)?.classList.add("active");
  updateProviderUI(provider, false);
}

function updateProviderUI(provider, save = false) {
  const badge     = $("#provider-badge");
  const hintName  = $("#provider-hint-name");

  if (provider === "claude") {
    if (badge) {
      badge.textContent = "✦ Claude Sonnet";
      badge.className   = "provider-badge provider-claude neon-text-purple";
    }
    if (hintName) { hintName.textContent = "Anthropic Claude Sonnet"; hintName.className = "neon-text"; }
  } else {
    if (badge) {
      badge.textContent = "☁ OCI Gen AI";
      badge.className   = "provider-badge provider-oci neon-text-cyan";
    }
    if (hintName) { hintName.textContent = "OCI Gen AI"; hintName.className = "neon-text-cyan"; }
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
    if (!state.config.saved_pats) state.config.saved_pats = [];
    if (!state.config.saved_repos) state.config.saved_repos = [];
    
    populateConfigForm(data);
    renderPATTable();
    populateReviewFormOptions();
    
    if (data.ai_provider) updateProviderUI(data.ai_provider, false);
  } catch (err) {
    toast("Could not load config: " + err.message, "error");
  }
}

function populateConfigForm(cfg) {
  const set = (id, val) => { const el = $(id); if (el) el.value = val || ""; };
  
  // OCI Auth Method
  set("#cfg-oci-auth", cfg.oci_auth_method || "config_file");
  handleOCIAuthChange();
  
  set("#cfg-oci-user", cfg.oci_user_ocid);
  set("#cfg-oci-tenancy", cfg.oci_tenancy_ocid);
  set("#cfg-oci-fingerprint", cfg.oci_fingerprint);
  set("#cfg-oci-region", cfg.oci_region);
  set("#cfg-oci-key", cfg.oci_private_key);

  // For selects, if options are not loaded yet, add the option dynamically
  const ensureSelectOption = (id, val) => {
      if (!val) return;
      const el = $(id);
      if (el && ![...el.options].some(o => o.value === val)) {
          const opt = document.createElement("option");
          opt.value = val;
          opt.textContent = val;
          el.appendChild(opt);
      }
      if (el) el.value = val;
  };
  
  ensureSelectOption("#cfg-model-id", cfg.model_id);
  ensureSelectOption("#cfg-compartment", cfg.compartment_id);
  ensureSelectOption("#cfg-bucket", cfg.bucket_name);
  
  set("#cfg-endpoint",      cfg.endpoint);

  if (cfg.ai_provider) {
    $$("#provider-toggle-group .provider-btn").forEach(btn => btn.classList.remove("active"));
    $(`#btn-provider-${cfg.ai_provider}`)?.classList.add("active");
  }

  if (cfg.enabled_agents) {
    ALL_AGENTS.forEach(agent => {
      const cb = $(`#agent-${agent}`);
      const chip = $(`#chip-${agent}`);
      if (cb && chip) {
        cb.checked = cfg.enabled_agents.includes(agent);
        chip.classList.toggle("active", cb.checked);
      }
    });
  }

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

  const activeProviderBtn = $("#provider-toggle-group .provider-btn.active");
  const selectedProvider  = activeProviderBtn?.id?.replace("btn-provider-", "") || "oci";

  const payload = {
    ai_provider:    selectedProvider,
    model_id:       $("#cfg-model-id")?.value.trim(),
    compartment_id: $("#cfg-compartment")?.value.trim(),
    bucket_name:    $("#cfg-bucket")?.value.trim(),
    endpoint:       $("#cfg-endpoint")?.value.trim(),
    
    // OCI Auth Config
    oci_auth_method:  $("#cfg-oci-auth")?.value,
    oci_user_ocid:    $("#cfg-oci-user")?.value.trim(),
    oci_tenancy_ocid: $("#cfg-oci-tenancy")?.value.trim(),
    oci_fingerprint:  $("#cfg-oci-fingerprint")?.value.trim(),
    oci_region:       $("#cfg-oci-region")?.value.trim(),
    oci_private_key:  $("#cfg-oci-key")?.value.trim(),

    enabled_agents: getEnabledAgents(),
    prompts,
    saved_pats:     state.config.saved_pats,
    saved_repos:    state.config.saved_repos
  };

  try {
    const res  = await fetch("/api/config", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Save failed");
    toast(`Config saved successfully`, "success");
    updateProviderUI(selectedProvider, false);
  } catch (err) {
    toast(err.message, "error");
  } finally {
    btn.disabled    = false;
    btn.textContent = "💾 Save Configuration";
  }
}

// ─── PAT MANAGEMENT ──────────────────────────────────────────────────────────
function renderPATTable() {
  const tbody = $("#pat-table tbody");
  if (!tbody) return;
  
  tbody.innerHTML = state.config.saved_pats.map((pat, index) => `
    <tr>
      <td>${pat.name}</td>
      <td>${pat.username}</td>
      <td>
        <button class="btn btn-sm btn-icon ghost-btn" style="color:var(--neon-pink)" onclick="deletePAT(${index})" title="Delete Token">🗑️</button>
      </td>
    </tr>
  `).join("");
  
  if (state.config.saved_pats.length === 0) {
      tbody.innerHTML = `<tr><td colspan="3" class="text-muted text-center" style="text-align:center">No tokens saved yet.</td></tr>`;
  }
}

async function addPAT() {
  const name = $("#new-pat-name").value.trim();
  const username = $("#new-pat-user").value.trim();
  const token = $("#new-pat-token").value.trim();
  
  if (!name || !username || !token) {
      toast("Please fill in all token fields.", "error");
      return;
  }
  
  state.config.saved_pats.push({ name, username, token });
  $("#new-pat-name").value = "";
  $("#new-pat-user").value = "";
  $("#new-pat-token").value = "";
  
  renderPATTable();
  await saveConfig();
}

async function deletePAT(index) {
  if (confirm("Are you sure you want to delete this token?")) {
      state.config.saved_pats.splice(index, 1);
      renderPATTable();
      await saveConfig();
  }
}

// ─── REPO MANAGEMENT & DROPDOWNS ──────────────────────────────────────────────
function populateReviewFormOptions() {
  const patSelect = $("#review-pat");
  const repoSelect = $("#review-repo-select");
  
  if (!patSelect || !repoSelect) return;
  
  // PATs
  // Remember currently selected
  const currPat = patSelect.value;
  patSelect.innerHTML = `<option value="" disabled ${!currPat ? 'selected' : ''}>Select a Personal Access Token...</option>`;
  state.config.saved_pats.forEach((pat, i) => {
      const opt = document.createElement("option");
      opt.value = i;
      opt.textContent = `${pat.name} (${pat.username})`;
      patSelect.appendChild(opt);
  });
  if (currPat && state.config.saved_pats[currPat]) patSelect.value = currPat;
  
  // Repos
  const currRepo = repoSelect.value;
  repoSelect.innerHTML = `<option value="" disabled ${!currRepo ? 'selected' : ''}>Select a saved repository...</option>`;
  state.config.saved_repos.forEach(repo => {
      const opt = document.createElement("option");
      opt.value = repo;
      opt.textContent = repo;
      repoSelect.appendChild(opt);
  });
  if (currRepo && state.config.saved_repos.includes(currRepo)) repoSelect.value = currRepo;
}

function handleSingleBranchToggle() {
    const isSingle = $("#review-single-branch").checked;
    const targetGroup = $("#group-target-branch");
    
    if (isSingle) {
        targetGroup.classList.add("hidden");
        $("#label-source-branch").textContent = "Branch to review *";
        $("#hint-source-branch").textContent = "The branch that will be completely analyzed";
    } else {
        targetGroup.classList.remove("hidden");
        $("#label-source-branch").textContent = "Source Branch *";
        $("#hint-source-branch").textContent = "The feature / MR branch";
    }
}

async function fetchBranches() {
    const patIdx = $("#review-pat").value;
    const repoUrl = $("#review-repo-select").value;
    
    if (!patIdx || !repoUrl) {
        toast("Please select a Token and a Repository first.", "error");
        return;
    }
    
    const pat = state.config.saved_pats[patIdx];
    if (!pat) return;
    
    const btn = $("#fetch-branches-btn");
    btn.innerHTML = `<span class="spinner" style="width:14px;height:14px;border-width:2px"></span>`;
    btn.disabled = true;
    
    try {
        const res = await fetch("/api/git/branches", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                repo_url: repoUrl,
                git_pat: pat.token,
                git_username: pat.username
            })
        });
        
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "Failed to fetch branches");
        
        const sourceSelect = $("#review-source");
        const targetSelect = $("#review-target");
        
        const optionsHtml = data.branches.map(b => `<option value="${b}">${b}</option>`).join("");
        const defaultHtml = `<option value="">Select branch...</option>`;
        
        sourceSelect.innerHTML = defaultHtml + optionsHtml;
        targetSelect.innerHTML = defaultHtml + optionsHtml;
        
        toast(`Fetched ${data.branches.length} branches successfully`, "success");
        
    } catch (e) {
        toast(e.message, "error");
    } finally {
        btn.innerHTML = "⬇️";
        btn.disabled = false;
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
      e.preventDefault(); 
      cb.checked = !cb.checked;
      chip.classList.toggle("active", cb.checked);
    });
  });
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

  const patIdx = $("#review-pat").value;
  const repoUrl = $("#review-repo-select").value;
  const sourceBranch = $("#review-source").value;
  const targetBranch = $("#review-target").value;
  const isSingle = $("#review-single-branch").checked;
  const prId = $("#review-pr-id").value.trim();
  
  if (!patIdx || !repoUrl) {
      toast("Token and Repository are required.", "error"); return;
  }
  if (!sourceBranch) {
      toast("Source/Target branch required.", "error"); return;
  }
  if (!isSingle && !targetBranch) {
      toast("Target branch required when not doing single-branch mode.", "error"); return;
  }
  
  const pat = state.config.saved_pats[patIdx];

  const payload = {
    repo_url:       repoUrl,
    source_branch:  sourceBranch,
    target_branch:  targetBranch,
    pr_id:          prId,
    git_pat:        pat.token,
    git_username:   pat.username,
    is_single_branch: isSingle
  };

  btn.disabled          = true;
  btn.innerHTML         = `<span class="spinner" style="width:16px;height:16px"></span> Analyzing...`;
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
      .map(([k, v]) => `<span style="margin-right: 15px; padding: 4px 8px; border-radius: 4px; background: rgba(255,255,255,0.1)">${k}: <b>${v}</b></span>`)
      .join("");

    resultEl.className = "card glass";
    resultEl.innerHTML = `
      <div class="flex items-center gap-12" style="margin-bottom:15px; border-bottom: 1px solid var(--glass-border); padding-bottom: 15px;">
        <span style="font-size:26px;">✅</span>
        <div>
          <div style="font-weight:700;font-size:16px; color: var(--neon-cyan)">Scan Complete</div>
          <div class="text-muted" style="font-size:12px;">Elapsed: ${s.elapsed_seconds}s</div>
        </div>
        <span class="badge ml-auto" style="border: 1px solid var(--glass-border); padding: 5px 12px; border-radius: 20px;">${s.overall_status}</span>
      </div>
      <div>
        <div style="margin-bottom:10px;"><strong>Total:</strong> ${s.total_findings} findings discovered</div>
        <div>${severities}</div>
      </div>
      ${data.oci_uploaded ? `<div class="mt-8 text-muted" style="font-size:12px; margin-top:20px;">☁ Archived to OCI Storage</div>` : ""}
    `;

    toast("Review complete! Loading report...", "success", 5000);

    if (data.report_filename) {
      showInlineReport(data.report_filename);
    }

    if (state.currentView === "reports") {
      loadReports(1);
    }

  } catch (err) {
    bar?.classList.remove("indeterminate");
    resultEl.className = "card glass";
    resultEl.style.borderColor = "var(--neon-pink)";
    resultEl.innerHTML = `<span style="font-size:20px;">❌</span> <strong>System Error:</strong> ${err.message}`;
    toast(err.message, "error");
  } finally {
    btn.disabled      = false;
    btn.innerHTML     = "🚀 Initialize Scan";
    if (bar) bar.style.width = "100%";
    setTimeout(() => progress?.classList.add("hidden"), 1000);
  }
}

// ─── Inline Report Viewer ────────────────────────────────────────────────────
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
  state.reports.from   = $("#filter-from")?.value || "";
  state.reports.to     = $("#filter-to")?.value || "";
  state.reports.repo   = $("#filter-repo")?.value || "";
  state.reports.branch = $("#filter-branch")?.value || "";
  loadReports(1);
}

function clearFilters() {
  if ($("#filter-from"))   $("#filter-from").value   = "";
  if ($("#filter-to"))     $("#filter-to").value     = "";
  if ($("#filter-repo"))   $("#filter-repo").value   = "";
  if ($("#filter-branch")) $("#filter-branch").value = "";
  
  state.reports.from   = "";
  state.reports.to     = "";
  state.reports.repo   = "";
  state.reports.branch = "";
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

// ─── OCI Fetch handlers ────────────────────────────────────────────────────────
function handleOCIAuthChange() {
    const authMethod = $("#cfg-oci-auth")?.value;
    const keysGroup = $("#cfg-oci-keys-group");
    if (keysGroup) {
        if (authMethod === "keys") {
            keysGroup.classList.remove("hidden");
        } else {
            keysGroup.classList.add("hidden");
        }
    }
}

async function fetchOCICompartments() {
    const btn = $("#btn-fetch-compartments");
    if (btn) { btn.disabled = true; btn.innerHTML = "↻ Fetching..."; }
    
    // Auto-save the config first so auth logic on server is fresh
    await saveConfig();
    
    try {
        const res = await fetch("/api/oci/compartments");
        const data = await res.json();
        if (!res.ok) throw new Error(data.error);
        
        const select = $("#cfg-compartment");
        select.innerHTML = `<option value="">Select Compartment...</option>` + 
            data.compartments.map(c => `<option value="${c.id}">${c.name}</option>`).join("");
        toast(`Loaded ${data.compartments.length} compartments`, "success");
    } catch (e) {
        toast("Failed loading compartments: " + e.message, "error");
    } finally {
        if (btn) { btn.disabled = false; btn.innerHTML = "↻ Fetch"; }
    }
}

async function fetchOCIBuckets() {
    const compartmentId = $("#cfg-compartment").value;
    if (!compartmentId) return toast("Select a Compartment first", "error");
    
    const btn = $("#btn-fetch-buckets");
    if (btn) { btn.disabled = true; btn.innerHTML = "↻..."; }
    try {
        const res = await fetch(`/api/oci/buckets?compartment_id=${encodeURIComponent(compartmentId)}`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.error);
        
        const select = $("#cfg-bucket");
        select.innerHTML = `<option value="">Select Bucket...</option>` + 
            data.buckets.map(b => `<option value="${b.name}">${b.name}</option>`).join("");
        toast(`Loaded ${data.buckets.length} buckets`, "success");
    } catch (e) {
        toast("Failed loading buckets: " + e.message, "error");
    } finally {
        if (btn) { btn.disabled = false; btn.innerHTML = "↻"; }
    }
}

async function fetchOCIModels() {
    const compartmentId = $("#cfg-compartment").value;
    if (!compartmentId) return toast("Select a Compartment first", "error");
    
    const btn = $("#btn-fetch-models");
    if (btn) { btn.disabled = true; btn.innerHTML = "↻..."; }
    try {
        const res = await fetch(`/api/oci/models?compartment_id=${encodeURIComponent(compartmentId)}`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.error);
        
        const select = $("#cfg-model-id");
        select.innerHTML = `<option value="">Select Model...</option>` + 
            data.models.map(m => `<option value="${m.id}">${m.name}</option>`).join("");
        toast(`Loaded ${data.models.length} models`, "success");
    } catch (e) {
        toast("Failed loading models: " + e.message, "error");
    } finally {
        if (btn) { btn.disabled = false; btn.innerHTML = "↻"; }
    }
}

// ─── Bootstrap ───────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
    
  initTheme();
  initParticles();

  // Load config immediately to populate dropdowns across views
  loadConfig();

  $$(".nav-item").forEach(item => {
    item.addEventListener("click", () => navigateTo(item.dataset.view));
  });

  $("#modal-close")?.addEventListener("click", closeModal);
  $("#report-modal")?.addEventListener("click", (e) => {
    if (e.target === e.currentTarget) closeModal();
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && state.modal.open) closeModal();
  });

  $("#filter-apply")?.addEventListener("click", applyFilters);
  $("#filter-clear")?.addEventListener("click", clearFilters);
  ["filter-from", "filter-to", "filter-repo", "filter-branch"].forEach(id => {
    $(`#${id}`)?.addEventListener("keydown", (e) => { if (e.key === "Enter") applyFilters(); });
  });

  $$(".agent-tab").forEach(tab => {
    tab.addEventListener("click", () => switchAgentTab(tab.dataset.agent));
  });

  $("#save-config-btn")?.addEventListener("click", saveConfig);
  $("#run-review-btn")?.addEventListener("click", runReview);
  
  // OCI UI Binding
  $("#cfg-oci-auth")?.addEventListener("change", handleOCIAuthChange);
  $("#btn-fetch-compartments")?.addEventListener("click", fetchOCICompartments);
  $("#btn-fetch-buckets")?.addEventListener("click", fetchOCIBuckets);
  $("#btn-fetch-models")?.addEventListener("click", fetchOCIModels);

  // PAT Add btn
  $("#btn-add-pat")?.addEventListener("click", addPAT);
  
  // Repo Add/Cancel logic
  $("#add-repo-btn")?.addEventListener("click", () => {
      $("#add-repo-form").classList.remove("hidden");
  });
  $("#cancel-new-repo-btn")?.addEventListener("click", () => {
      $("#add-repo-form").classList.add("hidden");
  });
  $("#save-new-repo-btn")?.addEventListener("click", async () => {
      const url = $("#new-repo-url").value.trim();
      if (!url) return;
      if (!state.config.saved_repos.includes(url)) {
          state.config.saved_repos.push(url);
          await saveConfig();
          populateReviewFormOptions();
          $("#new-repo-url").value = "";
          $("#add-repo-form").classList.add("hidden");
      }
  });
  
  $("#review-single-branch")?.addEventListener("change", handleSingleBranchToggle);
  $("#fetch-branches-btn")?.addEventListener("click", fetchBranches);

  initAgentToggles();

  $("#page-size-select")?.addEventListener("change", (e) => {
    state.reports.pageSize = parseInt(e.target.value, 10);
    loadReports(1);
  });

  navigateTo("reports");
});
