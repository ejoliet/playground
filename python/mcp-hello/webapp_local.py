"""
Web chatbot (local LLM) — Flask app that connects to the MCP server via HTTP
and uses Ollama instead of the Anthropic API.

Requires the MCP server running in HTTP mode:
    python server.py --transport http

And Ollama running locally (or via OLLAMA_HOST):
    brew install ollama && ollama pull qwen2.5:7b && ollama serve

Usage:
    python webapp_local.py       # then open http://localhost:5000

Docker Compose (with Ollama on host macOS):
    OLLAMA_HOST=http://host.docker.internal:11434 \
    docker compose -f docker-compose.local.yml up --build
"""

import asyncio
import os

import ollama
from flask import Flask, jsonify, render_template, request
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

app = Flask(__name__)

MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8000/mcp")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")


def _to_ollama_tools(mcp_tools) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description or "",
                "parameters": t.inputSchema,
            },
        }
        for t in mcp_tools
    ]


async def _process_message(user_message: str) -> str:
    client = ollama.Client(host=OLLAMA_HOST)

    async with streamablehttp_client(MCP_SERVER_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            mcp_tools = (await session.list_tools()).tools
            tools = _to_ollama_tools(mcp_tools)

            messages: list = [{"role": "user", "content": user_message}]

            while True:
                response = client.chat(model=MODEL, messages=messages, tools=tools)
                msg = response.message

                if not msg.tool_calls:
                    return msg.content or ""

                messages.append(msg)

                for tc in msg.tool_calls:
                    name = tc.function.name
                    args = dict(tc.function.arguments)
                    result = await session.call_tool(name, args)
                    result_text = "".join(
                        c.text for c in result.content if hasattr(c, "text")
                    )
                    messages.append({"role": "tool", "content": result_text})


@app.route("/")
def index():
    return render_template(
        "index.html",
        mcp_server_url=MCP_SERVER_URL,
        extra_info=f"Local LLM: {MODEL} via {OLLAMA_HOST}",
    )


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
    return jsonify(
        {"status": "ok", "mcp_server": MCP_SERVER_URL, "llm": MODEL, "ollama": OLLAMA_HOST}
    )


if __name__ == "__main__":
    port = int(os.getenv("WEBAPP_PORT", "5000"))
    print(f"Web chatbot (local LLM) at http://localhost:{port}")
    print(f"MCP server : {MCP_SERVER_URL}")
    print(f"Ollama     : {OLLAMA_HOST}  model={MODEL}")
    app.run(host="0.0.0.0", port=port, debug=False)
