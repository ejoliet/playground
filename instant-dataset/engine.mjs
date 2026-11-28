import initSQLite from './vendor/sqlite.mjs';
import { readCSV } from './csv.mjs';

const ready = initSQLite();
const ident = (name) => '"' + name.replaceAll('"', '""') + '"';
let sqlite,
  db,
  catalog,
  deadline = Infinity;
const pageSize = 50;

function fail(message) {
  throw new Error(message);
}
function checkColumns(names) {
  if (!names.length || names.length > 256) fail('Import needs between 1 and 256 columns.');
  const seen = new Set();
  for (const name of names) {
    const key = name.replace(/[A-Z]/g, (c) => c.toLowerCase());
    if (!name || name.includes('\0') || seen.has(key))
      fail('Empty or duplicate column name: ' + name);
    seen.add(key);
  }
}
function writer(columns, textOnly = false) {
  checkColumns(columns);
  db.exec(
    'CREATE TABLE data (' +
      columns.map((c) => ident(c) + (textOnly ? ' TEXT' : '')).join(',') +
      ')',
  );
  return db.prepare('INSERT INTO data VALUES (' + columns.map(() => '?').join(',') + ')');
}
function jsonValue(value) {
  if (value === null || typeof value === 'string') return value;
  if (typeof value === 'boolean') return Number(value);
  if (typeof value === 'number') {
    if (!Number.isFinite(value) || (Number.isInteger(value) && !Number.isSafeInteger(value)))
      fail(
        'JSON number is outside the supported precision range. Quote large integer identifiers.',
      );
    return value;
  }
  return JSON.stringify(value);
}
async function importFile(file) {
  sqlite = await ready;
  const c = sqlite.capi;
  db = new sqlite.oo1.DB(':memory:');
  db.exec('PRAGMA trusted_schema=OFF');
  const head = new Uint8Array(await file.slice(0, 20).arrayBuffer());
  let importedRows = null,
    last = 0;
  const progress = (bytes) => {
    if (performance.now() - last > 100 || bytes === file.size) {
      postMessage({ progress: bytes, total: file.size });
      last = performance.now();
    }
  };
  if (new TextDecoder().decode(head.subarray(0, 16)) === 'SQLite format 3\0') {
    if (head[18] === 2 || head[19] === 2)
      fail('WAL-mode SQLite file. Export a standalone snapshot with VACUUM INTO and retry.');
    const buffer = new Uint8Array(await file.arrayBuffer());
    const p = sqlite.wasm.allocFromTypedArray(buffer);
    // FREEONCLOSE transfers ownership, including cleanup when deserialize fails.
    db.checkRc(
      c.sqlite3_deserialize(
        db.pointer,
        'main',
        p,
        buffer.length,
        buffer.length,
        c.SQLITE_DESERIALIZE_FREEONCLOSE | c.SQLITE_DESERIALIZE_READONLY,
      ),
    );
  } else {
    let statement;
    db.exec('BEGIN');
    try {
      importedRows = 0;
      if (/\.csv$/i.test(file.name)) {
        let width;
        await readCSV(
          file,
          (row, record) => {
            if (record === 1) {
              width = row.length;
              statement = writer(row, true);
              return;
            }
            if (row.length !== width)
              fail(
                'CSV record ' + record + ' has ' + row.length + ' columns. Expected ' + width + '.',
              );
            statement.bind(row).stepReset();
            importedRows++;
          },
          progress,
        );
      } else if (/\.json$/i.test(file.name)) {
        if (file.size > 16 * 1024 ** 2)
          fail('JSON import limit is 16 MiB. Convert larger arrays to CSV or SQLite.');
        const records = JSON.parse(await file.text());
        if (!Array.isArray(records) || !records.length)
          fail('Expected a nonempty JSON array of objects.');
        const keys = new Set();
        for (const row of records) {
          if (!row || typeof row !== 'object' || Array.isArray(row))
            fail('Each JSON row must be an object.');
          for (const key of Object.keys(row)) keys.add(key);
        }
        const columns = [...keys];
        statement = writer(columns);
        for (const row of records) {
          statement
            .bind(columns.map((k) => (Object.hasOwn(row, k) ? jsonValue(row[k]) : null)))
            .stepReset();
          importedRows++;
        }
      } else fail('Choose a UTF-8 CSV, JSON array, or standalone SQLite database.');
      db.exec('COMMIT');
    } finally {
      statement?.finalize();
    }
  }
  const entries = db.selectArrays(
    "SELECT name,type FROM sqlite_schema WHERE type IN ('table','view') AND name NOT GLOB 'sqlite_*' ORDER BY type,name",
  );
  catalog = new Map(entries.map(([name, type]) => [name, { name, type }]));
  if (!catalog.size) fail('Database contains no user tables or views.');
  const heapBytes = sqlite.wasm.heap8u().byteLength;
  const databaseBytes = db.selectValue('PRAGMA page_count') * db.selectValue('PRAGMA page_size');
  db.exec('PRAGMA query_only=ON');
  const allowed = new Set([c.SQLITE_SELECT, c.SQLITE_READ, c.SQLITE_FUNCTION, c.SQLITE_RECURSIVE]);
  db.checkRc(
    c.sqlite3_set_authorizer(
      db.pointer,
      (_, operation) => (allowed.has(operation) ? c.SQLITE_OK : c.SQLITE_DENY),
      0,
    ),
  );
  c.sqlite3_progress_handler(db.pointer, 20000, () => (performance.now() > deadline ? 1 : 0), 0);
  progress(file.size);
  return { tables: [...catalog.values()], importedRows, heapBytes, databaseBytes };
}
function portable(value) {
  if (typeof value === 'bigint') return value.toString();
  if (value instanceof Uint8Array)
    return {
      hex: Array.from(value, (b) => b.toString(16).padStart(2, '0'))
        .join('')
        .toUpperCase(),
    };
  return value;
}
function result(sql, args, take) {
  const stmt = db.prepare(sql);
  try {
    if (args.length) stmt.bind(args);
    const columns = stmt.getColumnNames([]),
      rows = [];
    let bytes = 0;
    while (rows.length < take && stmt.step()) {
      for (let col = 0; col < columns.length; col++) {
        const c = sqlite.capi,
          type = c.sqlite3_column_type(stmt.pointer, col);
        bytes +=
          type === c.SQLITE_TEXT || type === c.SQLITE_BLOB
            ? c.sqlite3_column_bytes(stmt.pointer, col)
            : 8;
      }
      if (bytes > 2 * 1024 ** 2)
        fail('Result page exceeds 2 MiB. Select fewer columns or shorten large values in SQL.');
      rows.push(stmt.get([]).map(portable));
    }
    return { columns, rows };
  } finally {
    stmt.finalize();
  }
}
function query(view) {
  const offset = view.offset ?? 0;
  if (!Number.isSafeInteger(offset) || offset < 0) fail('Invalid offset.');
  let source,
    args = [],
    where = '';
  if (view.kind === 'sql') {
    const sql = view.sql.trim().replace(/;\s*$/, '');
    if (!sql) fail('Enter a SELECT query.');
    source = '(' + sql + '\n)';
  } else {
    const table = catalog.get(view.table);
    if (!table) fail('Unknown table.');
    source = ident(table.name);
    const columns = (table.columns ??= result(
      'SELECT * FROM ' + source + ' LIMIT 0',
      [],
      0,
    ).columns);
    const clauses = [];
    for (const f of view.filters ?? []) {
      if (!columns.includes(f.column)) fail('Unknown filter column.');
      const col = ident(f.column);
      switch (f.type) {
        case 'null':
          clauses.push(col + ' IS NULL');
          break;
        case 'blob':
          clauses.push('typeof(' + col + ")='blob' AND hex(" + col + ')=?');
          args.push(f.value.hex);
          break;
        case 'integer':
        case 'real':
        case 'text':
          clauses.push('typeof(' + col + ')=? AND ' + col + ' IS CAST(? AS ' + f.type + ')');
          args.push(f.type, f.value);
          break;
        default:
          fail('Invalid filter type.');
      }
    }
    if (view.search) {
      clauses.push(
        '(' +
          columns
            .map((col) => 'instr(lower(CAST(' + ident(col) + ' AS TEXT)),lower(?))>0')
            .join(' OR ') +
          ')',
      );
      args.push(...columns.map(() => view.search));
    }
    where = clauses.length ? ' WHERE ' + clauses.map((x) => '(' + x + ')').join(' AND ') : '';
    if (view.kind === 'facets') {
      if (!columns.includes(view.column)) fail('Unknown facet column.');
      const col = ident(view.column);
      return result(
        'SELECT ' +
          col +
          ' AS value, typeof(' +
          col +
          ') AS storage_type, count(*) AS n FROM ' +
          source +
          where +
          ' GROUP BY 1,2 ORDER BY 3 DESC,2,1 LIMIT 20',
        args,
        20,
      );
    }
    if (view.kind !== 'rows') fail('Unknown view type.');
  }
  const data = result(
    'SELECT * FROM ' + source + where + ' LIMIT ? OFFSET ?',
    [...args, pageSize + 1, offset],
    pageSize + 1,
  );
  const hasMore = data.rows.length > pageSize;
  if (hasMore) data.rows.pop();
  return { ...data, offset, hasMore };
}
self.onmessage = async ({ data: { id, file, view } }) => {
  try {
    deadline = performance.now() + 15000;
    const value = file ? await importFile(file) : query(view);
    postMessage({ id, value });
  } catch (error) {
    postMessage({
      id,
      error:
        performance.now() > deadline && !file
          ? 'Query exceeded the 15-second budget.'
          : error.message,
    });
  } finally {
    deadline = Infinity;
  }
};
