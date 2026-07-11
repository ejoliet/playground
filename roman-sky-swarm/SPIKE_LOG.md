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

`@duckdb/duckdb-wasm@1.32.0` (latest stable on npm; dist-tags `latest`/`next`
point at 1.33.1-dev builds — avoided). CDN assets verified present on
jsdelivr (`duckdb-browser.mjs`, eh/mvp worker JS + wasm; eh wasm ~39 MB class).

**Verdict: OpenUniverse2024 passes all three checks. No fallback needed.**

---

## Step 1 — Partial-read proof

_(pending)_

## Step 2 — Determinism proof

_(pending)_

## Step 3 — Constraint probes

_(pending)_

## Open questions

1. **Byte telemetry from httpfs?** _(pending)_
2. **Float determinism with plain SQL aggregates?** _(pending)_
3. **Row-group layout vs scientific predicates?** — Answered in Step 0: aligned
   with `redshift`, NOT with sky region (spatial selectivity is file-level).
