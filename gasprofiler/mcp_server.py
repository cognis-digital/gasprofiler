"""GASPROFILER MCP server — exposes profile() as an MCP tool for Cognis.Studio."""
from __future__ import annotations

import json
from gasprofiler.core import profile_path, snapshot_to_dict


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
        """Gas profiler: flags unbounded loops, DoS patterns, and regressions.

        Returns JSON findings for the given Solidity file path.
        """
        if not target or not target.strip():
            return json.dumps({"error": "target path must not be empty"})
        try:
            snap = profile_path(target)
        except (OSError, ValueError) as exc:
            return json.dumps({"error": str(exc)})
        return json.dumps(snapshot_to_dict(snap), indent=2)

    app.run()
    return 0
