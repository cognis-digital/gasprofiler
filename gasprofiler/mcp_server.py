"""GASPROFILER MCP server — exposes scan() as an MCP tool for Cognis.Studio."""
from __future__ import annotations
from gasprofiler.core import scan, to_json

def serve() -> int:
    """Start an MCP stdio server. Requires the optional 'mcp' extra:
        pip install "cognis-gasprofiler[mcp]"
    """
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception:
        print("Install the MCP extra: pip install 'cognis-gasprofiler[mcp]'")
        return 1
    app = FastMCP("gasprofiler")

    @app.tool()
    def gasprofiler_scan(target: str) -> str:
        """Per-opcode and per-function gas profiler that flags unbounded loops, DoS-prone patterns, and regressions against a committed baseline.. Returns JSON findings."""
        return to_json(scan(target))

    app.run()
    return 0
