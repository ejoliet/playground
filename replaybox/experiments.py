"""Integration, adversarial tests and end-to-end benchmarks; no pip dependencies."""
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parent
REPEATS = int(os.environ.get('REPEATS', '20'))

class Handler(BaseHTTPRequestHandler):
    hits = 0
    def do_GET(self):
        type(self).hits += 1
        body = f'live-{time.time_ns()}'.encode()
        self.send_response(200)
        self.send_header('X-Test', 'recorded')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *args):
        pass


def main():
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    env = dict(os.environ, URL=f'http://127.0.0.1:{server.server_port}/',
               PYTHONDONTWRITEBYTECODE='1', PYTHONHASHSEED='1', VALUE='before')
    results = {'python': sys.version, 'platform': platform.platform(), 'repeats': REPEATS,
               'cases': {}, 'benchmarks': {}}
    with tempfile.TemporaryDirectory(prefix='run-', dir=ROOT) as tmp:
        work = Path(tmp)
        def reset():
            (work/'input.txt').write_text('alpha\nbeta\n')
            (work/'listing').mkdir(exist_ok=True)
            (work/'listing'/'entry').write_text('x')
        def run(mode, name, overrides=None, tape=None):
            start = time.perf_counter()
            command = ([sys.executable, str(ROOT/'examples'/f'{name}.py')] if mode == 'direct' else
                       [sys.executable, str(ROOT/'replaybox.py'), mode,
                        str(work/(tape or name+'.json')), str(ROOT/'examples'/f'{name}.py')])
            p = subprocess.run(command,
                               cwd=work, env=env | (overrides or {}), capture_output=True, timeout=10)
            return p, (time.perf_counter()-start)*1000
        reset()
        baseline_outputs = [run('direct', 'mixed')[0].stdout for _ in range(REPEATS)]
        record_outputs = [run('record', 'mixed')[0].stdout for _ in range(REPEATS)]
        results['fresh_runs'] = {'direct_unique': len(set(baseline_outputs)),
                                 'record_unique': len(set(record_outputs)), 'runs': REPEATS}
        before_hash = hashlib.sha256((ROOT/'examples/mixed.py').read_bytes()).hexdigest()
        recorded, _ = run('record', 'mixed')
        assert recorded.returncode == 0, recorded.stderr.decode()
        (work/'input.txt').unlink()
        (work/'output.txt').unlink()
        (work/'listing'/'entry').unlink()
        (work/'listing').rmdir()
        hits = Handler.hits
        matches = 0
        for _ in range(REPEATS):
            p, _ = run('replay', 'mixed')
            assert p.returncode == 0, p.stderr.decode()
            matches += p.stdout == recorded.stdout
            assert not (work/'output.txt').exists()
        assert Handler.hits == hits
        assert hashlib.sha256((ROOT/'examples/mixed.py').read_bytes()).hexdigest() == before_hash
        results['cases']['mixed_files_removed_server_live'] = {'identical': matches, 'runs': REPEATS,
                                                              'additional_http_hits': Handler.hits-hits}
        reset()
        fs_rec, _ = run('record', 'fs_mutations')
        assert fs_rec.returncode == 0, fs_rec.stderr.decode()
        (work/'created').rmdir()
        fs_rep, _ = run('replay', 'fs_mutations')
        assert fs_rep.returncode == 0 and fs_rep.stdout == fs_rec.stdout, fs_rep.stderr.decode()
        assert not (work/'created').exists()
        results['filesystem_mutations_replay'] = True
        # Adversarial tests: compare successful outputs separately from rejection.
        cases = ['datetime_escape', 'random_instance', 'native_entropy', 'raw_file', 'stat_escape',
                 'environment', 'hash_seed', 'subprocess_escape', 'mutation', 'branch',
                 'short_trace', 'thread_order', 'socket_escape', 'native_socket', 'write_argument',
                 'file_descriptor', 'http_request']
        for name in cases:
            reset()
            rec, _ = run('record', name)
            row = {'record_exit': rec.returncode, 'identical': 0, 'rejected': 0, 'different': 0,
                   'runs': REPEATS if rec.returncode == 0 else 0}
            if rec.returncode == 0:
                (work/'input.txt').write_text('changed and longer\n')
                for _ in range(REPEATS):
                    p, _ = run('replay', name, {'VALUE':'after', 'PYTHONHASHSEED':'2'})
                    row['rejected' if p.returncode else 'identical' if p.stdout == rec.stdout else 'different'] += 1
                row['last_stderr'] = p.stderr.decode()[-1200:]
                row['record_stdout'] = rec.stdout.decode()
                row['last_stdout'] = p.stdout.decode()
            else:
                row['record_stderr'] = rec.stderr.decode()[-1200:]
            results['cases'][name] = row
            if name in ('file_descriptor', 'http_request'):
                assert row['record_exit'] != 0
            elif name in ('branch', 'short_trace', 'thread_order', 'socket_escape', 'write_argument'):
                assert row['rejected'] == REPEATS, (name, row)
            else:
                assert row['different'] == REPEATS, (name, row)
        # Plain, record, replay rotate per repetition; warm once, then keep raw times.
        for workload in ['empty', 'calls', 'files', 'http', 'sleep']:
            reset()
            target = 'empty' if workload == 'empty' else 'bench'
            extra = {'WORKLOAD': workload}
            for mode in ['direct', 'plain', 'record', 'replay']:
                p, _ = run(mode, target, extra)
                assert p.returncode == 0, p.stderr.decode()
            samples = {mode: [] for mode in ['direct', 'plain', 'record', 'replay']}
            for i in range(REPEATS):
                # Record must precede replay; rotate baseline placement to reduce drift.
                modes = ['direct','plain','record','replay'] if i % 2 else ['record','replay','plain','direct']
                for mode in modes:
                    p, elapsed = run(mode, target, extra)
                    assert p.returncode == 0, p.stderr.decode()
                    samples[mode].append(elapsed)
            medians = {k: statistics.median(v) for k,v in samples.items()}
            results['benchmarks'][workload] = {'milliseconds': samples, 'median_ms': medians,
                'ratio_to_plain': {k:v/medians['plain'] for k,v in medians.items()},
                'ratio_to_direct': {k:v/medians['direct'] for k,v in medians.items()},
                'tape_bytes': (work/(target+'.json')).stat().st_size}
        server.shutdown()
        server.server_close()
        p, _ = run('replay', 'mixed')
        assert p.returncode == 0 and p.stdout == recorded.stdout, p.stderr.decode()
        results['server_stopped_replay'] = True
    destination = ROOT/'results'/'results.json'
    destination.write_text(json.dumps(results, indent=2)+'\n')
    print(json.dumps({k:v for k,v in results.items() if k != 'benchmarks'}, indent=2))
    for name, row in results['benchmarks'].items():
        print(name, row['median_ms'], row['ratio_to_plain'], row['tape_bytes'])

if __name__ == '__main__':
    main()
