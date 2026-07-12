# Roman Sky Swarm — Spike 0 Log

Chronological record of what was tried, what broke, and measured numbers.
See `README.md` for what this spike proves and `HANDOFF.md` for next steps.

---

## Step 0 — Dataset verification (2026-07-11)

**Candidate**: OpenUniverse2024 Roman/Rubin simulated catalogs, AWS Open Data
registry, bucket `nasa-irsa-simulations`.

**Chosen file**:

```
https://nasa-irsa-simulations.s3.amazonaws.com/openuniverse2024/roman/preview/roman_rubin_cats_v1.1.2_faint/galaxy_10307.parquet
```

- Size: **373,399,168 bytes** (356 MB)
- ETag: `"26ea094798cf98e6e787d4e216d11899-45"` (S3 multipart, 45 parts — NOT a plain md5)
- Last-Modified: `Fri, 31 May 2024 22:42:50 GMT`

### Check 1 — CORS ✅

`curl -sSI -H "Origin: https://example.github.io" <URL>`:

```
HTTP/1.1 200 OK
Access-Control-Allow-Origin: *
Access-Control-Allow-Methods: HEAD, GET
Access-Control-Expose-Headers: ETag, x-amz-meta-custom-header
Access-Control-Max-Age: 3000
Vary: Origin, Access-Control-Request-Headers, Access-Control-Request-Method
```

A browser `fetch` with a `Range` header is *not* CORS-safelisted, so it triggers
an OPTIONS preflight. Verified the preflight allows it:

`curl -sSI -X OPTIONS -H "Origin: https://example.github.io" -H "Access-Control-Request-Method: GET" -H "Access-Control-Request-Headers: range" <URL>`:

```
HTTP/1.1 200 OK
Access-Control-Allow-Origin: *
Access-Control-Allow-Methods: HEAD, GET
Access-Control-Allow-Headers: range
Access-Control-Max-Age: 3000
```

**AIDEV-NOTE (potential gotcha, did not bite)**: `Access-Control-Expose-Headers`
does **not** include `Content-Range`. `Content-Length` is CORS-safelisted so the
HEAD-based file-size probe works, and DuckDB does not need to *read*
`Content-Range` on a 206 (it knows the range it asked for), so this is benign —
but any client that parses `Content-Range` cross-origin will get `null` here.

### Check 2 — Accept-Ranges ✅

`curl -sSI <URL>`:

```
HTTP/1.1 200 OK
Accept-Ranges: bytes
Content-Length: 373399168
Content-Type: binary/octet-stream
Server: AmazonS3
```

Range probe `curl -sS -D - -o /dev/null -H "Range: bytes=0-1023" <URL>`:

```
HTTP/1.1 206 Partial Content
Content-Range: bytes 0-1023/373399168
Content-Length: 1024
```

First 4 bytes are the Parquet magic `PAR1`. Last 8 bytes: footer length
`10805` (LE uint32) + `PAR1`.

### Check 3 — Parquet with multiple row groups ✅

Fetched the last 1 MB via Range, parsed the footer with pyarrow 25.0.0
(first attempt with only the 10.8 KB footer failed — pyarrow prefetches a
64 KB tail region for page indexes; 1 MB tail worked):

- **3,561,877 rows, 4 row groups, 18 columns**, written by `parquet-cpp-arrow 12.0.1`
- Row groups: 3 × 1,000,000 rows (~100 MB compressed each) + 1 × 561,877 rows (~61 MB)

Column-chunk statistics per row group (from footer metadata):

| column | rg0 | rg1 | rg2 | rg3 |
|---|---|---|---|---|
| `ra` min..max | 8.700..11.619 | 8.714..11.621 | 8.714..11.617 | 8.713..11.616 |
| `dec` min..max | −44.991..−41.805 | −44.990..−41.807 | −44.991..−41.800 | −44.984..−41.808 |
| `redshift` min..max | **0.013..2.037** | 1.041..1.754 | 0.985..3.088 | 1.921..2.422 |

