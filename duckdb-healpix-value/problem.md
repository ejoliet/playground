# Problem: does DuckDB need a HEALPix extension, and for whom?

**Author**: Emmanuel Joliet (`ejoliet`)
**Date**: 2026-11-11
**Status**: Draft — input to a fire-and-forget research run (`prompt.md`)

## Problem

DuckDB has no HEALPix (Hierarchical Equal Area isoLatitude Pixelization) or MOC (Multi-Order Coverage) support. Its `spatial` extension is planar: wrong near the poles and across RA = 0.

Every astronomy tool on DuckDB therefore hand-rolls "cone → pixel ranges → haversine", each one differently and mostly untested. Anything beyond a literal cone (cross-match, coverage maps, per-row regions) leaves SQL for Python or JavaScript.

I am building an extension to close this gap: `github.com/ejoliet/healpix-duckdb`. Before spending Gates 1–5 on it, I need to know **which use cases it changes, on which axis, and by how much**.

## The decision this feeds

- Finish the extension through Gate 5, or scope it down.
- Which use cases to lead with in the README and a public pitch.
- Whether the v1 non-goal "no cross-match join operator" is the wrong cut.

## What we do not know

All gains below are **untested priors** from a chat answer. None is measured.

The main doubt: HATS (Hierarchical Adaptive Tiling Scheme) files already carry `_healpix_29`. For a literal cone, a client can compute pixel ranges itself and pass `BETWEEN` filters. So the extension may add no speed there, only less code.

The main objection: the `geography` community extension (S2 cells) already does correct spherical predicates. The claim to test is that S2 cannot prune HATS or express MOC.

## Use cases

| # | Slug | Use case | Without the extension (today) | What the extension would change | Prior |
|---|------|----------|-------------------------------|---------------------------------|-------|
| 1 | `xmatch` | Cross-match two catalogs | Python KD-tree around DuckDB (e.g. `pyacid`), or a hand-made bucket join + haversine | Pixel-bucket join with neighbours, pure SQL | large |
| 2 | `moc-column` | Coverage as data: ObsCore footprints, survey overlap, probability sky map × galaxy catalog | `mocpy` outside the database, or row-by-row polygon tests | MOC values in a column; overlap, union, area in SQL | large |
| 3 | `per-row-cones` | Watchlist × alert stream; each row has its own cone | Python loop, or cross join + haversine | Cone → pixel ranges per row, then a range join | large |
| 4 | `adql-literal` | Literal cone or polygon on HATS (ADQL compilers, TAP on DuckDB) | Client computes ranges, sends `BETWEEN` lists + haversine macro | One tested call; partition list from a macro | medium, same speed |
| 5 | `sql-only` | CLI, dbt, R, Java clients with no Python | Pure SQL macros for ang2pix and cone → ranges, if feasible at all | Functions exist | medium |
| 6 | `browser` | DuckDB-WASM tools | Separate JS HEALPix library + generated range SQL | One extension load | medium |
| 7 | `ingest` | Index raw ra/dec data: compute pixel, sort, write Parquet | Python round trip | One `COPY` statement | medium |
| 8 | `density` | Sky density and completeness maps | Bit shift on `_healpix_29`; nothing for raw ra/dec | `GROUP BY` pixel at any order | small |
| 9 | `lightcurves` | Position → objects → photometry rows in a light-curve lake | Object table is already position-indexed | Little | small |
| 10 | `lake-partition` | Iceberg or DuckLake partition/sort column | Materialise a pixel column once | Helps fill it | small |
| 11 | `map-analysis` | Spherical harmonics, CMB maps | `healpy` | Nothing; not a SQL workload | none |
| 12 | `distributed` | Rubin-scale joins | LSDB + Dask | Nothing; DuckDB is single node | none |
| 13 | `s2-h3` | "Just use `geography` (S2) or `h3`" | Correct spherical predicates exist | HATS pruning and MOC | the objection |

## Arms to compare, per case

| Arm | What it is |
|-----|------------|
| **without** | Best of: pure SQL (macros allowed), Python around DuckDB, `geography` (S2) where it applies |
| **with** | The extension's SQL API, as listed in the repo README function tables |
| **oracle** | Independent truth: astropy separations, `mocpy`, brute force on a sample |

> ⚠️ The extension is unfinished. Per its README (2026-10-13): Gate 0 complete, Gate 1 next. Treat only `hpx_ang2pix` as existing; check at clone time.

So the **with** arm is a shim: DuckDB Python UDFs with the extension's names and signatures, backed by `cdshealpix` and `mocpy`. Shim timings are a floor for the real extension. Where the real `hpx_ang2pix` builds, native vs shim on 10M points gives a calibration factor.

## Verdict rules

One verdict per case, set by measurements, not by argument.

| Verdict | Rule |
|---------|------|
| **MATTERS** | No pure-SQL baseline exists, or the best baseline returns wrong rows on edge data, or **with** is ≥ 3× faster than the best baseline at 10M rows |
| **MARGINAL** | Only gain is ≥ 50% fewer lines of query code, or 1.5–3× speed |
| **NO** | Baseline is pure SQL, correct, and within 1.5× |
| **UNPROVEN** | Needs the real extension or a browser to measure |

- Record the winning axis: capability, correctness, speed, or code.
- If the calibration factor would flip a speed verdict, say so next to it. Do not flip it.
- Edge data is mandatory: Dec = ±90, within 1 arcsec of a pole, RA = 0 and 359.9999, a clump straddling RA = 0, a polygon covering a pole.

**Project pass line**: finish through Gate 5 if at least 3 cases are MATTERS on capability or correctness, and at least one of them is something `geography` cannot do. Otherwise scope down to the cases that won.

> 💡 The thresholds (3×, 50%, 3 cases) are my starting guesses. Edit them before the run, not after.

## Constraints

- Angles in degrees, ICRS. Pixels NESTED, `BIGINT`, order 0–29.
- Case 6 has no browser step. Evidence is the cost of the **without** path: gzipped bytes of the JS library and the length of generated range SQL for a 0.5° cone at order 12. Extension WASM size and load time stay UNPROVEN.
- Cases 11 and 12 are argued from the other cases' numbers. No benchmark.
- Synthetic data at 1M and 10M rows, fixed seed. One real check: a small cone on public Gaia DR3 HATS (case 4).
- Under 2 GB on disk. No credentials.

## Out of scope

- Implementing the extension itself.
- RING scheme, non-ICRS frames, proper motion, time coverage (T-MOC).
- Any browser demo.

## Risk to the result

I want to be convinced, which biases the run toward yes. The guard is the **without** arm: it must be the best available baseline, and a NO or UNPROVEN verdict is a valid outcome.

## Next Steps

1. Edit the thresholds if they are wrong.
2. Commit this file to `duckdb-healpix-value/` in `ejoliet/research`.
3. Start a coding agent in that repo with `prompt.md`.
4. Read the scoreboard, then decide Gates 1–5 scope and the cross-match non-goal.
