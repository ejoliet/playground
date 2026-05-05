"""
CLI chatbot — local LLM via Ollama, no API key needed.
Uses the MCP server over stdio (spawns it as a subprocess).

Requirements:
  brew install ollama
  ollama pull qwen2.5:7b        # or llama3.1:8b, mistral:7b-instruct
  ollama serve                  # (auto-starts on macOS after brew install)

Usage:
  python client_local.py
  OLLAMA_MODEL=llama3.1:8b python client_local.py
"""

import asyncio
import os
import sys
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Optional

import ollama
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER_SCRIPT = Path(__file__).parent / "server.py"
MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")


def _to_ollama_tools(mcp_tools) -> list[dict]:
    """Convert MCP tool schemas to Ollama/OpenAI function-calling format."""
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


class LocalMCPChatbot:
    def __init__(self) -> None:
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self.ollama = ollama.Client(host=OLLAMA_HOST)

    async def connect(self) -> None:
        server_params = StdioServerParameters(
            command=sys.executable,
            args=[str(SERVER_SCRIPT)],
            env=None,
        )
        transport = await self.exit_stack.enter_async_context(
            stdio_client(server_params)
        )
        read, write = transport
        self.session = await self.exit_stack.enter_async_context(
            ClientSession(read, write)
        )
        await self.session.initialize()

        tools = (await self.session.list_tools()).tools
        names = [t.name for t in tools]
        print(f"[MCP] Connected. Tools: {names}")
        print(f"[LLM] Using Ollama model: {MODEL}  ({OLLAMA_HOST})\n")

    async def chat(self, user_message: str) -> str:
        assert self.session

        mcp_tools = (await self.session.list_tools()).tools
        tools = _to_ollama_tools(mcp_tools)

        messages: list = [{"role": "user", "content": user_message}]

        # Agentic loop
        while True:
            response = self.ollama.chat(
                model=MODEL,
                messages=messages,
                tools=tools,
            )
            msg = response.message

            # No more tool calls — return final text
            if not msg.tool_calls:
                return msg.content or ""

            # Add assistant turn (with pending tool calls)
            messages.append(msg)

            # Execute each tool via MCP
            for tc in msg.tool_calls:
                name = tc.function.name
                args = dict(tc.function.arguments)
                result = await self.session.call_tool(name, args)
                result_text = "".join(
                    c.text for c in result.content if hasattr(c, "text")
                )
                print(f"  [tool] {name}({args}) → {result_text}")
                messages.append({"role": "tool", "content": result_text})

    async def close(self) -> None:
        await self.exit_stack.aclose()


async def run() -> None:
    bot = LocalMCPChatbot()
    await bot.connect()

    if len(sys.argv) > 1:
        answer = await bot.chat(" ".join(sys.argv[1:]))
        print(f"\nAssistant: {answer}")
        await bot.close()
        return

    print("Local MCP Chatbot — type 'quit' or Ctrl-C to exit.\n")
    try:
        while True:
            try:
                query = input("You: ").strip()
            except EOFError:
                break
            if not query:
                continue
            if query.lower() in {"quit", "exit", "q"}:
                break
            answer = await bot.chat(query)
            print(f"\nAssistant: {answer}\n")
    finally:
        await bot.close()


if __name__ == "__main__":
    asyncio.run(run())
