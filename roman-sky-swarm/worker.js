// Roman Sky Swarm — Spike 0 compute worker.
//
// Runs one declarative work unit: init pinned DuckDB-Wasm, execute the
// manifest's SQL kernel against a remote Parquet file over HTTP Range
// requests, canonicalize the result (rss-canon-v0), and emit sha256(result).
//
// AIDEV-NOTE: architecture is worker-in-worker. This module worker is the
// orchestrator; DuckDB-Wasm spawns its own classic worker (created here from
// a Blob URL so the cross-origin CDN script can be importScripts'd). Network
// telemetry is captured by a shim prepended to that Blob, reporting over a
// BroadcastChannel — DuckDB's httpfs uses synchronous XHR inside its own
// worker, so wrapping fetch/XHR *here* would observe nothing. (This answers
// Spike 0 open question 1: httpfs exposes no byte telemetry; a wrapper in the
// DuckDB worker context is required.)

'use strict';

const DEFAULTS = {
  // AIDEV-NOTE: engine pin is load-bearing, NOT arbitrary. 1.28.0 (DuckDB
  // 0.9.1) performs HTTP-Range row-group reads and honors the
  // reliableHeadRequests filesystem config → 8.98% of file for the reference
  // kernel. 1.32.0 (DuckDB 1.4.3) REGRESSED this: it ignores the range-HEAD
  // path and downloads the whole file (100%). Do not bump without re-running
  // the partial-read proof in SPIKE_LOG. See the version sweep there.
  engineVersion: '1.28.0', // @duckdb/duckdb-wasm, pinned — see note above
  cdnBase: 'https://cdn.jsdelivr.net/npm/@duckdb/duckdb-wasm',
  allowedDatasetHosts: ['nasa-irsa-simulations.s3.amazonaws.com'],
  maxDatasetBytes: 100 * 1024 * 1024,
  memoryLimit: '768MB', // best-effort duckdb-side cap, under the ~1 GB gate
};

const NET_CHANNEL = 'rss.net.v0';

// ---------------------------------------------------------------------------
// Manifest validation. Every field is untrusted input: declarative only.
// ---------------------------------------------------------------------------

// AIDEV-NOTE: deny-list is defense-in-depth for the spike, not the real trust
// model (signed manifests come in a later phase). Kernel must be one read-only
// SELECT/WITH statement; anything that installs, writes, or reconfigures is
// rejected before it reaches the engine.
const SQL_DENY = /\b(install|load|attach|detach|copy|export|import|create|insert|update|delete|drop|alter|pragma|set|reset|call|begin|commit|vacuum|checkpoint)\b/i;

function validateManifest(m, options) {
  const fail = (msg) => { throw new Error(`manifest rejected: ${msg}`); };
  if (!m || typeof m !== 'object') fail('not an object');
  if (typeof m.wu_id !== 'string' || !/^[\w.-]{1,64}$/.test(m.wu_id)) fail('bad wu_id');
  if (!Number.isInteger(m.wu_version)) fail('bad wu_version');
  if (!m.dataset || typeof m.dataset.url !== 'string') fail('missing dataset.url');
  if (m.dataset.format !== 'parquet') fail('dataset.format must be "parquet"');
  if (!m.kernel || m.kernel.type !== 'duckdb-sql') fail('kernel.type must be "duckdb-sql"');
  if (typeof m.kernel.sql !== 'string' || m.kernel.sql.length > 10000) fail('bad kernel.sql');

  const url = new URL(options.datasetUrl || m.dataset.url);
  // AIDEV-NOTE: loopback http is exempt for local test harnesses/mirrors only;
  // anything non-loopback must be https and on the host allowlist.
  const loopback = url.hostname === 'localhost' || url.hostname === '127.0.0.1';
  if (url.protocol !== 'https:' && !loopback) fail('dataset url must be https');
  const hosts = (options.allowedDatasetHosts || DEFAULTS.allowedDatasetHosts)
    .concat(loopback ? [url.hostname] : []);
  if (!hosts.includes(url.hostname)) fail(`dataset host ${url.hostname} not in allowlist`);

  const sql = m.kernel.sql.trim();
  if (sql.includes(';')) fail('kernel.sql must be a single statement');
  if (!/^(select|with)\b/i.test(sql)) fail('kernel.sql must start with SELECT or WITH');
  if (SQL_DENY.test(sql)) fail(`kernel.sql contains a denied keyword`);
  if (!sql.includes('$RSS_DATASET_URL')) fail('kernel.sql must reference $RSS_DATASET_URL');

  return { datasetUrl: url.href, sql };
}

