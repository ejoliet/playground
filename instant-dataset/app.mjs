const el = (id) => document.getElementById(id);
const node = (tag, text) => Object.assign(document.createElement(tag), { textContent: text });
const display = (value) =>
  value === null ? 'NULL' : typeof value === 'object' ? '0x' + value.hex : String(value);
const quote = (name) => '"' + name.replaceAll('"', '""') + '"';
let engine,
  candidate,
  session,
  clientId,
  serial = 0,
  generation = 0;
let mode = 'rows',
  offset = 0,
  search = '',
  filters = [],
  submittedSQL = '';
const views = new Map(),
  visible = new Map();
const status = (text) => {
  el('status').textContent = text;
};

function createEngine() {
  const worker = new Worker('./engine.mjs', { type: 'module' });
  const jobs = new Map();
  function rejectAll(message) {
    for (const job of jobs.values()) job.reject(Error(message));
    jobs.clear();
  }
  worker.onerror = (e) => rejectAll(e.message || 'SQLite worker stopped.');
  worker.onmessage = ({ data }) => {
    if ('progress' in data) {
      el('progress').value = data.progress;
      el('progress').max = data.total || 1;
      return;
    }
    const job = jobs.get(data.id);
    if (!job) return;
    jobs.delete(data.id);
    if (data.error) job.reject(Error(data.error));
    else job.resolve(data.value);
  };
  return {
    call(message) {
      return new Promise((resolve, reject) => {
        const id = ++serial;
        jobs.set(id, { resolve, reject });
        worker.postMessage({ id, ...message });
      });
    },
    close() {
      worker.terminate();
      rejectAll('Dataset replaced.');
    },
  };
}
function linkView(linkId, entry) {
  const link = el(linkId);
  link.hidden = !clientId || !entry;
  if (!link.hidden)
    link.href = new URL('./api/' + [clientId, session, entry].join('/'), location.href);
}
function remember(linkId, spec, result) {
  const id = crypto.randomUUID();
  views.set(id, { spec, result });
  visible.set(linkId, id);
  if (views.size > 32) {
    for (const key of views.keys()) {
      if (![...visible.values()].includes(key)) {
        views.delete(key);
        break;
      }
    }
  }
  linkView(linkId, id);
}
async function connectAPI() {
  if (!navigator.serviceWorker) throw Error('Local JSON URLs require HTTPS or localhost.');
  navigator.serviceWorker.addEventListener('message', async (event) => {
    if (event.data?.type !== 'view' || !event.ports[0]) return;
    const { datasetId, viewId, offset } = event.data;
    const entry = views.get(viewId);
    let body,
      code = 200;
    if (datasetId !== session || !entry) {
      body = { error: 'View expired. Reopen it in the dataset tab.' };
      code = 410;
    } else {
      try {
        const spec = { ...entry.spec };
        let result = entry.result;
        if (offset !== null && spec.kind !== 'facets') {
          spec.offset = /^\d+$/.test(offset) ? Number(offset) : -1;
          result = await engine.call({ view: spec });
        }
        body = { view: spec, ...result };
      } catch (e) {
        body = { error: e.message };
        code = 400;
      }
    }
    event.ports[0].postMessage({ status: code, body });
  });
  await navigator.serviceWorker.register('./sw.js');
  await navigator.serviceWorker.ready;
  if (!navigator.serviceWorker.controller)
    await new Promise((resolve) =>
      navigator.serviceWorker.addEventListener('controllerchange', resolve, { once: true }),
    );
  const channel = new MessageChannel();
  const identity = new Promise((resolve) => (channel.port1.onmessage = (e) => resolve(e.data)));
  navigator.serviceWorker.controller.postMessage('identify', [channel.port2]);
  clientId = await identity;
  channel.port1.close();
  for (const [link, id] of visible) linkView(link, id);
}
let apiWarning = '';
connectAPI().catch((e) => {
  apiWarning = e.message;
  status(apiWarning);
});

