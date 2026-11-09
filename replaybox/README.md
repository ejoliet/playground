# replaybox

A small, deliberately incomplete record/replay experiment for **unmodified Python scripts**.
The launcher records selected Python API calls to a JSON tape, then executes the same script
again with recorded return values. Linux seccomp blocks socket operations during replay.

**Result:** one program using clocks, random values, HTTP, text files, missing-file errors,
and directory listings replayed with identical stdout **20/20 times**, with its input files
removed. No HTTP requests reached the still-running server. Replay also succeeded after
stopping the server. This is a bounded demonstration, **not general Python record/replay**:
nine adversarial programs silently produced different results in all 20 replays each.
A zero exit status does not establish determinism.

## Run it

Requires Linux, Python 3.12 (tested on 3.12.14), and `libseccomp.so.2`
(Debian/Ubuntu package `libseccomp2`). No pip packages are needed for the prototype.
The filter is mandatory during replay: missing library or failed installation aborts replay.

From this folder:

```bash
PYTHONDONTWRITEBYTECODE=1 python contract_tests.py
PYTHONDONTWRITEBYTECODE=1 python experiments.py
```

`experiments.py` starts a real loopback HTTP server, launches fresh Python processes,
records the mixed example, deletes its input/output files, replays 20 times, checks that
no extra requests arrived, tests filesystem mutations and deliberate failures, benchmarks,
stops the server, and replays once more. It asserts the expected outcomes, including known
failures. All temporary files stay under this folder and are cleaned up. It overwrites
`results/results.json`. Allow about two minutes on a shared machine. Recording requires
permission to open loopback sockets; replay does not. `REPEATS=3` is a faster smoke run.

A manual example without a server:

```bash
mkdir -p demo
cd demo
printf 'hello\n' > input.txt
python ../replaybox.py record tape.json ../examples/basic.py > recorded.txt
rm input.txt output.txt
python ../replaybox.py replay tape.json ../examples/basic.py > replayed.txt
cmp recorded.txt replayed.txt
test ! -e output.txt
cd ..
```

The target imports ordinary Python modules and knows nothing about replaybox. No decorators,
imports, or source rewrites are added to it. `examples/mixed.py` is the complete HTTP example;
`experiments.py` supplies its `URL` environment variable and fixture files. Source hashes
before and after its runs are checked. The interpreter, launcher, target source and imported
modules must remain installed; the tape is not a deployment bundle.

## What is actually replayed?

| Boundary | Supported behavior | Important boundary of the claim |
|---|---|---|
| `time` | `time`, `time_ns`, `monotonic`, `monotonic_ns`, `perf_counter`, `perf_counter_ns`, `sleep` | Recorded return values; sleep does not wait. No `datetime.now`, process CPU clocks, or native clocks. |
| `random` | Module-level `random`, `randint`, `randrange`, `getrandbits`, `uniform`, `choice`, `randbytes` | Primitive serializable arguments/results only. No instance generators, shuffle, or restoration of PRNG internal state. |
| OS entropy | `os.urandom` | No direct libc/syscall entropy, C extensions, or interpreter hash seeding. |
| HTTP | `urllib.request.urlopen(URL_string, data=bytes_or_None, timeout=...)` | Eager full body, final URL, status, headers. No Request objects, custom openers, requests/aiohttp, streaming semantics, or custom exception reconstruction. |
| File streams | `builtins.open`, `io.open` (including Path.open), read/readline/readlines, write/writelines, seek/tell, truncate/flush/close, iteration and context managers | Operations are a transcript, not a coherent virtual filesystem. No descriptor, buffer, metadata attributes, mmap, raw os.open/read, or native I/O. |
| Directory operations | `os.listdir`, `mkdir`, `remove`, `unlink`, `rename` | No stat, scandir, exists, rmdir, directory handles, or general filesystem isolation. |
| Errors | Built-in exceptions at wrapped boundaries, including missing-file filename/errno | Arbitrary exception classes and all their attributes are not preserved. |

Supported writes/mutations run against the real filesystem during recording. During replay,
only their arguments and recorded return values are checked; they have **no real side effects**.
A later supported read returns its recorded data. An unwrapped `stat` or native read still
sees the live disk. The `fs_mutations.py` test exercises binary update, seek, truncate, flush,
rename, listing and unlink; replay creates no output directory.

