# MCP Hello World — prototype

A minimal **Model Context Protocol (MCP)** server demo with three run modes,
all working locally on macOS.

```
python/mcp-hello/
├── server.py                  # FastMCP server — tools + resource
├── client.py                  # CLI chatbot (stdio transport)
├── webapp.py                  # Web chatbot (HTTP transport)
├── templates/index.html       # Vanilla HTML/JS chat UI
├── Dockerfile                 # Single image for server + webapp
├── docker-compose.yml         # Full stack: mcp-server + chatbot
├── pyproject.toml
├── .env.example
└── claude_desktop_config.json # Snippet for Claude Desktop
```

---

## How MCP works

```
 MCP Client (Claude Desktop / CLI bot / web chatbot)
 ────────────────────────────────────────────────────
 1. list_tools()         discovers what the server can do
 2. Claude API call      Claude sees the tool schemas + user message
 3. tool_use response    Claude asks to call a specific tool
 4. call_tool()          client executes it on the MCP server
 5. tool_result          Claude gets the data, writes final answer
        │
        │  stdio  OR  streamable-http
        ▼
 MCP Server  (server.py — FastMCP)
 ────────────────────────────────────────────────────
 Tools:    greet · get_time · add · reverse · word_stats
 Resource: mcp://hello/welcome
```

Two transports are supported:

| Transport | How the server runs | Used by |
|---|---|---|
| **stdio** | Client spawns server as subprocess; JSON-RPC over stdin/stdout | CLI chatbot, Claude Desktop, MCP Inspector |
| **streamable-http** | Server runs as a standalone process on port 8000 | Web chatbot, Docker Compose |

---

## Prerequisites

```bash
cd python/mcp-hello

# Create a virtual environment
python -m venv .venv && source .venv/bin/activate

# Install all dependencies
pip install -e .
# or with uv:  uv sync

# Set your Anthropic API key
cp .env.example .env
# then edit .env and set ANTHROPIC_API_KEY=sk-ant-...
```

---

## Option 1 — CLI chatbot (simplest, no Docker)

`client.py` spawns `server.py` as a subprocess automatically — no server setup needed.

```bash
python client.py                          # interactive loop
python client.py "Greet me as a pirate"   # single query
```

Sample output:

```
[MCP] Connected. Tools: ['greet', 'get_time', 'add', 'reverse', 'word_stats']

MCP Chatbot — type 'quit' or Ctrl-C to exit.

You: Greet me as a pirate and tell me the time in Tokyo
  [tool] greet({'name': 'you', 'style': 'pirate'})    → Ahoy, you! Welcome aboard...
  [tool] get_time({'timezone': 'Asia/Tokyo'})           → Current time in Asia/Tokyo: 2026-03-29 14:32 JST
Assistant: Ahoy, you! Welcome aboard, ye landlubber! Here is the time in Tokyo: 2026-03-29 14:32 JST
```

---

## Option 2 — Web chatbot with HTML UI (Docker Compose)

This option runs the MCP server as a separate HTTP service and the chatbot
as a Flask web app. Both run in Docker.

### 2a. Docker Compose (recommended for Docker Desktop demo)

```bash
# Build and start both services
ANTHROPIC_API_KEY=sk-ant-... docker compose up --build

# Open the chatbot in your browser
open http://localhost:5000
```

The compose file starts:
- **mcp-server** on port 8000 — the FastMCP server in HTTP mode
- **chatbot** on port 5000 — the Flask web app that connects to it

### 2b. Run locally without Docker

```bash
# Terminal 1 — start the MCP server in HTTP mode
python server.py --transport http
# Listening at http://0.0.0.0:8000/mcp

# Terminal 2 — start the web chatbot
python webapp.py
# open http://localhost:5000
```

---

## Option 3 — Claude Desktop (GUI, no code needed)

Claude Desktop natively supports MCP servers. Once configured, every conversation
in Claude Desktop can call your tools transparently.

1. Copy the snippet from `claude_desktop_config.json` into Claude's config:

```bash
open "~/Library/Application Support/Claude/claude_desktop_config.json"
```

Add (or merge) the `mcpServers` block, replacing the path:

```json
{
  "mcpServers": {
    "hello-world": {
      "command": "python",
      "args": ["/absolute/path/to/python/mcp-hello/server.py"]
    }
  }
}
```

2. Quit and reopen Claude Desktop.
3. A hammer icon appears in the chat input — click it to see your tools.
4. Chat naturally: *"What time is it in Paris?"* — Claude calls `get_time` automatically.

---

## Option 4 — MCP Inspector (interactive debugging)

The Inspector gives you a browser UI to explore and manually test the server
without writing any client code. No installation required.

```bash
# Inspect the server via stdio (same as CLI client)
npx @modelcontextprotocol/inspector python server.py

# Then open http://localhost:6274 in your browser
```

The Inspector lets you:
- Browse all tools and their JSON schemas
- Call any tool with custom inputs and see raw responses
- Read resources
- Watch server logs in real time

This is the best way to understand exactly what the MCP server exposes.

---

## Tools reference

| Tool | Arguments | Example |
|---|---|---|
| `greet` | `name`, `style` (`friendly`/`formal`/`pirate`) | "Greet Alice as a pirate" |
| `get_time` | `timezone` (IANA, default `UTC`) | "Time in US/Pacific" |
| `add` | `a`, `b` (floats) | "Add 42 and 3.14" |
| `reverse` | `text` | "Reverse 'hello world'" |
| `word_stats` | `text` | "Count words in this sentence" |

Resource `mcp://hello/welcome` — a static welcome message.

---

## Docker Desktop MCP Toolkit (bonus)

Docker Desktop 4.62+ has a built-in MCP Catalog. To register your own server:

1. Package it as a Docker image: `docker build -t mcp-hello .`
2. In Docker Desktop → Extensions → MCP Toolkit, add a custom server pointing
   to your image with `CMD ["python", "server.py", "--transport", "http"]`.
3. Connect it to Claude Desktop via the Clients tab → Claude Desktop.
4. Restart Claude Desktop.

This way Docker manages the server lifecycle and your MCP tools appear
automatically in Claude Desktop without manual config file editing.

---

## Project layout explained

```
server.py   FastMCP server
            - @mcp.tool()     → decorated functions become callable tools
            - @mcp.resource() → URI-addressable read-only data
            - mcp.run(transport="stdio"|"streamable-http")

client.py   CLI chatbot (stdio)
            - StdioServerParameters → spawn server.py as subprocess
            - ClientSession.list_tools() + call_tool()
            - Anthropic().messages.create() with tool schemas
            - Agentic loop until stop_reason != "tool_use"

webapp.py   Web chatbot (HTTP)
            - streamablehttp_client("http://...") → connect to running server
            - Same agentic loop, wrapped in a Flask POST /chat endpoint
            - Serves templates/index.html

templates/index.html
            Vanilla HTML/CSS/JS chatbot UI
            - fetch("/chat", ...) on submit
            - Suggestion pills for quick demos
```
