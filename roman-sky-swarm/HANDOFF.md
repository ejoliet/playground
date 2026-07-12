# Roman Sky Swarm — Spike 0 Handoff

## Current state: Spike 0 complete, **conditional GO** at the gate

The load-bearing primitive is proven in an automated browser: a plain tab
fetches only the needed bytes (**8.99%** of a 356 MB S3 Parquet catalog), runs a
DuckDB-Wasm SQL kernel, and emits a deterministic **`sha256`** in **4.2 s**. All
six deliverables exist and are committed. What remains is the spike's
explicitly-manual cross-browser/cross-machine validation, which the CI container
physically cannot perform (see Blocker).

## Verified facts (don't re-litigate)

- **Dataset**: `…/roman_rubin_cats_v1.1.2_faint/galaxy_10307.parquet`
  (nasa-irsa-simulations, AWS Open Data). 356 MB, 4 row groups, 18 cols,
  3.56 M rows. CORS `*`, `Accept-Ranges: bytes`, 206 on HEAD+Range and GET+Range
  all verified via `curl` (Step 0 in `SPIKE_LOG.md`).
- **Engine pin is load-bearing**: `@duckdb/duckdb-wasm@1.28.0` (DuckDB 0.9.1)
  does row-group HTTP-Range reads → 8.99%. **1.30.0 and 1.32.0 regressed this
  and download the whole file (100%)**; 1.29.0 crashes. Do not bump the pin
  without re-running the Step-1 partial-read proof.
- **Determinism holds**: wu-001 hash `c138d412…f92301` is identical across 2
  runs, across duckdb-wasm 1.28.0 (partial) and 1.32.0 (full), and matches
  native DuckDB 1.5.4's aggregate values under `rss-canon-v0`.
- **Hosting**: the **eh** bundle runs with `crossOriginIsolated=false` / no
  SharedArrayBuffer → **GitHub Pages is fine** for single-threaded work units.
- **Predicate pruning**: `redshift` predicates prune row groups; `ra`/`dec` do
  not (spatial selectivity is file-level, one file per HEALPix pixel).

## Open blocker (why the gate is only "conditional")

This container's egress proxy resets Chromium's TLS ClientHello, so the browser
cannot reach S3/jsdelivr directly. In-container verification therefore runs
through a **localhost relay** (`scratchpad/drive.mjs`, not committed — it is a
test harness, not a deliverable) that forwards to S3 via the agent proxy,
preserving Range/206 byte-for-byte. Native `curl`/DuckDB confirm the relay is
faithful. **The manual GO-gate check must run on real machines** with direct S3
access — the container cannot do it.

## Exact next step (to fully close the GO gate)

1. Serve and open the page on a real machine:
   ```bash
   cd roman-sky-swarm && python3 -m http.server 8000
   # open http://localhost:8000/ , select wu-001, click "Run work unit"
   ```
2. Run it in **Chrome and Firefox on ≥2 machines**. Confirm every run shows
   `sha256 = c138d412a3dfd58486db3018597cae99b171f36730d5797ab0c3fdb60bf92301`
   and bytes < 20%. Use "Copy last run report" to collect them.
3. Note peak memory (Chrome DevTools → Memory) for the reference slice and for
   `wu-002-stress`; confirm under ~1 GB.
4. If all hashes match → gate fully met, proceed to the next phase.

## Next phase (do NOT start now — separate session)

On full GO: write a Type A RDD spec (per the `readme-driven-dev` skill) for the
coordinator — static manifest registry + result-collection endpoint,
redundancy-based validation (N independent tabs, majority hash), and the first
real workload (catalog statistics / photometric QA, the cheapest deterministic
candidates in `VISION.md`). The engine-version pin and `rss-canon-v0` become
part of the work-unit contract the coordinator enforces.

## Watch-outs for the next agent

- Never bump `engine_version` (manifest) or `DEFAULTS.engineVersion` (worker.js)
  without re-running the partial-read proof — 1.30+ silently full-downloads.
- `worker.js` forces partial reads via `filesystem.reliableHeadRequests=true` +
  `allowFullHTTPReads=false` (full download = hard error, not silent fallback) +
  `registerFileURL(..., HTTP, false)`. All three matter.
- Byte-budget + net telemetry are enforced by a shim injected into DuckDB's own
  worker (httpfs gives no telemetry API) — see the `AIDEV-NOTE`s in `worker.js`.
- `VISION.md` is a placeholder; replace with the real vision document.
