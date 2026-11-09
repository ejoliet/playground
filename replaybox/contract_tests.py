"""Small deterministic regression tests for tape validation and serialization."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent

class Contracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.script = self.work/'program.py'
        self.tape = self.work/'tape.json'

    def run_program(self, mode, *args, value='before'):
        return subprocess.run([sys.executable, str(ROOT/'replaybox.py'), mode,
                               str(self.tape), str(self.script), *args], cwd=self.work,
                              env=dict(os.environ, VALUE=value, PYTHONDONTWRITEBYTECODE='1'),
                              capture_output=True, timeout=10)

    def test_source_argv_version_guards(self):
        self.script.write_text('print("ok")\n')
        self.assertEqual(self.run_program('record').returncode, 0)
        self.assertEqual(self.run_program('replay').returncode, 0)
        self.assertNotEqual(self.run_program('replay', 'extra').returncode, 0)
        self.script.write_text('print("changed")\n')
        self.assertNotEqual(self.run_program('replay').returncode, 0)
        self.script.write_text('print("ok")\n')
        data = json.loads(self.tape.read_text())
        data['metadata']['python'] = 'other version'
        self.tape.write_text(json.dumps(data))
        self.assertNotEqual(self.run_program('replay').returncode, 0)

    def test_extra_call_rejected(self):
        self.script.write_bytes((ROOT/'examples/extra_call.py').read_bytes())
        self.assertEqual(self.run_program('record').returncode, 0)
        result = self.run_program('replay', value='after')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b'extra call', result.stderr)

    def test_imported_code_is_not_pinned(self):
        self.script.write_bytes((ROOT/'examples/imported_code.py').read_bytes())
        dependency = self.work/'dependency.py'
        dependency.write_text('VALUE = "before"\n')
        recorded = self.run_program('record')
        dependency.write_text('VALUE = "after"\n')
        replayed = self.run_program('replay')
        self.assertEqual(recorded.returncode, 0)
        self.assertEqual(replayed.returncode, 0)
        self.assertNotEqual(recorded.stdout, replayed.stdout)

    def test_unwrapped_random_state(self):
        self.script.write_bytes((ROOT/'examples/random_state.py').read_bytes())
        recorded = self.run_program('record')
        replayed = self.run_program('replay')
        self.assertEqual(recorded.returncode, 0)
        self.assertEqual(replayed.returncode, 0)
        self.assertNotEqual(recorded.stdout, replayed.stdout)

    def test_early_exit_does_not_save_tape(self):
        self.script.write_bytes((ROOT/'examples/early_exit.py').read_bytes())
        self.assertEqual(self.run_program('record').returncode, 0)
        self.assertFalse(self.tape.exists())

    def test_exception_replay_and_binary(self):
        self.script.write_text('''import time
try:
    time.sleep(-1)
except ValueError as e:
    print(type(e).__name__, str(e))
with open('bytes', 'wb') as f:
    f.write(b'\\x00\\xff')
with open('bytes', 'rb') as f:
    print(f.read())
''')
        recorded = self.run_program('record')
        (self.work/'bytes').unlink()
        replayed = self.run_program('replay')
        self.assertEqual(recorded.returncode, 0)
        self.assertEqual(replayed.returncode, 0, replayed.stderr)
        self.assertEqual(recorded.stdout, replayed.stdout)
        self.assertFalse((self.work/'bytes').exists())

if __name__ == '__main__':
    unittest.main()
