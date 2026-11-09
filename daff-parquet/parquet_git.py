#!/usr/bin/env python3
"""Keyed Parquet three-way merge and Git external diff drivers."""
import argparse
import json
import math
import os
from pathlib import Path
import sys
import tempfile

import pyarrow as pa
import pyarrow.parquet as pq


class Conflict(ValueError):
    pass


def equal(a, b):
    if isinstance(a, float) and isinstance(b, float):
        return a == b or (math.isnan(a) and math.isnan(b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(equal(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(equal(x, y) for x, y in zip(a, b))
    return a == b


def render(value):
    return json.dumps(value, default=str, sort_keys=True, ensure_ascii=True)


def read(path, key, empty=False):
    if empty and path == '/dev/null':
        return pa.schema([]), {}
    table = pq.ParquetFile(path).read()
    schema = table.schema
    if len(set(schema.names)) != len(schema.names):
        raise Conflict('duplicate column names')
    if key not in schema.names:
        raise Conflict(f'missing key column {key!r}')
    typ = schema.field(key).type
    if not (pa.types.is_integer(typ) or pa.types.is_string(typ) or pa.types.is_large_string(typ)):
        raise Conflict('key must have integer or string type')
    rows = {}
    for row in table.to_pylist():
        value = row[key]
        if value is None or value in rows:
            raise Conflict(f'null or duplicate key: {value!r}')
        rows[value] = row
    return schema, rows


def merge_schema(base, ours, theirs):
    # Refuse destructive/ambiguous migrations rather than silently dropping data.
    for field in base:
        for schema in (ours, theirs):
            if field.name not in schema.names or not field.equals(schema.field(field.name)):
                raise Conflict(f'unsupported schema change: {field.name} dropped or type/nullability changed')
    fields = list(base)
    for schema in (ours, theirs):
        for field in schema:
            if field.name in base.names:
                continue
            if not field.nullable:
                raise Conflict(f'new column must be nullable: {field.name}')
            existing = next((f for f in fields if f.name == field.name), None)
            if existing is not None and not existing.equals(field):
                raise Conflict(f'incompatible added column: {field.name}')
            if existing is None:
                fields.append(field)
    return pa.schema([pa.field(f.name, f.type, f.nullable) for f in fields])


def merge(base_path, ours_path, theirs_path, key):
    bs, base = read(base_path, key)
    oschema, ours = read(ours_path, key)
    ts, theirs = read(theirs_path, key)
    schema = merge_schema(bs, oschema, ts)
    for rows in (base, ours, theirs):
        for row in rows.values():
            for name in schema.names:
                row.setdefault(name, None)
    output, conflicts = [], []
    for value in sorted(base.keys() | ours.keys() | theirs.keys()):
        b, o, t = (rows.get(value) for rows in (base, ours, theirs))
        if equal(o, t):
            result = o
        elif equal(o, b):
            result = t
        elif equal(t, b):
            result = o
        elif b is None or o is None or t is None:
            conflicts.append({'key': value, 'kind': 'add/add' if b is None else 'delete/modify',
                              'ancestor': b, 'ours': o, 'theirs': t})
            continue
        else:
            result = {}
            for name in schema.names:
                if equal(o[name], t[name]) or equal(t[name], b[name]):
                    result[name] = o[name]
                elif equal(o[name], b[name]):
                    result[name] = t[name]
                else:
                    conflicts.append({'key': value, 'column': name, 'kind': 'cell',
                                      'ancestor': b[name], 'ours': o[name], 'theirs': t[name]})
        if result is not None:
            output.append(result)
    if conflicts:
        raise Conflict('\n'.join(render(c) for c in conflicts))
    table = pa.Table.from_pylist(output, schema=schema)
    # Same-directory replacement: failure never truncates Git's %A input.
    fd, temporary = tempfile.mkstemp(dir=Path(ours_path).resolve().parent, suffix='.parquet')
    os.close(fd)
    try:
        pq.write_table(table, temporary, compression='snappy')
        os.replace(temporary, ours_path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def diff(old_path, new_path, key, label):
    old_schema, old = read(old_path, key, empty=True)
    new_schema, new = read(new_path, key, empty=True)
    print(f'Parquet diff: {label} (key={key})')
    for name in sorted(set(old_schema.names) | set(new_schema.names)):
        before = str(old_schema.field(name)) if name in old_schema.names else None
        after = str(new_schema.field(name)) if name in new_schema.names else None
        if before != after:
            print(f'SCHEMA {name}: {before} -> {after}')
    # A key-type migration is still printable; sort by representation across types.
    for value in sorted(old.keys() | new.keys(), key=lambda v: (type(v).__name__, v)):
        if value not in old:
            print(f'ADDED {render(new[value])}')
        elif value not in new:
            print(f'REMOVED {render(old[value])}')
        elif not equal(old[value], new[value]):
            changes = {name: {'before': old[value].get(name), 'after': new[value].get(name)}
                       for name in sorted(old[value].keys() | new[value].keys())
                       if name not in old[value] or name not in new[value]
                       or not equal(old[value][name], new[value][name])}
            print(f'CHANGED key={render(value)} {render(changes)}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--key', default='id')
    sub = parser.add_subparsers(dest='command', required=True)
    m = sub.add_parser('merge')
    for name in ('ancestor', 'ours', 'theirs'):
        m.add_argument(name)
    d = sub.add_parser('diff', help='Git external diff protocol (seven arguments)')
    d.add_argument('git_args', nargs=7)
    args = parser.parse_args()
    try:
        if args.command == 'merge':
            merge(args.ancestor, args.ours, args.theirs, args.key)
        else:
            name, old, _, _, new, _, _ = args.git_args
            diff(old, new, args.key, name)
    except (ValueError, OSError, pa.ArrowException) as exc:
        print(f'parquet-git: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