function putGrid(result) {
  const grid = el('grid'),
    head = document.createElement('thead'),
    body = document.createElement('tbody');
  const names = head.insertRow();
  for (const col of result.columns) names.append(node('th', col));
  for (const row of result.rows) {
    const tr = body.insertRow();
    for (const value of row) tr.append(node('td', display(value)));
  }
  grid.replaceChildren(head, body);
  el('range').textContent = result.rows.length
    ? 'Rows ' + (offset + 1).toLocaleString() + '–' + (offset + result.rows.length).toLocaleString()
    : 'No matching rows';
  el('prev').disabled = offset === 0;
  el('next').disabled = !result.hasMore;
}
function drawFilters() {
  el('filters').replaceChildren(
    ...filters.map((f, i) => {
      const b = node('button', f.column + ' = ' + display(f.value) + ' ×');
      b.className = 'chip';
      b.title = 'Remove filter';
      b.onclick = () => {
        filters.splice(i, 1);
        offset = 0;
        render();
      };
      return b;
    }),
  );
}
async function render() {
  if (!engine) return;
  const rev = ++generation,
    table = el('tables').value,
    selected = el('facet').value;
  const spec =
    mode === 'sql'
      ? { kind: 'sql', sql: submittedSQL, offset }
      : { kind: 'rows', table, search, filters: [...filters], offset };
  el('sqlForm').hidden = mode !== 'sql';
  el('browseControls').hidden = mode !== 'rows';
  el('browse').setAttribute('aria-pressed', mode === 'rows');
  el('sqlTab').setAttribute('aria-pressed', mode === 'sql');
  for (const id of ['api', 'facetApi']) {
    visible.delete(id);
    linkView(id, null);
  }
  el('buckets').replaceChildren();
  el('grid').replaceChildren();
  el('range').textContent = 'Querying…';
  el('next').disabled = el('prev').disabled = true;
  drawFilters();
  status(apiWarning);
  try {
    const result = await engine.call({ view: spec });
    if (rev !== generation) return;
    putGrid(result);
    remember('api', spec, result);
    if (mode !== 'rows') return;
    el('facet').replaceChildren(
      new Option('Choose a column', ''),
      ...result.columns.map((c) => new Option(c, c)),
    );
    el('facet').value = selected;
    if (!el('facet').value) return;
    const facet = { ...spec, kind: 'facets', column: selected };
    const counts = await engine.call({ view: facet });
    if (rev !== generation) return;
    remember('facetApi', facet, counts);
    for (const [value, type, count] of counts.rows) {
      const b = document.createElement('button');
      b.className = 'bucket';
      b.append(node('span', display(value)), node('small', count.toLocaleString()));
      b.onclick = () => {
        filters = [
          ...filters.filter((f) => f.column !== selected),
          { column: selected, type, value },
        ];
        offset = 0;
        render();
      };
      el('buckets').append(b);
    }
  } catch (e) {
    if (rev === generation) {
      status(e.message);
      if (!el('grid').firstChild) el('range').textContent = 'Query failed';
    }
  }
}
function resetTable() {
  mode = 'rows';
  search = '';
  filters = [];
  offset = 0;
  el('search').value = '';
  el('facet').replaceChildren();
  el('sql').value = submittedSQL = 'SELECT * FROM ' + quote(el('tables').value);
  return render();
}
async function openFile(file) {
  if (!file) return;
  candidate?.close();
  const next = (candidate = createEngine());
  el('progress').hidden = false;
  el('progress').removeAttribute('value');
  status('Opening ' + file.name + '…');
  try {
    const { tables, importedRows, heapBytes, databaseBytes } = await next.call({ file });
    if (candidate !== next) return;
    engine?.close();
    engine = next;
    candidate = null;
    views.clear();
    visible.clear();
    session = crypto.randomUUID();
    el('filename').textContent = file.name;
    el('stats').textContent =
      (importedRows === null
        ? tables.length.toLocaleString() + ' tables / views'
        : importedRows.toLocaleString() + ' rows') +
      ' · ' +
      file.size.toLocaleString() +
      ' bytes';
    el('stats').dataset.heapBytes = heapBytes;
    el('stats').dataset.databaseBytes = databaseBytes;
    el('stats').title =
      'SQLite pages: ' +
      databaseBytes.toLocaleString() +
      ' bytes. Worker WebAssembly heap after import: ' +
      heapBytes.toLocaleString() +
      ' bytes.';
    el('tables').replaceChildren(...tables.map((t) => new Option(t.name, t.name)));
    el('workspace').hidden = false;
    await resetTable();
  } catch (e) {
    if (candidate === next) {
      next.close();
      candidate = null;
      status(e.message);
    }
  } finally {
    if (!candidate) el('progress').hidden = true;
  }
}
el('file').onchange = (e) => {
  openFile(e.target.files[0]);
  e.target.value = '';
};
el('example').onclick = async () => {
  try {
    const res = await fetch('./examples/observations.csv');
    if (!res.ok) throw Error('Sample file unavailable.');
    openFile(new File([await res.blob()], 'observations.csv'));
  } catch (e) {
    status(e.message);
  }
};
for (const type of ['dragover', 'drop'])
  window.addEventListener(type, (e) => {
    e.preventDefault();
    el('drop').classList.toggle('active', type === 'dragover');
    if (type === 'drop') openFile(e.dataTransfer.files[0]);
  });
window.addEventListener('dragleave', (e) => {
  if (!e.relatedTarget) el('drop').classList.remove('active');
});
el('tables').onchange = resetTable;
el('searchForm').onsubmit = (e) => {
  e.preventDefault();
  search = el('search').value;
  offset = 0;
  render();
};
el('facet').onchange = () => render();
el('browse').onclick = () => {
  if (mode === 'rows') return;
  mode = 'rows';
  offset = 0;
  render();
};
el('sqlTab').onclick = () => {
  if (mode === 'sql') return;
  mode = 'sql';
  offset = 0;
  render();
};
el('sqlForm').onsubmit = (e) => {
  e.preventDefault();
  submittedSQL = el('sql').value;
  offset = 0;
  render();
};
el('prev').onclick = () => {
  offset = Math.max(0, offset - 50);
  render();
};
el('next').onclick = () => {
  offset += 50;
  render();
};
