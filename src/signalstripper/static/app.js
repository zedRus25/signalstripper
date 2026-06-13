'use strict';

const api = {
  async get(path) {
    const r = await fetch(path);
    if (!r.ok) throw new Error(`${r.status} ${r.statusText} — ${path}`);
    return r.json();
  },
  async post(path, body) {
    const r = await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
    return r.text();
  },
};

function fmtBytes(n) {
  if (n >= 1e9) return (n / 1e9).toFixed(2) + ' GB';
  if (n >= 1e6) return (n / 1e6).toFixed(1) + ' MB';
  if (n >= 1e3) return (n / 1e3).toFixed(0) + ' KB';
  return n + ' B';
}

function fmtDate(ms) {
  if (!ms) return '—';
  return new Date(ms).toLocaleDateString();
}

let globalSummary = null;

async function loadAnalysis() {
  const data = await api.get('/api/analyze');
  globalSummary = data;
  const el = document.getElementById('summary');
  el.innerHTML = `
    <strong>DB size:</strong> ${fmtBytes(data.db_size_bytes)}<br>
    <strong>Attachments:</strong> ${fmtBytes(data.total_attachment_bytes)}<br>
    <strong>Schema version:</strong> ${data.schema_version}<br>
    <strong>Free pages:</strong> ${data.freelist_count} × ${data.page_size}B = ${fmtBytes(data.freelist_count * data.page_size)}
  `;
}

async function loadThreads() {
  const threads = await api.get('/api/threads');
  const tbody = document.getElementById('threads-body');
  tbody.innerHTML = '';

  threads.forEach(t => {
    const tr = document.createElement('tr');
    tr.dataset.threadId = t.thread_id;
    tr.innerHTML = `
      <td><input type="checkbox" class="thread-check" data-id="${t.thread_id}"></td>
      <td>${escHtml(t.recipient_display)}</td>
      <td>${t.message_count.toLocaleString()}</td>
      <td>${t.attachment_count.toLocaleString()}</td>
      <td>${fmtBytes(t.date_range ? 0 : 0)}</td>
      <td>${fmtDate(t.date_range[0])} – ${fmtDate(t.date_range[1])}</td>
      <td>
        <select data-id="${t.thread_id}" class="intent-select">
          <option value="strip_attachments">Strip attachments</option>
          <option value="remove_thread">Remove thread</option>
        </select>
      </td>
    `;
    tbody.appendChild(tr);
  });

  document.getElementById('select-all').addEventListener('change', e => {
    document.querySelectorAll('.thread-check').forEach(cb => { cb.checked = e.target.checked; });
  });
}

function escHtml(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function buildSelection() {
  const checks = document.querySelectorAll('.thread-check:checked');
  return Array.from(checks).map(cb => {
    const id = parseInt(cb.dataset.id, 10);
    const intent = document.querySelector(`.intent-select[data-id="${id}"]`).value;
    return { thread_id: id, intent };
  });
}

document.getElementById('generate-btn').addEventListener('click', async () => {
  const selections = buildSelection();
  if (!selections.length) {
    alert('Select at least one thread.');
    return;
  }
  const cmd = await api.post('/api/emit', { selections });
  document.getElementById('command-output').textContent = cmd;
});

(async () => {
  await Promise.all([loadAnalysis(), loadThreads()]);
})();
