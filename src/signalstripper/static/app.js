'use strict';

// ── Utilities ────────────────────────────────────────────────────────────────

function fmtBytes(n) {
  if (n == null || n === 0) return '0 B';
  if (n >= 1e9) return (n / 1e9).toFixed(2) + ' GB';
  if (n >= 1e6) return (n / 1e6).toFixed(1) + ' MB';
  if (n >= 1e3) return (n / 1e3).toFixed(0) + ' KB';
  return n + ' B';
}

function fmtNum(n) { return (n || 0).toLocaleString(); }

function fmtDate(ms) {
  if (!ms) return '—';
  return new Date(ms).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}

function isoDate(ms) {
  if (!ms) return '';
  return new Date(ms).toISOString().slice(0, 10);
}

function msFromIso(s) { return s ? new Date(s).getTime() : null; }

function esc(s) {
  return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

const TYPE_COLORS = {
  image:       '#3b82f6',
  video:       '#8b5cf6',
  audio:       '#10b981',
  application: '#f59e0b',
};

function typeColor(k) { return TYPE_COLORS[k] ?? '#6b7280'; }

// ── State ────────────────────────────────────────────────────────────────────

let summary = null;    // GlobalSummary from /api/analyze
let threads = null;    // [{thread_id, recipient_display, message_count, attachment_count, date_range}]
// selection: Map<thread_id, {intent, date_after, date_before}>
const selection = new Map();

// ── Fetch helpers ────────────────────────────────────────────────────────────

async function apiFetch(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText} — ${path}`);
  return r.json();
}

async function apiPost(path, body) {
  const r = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.text();
}

// ── Overview section ─────────────────────────────────────────────────────────

function renderOverview() {
  const s = summary;
  const attachPct = s.db_size_bytes ? Math.round(s.total_attachment_bytes / s.db_size_bytes * 100) : 0;
  const slackBytes = s.freelist_count * s.page_size;

  document.getElementById('db-info').innerHTML =
    `<div>${esc(s.db_path)}</div><div>schema v${s.schema_version}</div>`;

  document.getElementById('overview-grid').innerHTML = `
    <div class="stat-card">
      <div class="stat-label">Total DB size</div>
      <div class="stat-value">${fmtBytes(s.db_size_bytes)}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Attachments</div>
      <div class="stat-value">${fmtBytes(s.total_attachment_bytes)}</div>
      <div class="stat-sub">${attachPct}% of DB</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Free pages (slack)</div>
      <div class="stat-value">${fmtBytes(slackBytes)}</div>
      <div class="stat-sub">${fmtNum(s.freelist_count)} × ${fmtBytes(s.page_size)}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Conversations</div>
      <div class="stat-value">${fmtNum(s.threads.length)}</div>
    </div>
  `;

  // Table breakdown bars
  const tables = Object.entries(s.table_sizes)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 8);
  const maxSize = tables[0]?.[1] || 1;
  document.getElementById('table-breakdown').innerHTML =
    tables.map(([name, size]) => `
      <div class="table-bar-row">
        <div class="table-bar-label" title="${esc(name)}">${esc(name)}</div>
        <div class="table-bar-track">
          <div class="table-bar-fill" style="width:${Math.round(size / maxSize * 100)}%"></div>
        </div>
        <div class="table-bar-size">${fmtBytes(size)}</div>
      </div>
    `).join('');
}

// ── Thread list ──────────────────────────────────────────────────────────────

function sortedThreads() {
  const by = document.getElementById('sort-by').value;
  const copy = [...summary.threads];
  if (by === 'size')     copy.sort((a, b) => b.total_bytes - a.total_bytes);
  if (by === 'messages') copy.sort((a, b) => b.message_count - a.message_count);
  if (by === 'name')     copy.sort((a, b) => a.recipient_display.localeCompare(b.recipient_display));
  return copy;
}

function renderThreads() {
  const maxBytes = Math.max(...summary.threads.map(t => t.total_bytes), 1);
  const list = document.getElementById('threads-list');
  list.innerHTML = sortedThreads().map(t => threadCardHTML(t, maxBytes)).join('');

  // Wire events on each card
  list.querySelectorAll('.thread-card').forEach(card => {
    const id = parseInt(card.dataset.threadId, 10);
    const cb = card.querySelector('.thread-check');
    const intentSel = card.querySelector('.intent-select');
    const dateWrap = card.querySelector('.date-range-wrap');
    const dateAfter = card.querySelector('.date-after');
    const dateBefore = card.querySelector('.date-before');

    // Clicking the card body toggles the checkbox
    card.addEventListener('click', e => {
      if (e.target === cb || e.target.tagName === 'SELECT' ||
          e.target.tagName === 'INPUT' || e.target.tagName === 'LABEL') return;
      cb.checked = !cb.checked;
      cb.dispatchEvent(new Event('change'));
    });

    cb.addEventListener('change', () => {
      if (cb.checked) {
        selection.set(id, { intent: intentSel.value, date_after: null, date_before: null });
        card.classList.add('selected');
        dateWrap.classList.add('visible');
      } else {
        selection.delete(id);
        card.classList.remove('selected');
        dateWrap.classList.remove('visible');
      }
      updateTally();
      updateSelectAll();
    });

    intentSel.addEventListener('change', () => {
      if (selection.has(id)) {
        const s = selection.get(id);
        s.intent = intentSel.value;
        updateTally();
      }
    });

    dateAfter.addEventListener('change', () => {
      if (selection.has(id)) selection.get(id).date_after = msFromIso(dateAfter.value);
      updateTally();
    });
    dateBefore.addEventListener('change', () => {
      if (selection.has(id)) selection.get(id).date_before = msFromIso(dateBefore.value);
      updateTally();
    });

    // Restore selected state if re-rendering
    if (selection.has(id)) {
      cb.checked = true;
      card.classList.add('selected');
      dateWrap.classList.add('visible');
      const sel = selection.get(id);
      intentSel.value = sel.intent;
      if (sel.date_after)  dateAfter.value  = isoDate(sel.date_after);
      if (sel.date_before) dateBefore.value = isoDate(sel.date_before);
    }
  });
}

function threadCardHTML(t, maxBytes) {
  const pct = maxBytes ? Math.round(t.total_bytes / maxBytes * 100) : 0;
  const breakdown = Object.entries(t.breakdown || {})
    .sort((a, b) => b[1] - a[1])
    .map(([k, v]) => `<span class="type-chip" style="background:${typeColor(k)}22;color:${typeColor(k)}">${esc(k)} ${fmtBytes(v)}</span>`)
    .join('');

  return `
    <div class="thread-card" data-thread-id="${t.thread_id}">
      <div class="thread-check-col">
        <input type="checkbox" class="thread-check" data-id="${t.thread_id}">
      </div>
      <div class="thread-main">
        <div class="thread-name">${esc(t.recipient_display)}</div>
        <div class="thread-meta">
          ${fmtNum(t.message_count)} messages
          · ${fmtDate(t.oldest_message_ts)} – ${fmtDate(t.newest_message_ts)}
        </div>
        <div class="thread-size-bar">
          <div class="thread-size-fill" style="width:${pct}%"></div>
        </div>
        <div class="thread-breakdown">${breakdown}</div>
      </div>
      <div class="thread-controls">
        <div class="thread-size-label">${fmtBytes(t.total_bytes)}</div>
        <div class="intent-select-wrap">
          <label>Intent</label>
          <select class="intent-select">
            <option value="strip_attachments">Strip attachments</option>
            <option value="remove_thread">Remove thread</option>
          </select>
        </div>
        <div class="date-range-wrap">
          <span>Date range (optional)</span>
          <div class="date-inputs">
            <input type="date" class="date-after"  title="From" placeholder="From"
              min="${isoDate(t.oldest_message_ts)}" max="${isoDate(t.newest_message_ts)}">
            <input type="date" class="date-before" title="To"
              min="${isoDate(t.oldest_message_ts)}" max="${isoDate(t.newest_message_ts)}">
          </div>
        </div>
      </div>
    </div>
  `;
}

// ── Select-all ───────────────────────────────────────────────────────────────

function updateSelectAll() {
  const all = document.querySelectorAll('.thread-check');
  const checked = document.querySelectorAll('.thread-check:checked');
  const selectAll = document.getElementById('select-all');
  selectAll.indeterminate = checked.length > 0 && checked.length < all.length;
  selectAll.checked = all.length > 0 && checked.length === all.length;
}

document.getElementById('select-all').addEventListener('change', e => {
  // Capture desired state before the loop — updateSelectAll() called from
  // each cb's change handler mutates e.target.checked mid-loop otherwise.
  const shouldCheck = e.target.checked;
  document.querySelectorAll('.thread-check').forEach(cb => {
    if (cb.checked !== shouldCheck) {
      cb.checked = shouldCheck;
      cb.dispatchEvent(new Event('change'));
    }
  });
});

document.getElementById('sort-by').addEventListener('change', renderThreads);

// ── Tally ────────────────────────────────────────────────────────────────────

function updateTally() {
  const threadIndex = Object.fromEntries(summary.threads.map(t => [t.thread_id, t]));
  let total = 0;
  const byIntent = { strip_attachments: 0, remove_thread: 0 };

  for (const [id, sel] of selection) {
    const t = threadIndex[id];
    if (!t) continue;
    const bytes = sel.intent === 'remove_thread' ? t.total_bytes : t.attachment_bytes;
    total += bytes;
    byIntent[sel.intent] = (byIntent[sel.intent] || 0) + bytes;
  }

  document.getElementById('tally-bytes').textContent = fmtBytes(total);

  const parts = [];
  if (byIntent.strip_attachments) parts.push(`Strip: ${fmtBytes(byIntent.strip_attachments)}`);
  if (byIntent.remove_thread)     parts.push(`Remove: ${fmtBytes(byIntent.remove_thread)}`);
  if (selection.size > 0) parts.push(`${selection.size} conversation${selection.size > 1 ? 's' : ''}`);
  document.getElementById('tally-breakdown').textContent = parts.join(' · ');
}

// ── Emit ─────────────────────────────────────────────────────────────────────

document.getElementById('generate-btn').addEventListener('click', async () => {
  if (!selection.size) { alert('Select at least one conversation.'); return; }

  const selections = Array.from(selection.entries()).map(([thread_id, s]) => ({
    thread_id,
    intent: s.intent,
    date_after:  s.date_after  ?? null,
    date_before: s.date_before ?? null,
  }));

  const cmd = await apiPost('/api/emit', { selections });

  const out = document.getElementById('command-output');
  // Syntax-highlight comment lines
  out.innerHTML = cmd.split('\n').map(line =>
    line.startsWith('#')
      ? `<span class="comment">${esc(line)}</span>`
      : esc(line)
  ).join('\n');
  out.classList.remove('hidden');

  const copyBtn = document.getElementById('copy-btn');
  copyBtn.disabled = false;
  copyBtn._rawCmd = cmd;
});

document.getElementById('copy-btn').addEventListener('click', async function () {
  try {
    await navigator.clipboard.writeText(this._rawCmd);
    this.textContent = 'Copied!';
    this.classList.add('copied');
    setTimeout(() => { this.textContent = 'Copy'; this.classList.remove('copied'); }, 2000);
  } catch {
    this.textContent = 'Copy failed';
  }
});

// ── Init ─────────────────────────────────────────────────────────────────────

(async () => {
  try {
    [summary, threads] = await Promise.all([
      apiFetch('/api/analyze'),
      apiFetch('/api/threads'),
    ]);

    // Merge browse thread metadata (attachment_count, date_range) into summary threads
    const browseIndex = Object.fromEntries(threads.map(t => [t.thread_id, t]));
    summary.threads = summary.threads.map(t => ({
      ...t,
      attachment_count: browseIndex[t.thread_id]?.attachment_count ?? 0,
      oldest_message_ts: t.oldest_message_ts || browseIndex[t.thread_id]?.date_range?.[0] || 0,
      newest_message_ts: t.newest_message_ts || browseIndex[t.thread_id]?.date_range?.[1] || 0,
    }));

    renderOverview();
    renderThreads();
    updateTally();
  } catch (err) {
    document.querySelector('main').innerHTML =
      `<section><h2>Error</h2><pre>${esc(String(err))}</pre></section>`;
  }
})();
