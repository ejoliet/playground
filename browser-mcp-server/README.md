# Browser MCP server: Python and SQLite with no application backend

**Yes, a page can host MCP tools in Pyodide through the existing ASGI/service-worker bridge. No, that does not make the tab’s endpoint reachable by an ordinary remote MCP HTTP client.** The endpoint exists inside the browser’s fetch interception machinery; the browser does not listen for inbound HTTP connections.

This experiment implements three tools over a real in-memory SQLite database, tests them through `fetch()` in Chromium, and tests the same URL from outside the browser. Investigation date: **2026-11-09**.

[Demo URL after GitHub Pages publishes this folder](https://simonw.github.io/research/browser-mcp-server/) · [Original bridge project](https://github.com/simonw/research/tree/main/pyodide-asgi-browser)

This copy is available in [`ejoliet/playground`, branch `simonw/research`](https://github.com/ejoliet/playground/tree/simonw/research/browser-mcp-server). [Download the project source ZIP](https://github.com/ejoliet/playground/raw/refs/heads/simonw/research/browser-mcp-server/browser-mcp-server.zip), extract it, and run `python3 setup.py` inside `browser-mcp-server` before starting the static server. The ZIP includes the source, report and test evidence; runtime assets are downloaded by setup. The Pages link below describes the original intended location, not a deployment of this copy.

## Run it

```bash
cd browser-mcp-server
python3 setup.py
python3 -m http.server 8000 --bind 127.0.0.1
# Open http://127.0.0.1:8000/
```

Wait for **ready**, then click **Run in-page tests**. This discovers the server, lists its tools, inserts a note, searches for it, and checks the count. You can add/list notes manually. **Open separate client tab** runs the same tests from a page that does not own a Python runtime.

The only host process is a static file server. It neither runs the MCP app nor handles SQLite. HTTPS or localhost is required for service workers; opening `index.html` as a `file:` URL will not work.

`setup.py` downloads Pyodide **0.27.7**, its SQLite/micropip package dependencies, and the original bridge/runtime into ignored directories inside this folder. Runtime assets total about 14 MB. The browser loads them locally without CDN requests. This is not an offline-first app: there is no asset cache for reopening it without the static host. `github-pages.sh` prepares these assets during the repository’s existing Pages build; no publishing was performed in this investigation.

## Read the current specification first

On the investigation date, the official [`/specification/latest`](https://modelcontextprotocol.io/specification/latest) redirected to **2026-07-28**. The implementation targets that revision only. It does not silently assume the older initialization-based protocol.

Sources read before implementation:

- [Base protocol and per-request metadata](https://modelcontextprotocol.io/specification/2026-07-28/basic/index)
- [Versioning and compatibility](https://modelcontextprotocol.io/specification/2026-07-28/basic/versioning)
- [Transport overview](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports)
- [Streamable HTTP](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http)
- [Server discovery](https://modelcontextprotocol.io/specification/2026-07-28/server/discover)
- [Tools](https://modelcontextprotocol.io/specification/2026-07-28/server/tools)

Relevant changes in this revision:

| Requirement | Prototype behavior |
| --- | --- |
| Per-request protocol metadata replaces initialization | Each request includes `params._meta` protocol version and client capabilities; the client also includes its identity |
| `server/discover` is mandatory | Reports supported version, identity, and tools capability |
| Mirrored HTTP headers | Validates `MCP-Protocol-Version`, `Mcp-Method`, and `Mcp-Name`; decodes Base64 sentinel names |
| Version/header errors | HTTP 400 with `-32022` for unsupported versions and `-32020` for header mismatches |
| Result discriminant | Successful results include `resultType: "complete"` and server identity metadata |
| HTTP request responses may be JSON or SSE | Uses the permitted single JSON response option |
| POST endpoint; standalone GET streams and sessions removed | GET/DELETE return 405; no protocol session ID is issued |
| Validate Origin | A supplied foreign Origin gets 403; no cross-origin CORS allowance |
| Tool errors | Unknown tools/malformed call structure are protocol errors; tool input validation and SQLite failures use `isError: true` |

Missing required body metadata gets HTTP 400 / `-32602`. Unknown RPC methods get HTTP 404 / `-32601`. The server rejects batches, malformed JSON, invalid IDs, inappropriate media types, and missing Accept types. `ping` is implemented. No current HTTP client notifications are implemented; unsupported notification POSTs are rejected rather than given JSON-RPC success responses.

This is a deliberately small handwritten implementation, not an official SDK port or a certified complete MCP server. An older client sending `initialize` receives a diagnostic naming the supported revision. Legacy SDK interoperability was not implemented or claimed.

## What is reused

The workspace initially had no repository checkout. The source was located in `simonw/research` using repository access. All output was created in this folder; the original project was read without modification.

`setup.py` fetches **unchanged** `bridge-python.js` and `worker-runtime.js` from original commit [`aa4e39edad154dad649a1804e32a943cf670a6e4`](https://github.com/simonw/research/tree/aa4e39edad154dad649a1804e32a943cf670a6e4/pyodide-asgi-browser), with SHA-256 checks. They are generated dependencies, not duplicated source files to commit. The original `ASGIBridge` performs scope construction, host-header synthesis, lifespan, request delivery, and response collection. The original worker runtime performs Pyodide startup, package loading and request dispatch over a private message channel.

The new service worker and shell retain the original request path:

```text
page fetch(POST /app/<hosting-client-id>/mcp)
  -> service worker
  -> owning shell via one-shot MessageChannel
  -> dedicated Web Worker via private MessageChannel
  -> original ASGIBridge
  -> Python MCP app -> SQLite
  <- buffered JSON response through the same chain
```

The shell owns the long-lived worker. Unlike the original HTML application, this API demo needs no iframe: the shell calls the intercepted endpoint directly.

The original service worker selects the first non-app shell it finds. This experiment instead addresses a specific hosting browser client, so multiple tabs have separate databases. An initial approach using `history.replaceState()` and a UUID query parameter failed to locate the owner in Chromium. The fix asks the service worker for `event.source.id` and uses `clients.get(id)` on every request. There is no routing table to lose when the service worker stops. Host disappearance yields 503; an unresponsive host has a five-second bridge deadline (504). That timeout does not cancel Python execution.

## Three SQLite tools

| Tool | Input | SQLite operation |
| --- | --- | --- |
| `add_note` | `text`: 1–1000 characters | Parameterized INSERT, returning ID and text |
| `list_notes` | Optional `search` string | Literal substring search using `instr()`, ordered by ID, capped at 100 rows |
| `note_stats` | Empty arguments | `count(*)` and total text length |

The database starts with two notes. It is a real `sqlite3.connect(':memory:')` connection inside WebAssembly, not JavaScript emulation or a server database. Each tool returns text content and structured JSON. Fixed SQL and bound parameters prevent note contents from becoming SQL. There is no arbitrary SQL tool. Data belongs to one hosting tab and disappears on reload or close.

## Results

The final run used Chromium (exact version in [browser-results.json](browser-results.json)), Python 3.12, and Pyodide 0.27.7. **All 9 test methods passed:** eight native protocol/bridge tests and one browser experiment containing multiple scenarios. The final browser run served the app under `/browser-mcp-server/`, exercising the nested path needed for Pages.

| Experiment | Observed outcome |
| --- | --- |
| In-page `fetch()` discovery/list/insert/search/count | Passed; all three tools executed in Pyodide |
| Manual UI form driven by Playwright | Added a note and displayed its result |
| Separate controlled tab, same browser context and origin | Passed; called the hosting tab’s tools without owning Pyodide |
| Python `urllib` POST to the identical endpoint while tab was alive | **501** from the static HTTP server; never reached the service worker |
| Fresh browser context with service workers blocked | **501** from static server |
| External Playwright process evaluating a call inside the host page | Passed, through browser automation; this is not direct remote MCP transport |
| Two hosting tabs open together | Second tab had its own two seed rows and distinct endpoint |
| Reload host | Database reset to two seed rows; old endpoint returned **503** |
| Close host while other tabs remain | Endpoint returned **503**, not another tab’s database |
| Protocol validation, Origin, Unicode, SQL-injection-shaped text | Passed through the actual reused bridge |
| Controlled SSE bridge probe | First event remained buffered until the app finished |

[Machine-readable browser results](browser-results.json) · [Full final test log](test-results.txt) · [Investigation notes](notes.md)

No real LLM or desktop MCP application was connected. The in-page client exercises current MCP wire messages directly. The outside test intentionally uses a correct modern HTTP discovery request, isolating reachability from SDK-version compatibility.

## What broke, and what the result means

**An intercepted URL is not a public MCP endpoint.** A normal agent on a server, a desktop MCP HTTP client, or curl sends requests to the static host. Those requests never enter the tab’s service worker. The exact network failure depends on the host: Python’s static server returned 501 for POST; another host might return 404 or 405. CORS headers cannot turn a service worker into a network listener.

**Streaming does not survive the bridge unchanged.** `ASGIBridge.handle()` returns only after the ASGI app returns and joins every response chunk. The test sends one SSE event, pauses the app, and verifies the caller has received no response. A long-lived `subscriptions/listen` stream would never be delivered incrementally, and our broker would time out. The bridge also returns synthetic `http.disconnect` after consuming the request body; that is not a real client-disconnection signal. Progress, subscriptions, and cancellation would need an incremental message protocol plus a `ReadableStream` response and explicit abort propagation. None is advertised here.

**Lifetime remains tied to the hosting document.** Service worker survival does not keep the dedicated Python worker alive after the tab closes. Browser suspension can interrupt service, and reload creates a new endpoint and database. Persistence via IndexedDB/OPFS is possible future work, not part of this experiment. Service-worker restart behavior follows the original stateless lookup design but was not independently forced in a test.

**Browser-local trust is limited.** This demo trusts same-origin pages. A browser client ID is a routing identifier, not authentication. There is no OAuth, per-caller authorization, invocation rate limiting, persistent audit log, or total database-size quota. The request and text limits bound individual calls, not overall use. It is an experiment with disposable notes, not a production service for sensitive data. No cross-origin page integration, browser extension, relay, WebRTC transport, Firefox or Safari testing was attempted.

For an AI agent **running in the controlled page**, the technique works: the agent’s tool adapter can discover and invoke these tools with fetch, while Python and data stay local. An agent accessed through browser automation can also enter the page, as demonstrated. An ordinary external agent needs an additional connection mechanism: a browser extension/native bridge, an automation adapter, or an outbound relay/custom transport. A relay introduces infrastructure; none of those mechanisms is supplied by the service worker itself.

## Files and tests

- `app.py`: MCP ASGI app and three SQLite tools.
- `worker.js`: wires the app to the original bridge and runtime.
- `sw.js`, `bootstrap.js`: request interception, owner routing and worker lifecycle.
- `client.js`, `index.html`, `client.html`: modern MCP client, demo and separate-tab experiment.
- `setup.py`, `github-pages.sh`: reproducible static asset preparation.
- `test_protocol.py`: app/bridge validation, including a controlled SSE probe.
- `test_browser.py`: Chromium and external HTTP experiment.

```bash
python3 setup.py
python3 -m unittest test_protocol -v
# Requires Playwright and Chromium installed in your development environment:
python3 -m unittest test_browser -v
```

The browser test uses `/usr/bin/chromium`. The final captured run used an already installed Playwright. Downloaded runtime/source/spec files, caches, and bytecode are ignored; no `_summary.md` was created.
