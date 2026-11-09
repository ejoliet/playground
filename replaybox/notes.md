# Investigation notes

Investigation and experiments: 2026-11-09. These notes distinguish documentation review,
executed probes and hypotheses. Only files under `replaybox/` were created for this work.
The repository was accessed through GitHub; there was no existing local checkout. The new
branch starts at `b569f4a53e2acc675d170fa7666380f0078abe73` on `ejoliet/playground`.

## Tools and approaches investigated

Upstream READMEs were fetched and read on the investigation date. They are mutable upstream
links, not version-pinned specifications. Installed versions for executed probes are pinned
in `requirements-probes.txt`; results are in `results/tool_probes.json`.

| Tool / approach | What it captures or substitutes | Assessment and evidence |
|---|---|---|
| [rr](https://github.com/rr-debugger/rr), [technical report](https://arxiv.org/abs/1705.05937) | Linux application process/thread execution; replay debugging at a lower boundary than Python | The strongest existing answer to the broad premise. README explicitly describes process trees and threads, Linux requirements, supported CPU families and virtualized hardware performance counters. Documentation review only here; `rr` was absent. No rr overhead numbers or claim that this host cannot run it. |
| [VCR.py](https://github.com/kevin1024/vcrpy), [docs](https://vcrpy.readthedocs.io/) | HTTP exchanges through supported clients, stored as cassettes | Executed 9.4.2: record with `once`, stop server, replay with `none`; bodies matched. Time kept advancing inside the replay context. A wrapper around exec/runpy can avoid editing target source. Does not capture arbitrary clocks, filesystem or native calls. |
| [Freezegun](https://github.com/spulec/freezegun) | Substitutes Python date/time APIs | Executed 1.5.5: datetime became 2020-01-01; libc `time()` still returned real time. Freezing is a configured substitute, not a recorded ordered history. More complete Python datetime handling than this prototype. |
| [pyfakefs](https://github.com/pytest-dev/pyfakefs) | Fake Python filesystem APIs | Executed 6.3.2: Python could not see a real fixture file while libc open could. Upstream explicitly documents C-library limitations. Provides much better virtual filesystem coherence than our transcript, but population/recording and native accesses are separate problems. |
| [ReproZip](https://github.com/VIDA-NYU/reprozip) | Tracks system calls to package binaries, files and dependencies for rerunning an experiment | README reviewed, not installed. Environment capture is complementary to event replay; packaging inputs does not by itself supply the same future HTTP responses or entropy. |
| Python API monkey patches | Selected calls and return values | Implemented here. Small, inspectable, easy no-source-edit launcher. Coverage bounded by patched API identities, data types and Python execution. |
| LD_PRELOAD / libc interposition | Selected C library calls | Design review only, no implementation or measured performance. Broader than Python hooks, but direct syscalls, static binaries and some vDSO access paths can bypass selected symbols; scheduling remains separate. |
| Syscall tracing / ptrace | Kernel-boundary inputs and outputs | Design review only. Merely logging syscalls is not replay: need return injection, memory buffers, descriptor identity, scheduling and non-syscall nondeterminism. Reimplementing rr is not a small prototype. |
| VM snapshots / full-system replay | Potentially the entire guest boundary | Design review only. Snapshotting state is not sufficient without recording nondeterministic inputs after the snapshot. Larger storage/runtime boundary; no VM experiment attempted. |

The premise needs qualification: serious general record/replay systems already exist. This
prototype is not evidence that full-process replay is impossible. It shows why a small Python
interception layer cannot make the same claim, and how surprisingly easy false confidence is.

Optional probes are reproducible without changing the prototype's dependency set:

```bash
python -m venv .venv
.venv/bin/pip install -r requirements-probes.txt
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python tool_probes.py
```

The VCR probe checks server-offline replay; it does not install our seccomp filter. The core
prototype's integration suite is the one that proves socket-denied replay. We did not benchmark
VCR/Freezegun/pyfakefs or test a composition of all three; no comparative speed claim is made.

## Smallest useful boundary chosen

Use one launcher and a small JSON event log instead of a fake OS. Compile target source before
patching and execute it under `__main__`. Top-level code is unchanged. The runtime and modules
still have to exist, which is why this is not a portable self-contained capsule.

Keep the event model deliberately strict: positional and keyword arguments must match exactly,
not merely be semantically equivalent. Thus `read()` and `read(-1)` have different signatures.
Associate stream calls with a monotonically assigned open number. Binary values use base64,
tuples have explicit tags, and JSON handles the other supported primitive values. No pickle.
Return values are the contract; stdout is not merely cached and printed back by the launcher.

Wrap at a sufficiently high level to avoid recording urllib internals. During an outer call,
nested hooks call through. Otherwise recording a URL request would include internal clock and
filesystem calls that the synthetic response never executes during replay, leaving an
impossible event stream. This suppression flag is deliberately simple and global: concurrency
can bypass capture. The thread example tests order divergence, not correctness for arbitrary
multithreaded execution.

For HTTP, consume the entire body and construct `addinfourl(BytesIO(...))` with headers/status/
final URL. This establishes offline replay for the basic API while explicitly losing streaming,
connection identity, precise error behavior, and timing. Custom errors such as HTTPError are
not reconstructed. Request objects reject at the boundary rather than guessing a request key.

For files, record every supported stream method rather than snapshotting an initial file or
returning an in-memory file with guessed mode semantics. This handles partial reads, seeking,
binary updates, missing-file errors and exact write payloads. It does not model filesystem
state for unwrapped observers. Unsupported attributes fail visibly. Recorded errors retain
built-in exception class/args and OSError filename, not arbitrary custom attributes.

The source hash and exact interpreter/argv checks catch some obvious wrong-tape uses. Imported
code, environment and runtime configuration are not pinned. `imported_code.py` proves that
source-hash validation alone is insufficient. Tapes are not signed and are not intended as
adversarial input. The full log and HTTP body sit in memory; scalability was not established.

The replay filter uses libseccomp's syscall-name resolution instead of architecture-specific
syscall numbers. Rules deny sockets, socket I/O and io_uring setup; filter failure aborts.
It does not deny general file I/O or process creation. Ordinary terminal/pipe stdio and no
inherited networking descriptors are assumptions. This is an offline experiment runner for
cooperative programs, not a security container. A child may still write real files.

## Experiments that did not work, or could mislead

1. **Default execution environment denied sockets before our code ran.** The first integration
   attempt failed constructing the loopback server with EPERM. Such a run cannot validate our
   own offline filter. The successful runs enabled networking for the parent/server and normal
   recording processes; only replay processes installed our filter. The native socket control
   then changed from `allowed` to `blocked`, independently of Python socket hooks.
2. **Network namespace isolation was unavailable.** `unshare -Urn true` failed with
   `cannot open /proc/self/uid_map: Read-only file system`. Used seccomp instead; did not claim
   namespace isolation. `perf_event_paranoid` was 2 and rr was absent. These observations are
   not a definitive rr compatibility test; rr was not installed or executed.
3. **First thread breaker hung.** A replay divergence in the main thread occurred before waking
   the worker. The process timed out after 10 seconds. The final minimal program uses a finally
   block to release/join and bounded waits, forcing a repeatable ordering failure without a
   permanently stranded thread. The suite still uses process timeouts as a backstop.
4. **Subprocess pipe interception looked deceptively successful.** An initial example using
   `subprocess.check_output` replayed identical output in 3/3 smoke runs: its pipe reads went
   through patched io.open. The child still launched! Changed the checked-in minimal example
   to `subprocess.run` with inherited stdout. It now visibly diverges 20/20, making the missing
   process boundary explicit. We do not promise that check_output is correctly supported.
5. **Returning RNG values is not replaying RNG state.** Simple module calls worked, but newly
   created generators and shuffle diverged. An additional deterministic probe calls seed,
   random, then getstate: recording advances the internal index; replaying the return value
   does not. This is a stateful object problem, not simply another entropy source to patch.
6. **Python wrappers do not cover native observations.** Native entropy, raw file reads, stat,
   datetime, process output, environment and hash seed silently changed. The kernel filter
   makes native socket creation fail, but does not make those other observations replayable.
7. **Successful process exit is insufficient.** `sys.exit(0)` escapes the normal-return save
   and exhaustion-check paths. The contract test demonstrates a zero exit with no new tape.
   Uncaught failures similarly do not create a completed recording; existing tapes remain.
   This prototype does not model process termination as an event.
8. **A single timing number hides startup cost.** A smoke benchmark using only the `plain`
   launcher understated total user-facing overhead. Added direct Python as a separate baseline,
   an empty program, warmups and raw samples. Shared-host noise remains visible: record can
   appear faster than plain for tiny I/O workloads. No attempt was made to tune away the noise
   or report only favorable runs.

## Measurement record and interpretation

`results/results.json` is the completed 20-repeat run, not the earlier 3-repeat smoke run.
It contains every benchmark timing, median ratios, cassette size, platform/version, output
examples and failure stderr. Stdout contains synthetic data only. Absolute temporary paths
in stderr describe the original run and are not files needed for reproduction.

The supported mixed case has 20/20 identical successful replays, 0 additional HTTP hits while
the server is live, no recreated output file, and an additional successful replay with the
server stopped. Filesystem mutations get a separate successful check. Baseline and fresh
recording outputs are each 20/20 unique. Nine unsupported dependency probes have 0/20 matching
outputs and exit successfully; five strict/offline failures reject every replay. The native
socket control intentionally differs in every replay. Two unsupported API shapes fail while
recording. Those categories must not be collapsed into a single advertised success rate:
this is an adversarially selected suite, not a sample of real-world Python applications.

Benchmarks use 20,000 clock/RNG calls, 100 reads of an 11-byte file, 10 small loopback HTTP GETs,
one 50 ms sleep, and a print-only control. They measure whole-process wall time, not just hook
cost. Record/replay ratios to both direct Python and the unpatched launcher are available.
Memory, high-volume network streaming, real remote latency, long-running services, GPUs,
other Python versions/OSes, and cross-machine tape portability were not tested.

Future work should choose a boundary before adding features: improve a limited test-double
library with explicit adapters, or evaluate rr on supported hardware for whole-process replay.
A growing list of monkey patches cannot establish that every external observation is captured.
