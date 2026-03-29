"""
Web chatbot — Flask app that acts as an MCP client (HTTP transport).
It serves a simple HTML UI and proxies chat messages through Claude + the MCP server.

Requires the MCP server to be running in HTTP mode:
    python server.py --transport http

Usage:
    python webapp.py          # then open http://localhost:5000
"""

import asyncio
import os

from anthropic import Anthropic
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

load_dotenv()

app = Flask(__name__)
anthropic = Anthropic()

MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8000/mcp")
MODEL = "claude-sonnet-4-6"


# ── MCP helpers ───────────────────────────────────────────────────────────────

async def _process_message(user_message: str) -> str:
    """Open a fresh MCP session, fetch tools, run Claude's agentic loop."""
    async with streamablehttp_client(MCP_SERVER_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = (await session.list_tools()).tools
            tool_schemas = [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.inputSchema,
                }
                for t in tools
            ]

            messages = [{"role": "user", "content": user_message}]

            # Agentic loop
            while True:
                response = anthropic.messages.create(
                    model=MODEL,
                    max_tokens=1024,
                    tools=tool_schemas,
                    messages=messages,
                )

                text_parts = [
                    b.text for b in response.content if b.type == "text"
                ]

                if response.stop_reason != "tool_use":
                    return "\n".join(text_parts)

                tool_results = []
                for block in response.content:
                    if block.type != "tool_use":
                        continue
                    result = await session.call_tool(block.name, block.input)
                    result_text = "".join(
                        c.text for c in result.content if hasattr(c, "text")
                    )
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result_text,
                        }
                    )

                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": tool_results})


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html", mcp_server_url=MCP_SERVER_URL)


@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify({"error": "No message provided"}), 400

    try:
        answer = asyncio.run(_process_message(message))
        return jsonify({"response": answer})
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 500


@app.route("/health")
def health():
    return jsonify({"status": "ok", "mcp_server": MCP_SERVER_URL})


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.getenv("WEBAPP_PORT", "5000"))
    print(f"Web chatbot at http://localhost:{port}")
    print(f"Connecting to MCP server at {MCP_SERVER_URL}")
    app.run(host="0.0.0.0", port=port, debug=False)
