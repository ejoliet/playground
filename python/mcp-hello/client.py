"""
CLI chatbot — connects to the MCP server via stdio (spawns it as a subprocess).
Uses the Anthropic API so Claude can call the MCP tools automatically.

Usage:
    python client.py          # interactive chat loop
    python client.py "Hello"  # single query
"""

import asyncio
import sys
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Optional

from anthropic import Anthropic
from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

load_dotenv()

SERVER_SCRIPT = Path(__file__).parent / "server.py"
MODEL = "claude-sonnet-4-6"


class MCPChatbot:
    def __init__(self) -> None:
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self.anthropic = Anthropic()

    # ── Connection ────────────────────────────────────────────────────────────

    async def connect(self) -> None:
        """Launch server.py as a subprocess and open an MCP session over stdio."""
        server_params = StdioServerParameters(
            command=sys.executable,          # same python that runs this file
            args=[str(SERVER_SCRIPT)],       # --transport stdio is the default
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
        print(f"[MCP] Connected to server. Tools available: {names}\n")

    # ── Chat ──────────────────────────────────────────────────────────────────

    async def chat(self, user_message: str) -> str:
        """Send a message to Claude; let it call MCP tools as needed."""
        assert self.session, "Not connected — call connect() first."

        # Build tool schemas from the live MCP server
        tools = (await self.session.list_tools()).tools
        tool_schemas = [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.inputSchema,
            }
            for t in tools
        ]

        messages = [{"role": "user", "content": user_message}]

        # Agentic loop: keep going until Claude stops requesting tools
        while True:
            response = self.anthropic.messages.create(
                model=MODEL,
                max_tokens=1024,
                tools=tool_schemas,
                messages=messages,
            )

            # Collect text blocks from this turn
            text_parts = [
                block.text
                for block in response.content
                if block.type == "text"
            ]

            if response.stop_reason != "tool_use":
                return "\n".join(text_parts)

            # Execute every tool_use block via the MCP server
            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                result = await self.session.call_tool(block.name, block.input)
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
                print(f"  [tool] {block.name}({block.input}) → {result_text}")

            # Extend conversation with assistant turn + tool results
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

    # ── Cleanup ───────────────────────────────────────────────────────────────

    async def close(self) -> None:
        await self.exit_stack.aclose()


# ── Main ──────────────────────────────────────────────────────────────────────

async def run() -> None:
    bot = MCPChatbot()
    await bot.connect()

    # Single-query mode
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        answer = await bot.chat(query)
        print(f"\nAssistant: {answer}")
        await bot.close()
        return

    # Interactive loop
    print("MCP Chatbot — type 'quit' or Ctrl-C to exit.\n")
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
