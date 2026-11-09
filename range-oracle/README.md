# Range oracle: does blind byte-range prediction help?

**Verdict: supported for exploiting locality, but not for a general advantage of
adaptive prediction over simple caching/read-ahead.** In this experiment, the
simplest useful policy is a bounded cache with a modest fixed read-ahead window
for sequential readers. A two-transition sequential gate avoids much random
read amplification, at the cost of slower ramp-up. No learned model is needed.
This is a scoped experimental result, not a universal refutation of prediction.

## What was built

`oracle.py` is a content-blind, synchronous byte-range wrapper with an interval
LRU cache, tracing, and a seekable Python file adapter. It records offset, length,
sequence, start time, duration and demand hits. `workloads.py` integrates actual
PyArrow Parquet, standard-library ZIP, Astropy FITS section reads and SQLite via
an APSW read-only VFS. Parser code is unchanged; applications must supply the
file/VFS adapter. This is not transparent interception of arbitrary applications.

[Related work](related-work.md) covers HTTP partial-response caching, NGINX
slicing, fsspec caches/background prefetch, Arrow/DuckDB remote reads and Linux
read-ahead. Most mechanisms proposed here already exist. [Lab notes](notes.md)
record failed attempts and unexpected observations.

## Experimental design

Fixtures contain seeded random data: 8-column Parquet with 32 row groups, 128
compressed ZIP members, a 2048×2048 float32 FITS image, and a SQLite table with
16,384 approximately 1 KiB records. Files are approximately 8–17 MiB, versus
64 KiB, 256 KiB and 1 MiB cache budgets. Generated files are not committed;
versions, sizes, SHA-256 hashes and seed are in `results/environment.json`.

There are 13 workloads: projected Parquet reads with pre-buffering off/on,
clustered/random ZIP member reads, repeated ZIP metadata reopening,
sequential/random FITS rows, SQLite random point queries/sequential IDs,
and four explicitly synthetic controls (sequential, random, sequential→random,
constant stride). Actual readers produce nine workloads; synthetic controls
isolate patterns, not substitute for integrations.

Policies compared on **identical demand traces**, with a new cold cache per run:

| Policy | Behavior |
|---|---|
| `none` | Original range per demand; no cache |
| `cache` | Exact fetched intervals in a byte-bounded LRU; containment hits |
| `fixed` | Same cache; extend misses to at least 64 KiB forward |
| `adaptive` | Same cache/window; extend only after two observed contiguous transitions; stop on a noncontiguous demand |
| `stride` | Adaptive policy plus one-step constant-stride speculation after two equal positive strides; extra speculative requests are synchronous |

The last policy deliberately tests whether accurate prediction alone is enough.
It is **not** a competitive asynchronous predictor. `supplemental.py` separately
compares existing fsspec `BlockCache` and `BackgroundBlockCache`, using identical
192 KiB resident-cache limits and a 64 KiB allowance for a speculative result,
with 0 or 20 ms of simulated compute per read. Its cache geometry and hit
counter differ, so it has a separate table rather than a misleading common rank.

The explicit batch test merges overlapping/nearby requests supplied together.
`offline_batch_bound` in `model.csv` instead sees the entire trace and is labeled
an offline bound: it is not an online contender and does not satisfy the same
resident-cache constraints. A serial intermediary cannot merge unseen calls
without predicting them. Arrow's pre-buffering comparison is query-equivalent,
not trace-equivalent: it is explicitly allowed to change the trace.

### Timing and correctness

* `benchmark.py` first runs all live integrations against a real loopback HTTP
  server. The client requires `206`, exact `Content-Range`, identity encoding and
  exact length. This uses sockets and actual HTTP, not a mocked transport.
* It then replays the recorded reads with **20, 100 and 200 ms** of injected
  per-request round-trip delay and a 50 MiB/s transfer delay. The server sleeps
  for RTT + response bytes/bandwidth. TCP_NODELAY removes a delayed-ACK artifact.
* Three repeats per workload/policy/RTT, randomized job order: 585 measured HTTP
  runs. Six independent jobs run concurrently; each job's demand stream is
  serial. Bandwidth/delay are independent per request, not a shared-link model.
* `model.csv` additionally sweeps 1 and 50 MiB/s and three cache budgets, using
  `requests × RTT + bytes / bandwidth`. These are **modeled**, not measured WAN
  times. `replay_cpu_wall_seconds` measures local replay CPU/wall overhead only.
* `validate_live.py` also executes five actual reader workloads at 100 ms RTT,
  across four policies, checking that full-reader behavior agrees with replay.
  This is one timing sample per combination, not the three-repeat sweep.