// ---------------------------------------------------------------------------
// Network telemetry + byte-budget shim, injected into the DuckDB worker Blob.
// Runs in the DuckDB worker's global scope BEFORE importScripts of the engine.
// ---------------------------------------------------------------------------

function buildNetShim(datasetUrl, maxDatasetBytes) {
  // Serialized as source text; keep it dependency-free and classic-worker safe.
  // Requests are bucketed dataset-vs-engine by URL prefix (not hostname), so a
  // localhost mirror serving both dataset and CDN files still buckets right.
  return `
(() => {
  var bc; try { bc = new BroadcastChannel(${JSON.stringify(NET_CHANNEL)}); } catch (e) { return; }
  var DATASET_URL = ${JSON.stringify(datasetUrl)};
  var MAX_DATASET_BYTES = ${JSON.stringify(maxDatasetBytes)};
  var datasetBytes = 0, seq = 0;
  function report(rec) { try { bc.postMessage(rec); } catch (e) {} }
  function rangeSize(r) {
    var m = /bytes=(\\d+)-(\\d+)/.exec(r || '');
    return m ? (Number(m[2]) - Number(m[1]) + 1) : 0;
  }
  // AIDEV-NOTE: byte budget is enforced HERE (pre-flight, on the requested
  // range size) because nothing outside this worker can abort DuckDB's
  // synchronous XHR mid-query. Throwing makes httpfs surface an IO error,
  // which the orchestrator reports as a graceful work-unit failure.
  function checkBudget(url, range) {
    if (String(url).indexOf(DATASET_URL) !== 0) return;
    datasetBytes += rangeSize(range);
    if (datasetBytes > MAX_DATASET_BYTES) {
      report({ kind: 'budget-exceeded', datasetBytes: datasetBytes, max: MAX_DATASET_BYTES });
      throw new Error('RSS byte budget exceeded: ' + datasetBytes + ' > ' + MAX_DATASET_BYTES);
    }
  }
  var XHR = self.XMLHttpRequest;
  if (XHR) {
    var open = XHR.prototype.open, send = XHR.prototype.send, setH = XHR.prototype.setRequestHeader;
    XHR.prototype.open = function (method, url) {
      this.__rss = { method: String(method), url: String(url), range: null };
      return open.apply(this, arguments);
    };
    XHR.prototype.setRequestHeader = function (k, v) {
      if (this.__rss && String(k).toLowerCase() === 'range') this.__rss.range = String(v);
      return setH.apply(this, arguments);
    };
    XHR.prototype.send = function () {
      var meta = this.__rss || {};
      if (meta.method === 'GET') checkBudget(meta.url, meta.range);
      var xhr = this;
      try {
        xhr.addEventListener('loadend', function () {
          var bytes = 0;
          try {
            var r = xhr.response;
            if (r && r.byteLength != null) bytes = r.byteLength;
            else if (typeof r === 'string') bytes = r.length;
          } catch (e) {}
          report({ kind: 'xhr', seq: seq++, method: meta.method, url: meta.url,
                   range: meta.range, status: xhr.status, bytes: bytes });
        });
      } catch (e) {}
      return send.apply(this, arguments);
    };
  }
  var origFetch = self.fetch;
  if (origFetch) {
    self.fetch = function (input, init) {
      var url = typeof input === 'string' ? input : (input && input.url) || '';
      var range = null;
      try {
        if (init && init.headers) range = new Headers(init.headers).get('range');
        else if (input && input.headers && input.headers.get) range = input.headers.get('range');
      } catch (e) {}
      checkBudget(url, range);
      var s = seq++;
      return origFetch.call(this, input, init).then(function (resp) {
        var len = null;
        try { len = resp.headers.get('content-length'); } catch (e) {}
        if (len != null) {
          report({ kind: 'fetch', seq: s, method: (init && init.method) || 'GET',
                   url: String(url), range: range, status: resp.status, bytes: Number(len) });
        } else {
          try {
            resp.clone().arrayBuffer().then(function (buf) {
              report({ kind: 'fetch', seq: s, method: (init && init.method) || 'GET',
                       url: String(url), range: range, status: resp.status, bytes: buf.byteLength });
            }, function () {});
          } catch (e) {}
        }
        return resp;
      });
    };
  }
  report({ kind: 'shim-ready' });
})();
`;
}

