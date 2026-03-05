/* ─── Admin Credit Dashboard ──────────────────────────── */

const Auth = {
  getToken()  { return localStorage.getItem('cc_token'); },
  getUser()   { try { return JSON.parse(localStorage.getItem('cc_user')); } catch { return null; } },
  isLoggedIn(){ return !!this.getToken(); },
  headers()   {
    const h = { 'Content-Type': 'application/json' };
    const t = this.getToken();
    if (t) h['Authorization'] = `Bearer ${t}`;
    return h;
  },
};

// ── Toast ──────────────────────────────────────────────
function showToast(msg, type = 'success') {
  const c = document.getElementById('toast-container');
  const t = document.createElement('div');
  t.className = `toast ${type}`;
  t.textContent = msg;
  c.appendChild(t);
  setTimeout(() => t.remove(), 4000);
}

// ── Init ───────────────────────────────────────────────
(async function init() {
  if (!Auth.isLoggedIn()) {
    document.getElementById('dashboard').style.display = 'none';
    document.getElementById('login-required').style.display = '';
    return;
  }
  // Check admin access
  try {
    const res = await fetch('/api/admin/credits/overview', { headers: Auth.headers() });
    if (res.status === 403) {
      document.getElementById('dashboard').style.display = 'none';
      document.getElementById('access-denied').style.display = '';
      return;
    }
    if (res.status === 401) {
      document.getElementById('dashboard').style.display = 'none';
      document.getElementById('login-required').style.display = '';
      return;
    }
    const data = await res.json();
    renderStats(data);
    renderBudget(data);
    renderApiBreakdown(data);
  } catch (e) {
    console.error('Failed to load admin overview:', e);
  }

  loadHistory();
  loadUsers();
  loadConfig();
})();

async function loadAll() {
  const btn = document.getElementById('refresh-btn');
  btn.classList.add('loading');
  try {
    const res = await fetch('/api/admin/credits/overview', { headers: Auth.headers() });
    const data = await res.json();
    renderStats(data);
    renderBudget(data);
    renderApiBreakdown(data);
    await Promise.all([loadHistory(), loadUsers()]);
    showToast('Dashboard refreshed');
  } catch (e) {
    showToast('Refresh failed', 'error');
  } finally {
    btn.classList.remove('loading');
  }
}

// ── Stat Cards ─────────────────────────────────────────
function renderStats(data) {
  const row = document.getElementById('stats-row');
  const flux = data.by_api.flux2pro || {};
  const gemini = data.by_api.gemini || {};
  const totalCalls = (flux.total_calls || 0) + (gemini.total_calls || 0);
  const successRate = totalCalls > 0
    ? Math.round(((flux.successes || 0) + (gemini.successes || 0)) / totalCalls * 100) : 0;

  row.innerHTML = `
    <div class="stat-card purple">
      <div class="stat-icon purple">
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <rect x="2" y="5" width="20" height="14" rx="2"/><line x1="2" y1="10" x2="22" y2="10"/>
        </svg>
      </div>
      <div class="stat-label">Total Credits Used</div>
      <div class="stat-value">$${data.total_used.toFixed(2)}</div>
      <div class="stat-sub">${totalCalls} total API calls</div>
    </div>

    <div class="stat-card green">
      <div class="stat-icon green">
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>
        </svg>
      </div>
      <div class="stat-label">Remaining Balance</div>
      <div class="stat-value">$${data.remaining.toFixed(2)}</div>
      <div class="stat-sub">${data.usage_percent.toFixed(1)}% of budget used</div>
    </div>

    <div class="stat-card amber">
      <div class="stat-icon amber">
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
        </svg>
      </div>
      <div class="stat-label">Flux 2 Pro</div>
      <div class="stat-value">${flux.total_calls || 0}</div>
      <div class="stat-sub">$${(flux.total_credits || 0).toFixed(2)} credits · ${flux.successes || 0} success</div>
    </div>

    <div class="stat-card blue">
      <div class="stat-icon blue">
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
        </svg>
      </div>
      <div class="stat-label">Gemini</div>
      <div class="stat-value">${gemini.total_calls || 0}</div>
      <div class="stat-sub">$${(gemini.total_credits || 0).toFixed(2)} credits · ${gemini.successes || 0} success</div>
    </div>

    <div class="stat-card rose">
      <div class="stat-icon rose">
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>
        </svg>
      </div>
      <div class="stat-label">Success Rate</div>
      <div class="stat-value">${successRate}%</div>
      <div class="stat-sub">${(flux.failures || 0) + (gemini.failures || 0)} failures total</div>
    </div>
  `;
}