* Every replayed byte is compared to the original fixture. Live-reader digests
  and demand traces are compared across all five policies; tests also verify
  randomized reads, budget enforcement, EOF/seek semantics and waste accounting.
* Files are immutable. Server fixture memory is warm by design to isolate network
  effects, but client/reader caches start cold. No HTTP/shared persistent cache,
  learned warm-up state, or training trace is reused across trials.

### Metric definitions

`bytes` counts response body bytes, including repeated and speculative fetches;
headers/TCP/TLS are excluded. `useful_unique_bytes` is the union of demand ranges,
not their repeated lengths. `unused_bytes` counts bytes never consumed **within
each fetch incarnation**, including evictions and the final speculative tail.
It is not simply transferred minus unique useful bytes (useful repeated fetches
are possible). Demand `hit_rate` means an entire demand was served from cache.

`cache_peak_bytes` is retained payload, bounded by the stated budget. Python
allocation peaks from `tracemalloc` include wrapper instrumentation and transient
response/output buffers, but exclude native libraries, the preloaded fixture and
server process memory. They are not total RSS. Demands larger than the budget
bypass cache; the response and consumer still require memory. Trace/metric logs
are intentionally retained and grow with workload length. fsspec's raw cache
counters are internal block hits, **not comparable to demand hit rates**; its
unused-byte statistic is a labeled lower bound based on all demand intervals,
not exact per-incarnation eviction accounting.

## Results

See [measured tables](results/tables.md), [per-repeat HTTP data](results/http.jsonl),
[summary with min/max](results/summary.csv), and [model/budget sweep](results/model.csv).
The numeric findings below are filled from the recorded run, not estimates.

At **100 ms RTT, 50 MiB/s, 256 KiB payload budget** (three-repeat medians):

| Observation | Measured result |
|---|---|
| Plain caching solves repeated metadata | ZIP metadata: 24 → 3 requests, 2.424 → 0.306 s (**7.9×**); only 6,716 retained bytes needed |
| Fixed beats adaptive on sequential reads | FITS rows: 1.813 s baseline, **0.306 s fixed**, 0.506 s adaptive; 18 → 3 vs 5 requests |
| Same across another format | SQLite sequential IDs: 2.022 s baseline, **0.306 s fixed**, 0.707 s adaptive |
| Speculation can evict useful data | Random SQLite: cache **2.626 s / 102,500 bytes**, fixed 2.958 s / 1,900,544 bytes; fixed makes 29 requests vs cache's 26 |
| High hit rate can be misleading | Constant stride: predictor has **90.6% demand hits**, but 33 requests vs baseline 32, and 3.334 s vs 3.225 s |
| Format-aware planning beats blind prediction | Parquet query: Arrow pre-buffering **9 → 5 requests**, 0.917 → 0.515 s, same 590,440 bytes; no generic policy improves either trace |
| Phase change favors different policies at different bandwidths | 50 MiB/s measured: fixed 1.731 s vs adaptive 1.918 s; at 1 MiB/s / 20 ms **modeled**: fixed 1.403 s vs adaptive 0.513 s |

The FITS fixed-policy gain persists across RTT: baseline/fixed medians are
0.374/0.066 s at 20 ms, 1.813/0.306 s at 100 ms and 3.615/0.606 s at 200 ms.
For the 100 ms FITS samples, baseline spread (max−min) is 0.003 s and fixed
spread is 0.002 s. Small differences between policies issuing identical requests
are measurement noise, not evidence of algorithmic improvement.

**Traffic matters.** On the random control, fixed read-ahead transfers
2,097,152 bytes for 131,072 useful bytes (16×), with 1,966,080 bytes never used.
At 20 ms RTT / 1 MiB/s the modeled latency rises from 0.765 s to 2.640 s.
For random ZIP members, fixed improves measured high-bandwidth latency but
regresses the same low-bandwidth model from 1.047 s to 1.387 s.

**Budget matters.** Random SQLite fixed read-ahead makes 30, 29 and 23 requests
at 64 KiB, 256 KiB and 1 MiB budgets; plain caching makes 26 at all three.
An unlimited cache would conceal the small-budget pollution regression.
At 256 KiB, fixed's measured payload peak is exactly 262,144 bytes and its local
Python allocation peak is 344,609 bytes, including transient buffers/logs.
Plain caching uses 102,500 retained bytes and peaks at 125,647 Python bytes.

The full-reader 100 ms check agrees: FITS takes 1.820 s baseline / 0.308 s fixed /
0.509 s adaptive; random SQLite takes 2.624 s cache / 2.968 s fixed. These include
parsing/consumer work but are single samples, not the repeated replay statistics.

