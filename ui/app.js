(function () {
  const EDITABLE_FIELDS = [
    'qty',
    'description',
    'catalog_number',
    'mfr',
    'finish',
    'notes',
    'resolved_description',
  ];

  const state = {
    files: [],
    activeFile: null,
    data: null,
    originalData: null,
    filter: '',
    dirty: false,
  };

  const ui = {
    app: null,
    sidebar: null,
    main: null,
    filterInput: null,
    status: null,
    stats: null,
    setsContainer: null,
  };

  function clone(obj) {
    return JSON.parse(JSON.stringify(obj));
  }

  function norm(v) {
    return v == null ? '' : String(v);
  }

  function asComparable(v) {
    const s = norm(v).trim();
    return s === '' ? null : s;
  }

  function create(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text != null) node.textContent = text;
    return node;
  }

  async function apiGet(path) {
    const res = await fetch(path);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  }

  async function apiPost(path, payload) {
    const res = await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  }

  function setStatus(msg, tone) {
    if (!ui.status) return;
    ui.status.textContent = msg;
    ui.status.dataset.tone = tone || 'normal';
  }

  function countFieldChanges() {
    if (!state.data || !state.originalData) return 0;
    let changes = 0;

    const docs = state.data.documents || [];
    const origDocs = state.originalData.documents || [];

    for (let di = 0; di < docs.length; di += 1) {
      const sets = (docs[di] || {}).hardware_sets || [];
      const oSets = (origDocs[di] || {}).hardware_sets || [];
      for (let si = 0; si < sets.length; si += 1) {
        const comps = (sets[si] || {}).components || [];
        const oComps = (oSets[si] || {}).components || [];
        for (let ci = 0; ci < comps.length; ci += 1) {
          const comp = comps[ci] || {};
          const oComp = oComps[ci] || {};
          for (const field of EDITABLE_FIELDS) {
            if (asComparable(comp[field]) !== asComparable(oComp[field])) {
              changes += 1;
            }
          }
        }
      }
    }

    return changes;
  }

  function updateDirtyState() {
    const changes = countFieldChanges();
    state.dirty = changes > 0;
    const label = state.dirty ? `You changed ${changes} field(s). Save or download to keep them.` : 'No edits yet. Select a row and start editing.';
    setStatus(label, state.dirty ? 'warn' : 'normal');
  }

  function buildEditor(comp, field) {
    const isDescription = field === 'description';
    const isLong = isDescription || field === 'notes' || field === 'resolved_description';

    const wrap = create('div', 'field-wrap');
    const input = isLong
      ? create('textarea', `field-input area ${isDescription ? 'desc-field' : 'long-field'}`)
      : create('input', 'field-input short-field');

    if (!isLong) input.type = 'text';
    input.value = norm(comp[field]);

    const confVal = fieldConfidence(comp, field);
    if (confVal != null) {
      const badge = create('span', 'field-conf', Number(confVal).toFixed(2));
      badge.dataset.level = confidenceLevel(confVal);
      wrap.appendChild(badge);
    }

    input.addEventListener('input', () => {
      const v = input.value;
      comp[field] = v.trim() === '' ? null : v;
      updateDirtyState();
    });

    wrap.appendChild(input);
    return wrap;
  }

  function fieldConfidence(comp, field) {
    const conf = comp.field_confidence || {};
    return conf[field] == null ? null : conf[field];
  }

  function confidenceLevel(v) {
    if (v == null) return 'none';
    if (v >= 0.85) return 'high';
    if (v >= 0.6) return 'mid';
    return 'low';
  }

  function matchesFilter(set) {
    if (!state.filter) return true;
    const q = state.filter.toLowerCase();
    return norm(set.set_number).toLowerCase().includes(q) || norm(set.description).toLowerCase().includes(q);
  }

  function renderSidebar() {
    ui.sidebar.innerHTML = '';
    ui.sidebar.appendChild(create('h1', 'side-title', 'Result Files'));

    const fileList = create('div', 'file-list');
    for (const name of state.files) {
      const btn = create('button', 'file-btn' + (name === state.activeFile ? ' active' : ''), name);
      btn.type = 'button';
      btn.addEventListener('click', async () => {
        await loadFile(name);
      });
      fileList.appendChild(btn);
    }
    ui.sidebar.appendChild(fileList);

    const hint = create('p', 'side-hint', 'Tip: start with low-confidence rows first.');
    ui.sidebar.appendChild(hint);
  }

  function renderSets() {
    ui.setsContainer.innerHTML = '';

    if (!state.data) {
      ui.setsContainer.appendChild(create('div', 'empty', 'Select a file to start.'));
      ui.stats.textContent = '';
      return;
    }

    let shownSets = 0;
    let shownComponents = 0;

    for (const doc of state.data.documents || []) {
      for (const set of doc.hardware_sets || []) {
        if (!matchesFilter(set)) continue;
        shownSets += 1;

        const details = create('details', 'set-card');

        const summary = create('summary', 'set-summary');
        const summaryText = create('span', 'set-summary-text');
        const setTitle = norm(set.description).trim() || "No title";
        summaryText.textContent = `Set ${norm(set.set_number)} · ${setTitle} · ${(set.components || []).length} components`;
        summary.appendChild(summaryText);

        const loc = set.location || {};
        const pageBadge = create('span', 'set-summary-page');
        pageBadge.textContent = `p. ${norm(loc.page_start)}-${norm(loc.page_end)}`;
        summary.appendChild(pageBadge);

        details.appendChild(summary);
        const meta = create('div', 'set-meta');

        const tagFile = create('span', 'meta-tag meta-tag--file');
        tagFile.textContent = norm(doc.doc_path);
        const tagPages = create('span', 'meta-tag meta-tag--pages');
        tagPages.textContent = `pages ${norm(loc.page_start)}-${norm(loc.page_end)}`;
        const tagLines = create('span', 'meta-tag meta-tag--lines');
        tagLines.textContent = `lines ${Array.isArray(loc.line_range) ? loc.line_range.join('-') : ''}`;

        meta.append(tagFile, tagPages, tagLines);
        details.appendChild(meta);

        const tableWrap = create('div', 'table-wrap');
        const table = create('table', 'comp-table');
        table.innerHTML = `
          <colgroup>
            <col class="col-qty" /><col class="col-description" /><col class="col-catalog" /><col class="col-mfr" />
            <col class="col-finish" /><col class="col-notes" /><col class="col-resolved" />
          </colgroup>
          <thead>
            <tr>
              <th>qty</th><th>description</th><th>catalog</th><th>mfr</th><th>finish</th><th>notes</th><th>resolved</th>
            </tr>
          </thead>
          <tbody></tbody>`;
        const tbody = table.querySelector('tbody');

        for (const comp of set.components || []) {
          shownComponents += 1;
          const tr = document.createElement('tr');

          for (const field of EDITABLE_FIELDS) {
            const td = create('td');
            td.appendChild(buildEditor(comp, field));
            tr.appendChild(td);
          }


          tbody.appendChild(tr);
        }

        tableWrap.appendChild(table);
        details.appendChild(tableWrap);
        ui.setsContainer.appendChild(details);
      }
    }

    ui.stats.textContent = `Sets shown: ${shownSets} | Components shown: ${shownComponents}`;
    if (shownSets === 0) {
      ui.setsContainer.appendChild(create('div', 'empty', 'No sets match the current filter.'));
    }
  }

  async function saveCurrent() {
    const changes = countFieldChanges();
    const ok = window.confirm(`Save ${changes} changed field(s) to corrections folder?`);
    if (!ok) return;

    try {
      const out = await apiPost(`/api/save?name=${encodeURIComponent(state.activeFile)}`, state.data);
      state.originalData = clone(state.data);
      updateDirtyState();
      setStatus(`Saved successfully. File written to out/corrections.`, 'ok');
    } catch (e) {
      setStatus(`Save failed: ${e.message}`, 'error');
    }
  }

  function downloadCurrent() {
    const changes = countFieldChanges();
    const ok = window.confirm(`Download current JSON now? Changed fields: ${changes}.`);
    if (!ok) return;

    const blob = new Blob([JSON.stringify(state.data, null, 2)], { type: 'application/json' });
    const href = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = href;
    a.download = `${state.activeFile.replace(/\.json$/i, '')}.edited.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(href);
    setStatus('Download started. Check your browser downloads.', 'ok');
  }

  function renderLayout() {
    ui.app.innerHTML = '';

    const layout = create('div', 'app-shell');
    ui.sidebar = create('aside', 'sidebar');
    ui.main = create('main', 'main');

    const toolbar = create('div', 'toolbar');
    const saveBtn = create('button', 'btn primary', 'Save Corrected JSON');
    saveBtn.type = 'button';
    saveBtn.addEventListener('click', saveCurrent);

    const downloadBtn = create('button', 'btn', 'Download JSON');
    downloadBtn.type = 'button';
    downloadBtn.addEventListener('click', downloadCurrent);

    ui.filterInput = create('input', 'search');
    ui.filterInput.type = 'text';
    ui.filterInput.placeholder = 'Search by set number or description';
    ui.filterInput.addEventListener('input', () => {
      state.filter = ui.filterInput.value.trim();
      renderSets();
    });

    ui.stats = create('div', 'stats');
    ui.status = create('div', 'status', 'No edits yet. Select a row and start editing.');

    toolbar.append(saveBtn, downloadBtn, ui.filterInput, ui.stats, ui.status);

    ui.setsContainer = create('div', 'sets');
    ui.main.append(toolbar, ui.setsContainer);

    layout.append(ui.sidebar, ui.main);
    ui.app.appendChild(layout);

    renderSidebar();
    renderSets();
    updateDirtyState();
  }

  async function loadFile(name, checkDirty = true) {
    if (checkDirty && state.dirty) {
      const ok = window.confirm('You have unsaved changes. Switch file and discard those changes?');
      if (!ok) return;
    }

    try {
      const payload = await apiGet(`/api/file?name=${encodeURIComponent(name)}`);
      state.activeFile = name;
      state.data = payload.content;
      state.originalData = clone(payload.content);
      state.filter = '';
      if (ui.filterInput) ui.filterInput.value = '';
      renderSidebar();
      renderSets();
      updateDirtyState();
      if (!state.dirty) setStatus('File loaded. You can edit any cell directly.', 'normal');
    } catch (e) {
      setStatus(`Could not load file: ${e.message}`, 'error');
    }
  }

  async function init() {
    ui.app = document.getElementById('app');
    renderLayout();

    try {
      const payload = await apiGet('/api/files');
      state.files = payload.files || [];
      renderSidebar();
      if (state.files.length) {
        await loadFile(state.files[0], false);
      } else {
        setStatus('No result files found. Put JSON outputs in out/ and refresh.', 'warn');
      }
    } catch (e) {
      setStatus(`Could not load file list: ${e.message}`, 'error');
    }
  }

  init();
})();