**Finding (answers open question 3)**: `ra`/`dec` span the full tile in *every*
row group — sky-region predicates cannot prune row groups *within* a file.
Spatial partitioning in this catalog lives at the **file** level (one file per
HEALPix pixel; `10307` is the pixel id). But `redshift` is partially sorted:
a predicate `redshift < 0.5` satisfies only rg0's zone map and prunes rg1,
rg2, rg3 (mins 1.041 / 0.985 / 1.921 ≥ 0.5... rg2 min is 0.985 ≥ 0.5, pruned).
So the reference kernel uses a redshift predicate for the row-group-pruning
proof, and the byte-savings story for sky predicates is file-level selection —
logged as a scheduler-design input for later phases.

Per-column compressed sizes (all row groups): `ra`/`dec`/`redshift` ≈ 29.6 MB
each; whole file 373 MB over 18 columns. Predicted bytes for a kernel touching
(`ra`, `dec`, `redshift`) restricted to rg0 by predicate:
**≈ 24.8 MB = 6.7% of file** (plus footer + HEAD overhead). Well under the
20% GO gate if pruning works from the browser.

### Dataset checksum for the manifest

Full-file sha256 would require downloading 356 MB, and the S3 multipart ETag is
not a content hash. For Spike 0 the manifest pins the **footer**: sha256 of the
last 10,813 bytes (footer struct + length + magic, byte range
`373388355–373399167`):

```
9559a4045bf263a99cf76c1245ccbf1da519b704b7f3e0a85d6cd659b424722b
```

The footer transitively commits to all row-group offsets/sizes and column
statistics, so a silently swapped file body would be caught by result-hash
divergence anyway. AIDEV-TODO: full-file or per-row-group content hashes need a
one-time trusted indexing pass — coordinator-phase concern.

### Engine pin

**`@duckdb/duckdb-wasm@1.28.0`** (DuckDB 0.9.1). Originally pinned 1.32.0 (latest
stable; dist-tags point at 1.33.1-dev, avoided) — but **1.32.0 does not do
partial reads** (see Step 1 version sweep). 1.28.0 does. Pin is load-bearing.

**Verdict: OpenUniverse2024 passes all three checks. No fallback needed.**

---

## Step 1 — Partial-read proof

**Test harness.** This container's egress proxy resets Chromium's TLS
ClientHello (curl/openssl succeed; the browser fingerprint is refused), so the
browser cannot reach S3/jsdelivr directly. `scratchpad/drive.mjs` runs the real
`index.html`/`worker.js` in headless Chromium against a **localhost relay** that
forwards to S3/jsdelivr through the agent proxy, preserving `Range`/206
semantics byte-for-byte. Ground-truth request logging is at the relay. Real
browser + direct-S3 runs are the manual GO-gate validation (below).

**Result (wu-001, shipped defaults, duckdb-wasm 1.28.0):**

| metric | value | gate |
|---|---|---|
| dataset bytes fetched | **33,562,240 (8.99% of file)** | < 20% ✅ |
| dataset requests | 19–23 (adaptive read-ahead) | — |
| wall time | **4.2 s** (3.6 s query) | < 60 s ✅ |
| engine CDN bytes | 18.1 MB (wasm, one-time) | — |
| result hash | `c138d412a3dfd58486db3018597cae99b171f36730d5797ab0c3fdb60bf92301` | — |

Relay request trace (confirms row-group range reads, not a full download):

```
HEAD Range: bytes=0-              -> 206  (reliableHeadRequests probe)
GET  Range: bytes=373399160-...67 -> 206  (footer length+magic, 8 B)
GET  Range: bytes=373388355-...59 -> 206  (footer, 10,805 B)
HEAD Range: bytes=0-              -> 206
GET  Range: bytes=20842533-...    -> 206  (rg0 redshift column, exactly where
GET  Range: bytes=20842534-...    -> 206   native DuckDB reads it — see below)
... exponential read-ahead: 16 KB, 64 KB, 256 KB, 1 MB, 4 MB chunks ...
```

