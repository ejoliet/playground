# Lab notes

## Scope and setup

All local writes (including virtualenv, package cache, temp files, bare Git object
store and fixtures) stayed under `/workspace/range-oracle`. The repository had no
AGENTS.md or existing range-oracle directory. The branch is
`experiment/range-oracle`, based on `ejoliet/playground`'s `master`.

Chose Python because standard ZIP, PyArrow, Astropy and APSW can use a small
file-like/VFS adapter. SQLite's built-in Python module cannot substitute arbitrary
remote reads, so used APSW's read-only VFS instead. No production filesystem,
proxy, daemon or application was built. Reader algorithms are unchanged; callers
must supply the adapter. Transparent interception of arbitrary binaries is not
implemented.

## Research and failures

* Initial sandboxed network and socket access failed. Retried through the
  environment's approved execution mechanism; no external project files needed.
* fsspec and DuckDB documentation hosts returned 403. Inspected the installed
  fsspec source and located versioned DuckDB 2.0 Markdown on GitHub. Guessed
  `stable`/`current` source paths returned 404; the repository tree identified
  the correct paths. These are retrieval failures, not benchmark failures.
* Existing fsspec background prefetch already implements much of the proposed
  generic mechanism. Novelty cannot be claimed for format-blind read-ahead.
* First loopback timing pilot had an extra ~40 ms on small responses: the server
  sent headers and body separately under TCP delayed ACK/Nagle interaction.
  Enabled TCP_NODELAY on accepted server sockets, discarded pilot timings, and
  restarted. This is why a real HTTP validation matters even for a simple model.
* The final timing sweep runs six independent benchmark jobs concurrently to
  reduce runtime. Within each job requests remain serial. Delay and bandwidth
  are per request, not a shared-link congestion model. Each job has its own cold
  cache and connection; results are not claims about shared-link throughput.

## Early observations that motivated additional tests

* ZIP metadata reopening dropped from 24 requests to 3 with plain exact caching.
* A perfectly regular stride created ~91% demand hits but *more* HTTP requests.
  Counting hits as a performance proxy would have produced the wrong conclusion.
* Fixed read-ahead polluted the small SQLite cache on random point lookups.
* Fixed read-ahead fetched each random 4 KiB read as 64 KiB. Low bandwidth can
  reverse the apparent benefit of saving a network round trip elsewhere.
* Astropy section reads expose sequential row locality. PyArrow already issues
  relatively large column reads and gets little from blind forward extension.
* ZIP compressed members are slightly larger than 64 KiB. A 64 KiB extension
  can cover a local header but fail to cover the following entire compressed
  payload, causing duplicated traffic. This implementation checks whole-range
  containment, not arbitrary interval assembly; the fsspec block comparison
  tests a different cache geometry.
* Added an explicit batch experiment because merging an already recorded whole
  trace would unfairly give the optimizer knowledge of future synchronous reads.
* Added fsspec BackgroundBlockCache to distinguish prediction from useful
  asynchronous overlap. The naive stride predictor is intentionally synchronous;
  its failure cannot refute asynchronous prefetch in general.

## Decisions and boundaries

No training trace is reused as a warm cache. Generated fixtures use a fixed seed,
versions and hashes are recorded. Byte ranges are verified against fixture bytes,
and every actual reader's output digest is compared across policies. The wrapper
never examines file content. Semantic hashes are reader-specific and not a
cross-platform serialization guarantee.

No WAN benchmark, ASDF integration, DuckDB runtime integration, mmap interception,
multi-client cache, ETag revalidation, TLS benchmark, cache persistence, compressed
HTTP bodies or write support. These omissions are explicit rather than partial
integrations. FITS/ZIP/Parquet/SQLite fixtures are roughly 8–17 MiB: large relative
to the 64 KiB–1 MiB cache budgets, not evidence about terabyte-scale deployments.

## Final supplemental observations

The standard fsspec block LRU nearly halves clustered ZIP time relative to the
custom adaptive interval cache despite a smaller resident allowance. Splitting
and reusing blocks handles overlapping parser reads better than whole-range
containment. This is a more promising immediate improvement than prediction.

Background prefetch does help when 20 ms/read of application work overlaps I/O:
clustered ZIP foreground 1.581 → 1.116 s, or 1.199 s with background drain charged.
Without that compute gap the same trace gains essentially nothing. Random
access sends roughly 50% more bytes and runs slower. All background transfers
are drained before the next trial, so trailing work cannot silently escape the
traffic accounting or warm the next trial.

Validation finished with 33 passing tests, 585 measured HTTP trials, 1,209 model
rows, 60 fsspec trials and 85 full-reader executions. `verify_results.py` checks
completeness, deterministic metrics, equal reader outputs and payload budgets.
