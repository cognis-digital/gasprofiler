# GASPROFILER — Architecture

> Per-opcode and per-function gas profiler that flags unbounded loops, DoS-prone patterns, and regressions against a committed baseline.

```
input ──▶ collect ──▶ rules/analyzers ──▶ score ──▶ findings ──▶ table · json
                              │                          │
                         (this repo)                 MCP tool (agents)
```

- **collect** normalizes the target (file/dir/API) into records.
- **rules/analyzers** apply the heuristics shipped in `gasprofiler/core.py`.
- **score** ranks by severity.
- **MCP server** (`gasprofiler mcp`) exposes `scan` for Cognis.Studio agents.

Extend by adding a rule + a test + a `demos/NN-*/SCENARIO.md`. See [CONTRIBUTING.md](../CONTRIBUTING.md).
