import contextlib
import copy
import io
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest

import pyarrow as pa
import pyarrow.parquet as pq
import parquet_git as driver

ROOT = Path(__file__).resolve().parent
SCHEMA = pa.schema([('id', pa.int64()), ('region', pa.string()), ('sales', pa.float64())])


class Drivers(unittest.TestCase):
    def setUp(self):
        work = ROOT / '.test-work'
        work.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=work)
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        self.base = [{'id': i, 'region': 'west', 'sales': float(i * 10)} for i in range(1, 101)]

    def write(self, name, rows, schema=SCHEMA):
        path = self.path / name
        pq.write_table(pa.Table.from_pylist(rows, schema=schema), path)
        return str(path)

    def run_merge(self, ours, theirs, oschema=SCHEMA, tschema=SCHEMA):
        b = self.write('base.parquet', self.base)
        o = self.write('ours.parquet', ours, oschema)
        t = self.write('theirs.parquet', theirs, tschema)
        driver.merge(b, o, t, 'id')
        return pq.read_table(o)

    def test_disjoint_rows_cells_add_delete_reorder(self):
        o, t = copy.deepcopy(self.base), copy.deepcopy(self.base)
        o[0]['sales'] = 99.
        t[0]['region'] = 'east'
        t[1]['sales'] = 88.
        o.pop(2)
        t.append({'id': 101, 'region': 'north', 'sales': 3.})
        result = self.run_merge(o[::-1], t).to_pylist()
        self.assertEqual(result[0], {'id': 1, 'region': 'east', 'sales': 99.})
        self.assertEqual(result[1]['sales'], 88.)
        self.assertNotIn(3, [r['id'] for r in result])
        self.assertEqual(result[-1]['id'], 101)

    def test_cell_conflict_is_atomic(self):
        o, t = copy.deepcopy(self.base), copy.deepcopy(self.base)
        o[0]['sales'], t[0]['sales'] = 99., 88.
        path = self.write('ours.parquet', o)
        before = Path(path).read_bytes()
        with self.assertRaisesRegex(driver.Conflict, '"column": "sales"'):
            self.run_merge(o, t)
        self.assertEqual(Path(path).read_bytes(), before)

    def test_identical_edits(self):
        o = copy.deepcopy(self.base)
        o[0]['sales'] = 99.
        self.assertEqual(self.run_merge(o, o).to_pylist(), o)

    def test_delete_modify_and_add_add(self):
        o, t = copy.deepcopy(self.base), copy.deepcopy(self.base)
        t[0]['sales'] = 99.
        with self.assertRaisesRegex(driver.Conflict, 'delete/modify'):
            self.run_merge(o[1:], t)
        with self.assertRaisesRegex(driver.Conflict, 'add/add'):
            self.run_merge(o + [{'id': 101, 'sales': 1.}], o + [{'id': 101, 'sales': 2.}])

    def test_nullable_column_addition_and_row_insert(self):
        o, t = copy.deepcopy(self.base), copy.deepcopy(self.base)
        for row in o:
            row['reviewed'] = True
        t[0]['sales'] = 99.
        t.append({'id': 101, 'region': 'east', 'sales': 1.})
        result = self.run_merge(o, t, SCHEMA.append(pa.field('reviewed', pa.bool_())))
        self.assertTrue(result.to_pylist()[0]['reviewed'])
        self.assertEqual(result.to_pylist()[0]['sales'], 99.)
        self.assertIsNone(result.to_pylist()[-1]['reviewed'])

    def test_backfill_versus_delete_conflicts(self):
        o = copy.deepcopy(self.base)
        for row in o:
            row['reviewed'] = False
        with self.assertRaisesRegex(driver.Conflict, 'delete/modify'):
            self.run_merge(o, self.base[1:], SCHEMA.append(pa.field('reviewed', pa.bool_())))

    def test_schema_drop_type_and_incompatible_additions(self):
        for schema in (pa.schema([('id', pa.int64()), ('region', pa.string())]),
                       pa.schema([('id', pa.int64()), ('region', pa.string()), ('sales', pa.int64())])):
            with self.assertRaisesRegex(driver.Conflict, 'unsupported schema change'):
                self.run_merge(self.base, self.base, schema)
        with self.assertRaisesRegex(driver.Conflict, 'incompatible added column'):
            self.run_merge(self.base, self.base, SCHEMA.append(pa.field('x', pa.int64())),
                           SCHEMA.append(pa.field('x', pa.string())))

    def test_invalid_keys_and_empty_table(self):
        for rows in ([{'id': None}], [{'id': 1}, {'id': 1}]):
            with self.assertRaisesRegex(driver.Conflict, 'null or duplicate key'):
                self.run_merge(rows, self.base)
        with self.assertRaisesRegex(driver.Conflict, 'missing key'):
            driver.read(self.write('nokey.parquet', [{}], pa.schema([('x', pa.int64())])), 'id')
        self.base = []
        self.assertEqual(self.run_merge([], []).num_rows, 0)

    def test_nan_and_null(self):
        self.base = [{'id': 1, 'region': None, 'sales': float('nan')}]
        result = self.run_merge(self.base, [{'id': 1, 'region': 'east', 'sales': float('nan')}])
        self.assertEqual(result.to_pylist()[0]['region'], 'east')

    def test_diff_rows_and_schema(self):
        o = self.write('old.parquet', self.base)
        rows = copy.deepcopy(self.base[1:])
        rows[0]['sales'] = 99.
        rows.append({'id': 101, 'sales': 1.})
        n = self.write('new.parquet', rows, SCHEMA.append(pa.field('reviewed', pa.bool_())))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            driver.diff(o, n, 'id', 'sales.parquet')
        for text in ('ADDED', 'REMOVED', 'CHANGED key=2', 'SCHEMA reviewed'):
            self.assertIn(text, out.getvalue())

    def git(self, *args, ok=True):
        result = subprocess.run(['git', '-C', str(self.path), *args], capture_output=True, text=True)
        if ok:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def setup_git(self):
        self.git('init', '-b', 'main')
        self.git('config', 'user.email', 'test@example.invalid')
        self.git('config', 'user.name', 'Parquet test')
        command = shlex.join([sys.executable, str(ROOT / 'parquet_git.py'), '--key', 'id'])
        self.git('config', 'merge.parquet.driver', command + ' merge %O %A %B')
        self.git('config', 'diff.parquet.command', command + ' diff')
        (self.path / '.gitattributes').write_text('*.parquet merge=parquet diff=parquet -text\n')
        self.write('sales.parquet', self.base)
        self.git('add', '.')
        self.git('commit', '-m', 'base')
        self.git('branch', 'theirs')

    def test_real_git_merge_and_diff_10000_rows(self):
        self.base = [{'id': i, 'region': 'west', 'sales': float(i)} for i in range(10000)]
        self.setup_git()
        o, t = copy.deepcopy(self.base), copy.deepcopy(self.base)
        for row in o:
            row['reviewed'] = False
        o[30]['reviewed'] = None  # Leave the deleted row unchanged.
        o[10]['sales'] = 100.
        self.write('sales.parquet', o, SCHEMA.append(pa.field('reviewed', pa.bool_())))
        self.git('commit', '-am', 'ours: review column and corrected sales')
        self.git('checkout', 'theirs')
        t[20]['sales'] = 200.
        t.pop(30)
        t.append({'id': 10000, 'region': 'north', 'sales': 30.})
        self.write('sales.parquet', t)
        diff = self.git('diff').stdout
        for text in ('CHANGED key=20', 'REMOVED', 'ADDED'):
            self.assertIn(text, diff)
        self.git('commit', '-am', 'theirs: sales correction, deletion and insertion')
        self.git('checkout', 'main')
        self.git('merge', 'theirs', '--no-edit')
        rows = {r['id']: r for r in pq.read_table(self.path / 'sales.parquet').to_pylist()}
        self.assertEqual(rows[10]['sales'], 100.)
        self.assertEqual(rows[20]['sales'], 200.)
        self.assertNotIn(30, rows)
        self.assertIsNone(rows[10000]['reviewed'])
        self.assertEqual(self.git('status', '--porcelain').stdout, '')
        # Git's external driver also handles added/deleted whole files.
        (self.path / 'sales.parquet').unlink()
        self.assertIn('REMOVED', self.git('diff').stdout)

    def test_real_git_conflict_preserves_index_stages(self):
        self.setup_git()
        o, t = copy.deepcopy(self.base), copy.deepcopy(self.base)
        o[0]['sales'], t[0]['sales'] = 99., 88.
        self.write('sales.parquet', o)
        self.git('commit', '-am', 'ours')
        self.git('checkout', 'theirs')
        self.write('sales.parquet', t)
        self.git('commit', '-am', 'theirs')
        self.git('checkout', 'main')
        before = (self.path / 'sales.parquet').read_bytes()
        result = self.git('merge', 'theirs', '--no-edit', ok=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn('"column": "sales"', result.stderr)
        self.assertEqual(len(self.git('ls-files', '-u').stdout.splitlines()), 3)
        self.assertEqual((self.path / 'sales.parquet').read_bytes(), before)
        self.assertEqual(pq.read_table(self.path / 'sales.parquet').to_pylist(), o)


if __name__ == '__main__':
    unittest.main(verbosity=2)
