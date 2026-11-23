# Instant Dataset

Drop a CSV, a JSON array or a SQLite file into the page. Browse its rows, search across columns, narrow the results by clicking facet values, run SQL, or open the current result as JSON. The browser owns the database for the lifetime of the tab. A static host serves the application files.

## Try it

From the repository root on branch `instant-dataset`, run `python3 -m http.server 8000 --bind 127.0.0.1 --directory instant-dataset`. Open [localhost:8000](http://localhost:8000/). The same directory can be served under a subpath on an HTTPS static host. Serve `.mjs` as JavaScript and `.wasm` as `application/wasm`. Opening the HTML with `file://` does not provide the required worker environment.

Click **Open example** for a 12-row synthetic observing log. Choose **site** under **Browse by facet**, then click **Palomar** to see five observations. Click its filter chip to clear it. **SQL console** queries the underlying database independently of the table controls. For example, sum the exposure minutes by site.

```sql
SELECT site, SUM(CAST(minutes AS INTEGER)) AS total_minutes
FROM data
GROUP BY site
ORDER BY total_minutes DESC;
```

## What the browser actually handled

The small file felt instant. The 100 MB file was usable after a **14.48-second median import**. Once open, the median grouped SQL query took **376 ms**. Import latency is the first obstacle to promising an instant site at this size.

Three runs per file on November 22, 2026, in headless Chromium 153.0.8010.0 on Linux x86-64 (AMD EPYC 9V74). Times below are medians with the full range in parentheses.

| Measurement | Small CSV · 345 bytes, 12 rows | Large CSV · 100 MB, 1,000,000 rows |
| --- | ---: | ---: |
| File selection to first table | 156 ms (142–198) | 14.48 s (14.27–14.79) |
| Facet on site | 33 ms (30–34) | 794 ms (792–1,294) |
| Text search and fetch matching JSON | 72 ms (67–75) | 825 ms (824–850) |
| SQL group count by site | 56 ms (55–58) | 376 ms (342–390) |
| SQLite database page bytes | 16,384 | 109,363,200 |
| Worker WebAssembly heap bytes after import | 8,388,608 | 131,137,536 |

Across the three large imports, a 50 ms main-thread timer had a longest observed gap of 67 ms. This measures responsiveness in a foreground headless tab. The heap reading covers the worker’s WebAssembly linear memory. It excludes the browser, JavaScript objects, file backing and transient allocations. Peak process memory and a maximum safe file size remain unknown.

Each run opened a fresh browser context and selected a file through the page's file input. Open time covers selection, SQLite worker startup, import and the first rendered page. The timer starts after the static page has loaded. Facet time covers selecting a column through rendering its counts. Search time includes submitting the literal, rendering the match and fetching its JSON. SQL time covers submitting the grouping query through the result becoming available. The test uses Playwright wall-clock timings, so short operations include browser automation overhead.

The large fixture has exactly 100,000,000 bytes, one million rows, five text columns, four sites and a repeated ASCII note. The harness searched for a unique target in the last row, verified four counts of 250,000, paged to the final record through the JSON endpoint, and checked that the SQL group totals summed to one million. It generates the fixture locally and removes it after the run. Wide tables, long Unicode fields, more distinct facet values and slower devices can change the results substantially. Safari, Firefox, phones, and files larger than 100 MB remain unmeasured.

## Design and limits

Datasette Lite established the model of running SQLite and a dataset explorer in a browser worker. For this experiment I chose SQLite's JavaScript interface and a purpose-built viewer. The pinned module and WebAssembly binary together weigh 1,535,956 bytes uncompressed and load from this folder. This removes the Python runtime from the startup path. I did not benchmark Datasette Lite head-to-head. [Datasette Lite](https://github.com/simonw/datasette-lite) · [SQLite WebAssembly API](https://sqlite.org/wasm/doc/trunk/api-oo1.md)

| Input | Import behavior | Boundary |
| --- | --- | --- |
| CSV | Decodes UTF-8 in 256 KiB chunks in a worker and inserts through one prepared statement in one transaction. Preserves leading zeroes and empty strings. Supports BOM, CRLF, quoted commas, escaped quotes and multiline fields. | Comma-separated with one header row and consistent widths. Up to 256 nonempty, unique column names and 4,194,304 Unicode code points per record. CSV fields stay text. Cast them for numeric sorting and math. |
| JSON | Reads a nonempty array of objects, takes the union of the keys and maps missing fields to SQL NULL. Numbers retain numeric types, booleans become 0/1 and nested values become JSON text. | 16 MiB input cap because the text and parsed object graph coexist. Up to 256 columns. Quote precision-sensitive values before import. JSON parsing uses JavaScript numbers. |
| SQLite | Opens an in-memory copy of a standalone database and lists user tables and views. Ordinary indexes in the input remain available to SQLite. | Requires the complete main database. For a write-ahead log (WAL) database, export a standalone snapshot with `VACUUM INTO 'snapshot.sqlite'` in the database's original environment. External extensions and custom collations may be unavailable. |

The database for a CSV becomes queryable after its import transaction commits. Reading in chunks bounds input buffering, but the database still grows in memory. Opening a replacement temporarily keeps the previous worker alive so a malformed import leaves the current dataset usable. A failed quoted-field import and an oversized JSON file both produced visible errors in testing.

Browsing returns 50 rows per page. A facet ranks the 20 most frequent values *within the current filters*. Click values in successive columns to intersect filters. Search uses a literal substring across all columns with SQLite's default ASCII case folding. Imported CSVs have no indexes. Searches for a late match, grouping, and large offsets can scan the table even though the page displays only 50 rows. Use an explicit SQL `ORDER BY` when stable page order matters.

The SQL box accepts a single query usable as a SQLite subquery, including common table expressions. A read-only connection policy and authorizer restrict operations after import. SQLite checks a 15-second budget periodically during query execution. The viewer rejects a result page over a 2 MiB value budget before copying it to the UI. An unbounded recursive aggregate hit the timeout, and a 3 MB blob hit the result limit. The same tab could run another query afterward.

## Browser-local JSON API

**View JSON** exposes the displayed table page or SQL result. **Facet JSON** exposes the displayed value, storage type and count for each bucket. Both are real GET endpoints handled by a service worker. Opening a link in another tab of the same browser profile works while the dataset tab stays open. The path contains opaque tab, dataset and view IDs. File contents, search terms and SQL stay out of the URL. [Service worker fetch events](https://developer.mozilla.org/en-US/docs/Web/API/ServiceWorkerGlobalScope/fetch_event)

From the explorer's browser console, fetch the displayed snapshot, then request another page of the same query.

```js
const url = new URL(document.querySelector('#api').href);
const current = await fetch(url).then(response => response.json());
url.searchParams.set('offset', '50');
const next = await fetch(url).then(response => response.json());
```

A table or SQL response contains `view`, `columns`, `rows`, `offset` and `hasMore`. Rows are arrays in column order. An explicit offset re-executes the saved query. Large SQLite integers are decimal strings and blobs are objects with a `hex` property. Facet responses have `view`, `columns` and `rows`. Opening another file or reloading the owner tab expires its views. The tab retains up to 32 recent snapshots, including the visible ones. An expired view returns HTTP 410 within the service worker's scope. The static host has no dataset endpoint for curl, another device or a shared public link.

## Reproduce the experiment

From this folder with Python 3.12 and uv installed, run the following commands.

```sh
uv run --with playwright==1.62.0 playwright install chromium
uv run --with playwright==1.62.0 python tests/bench.py --runs 3
```

Use `--small-only` to skip the large fixture, or set `CHROMIUM` to an existing Chromium executable. The harness starts an ephemeral loopback static server. It exercises the file picker and drag-and-drop, native SQLite tables and views, JSON with uneven keys, typed NULL facets, UTF-8 split across a chunk boundary, multiline CSV, SQL failures and recovery, JSON navigation from another tab, URL expiry, and querying a loaded dataset with the browser offline. It also asserts that no API request reached the static server.

The runtime comes from `@sqlite.org/sqlite-wasm@3.54.1-build1`. Its `dist/index.mjs` is vendored as `vendor/sqlite.mjs`, alongside the Wasm binary, optional upstream worker helper and license. No package install, build step or external content delivery network is needed to use the page.