The tape is a single ordered sequence of `(API, args, kwargs) -> value/error` events.
Replay rejects extra calls, changed arguments, changed order, and leftover events on normal
return. It also checks the top-level script SHA-256, exact Python version string and argv.
It does not hash imported modules or capture environment variables, cwd, locale, stdin,
process IDs, interpreter startup, signals or scheduling. Wrapper imports occur before target
execution, so startup semantics differ from direct Python. It is a script launcher, not a
transparent replacement for every Python invocation (`-m`, interactive, embedded Python).

## Measured reproducibility and deliberate breakage

Runs below use a **single tape per program** and 20 fresh replay processes. The mixed target
had 20 distinct stdout values in 20 direct runs and also 20 distinct values in 20 fresh
recordings. Its 20 replays all matched the selected recording byte-for-byte. Equality means
stdout bytes plus successful exit; stderr is retained for failures, and specified side
effects are checked separately. It does not mean identical process state.

Every row links to a minimal program. `experiments.py` executes the first table, changing
`VALUE=before` to `after`, `PYTHONHASHSEED=1` to `2`, and input file content between phases.
It compares each result with its own recording; it never counts two matching failures as success.

| Minimal program | Identical / 20 | Observed result and cause |
|---|---:|---|
| [mixed.py](examples/mixed.py) | 20 | Clock, RNG, entropy, HTTP and supported filesystem transcript replayed. |
| [datetime_escape.py](examples/datetime_escape.py) | 0 | Silent divergence: datetime reads an unwrapped clock. |
| [random_instance.py](examples/random_instance.py) | 0 | Silent divergence: a new Random instance is not patched. |
| [native_entropy.py](examples/native_entropy.py) | 0 | Silent divergence: libc getrandom bypasses Python. |
| [raw_file.py](examples/raw_file.py) | 0 | Silent divergence: os.open/read observes the changed file. |
| [stat_escape.py](examples/stat_escape.py) | 0 | Silent divergence: stat observes live file size. |
| [environment.py](examples/environment.py) | 0 | Silent divergence: environment is not captured. |
| [hash_seed.py](examples/hash_seed.py) | 0 | Silent divergence: hash seed is chosen before hooks install. |
| [subprocess_escape.py](examples/subprocess_escape.py) | 0 | Silent divergence: child interpreter runs uninstrumented. |
| [mutation.py](examples/mutation.py) | 0 | Silent divergence: shuffle uses unpatched state and mutates its argument. |
| [branch.py](examples/branch.py) | 0 | All rejected: an environment-dependent branch changes the API. |
| [short_trace.py](examples/short_trace.py) | 0 | All rejected: recorded events remain unconsumed. |
| [write_argument.py](examples/write_argument.py) | 0 | All rejected: the write payload changed. |
| [thread_order.py](examples/thread_order.py) | 0 | All rejected: forced opposite thread order changes sleep arguments. |
| [socket_escape.py](examples/socket_escape.py) | 0 | All rejected: raw socket access gets EPERM, not a replayed response. |
| [native_socket.py](examples/native_socket.py) | 0 | Control: prints `allowed` during recording, `blocked` during replay. |
| [file_descriptor.py](examples/file_descriptor.py) | — | Recording fails: proxy has no fileno. Direct Python succeeds. |
| [http_request.py](examples/http_request.py) | — | Recording fails: Request object deliberately unsupported. |

Six deterministic checks in `contract_tests.py` additionally demonstrate:

* Changed top-level source, argv or interpreter metadata is rejected before target execution.
* [extra_call.py](examples/extra_call.py): adding an interaction exhausts the tape and is rejected.
* [imported_code.py](examples/imported_code.py): changing `dependency.py` from `VALUE="before"`
  to `VALUE="after"` silently changes output despite the top-level source hash matching.
* [random_state.py](examples/random_state.py): a wrapped RNG return value replays, but unwrapped
  `getstate()` exposes different state (`2` versus `624`).
* [early_exit.py](examples/early_exit.py): even `sys.exit(0)` bypasses tape saving and completion
  validation. Only normal script return is supported; an old tape is not removed on failure.
* A caught ValueError and binary file reads/writes replay identically after the file is deleted.