**Native cross-check.** Native DuckDB 1.5.4 against the *identical* relay reads
HEAD + footer(256 KB) + one column chunk(8.3 MB) = ~2.3% of file in 2.2 s. So
the dataset, S3, and relay all support predicate-pushdown range reads; the only
variable is the Wasm engine. (Wasm fetches more than native — 8.99% vs 2.3% —
because its read-ahead coalesces larger contiguous windows. Still well under
gate.)

### The load-bearing finding: DuckDB-Wasm 1.32.0 REGRESSED partial reads

Version sweep, same kernel, same relay, same config:

| duckdb-wasm | DuckDB | behavior | bytes |
|---|---|---|---|
| **1.28.0** | 0.9.1 | **row-group range reads** | **8.99%** ✅ |
| 1.29.0 | — | crashes (`table index is out of bounds`) | — |
| 1.30.0 | — | full download | 100% |
| 1.32.0 | 1.4.3 | full download | 100% |

In 1.30+, the `filesystem.reliableHeadRequests=true` config no longer triggers
the `HEAD Range: bytes=0-` → 206 → seekable-handle path; the engine silently
downloads the whole file. Confirmed the config *is* parsed (setting
`allowFullHTTPReads:false` on 1.32.0 makes the open FAIL rather than
full-download — so `allowFullHTTPReads` takes effect but `reliableHeadRequests`
no longer does). Reproduced identically outside the browser (duckdb-wasm node
bundle), so it is not a headless/relay artifact — it is the engine.

**Consequence for the platform:** the engine version is a pinned, security- and
correctness-relevant part of the work-unit contract, not an incidental
dependency. `engine_version` lives in the manifest and the worker refuses to
silently "upgrade." AIDEV-TODO (coordinator phase): track upstream
(duckdb/duckdb-wasm) for a fixed ≥1.29 release, or carry a self-hosted 1.28.0
mirror; either way the pin is validated by re-running this proof, never bumped
blind.

### Open question 1 — byte telemetry from httpfs? ANSWERED

httpfs exposes **no** byte-level fetch API. DuckDB's HTTP reads are synchronous
XHR issued from inside its own Web Worker, so a fetch/XHR wrapper on the *page*
or the orchestrator worker sees nothing. `worker.js` injects a telemetry+budget
shim into the DuckDB worker's global scope (prepended to the Blob that
`importScripts`es the CDN worker) and reports over a `BroadcastChannel`. This is
also where the hard byte-budget is enforced (pre-flight on each requested range
size) — nothing outside that worker can abort a synchronous XHR mid-query.

### Open question 3 — row-group layout vs predicates? ANSWERED (Step 0)

`redshift` predicates prune row groups (partially sorted; `redshift < 0.5`
selects rg0, prunes rg1–rg3). Sky (`ra`/`dec`) predicates do **not** prune —
every row group spans the full tile; spatial selectivity is file-level (one file
per HEALPix pixel). Scheduler-design input for later phases.

## Step 2 — Determinism proof

**Canonicalization contract — `rss-canon-v0`** (implemented in `worker.js`,
`canonValue`/`canonStringify`):

1. Per-cell by type: `null`→`null`; bool/string as-is; **float → fixed 6-decimal
   string** via `toFixed(6)` (ECMA-262 fully specifies the rounding →
   engine-independent), with `-0`→`0` and non-finite→`"NaN"`/`"Infinity"`;
   int64/bigint → JSON number if `|v| ≤ 2^53−1` else decimal string.
2. Each row → object with lexicographically sorted keys, no whitespace.
3. Rows sorted by their canonical serialization (order-independent even without
   SQL `ORDER BY`).
4. Envelope `{kernel_type,row_count,rows,wu_id,wu_version}` → same stringify →
   `sha256` over UTF-8 (WebCrypto).

**Observed hashes for wu-001 → all identical:**

- `c138d412…f92301` — headless Chromium, duckdb-wasm **1.28.0** (partial read), ×2 runs
- `c138d412…f92301` — headless Chromium, duckdb-wasm **1.32.0** (full download)
- native DuckDB **1.5.4** produces the same aggregate values (canonicalizes to
  the same envelope)