class NetTelemetry {
  constructor(datasetUrl) {
    this.datasetUrl = datasetUrl;
    this.requests = [];
    this.datasetBytes = 0;
    this.engineBytes = 0;
    this.budgetExceeded = false;
    this.channel = new BroadcastChannel(NET_CHANNEL);
    this.channel.onmessage = (e) => {
      const rec = e.data || {};
      if (rec.kind === 'console') { status('db-worker-console', `[${rec.level}] ${rec.text}`); return; }
      if (rec.kind === 'budget-exceeded') { this.budgetExceeded = true; return; }
      if (rec.kind !== 'xhr' && rec.kind !== 'fetch') return;
      this.requests.push(rec);
      if (String(rec.url).startsWith(this.datasetUrl)) this.datasetBytes += rec.bytes || 0;
      else this.engineBytes += rec.bytes || 0;
    };
  }
  close() { this.channel.close(); }
  snapshot(fileSizeBytes) {
    const datasetReqs = this.requests.filter((r) => String(r.url).startsWith(this.datasetUrl));
    return {
      dataset_bytes: this.datasetBytes,
      dataset_requests: datasetReqs.length,
      dataset_fraction_of_file: fileSizeBytes ? this.datasetBytes / fileSizeBytes : null,
      engine_cdn_bytes: this.engineBytes,
      total_requests: this.requests.length,
      budget_exceeded: this.budgetExceeded,
      dataset_request_log: datasetReqs.map((r) => ({
        method: r.method, range: r.range, status: r.status, bytes: r.bytes,
      })),
    };
  }
}

// ---------------------------------------------------------------------------
// rss-canon-v0 — the reproducibility contract.
//
// 1. Each cell value is canonicalized by type:
//    - null/undefined            -> null
//    - boolean, string           -> as-is
//    - bigint / integer number   -> JSON number if |v| <= 2^53-1, else decimal string
//    - float number              -> STRING with exactly 6 fractional digits via
//                                   Number.prototype.toFixed(6) (rounding fully
//                                   specified by ECMA-262, deterministic across
//                                   engines); -0 normalized to 0 first;
//                                   non-finite -> "NaN"/"Infinity"/"-Infinity".
//    - anything else             -> hard error (fail loud, no silent coercion)
// 2. Each row -> object serialized with lexicographically sorted keys, no
//    whitespace (JSON.stringify with sorted key order).
// 3. Rows sorted by their canonical serialization (code-unit order), making
//    the hash independent of engine output order even without SQL ORDER BY.
// 4. Envelope { kernel_type, rows, row_count, wu_id, wu_version } serialized
//    the same way; sha256 over its UTF-8 bytes.
//
// AIDEV-NOTE: float determinism risk lives UPSTREAM of this formatting: SUM/
// AVG over doubles depends on accumulation order. Wasm float ops themselves
// are IEEE-754 deterministic; the eh (non-threaded) bundle runs single-
// threaded so DuckDB's aggregation order is fixed for a given engine binary.
// If hashes ever diverge across browsers, suspect (a) threads-enabled bundle
// selected under crossOriginIsolated, or (b) different engine version — both
// are recorded in telemetry for exactly that diagnosis.
// AIDEV-NOTE: toFixed(6) only behaves for |v| < 1e21; astronomy magnitudes/
// coords/sums here are far below that. Guarded anyway.
// ---------------------------------------------------------------------------

const MAX_SAFE = 9007199254740991n;

function canonValue(v) {
  if (v === null || v === undefined) return null;
  const t = typeof v;
  if (t === 'boolean' || t === 'string') return v;
  if (t === 'bigint') {
    return (v <= MAX_SAFE && v >= -MAX_SAFE) ? Number(v) : v.toString();
  }
  if (t === 'number') {
    if (Number.isInteger(v) && Number.isSafeInteger(v)) return v;
    if (!Number.isFinite(v)) return Number.isNaN(v) ? 'NaN' : (v > 0 ? 'Infinity' : '-Infinity');
    if (Math.abs(v) >= 1e21) throw new Error(`rss-canon-v0: |value| >= 1e21 unsupported: ${v}`);
    const x = Object.is(v, -0) ? 0 : v;
    return x.toFixed(6);
  }
  throw new Error(`rss-canon-v0: unsupported value type ${t}`);
}