For a standalone failure, use the same record/replay commands as the manual example, replacing
`basic.py` with `datetime_escape.py`; `cmp` will fail although both launches exit successfully.
For deterministic changed-environment failure:

```bash
cd demo
VALUE=before python ../replaybox.py record branch.json ../examples/branch.py
VALUE=after python ../replaybox.py replay branch.json ../examples/branch.py
# Divergence: expected time.time, got time.time_ns
cd ..
```

## Benchmark results

Measured on Linux 6.18.57 x86_64/glibc 2.41, Python 3.12.14, in a shared execution environment.
20 measurements per mode/workload after one warmup, one fresh interpreter per measurement.
Parent-process `perf_counter` measures wall time; the target's patched clock cannot bias it.
Each iteration records before replaying and alternates baseline placement. Timings include
startup, imports, tape JSON I/O and replay filter installation. The HTTP server is loopback,
not a WAN service. No speedup or overhead estimate should be generalized to other workloads.

`direct` runs `python target.py`. `plain` uses this launcher's pre-imports and exec path with
hooks disabled. The latter helps separate launcher overhead from interception overhead.
Raw samples, metadata and tape sizes are in [results/results.json](results/results.json).

| Workload | Direct ms | Plain ms | Record ms | Replay ms | Record/direct | Replay/direct | Tape bytes |
|---|---:|---:|---:|---:|---:|---:|---:|
| Print only | 12.70 | 54.65 | 51.77 | 58.70 | 4.08× | 4.62× | 239 |
| 10,000 clock + 10,000 RNG calls | 46.26 | 55.39 | 201.10 | 110.94 | 4.35× | 2.40× | 1,542,911 |
| 100 open/read/close, 11-byte file | 47.77 | 71.13 | 64.54 | 59.96 | 1.35× | 1.26× | 22,121 |
| 10 small HTTP GETs | 73.12 | 103.95 | 99.11 | 63.62 | 1.36× | 0.87× | 3,857 |
| One 50 ms sleep | 94.45 | 101.91 | 103.49 | 55.23 | 1.10× | 0.58× | 301 |

The 20,000-call workload has substantial serialization overhead. Replay can be faster for
HTTP and sleep because it omits actual waiting. It does **not** preserve elapsed wall time.
Some recording medians are below `plain` for the small I/O workloads: shared-host noise and
startup dominate these short samples, not evidence that interception accelerates file I/O.
Tapes and HTTP responses are buffered in memory, then dumped as JSON; memory usage and large
stream throughput were not benchmarked. No CPU-only, memory, cross-host or long-running
service performance claim is made.

## Offline, reproducible, and isolated are different claims

Replay installs libseccomp rules denying socket creation, connect/bind/listen/accept,
socket send/receive APIs, legacy socketcall where available, and io_uring setup. The filter
is inherited by child processes. A live-server hit counter and direct libc socket probe
verify the filter independently of HTTP interception. This does not simulate networking
for unsupported clients: they fail.

This is **not a hostile-code sandbox**. Launch it with ordinary terminal/pipe stdio and no
inherited connected sockets or io_uring rings. Existing descriptors can have read/write
paths outside these rules; local IPC proxies are outside the threat model. Native and
unwrapped filesystem writes and child-process side effects remain possible. There is no
claim of general process isolation or determinism just because sockets are blocked.

Tapes contain file contents, HTTP payloads/headers and random bytes in plaintext/base64.
Do not publish recordings of secrets. JSON avoids pickle execution, but tapes are trusted
experimental inputs, not authenticated or resource-limited artifacts.

## What would make the claim broader?

At the Python layer, every new dependency surface needs another adapter and tests. Threads
need schedule recording, mutable state needs state transitions, and native code escapes
monkey patches. The global nested-call suppression flag is also not thread-safe. Extending
this prototype indefinitely would not establish completeness.

A lower execution boundary can cover far more: **rr** records Linux process/thread execution,
including syscall results and scheduling, without target-source edits. Its hardware/kernel
requirements and unsupported resources still matter. ReproZip packages dependencies; that
alone does not record future clock, entropy or network observations. VCR.py, Freezegun and
pyfakefs are useful narrower tools; they do not collectively prove arbitrary Python replay.
See [notes.md](notes.md) for sources, real-tool probes, rejected approaches and failed experiments.
