# daff-parquet: can Git merge datasets by row and column?

Yes, for single Parquet files with stable unique keys and compatible schemas.
This prototype implements the idea behind [daff](https://github.com/paulfitz/daff)
with PyArrow; it does not invoke or extend daff itself. It provides a real Git
three-way merge driver and an external diff driver. All project files and test
artifacts stay in this folder.

## Run it

Requires Python 3.12 (tested), Git, and PyArrow. From the repository root:

```bash
python -m venv daff-parquet/.venv
daff-parquet/.venv/bin/pip install -r daff-parquet/requirements.txt
(cd daff-parquet && .venv/bin/python -m unittest -v)
```

The included `.gitattributes` selects both drivers for `*.parquet` under this
folder, including subdirectories. Use this wrapper from the repository root:

```bash
daff-parquet/.venv/bin/python daff-parquet/git_parquet.py diff
daff-parquet/.venv/bin/python daff-parquet/git_parquet.py diff HEAD~1 HEAD
daff-parquet/.venv/bin/python daff-parquet/git_parquet.py merge other-branch
```

The wrapper supplies configuration with `git -c` for that invocation, so it
never edits `.git/config` or files outside this folder. Ordinary `git diff`
needs the same driver configuration; attributes alone do not install drivers.
For a persistent installation, you can optionally run the following yourself
from the repository root (these commands change local `.git/config`):

```bash
git config merge.parquet.driver '"./daff-parquet/.venv/bin/python" "./daff-parquet/parquet_git.py" --key id merge %O %A %B'
git config merge.parquet.recursive binary
git config diff.parquet.command '"./daff-parquet/.venv/bin/python" "./daff-parquet/parquet_git.py" --key id diff'
```

Use `--key customer_id` instead of `--key id` in both driver commands to select
another key. The wrapper uses `id`. Separate driver names/configuration are
needed for datasets with different key columns. No composite-key inference.
An external diff produces a review report, not a patch usable with `git apply`.
Some commands (e.g. `git show`) need `--ext-diff` to invoke external drivers.

Standalone merge (overwrites `ours.parquet` only on success):

```bash
daff-parquet/.venv/bin/python daff-parquet/parquet_git.py --key id merge ancestor.parquet ours.parquet theirs.parquet
```

## Merge rules

Read each file into a dictionary indexed by its key. Require one integer or
string key column with unique, non-null values. Row order is irrelevant.
For each key and cell, compare ancestor, ours and theirs:

- If both sides agree, use that value.
- If only one side changed from the ancestor, use that change.
- If both changed the same cell to different values, report a conflict.
- Combine changes to different cells, including cells in the same row.
- Accept independent inserts and unchanged-row deletions. Identical concurrent
  inserts coalesce; different inserts at the same new key conflict.
- Deleting a row that the other branch edited conflicts.

Null is a value, distinct from an absent row. Float NaNs compare equal to other
float NaNs; other floats use exact equality. Nullable added columns are unioned;
rows from a version without that column get null. Columns retain ancestor order,
then ours' additions, then theirs'. Output rows are sorted by key.
Column deletion, type changes and nullability changes on existing columns are
rejected, as are incompatible definitions of the same added column. Column
reordering is harmless. New non-nullable columns are rejected.

The driver writes a temporary Parquet file beside `%A`, then atomically replaces
`%A` only after the entire merge succeeds. On conflict it returns 1, prints key,
column and ancestor/ours/theirs values to stderr, and leaves ours byte-for-byte
intact. Git retains all three index stages and marks the path unmerged. It does
not insert text conflict markers into a binary file or silently keep a partial
merge. Validation and I/O failures also return nonzero.

## Experiment and results

Tested on Linux with Python 3.12, PyArrow 26.0.1 and real temporary Git
repositories. Run `python -m unittest -v` in this folder to reproduce.
The fixtures are generated synthetic sales data, not an externally sourced
production dataset. No network access is needed after dependency installation.

**12 tests passed** in approximately one second on the development machine.
This is a functional test duration, not a performance benchmark.

| Scenario | Observed result |
| --- | --- |
| Different rows edited; row order reversed | Combined by key |
| Same row, different columns edited | Both edits preserved |
| Identical concurrent cell edits | Clean merge |
| Same cell changed to different values | Conflict with values; ours unchanged |
| Insert, delete, and update in one merge | Correct keyed result |
| Same key inserted with different data | Add/add conflict |
| Delete versus row modification | Delete/modify conflict |
| Nullable Boolean column added on one branch; sales edited on the other | Schema and values combined |
| Other branch inserts a row without the new column | New field filled with null |
| New-column backfill versus row deletion | Delete/modify conflict |
| Column dropped, type changed, or incompatible additions | Explicit schema conflict |
| Duplicate, null, or missing key | Rejected |
| Empty table, null values, unchanged NaN | Handled |
| Actual `git diff` with additions/removals/changes | ADDED / REMOVED / CHANGED records |
| Actual Git same-cell conflict | Merge exits 1; three index stages remain; valid original Parquet |

The larger integration test starts with **10,000 sales rows**. Ours adds a
nullable `reviewed` column and changes sales for key 10. Theirs changes sales
for key 20, deletes key 30, and inserts key 10000. Key 30 is left null in the
new column so it is unchanged relative to the ancestor. Git merges successfully:
both corrections survive, key 30 is absent, key 10000 has `reviewed=null`, and
Git's working tree is clean after the merge commit. The test also exercises a
whole-file deletion through the diff driver's `/dev/null` input.

Example conflict from the actual Git integration test:

```text
parquet-git: {"ancestor": 10.0, "column": "sales", "key": 1, "kind": "cell", "ours": 99.0, "theirs": 88.0}
```

The row diff reports schema changes as well as data changes, for example:

```text
CHANGED key=20 {"sales": {"after": 200.0, "before": 20.0}}
REMOVED {"id": 30, "region": "west", "sales": 30.0}
ADDED {"id": 10000, "region": "north", "sales": 30.0}
```

## What broke and what is deliberately limited

The first integration run filled `reviewed=false` for *every* existing row,
while the other branch deleted key 30. Expecting a clean merge was wrong: the
backfill modifies that row. The driver correctly refused to discard that edit.
The successful fixture now leaves that one cell null, and a separate regression
test preserves the original conflict. Schema changes are data changes when
values are backfilled, even if they look like an independent migration.

Schema evolution needs policy. This experiment only auto-merges nullable
additions. It cannot safely infer renames, widen types, or decide whether a
column deletion should discard another branch's changes. These cases stop for
manual resolution; they are not silently coerced.

Other limits:

- All three inputs and the output are materialized in memory as Python rows.
  Work is proportional to cells plus key sorting; memory is much larger than
  compressed Parquet size. This is not suitable for warehouse-scale datasets.
- Parquet is rewritten with Snappy compression. Row groups, compression choices,
  physical encodings, file metadata and field metadata are not preserved as a
  fidelity contract. Top-level schema metadata is discarded. This includes
  pandas index metadata; store meaningful identity in the explicit key column.
- Exact decimal/timestamp values can pass through Arrow, but the test matrix
  focuses on integer keys, strings, floats and Booleans. Nested values are
  compared as whole cells, not recursively merged. Extension/complex Arrow
  types and unusual logical types are not certified by these tests.
- Key changes appear as deletion plus insertion, not renames. Renaming an entire
  file, whole-file add/add and delete/modify conflicts may be handled by Git
  before the custom merge driver is invoked.
- Git may bypass the driver for trivial merges (one unchanged side). Key/schema
  validation here is therefore not a repository-wide validation gate.
- Multiple merge bases use Git's binary recursive driver via the supplied
  configuration; criss-cross history is not validated by this experiment.
- Git LFS pointers, partitioned dataset directories, encryption and remote
  object storage are outside scope. Normal Git stores full binary blobs;
  a semantic merge driver does not solve repository growth.
- Diff output renders non-JSON scalar types as strings and NaN using Python's
  JSON extension. It is a human review format, not a lossless interchange file.

## Resolve a conflict

Git keeps the working file as ours. Extract all three versions inside this
folder, use PyArrow or your dataset editor to reconcile them, and stage the
resolved file:

```bash
git show :1:daff-parquet/sales.parquet > daff-parquet/ancestor.parquet
git show :2:daff-parquet/sales.parquet > daff-parquet/ours.parquet
git show :3:daff-parquet/sales.parquet > daff-parquet/theirs.parquet
# Write the reconciled dataset to daff-parquet/sales.parquet and inspect it.
git add daff-parquet/sales.parquet
git commit
```

Delete the extracted scratch copies when done; do not commit them accidentally.
Because a failed merge preserves the entire ours file, manual resolution must
also carry over nonconflicting edits from theirs. The prototype intentionally
provides no interactive resolver.
