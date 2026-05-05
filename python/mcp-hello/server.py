"""
Hello World MCP Server — FastMCP demo with tools and a resource.

Supports two transports:
  stdio  (default) — used by Claude Desktop and the CLI client
  http             — used by the web chatbot and Docker Compose
"""

import argparse
import os
import sys
from datetime import datetime

import pytz
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "hello-world-mcp",
    instructions=(
        "A hello-world MCP server that demonstrates tools and resources. "
        "Use it to greet people, get the current time, do math, reverse text, "
        "or count words."
    ),
)


# ── Tools ────────────────────────────────────────────────────────────────────

@mcp.tool()
def greet(name: str, style: str = "friendly") -> str:
    """Greet someone by name with a chosen style.

    Args:
        name: The person's name.
        style: One of "friendly" (default), "formal", or "pirate".
    """
    styles = {
        "friendly": f"Hey {name}! Great to meet you! 👋",
        "formal": f"Good day, {name}. It is a pleasure to make your acquaintance.",
        "pirate": f"Ahoy, {name}! Welcome aboard, ye landlubber! ☠️",
    }
    return styles.get(style, styles["friendly"])


@mcp.tool()
def get_time(timezone: str = "UTC") -> str:
    """Get the current date and time in a given timezone.

    Args:
        timezone: IANA timezone name, e.g. "UTC", "US/Pacific", "Europe/Paris".
    """
    try:
        tz = pytz.timezone(timezone)
        now = datetime.now(tz)
        return f"Current time in {timezone}: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}"
    except pytz.UnknownTimeZoneError:
        return (
            f"Unknown timezone '{timezone}'. "
            "Try 'UTC', 'US/Pacific', 'Europe/London', 'Asia/Tokyo', etc."
        )


@mcp.tool()
def add(a: float, b: float) -> str:
    """Add two numbers.

    Args:
        a: First number.
        b: Second number.
    """
    return f"{a} + {b} = {a + b}"


@mcp.tool()
def reverse(text: str) -> str:
    """Reverse a string.

    Args:
        text: The text to reverse.
    """
    return text[::-1]


@mcp.tool()
def word_stats(text: str) -> str:
    """Count words and characters in a piece of text.

    Args:
        text: The text to analyse.
    """
    words = len(text.split())
    chars = len(text)
    no_spaces = len(text.replace(" ", ""))
    return (
        f"Words: {words} | Characters: {chars} | "
        f"Characters (no spaces): {no_spaces}"
    )


# ── Resource ─────────────────────────────────────────────────────────────────

@mcp.resource("mcp://hello/welcome")
def welcome() -> str:
    """A static welcome message exposed as an MCP resource."""
    return (
        "Welcome to the Hello World MCP Server!\n"
        "Available tools: greet, get_time, add, reverse, word_stats.\n"
        "Ask me to greet you, tell you the time in Tokyo, add numbers, etc."
    )


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Hello World MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
        help="Transport layer: 'stdio' (default, for Claude Desktop / CLI) "
             "or 'http' (for the web chatbot / Docker).",
    )
    parser.add_argument(
        "--host",
        default=os.getenv("MCP_HOST", "0.0.0.0"),
        help="Host for HTTP transport (default: 0.0.0.0).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("MCP_PORT", "8000")),
        help="Port for HTTP transport (default: 8000).",
    )
    args = parser.parse_args()

    if args.transport == "http":
        print(
            f"[MCP] Starting HTTP server at http://{args.host}:{args.port}/mcp",
            file=sys.stderr,
        )
        # FastMCP reads FASTMCP_HOST / FASTMCP_PORT env-vars automatically;
        # set them from our CLI args so callers don't have to duplicate them.
        os.environ.setdefault("FASTMCP_HOST", args.host)
        os.environ.setdefault("FASTMCP_PORT", str(args.port))
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