// ── Budget Bar ─────────────────────────────────────────
function renderBudget(data) {
  const section = document.getElementById('budget-section');
  section.style.display = '';
  document.getElementById('budget-used-label').textContent = `$${data.total_used.toFixed(2)} used`;
  document.getElementById('budget-total-label').textContent = `$${data.total_budget.toFixed(2)} budget`;
  const fill = document.getElementById('budget-fill');
  const pct = Math.min(data.usage_percent, 100);
  fill.style.width = pct + '%';
  fill.className = 'progress-bar-fill' +
    (pct >= 90 ? ' danger' : pct >= 70 ? ' warning' : '');
}

// ── API Breakdown ──────────────────────────────────────
function renderApiBreakdown(data) {
  const el = document.getElementById('api-breakdown');
  const apis = data.by_api;
  if (!Object.keys(apis).length) {
    el.innerHTML = `<div class="empty-state"><p>No API usage recorded yet</p></div>`;
    return;
  }

  let html = '';
  for (const [name, info] of Object.entries(apis)) {
    const successPct = info.total_calls > 0
      ? Math.round(info.successes / info.total_calls * 100) : 0;
    const colorCls = name === 'flux2pro' ? 'purple' : name === 'gemini' ? 'blue' : 'amber';
    html += `
      <div style="margin-bottom:1.25rem;padding:1rem;background:rgba(124,58,237,.02);border-radius:var(--radius-sm)">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:.5rem">
          <span class="badge badge-${colorCls}" style="font-size:.75rem">${name.toUpperCase()}</span>
          <span class="credit-num" style="font-size:1.1rem">$${(info.total_credits || 0).toFixed(2)}</span>
        </div>
        <div style="display:flex;gap:1.5rem;font-size:.8rem;color:var(--muted-fg)">
          <span>${info.total_calls} calls</span>
          <span>${info.successes} ok</span>
          <span>${info.failures} fail</span>
          <span>${successPct}% success</span>
        </div>
        <div class="progress-bar" style="margin-top:.5rem;height:.35rem">
          <div class="progress-bar-fill" style="width:${successPct}%"></div>
        </div>
      </div>`;
  }
  el.innerHTML = html;
}

// ── History Chart ──────────────────────────────────────
async function loadHistory() {
  try {
    const res = await fetch('/api/admin/credits/history?days=14', { headers: Auth.headers() });
    const { history } = await res.json();
    renderHistoryChart(history);
  } catch (e) {
    console.error('Failed to load history:', e);
  }
}

