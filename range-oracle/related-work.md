# Existing approaches and the experimental gap

Sources checked 2026-11-09. Retrieval status is in `results/sources.json`;
`research.py` refreshes the initial sources. Documentation on live websites can
differ from the pinned installed release. The installed fsspec implementation
was inspected directly after its documentation host returned HTTP 403.

| Approach | Already solves | Remaining limitation / implication here |
|---|---|---|
| [RFC 9111 §3.3–3.4](https://www.rfc-editor.org/rfc/rfc9111.html#section-3.4) | Storage of incomplete responses and combination of partial content under correct validators | Does not predict the next miss. A production implementation must use strong validators and enforce representation identity. This experiment uses immutable fixtures. |
| [NGINX slice cache](https://nginx.org/en/docs/http/ngx_http_slice_module.html) | Divides resources into cacheable fixed-size slices; cache keys include the slice range | Slice size trades request overhead against overfetch. This is an existing simple solution, not a new idea. |
| [fsspec caching](https://github.com/fsspec/filesystem_spec/blob/master/fsspec/caching.py) | `ReadAheadCache`, `BytesCache`, block LRU, whole-file and mmap caching; `BackgroundBlockCache` overlaps next-block fetching | Generic, format-independent prefetch already exists. Compare against it before claiming novelty. Block boundary and request size affect amplification. Supplemental experiment uses the installed implementation, including its boundary behavior. |
| [Arrow ParquetFile](https://arrow.apache.org/docs/python/generated/pyarrow.parquet.ParquetFile.html) | `pre_buffer` coalesces known column ranges and uses background I/O threads; column projection and row-group selection avoid unwanted data | The reader knows future ranges before a blind intermediary can. Arrow docs explicitly advise avoiding redundant filesystem read-ahead. We compare the same query with pre-buffering off/on, separately from identical-trace comparisons. |
| [DuckDB remote files](https://duckdb.org/docs/stable/core_extensions/httpfs/https.html), [performance guide](https://duckdb.org/docs/stable/guides/performance/how_to_tune_workloads.html) | HTTP Range access, Parquet projection/filtering; v2.0 asynchronous I/O and read-ahead depth; external file cache since v1.3 | Replacing these with serial generic requests could regress performance. DuckDB is researched, not benchmarked here; PyArrow is the working format-aware comparator. |
| [Linux mm/readahead.c](https://github.com/torvalds/linux/blob/master/mm/readahead.c) | Per-file sequential detection, window growth, asynchronous trigger pages, page-cache reuse | Already learns without file-format knowledge. Benefits depend on compute overlap and available bandwidth. Page-cache algorithms do not automatically optimize HTTP transactions. |

## What could still be useful?

A shared byte-range wrapper could help readers that issue small synchronous
reads, have weak caches, or repeatedly reopen metadata. It cannot merge a future
synchronous call it has not seen. It must either speculate by extending the
current request, issue extra requests concurrently, or accept an explicit batch
from the application. These are different information/transport budgets.

The experiment therefore separates:

* Exact-range LRU reuse, fixed extension, and history-gated extension on identical
  synchronous traces.
* A deliberately naive stride predictor issuing a separate synchronous fetch.
  This tests whether prediction accuracy alone helps; it is not a model of all
  possible asynchronous predictors.
* Existing fsspec asynchronous next-block prefetch against its own block-cache
  baseline, with and without application think time.
* Explicit batched overlap/nearby-range merging, and a separately labeled offline
  whole-trace merging bound. The offline bound is not deployable transparently.
* Arrow's format-aware pre-buffering, which changes the request trace and hence
  belongs in a query-equivalent comparison, not the identical-trace ranking.