**Existing implementations can beat the prototype without prediction.** On the
same clustered ZIP trace at 100 ms RTT, fsspec's ordinary block LRU takes
**1.034 s**, versus 2.034 s for the custom adaptive interval cache. It fetches
603,706 bytes versus 989,951, with only 192 KiB of resident allowance versus
256 KiB. This is a separate transport run (new connection per fsspec fetch), not
an equal-implementation ablation, but strongly motivates improving cache geometry
before adding prediction.

**Asynchronous overlap is real, but conditional.** With 20 ms of compute per read,
fsspec background prefetch reduces clustered ZIP foreground time from 1.581 s to
**1.116 s** (1.199 s including background drain); it transfers 669,242 instead of
603,706 bytes. FITS foreground time falls from 0.674 s to 0.468 s (0.551 s with
drain). With no compute gap, clustered ZIP is essentially unchanged. Random
reads instead rise from 3.324 s to 3.635 s including drain, and traffic rises from
2 MiB to 3 MiB. Scheduling changes some speculative request counts across repeats;
raw per-repeat records include both foreground and drain-inclusive times.

**Coalescing when the batch is known** reduces the explicit overlapping-range
control from 32 to 8 requests, 393,216 to 294,912 bytes, and 3.233 to 0.813 s at
100 ms RTT. This single-sample test is deliberately separated from serial
workloads: its caller provides four ranges at once, so no future knowledge is
smuggled into the online comparison.

### Answers to the research questions

1. **Predictable enough?** Yes for sequential locality, metadata reuse and the
   stride control; no useful general next-offset prediction emerged for random
   queries. Different libraries expose very different request shapes.
2. **Latency or traffic?** Enlarging a request can save round trips. Issuing a
   separate synchronous speculative request mostly moves the wait and can add
   useless traffic. Cache-hit rate alone is a particularly bad success metric.
3. **Who benefits or slows down?** FITS rows, SQLite sequential queries and ZIP
   metadata benefit. Random SQLite suffers cache pollution; random controls and
   ZIP regress when bandwidth is scarce. Adaptive gating limits this damage.
4. **Across formats?** The same content-blind wrapper works for all four formats,
   but a single winning policy does not generalize across their workloads.
5. **Competitive with format-aware readers?** It helps weaker small-read paths,
   but cannot improve the measured Arrow traces; Arrow coalesces known column
   ranges more effectively. DuckDB is not benchmarked, so no speed claim applies
   to it. Equal total memory with Arrow's internal buffers is not established.
6. **Simplest effective implementation?** Bounded caching first; add a small fixed
   read-ahead window for sequential streams. Add a two-transition gate if random
   access or bandwidth cost matters. Do not build a general prediction service
   on this evidence.


## Reproduce

Python 3.12 on Linux was used. Run from this directory; all generated files,
Python packages and temporary files stay inside it:

```bash
mkdir -p tmp
export TMPDIR="$PWD/tmp" PIP_CACHE_DIR="$PWD/.cache"
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest -q
.venv/bin/python benchmark.py --http --repeats 3
.venv/bin/python supplemental.py
.venv/bin/python validate_live.py
.venv/bin/python analyze.py
.venv/bin/python verify_results.py
# Optional refresh of research sources (network access required):
.venv/bin/python research.py
```

The benchmark creates fixtures on its first run. To regenerate fixtures after
changing generator code or dependencies, remove only this folder's `data/`
directory first. Results are overwritten by their corresponding script. Plain
`benchmark.py` omits the latency sweep but still requires loopback sockets for
live integration checks. Expect several minutes for the HTTP sweep and several
more for the sequential fsspec supplemental runs. No external datasets, cloud
credentials or paid services are required.

## Limits and next experiment

The experiment covers one small fixture family per format and short, deterministic
workloads. It does not establish behavior on production object stores, very
large catalogs, contention, packet loss, TLS, connection multiplexing, changing
objects, multi-reader interference or write traffic. There is no public WAN
measurement. The real HTTP server is local with controlled injected delay.

The interval cache requires whole-range containment and does not assemble partial
hits. A block cache can avoid duplicated overlapping reads, but may split large
requests into extra transactions. The fsspec comparison helps expose that tradeoff;
it does not exhaust cache design choices. Native Arrow caches/pre-buffering are
not forced into the wrapper's budget, so the format-aware result is not a claim
of equal total memory consumption. No DuckDB or ASDF runtime benchmark is claimed.

**Most interesting follow-up:** compare a bounded asynchronous, demand-priority
prefetch queue against fsspec background blocks and a simple aligned-block cache
on real object storage. Sweep compute gaps and a shared bandwidth cap, charge
in-flight buffers to the same budget, and include abrupt pattern changes. The
key question is whether overlap survives bandwidth contention and cache pollution,
not whether next-offset prediction is accurate.