function renderHistoryChart(history) {
  const container = document.getElementById('history-chart');
  if (!history.length) {
    container.innerHTML = `<div class="empty-state"><p>No usage history yet</p><p class="hint">Generate some stories to see data here</p></div>`;
    return;
  }

  // Group by date
  const byDate = {};
  history.forEach(h => {
    if (!byDate[h.date]) byDate[h.date] = {};
    byDate[h.date][h.api_name] = h.credits;
  });

  const dates = Object.keys(byDate).sort();
  const maxCredits = Math.max(...dates.map(d => {
    const v = byDate[d];
    return (v.flux2pro || 0) + (v.gemini || 0);
  }), 0.01);

  let barsHtml = '';
  dates.forEach(date => {
    const d = byDate[date];
    const fluxH = ((d.flux2pro || 0) / maxCredits * 170);
    const geminiH = ((d.gemini || 0) / maxCredits * 170);
    const shortDate = date.slice(5); // MM-DD
    barsHtml += `
      <div class="chart-bar-col">
        <div style="display:flex;gap:2px;align-items:flex-end;height:100%">
          <div class="chart-bar flux" style="height:${Math.max(fluxH, 2)}px"
               data-tooltip="Flux: $${(d.flux2pro || 0).toFixed(3)}"></div>
          <div class="chart-bar gemini" style="height:${Math.max(geminiH, 2)}px"
               data-tooltip="Gemini: $${(d.gemini || 0).toFixed(3)}"></div>
        </div>
        <div class="chart-bar-label">${shortDate}</div>
      </div>`;
  });

  container.innerHTML = `<div class="chart-bar-group">${barsHtml}</div>`;
}

// ── User Table ─────────────────────────────────────────
async function loadUsers() {
  try {
    const res = await fetch('/api/admin/credits/by-user', { headers: Auth.headers() });
    const { users } = await res.json();
    renderUsersTable(users);
  } catch (e) {
    console.error('Failed to load users:', e);
  }
}

function renderUsersTable(users) {
  const tbody = document.getElementById('users-tbody');
  if (!users.length) {
    tbody.innerHTML = `<tr><td colspan="6"><div class="empty-state"><p>No user activity yet</p></div></td></tr>`;
    return;
  }

  tbody.innerHTML = users.map(u => {
    const initial = (u.user_name || 'A')[0].toUpperCase();
    const lastAct = u.last_activity ? new Date(u.last_activity).toLocaleDateString() : '—';
    return `
      <tr>
        <td>
          <div class="user-cell">
            <div class="user-avatar-sm">${initial}</div>
            <div>
              <div class="user-name">${escHtml(u.user_name)}</div>
              <div class="user-email">${escHtml(u.email)}</div>
            </div>
          </div>
        </td>
        <td>${u.total_calls}</td>
        <td><span class="badge badge-success">${u.successes}</span></td>
        <td class="credit-num">$${(u.total_credits || 0).toFixed(2)}</td>
        <td>${u.active_days}</td>
        <td>${lastAct}</td>
      </tr>`;
  }).join('');
}

// ── Config ─────────────────────────────────────────────
async function loadConfig() {
  try {
    const res = await fetch('/api/admin/credits/config', { headers: Auth.headers() });
    const config = await res.json();
    document.getElementById('cfg-budget').value = config.total_budget || 1000;
    document.getElementById('cfg-flux-cost').value = config.flux2pro_cost_per_image || 0.05;
    document.getElementById('cfg-gemini-cost').value = config.gemini_cost_per_call || 0.01;
  } catch (e) {
    console.error('Failed to load config:', e);
  }
}

async function saveConfig() {
  try {
    const body = {
      total_budget: parseFloat(document.getElementById('cfg-budget').value),
      flux2pro_cost_per_image: parseFloat(document.getElementById('cfg-flux-cost').value),
      gemini_cost_per_call: parseFloat(document.getElementById('cfg-gemini-cost').value),
    };
    const res = await fetch('/api/admin/credits/config', {
      method: 'PUT',
      headers: Auth.headers(),
      body: JSON.stringify(body),
    });
    if (res.ok) {
      showToast('Configuration saved');
      loadAll();
    } else {
      const data = await res.json();
      showToast(data.message || 'Save failed', 'error');
    }
  } catch (e) {
    showToast('Save failed', 'error');
  }
}

// ── Helpers ────────────────────────────────────────────
function escHtml(s) {
  const d = document.createElement('div');
  d.textContent = s || '';
  return d.innerHTML;
}