function canonStringify(x) {
  if (x === null) return 'null';
  if (Array.isArray(x)) return '[' + x.map(canonStringify).join(',') + ']';
  if (typeof x === 'object') {
    const keys = Object.keys(x).sort();
    return '{' + keys.map((k) => JSON.stringify(k) + ':' + canonStringify(x[k])).join(',') + '}';
  }
  return JSON.stringify(x);
}

function canonicalizeRows(rawRows) {
  const rows = rawRows.map((row) => {
    const out = {};
    for (const [k, v] of Object.entries(row)) out[k] = canonValue(v);
    return out;
  });
  rows.sort((a, b) => {
    const sa = canonStringify(a), sb = canonStringify(b);
    return sa < sb ? -1 : sa > sb ? 1 : 0;
  });
  return rows;
}

async function sha256Hex(text) {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

// ---------------------------------------------------------------------------
// Work unit execution
// ---------------------------------------------------------------------------

const post = (msg) => self.postMessage(msg);
const status = (stage, detail) => post({ type: 'status', stage, detail: detail || '' });

async function runWorkUnit(manifest, options) {
  options = options || {};
  const t0 = performance.now();
  const { datasetUrl, sql } = validateManifest(manifest, options);
  const maxBytes = Number(manifest.limits?.max_dataset_bytes)
    || options.maxDatasetBytes || DEFAULTS.maxDatasetBytes;

  // Engine version: manifest pin, overridable via RSS_OPTIONS (config seam).
  const pinned = /^duckdb-wasm@([\w.-]+)$/.exec(manifest.kernel.engine_version || '');
  const engineVersion = options.engineVersion || (pinned ? pinned[1] : DEFAULTS.engineVersion);
  const cdnBase = options.cdnBase || DEFAULTS.cdnBase;

  status('init', `loading @duckdb/duckdb-wasm@${engineVersion}`);
  const duckdb = await import(`${cdnBase}@${engineVersion}/+esm`);

  const dist = `${cdnBase}@${engineVersion}/dist`;
  const candidates = {
    mvp: { mainModule: `${dist}/duckdb-mvp.wasm`, mainWorker: `${dist}/duckdb-browser-mvp.worker.js` },
    eh: { mainModule: `${dist}/duckdb-eh.wasm`, mainWorker: `${dist}/duckdb-browser-eh.worker.js` },
  };
  const bundle = options.forceBundle
    ? candidates[options.forceBundle]
    : await duckdb.selectBundle(candidates);

  const telemetry = new NetTelemetry(datasetUrl);

  // AIDEV-NOTE: CDN worker scripts are cross-origin, so we importScripts them
  // from a same-origin Blob. The net shim is prepended into that Blob — the
  // only place httpfs's synchronous XHR traffic is observable.
  const blob = new Blob(
    [
      buildNetShim(datasetUrl, maxBytes),
      `importScripts(${JSON.stringify(bundle.mainWorker)});`,
    ],
    { type: 'text/javascript' },
  );
  const blobUrl = URL.createObjectURL(blob);
  const dbWorker = new Worker(blobUrl);

  let db = null;
  try {
    db = new duckdb.AsyncDuckDB(new duckdb.ConsoleLogger(duckdb.LogLevel.WARNING), dbWorker);
    await db.instantiate(bundle.mainModule, bundle.pthreadWorker ?? null);
    // AIDEV-NOTE: filesystem config is what forces partial reads.
    // reliableHeadRequests=true makes httpfs trust a HEAD+Range probe (S3
    // returns 206 + Content-Length — verified Step 0) and open the file as a
    // seekable remote handle → row-group range reads. allowFullHTTPReads=false
    // makes a full-file download a hard error rather than a silent fallback,
    // so a mis-hosted dataset FAILS LOUD instead of blowing the byte budget.
    // castBigIntToDouble=false keeps COUNT/int64 exact for canonicalization.
    await db.open({
      path: ':memory:',
      query: { castBigIntToDouble: false },
      filesystem: {
        allowFullHTTPReads: options.allowFullHttpReads === true,
        reliableHeadRequests: options.reliableHeadRequests !== false,
      },
    });
    const conn = await db.connect();

    let engineReported = 'unknown';
    try {
      const v = await conn.query('SELECT version() AS v');
      engineReported = v.toArray()[0].toJSON().v;
    } catch (_) { /* telemetry only */ }

    // Best-effort memory cap (Step 3 probe support); wasm build may reject it.
    let memoryLimitApplied = false;
    try {
      await conn.query(`SET memory_limit='${options.memoryLimit || DEFAULTS.memoryLimit}'`);
      memoryLimitApplied = true;
    } catch (_) {}

    // AIDEV-NOTE: DuckDB-Wasm >= 1.30 (DuckDB 1.4.x) autoloads the parquet
    // extension from extensions.duckdb.org at first read_parquet() — an extra
    // runtime dependency fetched over the network (counted in engine bytes,
    // logged in SPIKE_LOG). This seam redirects it to a mirror (config, not
    // code change); the URL comes from trusted RSS_OPTIONS, never manifests.
    if (options.extensionRepository) {
      const repo = String(options.extensionRepository).replaceAll("'", '');
      await conn.query(`SET autoinstall_extension_repository='${repo}'`);
      await conn.query(`SET custom_extension_repository='${repo}'`);
    }

    // AIDEV-NOTE: THE load-bearing call for partial reads. Passing an http URL
    // straight to read_parquet() lets DuckDB-Wasm's open heuristic default to a
    // full-file download. Registering the URL explicitly with protocol HTTP (4)
    // and directIO=false makes httpfs treat it as a seekable remote file and
    // fetch only the row groups the predicate needs, via HTTP Range. The kernel
    // then references a fixed internal filename, never the raw URL.
    const REGISTERED = 'rss_dataset.parquet';
    await db.registerFileURL(REGISTERED, datasetUrl, duckdb.DuckDBDataProtocol.HTTP, false);

    status('query', 'executing kernel (HTTP range reads happen now)');
    const tq0 = performance.now();
    const finalSql = sql.replaceAll('$RSS_DATASET_URL', REGISTERED);
    const table = await conn.query(finalSql);
    const queryMs = performance.now() - tq0;

    const maxRows = Number(manifest.limits?.max_result_rows) || 100000;
    if (table.numRows > maxRows) throw new Error(`result too large: ${table.numRows} rows > ${maxRows}`);
    const rawRows = table.toArray().map((r) => r.toJSON());

    status('canonicalize', `${rawRows.length} result rows`);
    const rows = canonicalizeRows(rawRows);
    const envelope = {
      kernel_type: manifest.kernel.type,
      row_count: rows.length,
      rows,
      wu_id: manifest.wu_id,
      wu_version: manifest.wu_version,
    };
    const canonical = canonStringify(envelope);
    const hash = await sha256Hex(canonical);

    await conn.close();

    // Give trailing BroadcastChannel messages a beat to arrive before snapshot.
    await new Promise((r) => setTimeout(r, 250));

    const wallMs = performance.now() - t0;
    // performance.memory is Chrome-only; null elsewhere (recorded as such).
    const mem = self.performance && performance.memory
      ? { usedJSHeapSize: performance.memory.usedJSHeapSize, jsHeapSizeLimit: performance.memory.jsHeapSizeLimit }
      : null;

    post({
      type: 'done',
      payload: {
        wu_id: manifest.wu_id,
        hash,
        canonical,
        rows,
        telemetry: {
          wall_ms: Math.round(wallMs),
          query_ms: Math.round(queryMs),
          engine_pinned: `duckdb-wasm@${engineVersion}`,
          engine_reported: engineReported,
          wasm_bundle: bundle.mainModule.includes('-eh') ? 'eh' : 'mvp',
          cross_origin_isolated: !!self.crossOriginIsolated,
          memory_limit_applied: memoryLimitApplied,
          js_heap: mem,
          net: telemetry.snapshot(Number(manifest.dataset.size_bytes) || null),
          user_agent: navigator.userAgent,
        },
      },
    });
  } finally {
    telemetry.close();
    try { if (db) await db.terminate(); } catch (_) {}
    dbWorker.terminate();
    URL.revokeObjectURL(blobUrl);
  }
}

self.onmessage = (e) => {
  const { type, manifest, options } = e.data || {};
  if (type !== 'run') return;
  runWorkUnit(manifest, options).catch((err) => {
    post({ type: 'error', message: String(err && err.message || err), stack: String(err && err.stack || '') });
  });
};