**Open question 2 — float determinism with plain SQL aggregates? ANSWERED:**
bit-identical hashes across **three** DuckDB engine generations (0.9.1 / 1.4.3 /
1.5.4) and across full-vs-partial read strategies. `SUM`/`AVG` over ~113 K
doubles agreed to ≥6 decimals, which the fixed-6-decimal rule then makes
exactly equal. So for this kernel class, plain-SQL float aggregates are
reproducible under `rss-canon-v0` — no need to fall back to integer/decimal-only
kernels for v0. **Caveat (`AIDEV-NOTE` in worker.js):** the 6-decimal rule
absorbs sub-1e-6 divergence but a value landing on a rounding half-ulp boundary
could still flip; higher-risk kernels (long double sums, SIMD reductions) should
be validated per-kernel, and the real Chrome-vs-Firefox check is still owed
(headless-Chromium-only here).

## Step 3 — Constraint probes

- **COOP/COEP / SharedArrayBuffer:** run reports `crossOriginIsolated=false`,
  `bundle=eh`. The **eh** (exception-handling, non-threaded) bundle is selected
  and works with **no** cross-origin isolation and **no** SharedArrayBuffer.
  → **GitHub Pages is viable** for Spike-0-class single-threaded work units (it
  cannot send COOP/COEP headers). If a future phase wants the threaded (`coi`)
  bundle for parallelism, hosting must move to Netlify `_headers` / Cloudflare
  Pages / a worker that sets COOP+COEP. Logged as a hosting constraint, not a
  blocker.
- **Byte-budget enforcement:** wu-002-stress with a 200 MB cap aborted mid-scan
  (`RSS byte budget exceeded: 218062464 > 209715200`) — the hard cap fires and
  surfaces as a graceful work-unit failure, exactly as designed.
- **Full-scan ceiling (memory/time upper bound):** wu-002-stress (all 4 row
  groups, 4 columns, ~3.56 M rows) with the cap raised completes at **325 MB /
  87.22% of file / 17.4 s**, distinct hash `e21ca1d1…`. The tab stays alive; a
  ~325 MB working set is well under the ~1 GB gate. Note the read-ahead
  amplification: ~99 MB of actual column data pulls ~325 MB because coalesced
  ranges span unneeded bytes on a non-selective scan — an argument for keeping
  work-unit predicates selective.
- **Peak JS heap:** `performance.memory` is unavailable in headless Chromium
  here (reported `null`), so exact peak heap is **not** captured in-container —
  owed to the manual real-browser validation.
- **Tab suspension (backgrounded 60 s):** not observable headless; the UI logs
  `visibilitychange` events for the manual test. Owed to real-browser validation.

## GO / NO-GO — automated portion

Proven in an automated browser (headless Chromium + relay):

- [x] **Bytes < 20%** — 8.99% ✅ (the load-bearing primitive)
- [x] **< 60 s on a laptop** — 4.2 s ✅
- [x] Deterministic checksummable result — stable across runs, engine versions,
      and read strategies ✅
- [x] Constraint probes logged (COOP/COEP, byte-budget, full-scan ceiling) ✅
- [~] **Identical SHA-256 across Chrome + Firefox on ≥2 machines** — strong
      evidence (identical across runs / 3 engine versions / native), but the
      literal cross-browser + cross-machine check is the spike's designated
      **manual** step and cannot run in this TLS-restricted container.
- [~] **Peak memory < ~1 GB** — reference slice ~33 MB and full scan ~325 MB
      both complete; exact peak heap not measurable headless.

**Recommendation: conditional GO.** The unproven primitive — browser fetches
only the needed bytes, runs a kernel, emits a bit-identical checksummable
result — is **proven**. The two `[~]` items are the explicitly-manual
validation the spike defines (real Chrome + Firefox on ≥2 machines against
direct S3); run `index.html` there, confirm hash `c138d412…f92301` for wu-001,
and the gate is fully met. See `HANDOFF.md`.
