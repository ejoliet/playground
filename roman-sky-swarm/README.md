# Roman Sky Swarm — Spike 0

A browser-native distributed scientific-computing spike: prove that a **plain
browser tab** can fetch **only the needed bytes** of a large public Parquet
catalog over HTTP, run a scientific SQL kernel on it, and emit a
**bit-identical, checksummable result**. Everything else in the platform vision
(`VISION.md`) depends on this one primitive. This repo builds **only** that
probe — no scheduler, no coordinator, no upload, no P2P.

## What it proves

Given a declarative JSON work-unit manifest, a single static HTML page:

1. fetches a slice of a 356 MB OpenUniverse2024 Roman/Rubin galaxy catalog on
   AWS Open Data via **HTTP Range requests** (row-group + column pruning),
2. runs a fixed **DuckDB-Wasm** SQL kernel in a Web Worker,
3. canonicalizes the result (`rss-canon-v0`) and emits **`sha256(result)`**,
4. displays result + hash + bytes-downloaded + wall time.

Measured (headless Chromium, reference work unit `wu-001`):

| | result | gate |
|---|---|---|
| bytes fetched | **8.99% of file** (~33 MB of 356 MB) | < 20% ✅ |
| wall time | **4.2 s** | < 60 s ✅ |
| result hash | `c138d412…f92301`, stable across runs & engine versions | — |

## GO / NO-GO status: **conditional GO**

The load-bearing primitive is **proven**. The remaining gate items are the
spike's explicitly-manual validation — identical `sha256` in real **Chrome +
Firefox on ≥2 machines**, and peak-memory confirmation — which cannot run in the
CI container (its egress proxy blocks the browser's TLS to S3). Run `index.html`
in real browsers against direct S3 and confirm the wu-001 hash to fully close
the gate. Full detail, measurements, and the version-regression finding are in
[`SPIKE_LOG.md`](./SPIKE_LOG.md); next steps in [`HANDOFF.md`](./HANDOFF.md).

## How to run

No build step. Serve the directory over HTTP (a browser won't run ES-module
workers from `file://`) and open it:

```bash
cd roman-sky-swarm
python3 -m http.server 8000        # or: npx http-server -p 8000
# open http://localhost:8000/ , pick wu-001, click "Run work unit"
```

The page loads `workunits/wu-001.json`, fetches only the needed bytes of the
public dataset directly from S3, and shows the hash + telemetry. Run it in
Chrome and Firefox on two machines; **the hashes must match** — that is the
Spike-0 consensus check.

### Config seam (no code changes)

Inject `window.RSS_OPTIONS` before the page script to override, e.g.:

```html
<script>window.RSS_OPTIONS = { engineVersion: '1.28.0' /*, datasetUrl, cdnBase */ };</script>
```

## Files

| file | purpose |
|---|---|
| `index.html` | single-page UI: load manifest, run, show result/hash/telemetry, run history |
| `worker.js` | Web Worker: DuckDB-Wasm init, range-read query, `rss-canon-v0`, sha256, byte-budget + net telemetry |
| `workunits/wu-001.json` | reference work-unit manifest (redshift-binned galaxy stats; the GO-gate WU) |
| `workunits/wu-002-stress.json` | Step-3 probe: full-scan memory/time ceiling (not a GO-gate WU) |
| `SPIKE_LOG.md` | dataset verification, measurements, the DuckDB-Wasm version-regression finding |
| `HANDOFF.md` | current state, verified facts, open items, exact next step |
| `VISION.md` | platform vision (placeholder — see note in file) |

## Locked constraints

Vanilla JS + ES modules, **no framework, no bundler, no build step**; runs from
static HTTPS hosting; all CDN deps version-pinned (**`@duckdb/duckdb-wasm@1.28.0`**
— the pin is load-bearing, see `SPIKE_LOG.md`); `localStorage` namespaced
`rss.*` with in-memory fallback; declarative manifests only (no executable code,
SQL kernel is validated read-only); dynamic output rendered via `textContent`
only.
