# GASPROFILER — Per-opcode and per-function gas profiler that flags unbounded loops, DoS-prone patterns, and regressions against a committed baseline.

> Part of the **[Cognis Neural Suite](https://github.com/cognis-digital)** by [Cognis Digital](https://cognis.digital)
> Cognis Open Collaboration License (COCL) v1.0 · domain: `web3`

[![PyPI](https://img.shields.io/pypi/v/cognis-gasprofiler.svg)](https://pypi.org/project/cognis-gasprofiler/)
[![CI](https://github.com/cognis-digital/gasprofiler/actions/workflows/ci.yml/badge.svg)](https://github.com/cognis-digital/gasprofiler/actions)
[![License: COCL 1.0](https://img.shields.io/badge/License-COCL%201.0-2b6cb0.svg)](LICENSE)
[![Suite](https://img.shields.io/badge/Cognis-Neural%20Suite-6b46c1.svg)](https://github.com/cognis-digital)

**Per-opcode and per-function gas profiler that flags unbounded loops, DoS-prone patterns, and regressions against a committed baseline..**

*Web3 & Smart-Contract Security — on-chain safety and analytics.*

## Why

GASPROFILER exists for one job — per-opcode and per-function gas profiler that flags unbounded loops, dos-prone patterns, and regressions against a committed baseline. — and does it without a SaaS bill or heavyweight setup.
Single-purpose, scriptable, CI-friendly, self-hostable, and callable by AI agents over MCP.

## Install

```bash
pip install cognis-gasprofiler
# or from this repo:
pip install -e ".[dev]"
```

## Quick start

```bash
gasprofiler --version
gasprofiler scan .                      # scan the current project
gasprofiler scan . --format json
gasprofiler scan . --fail-on high       # non-zero exit for CI gates
gasprofiler mcp                         # expose as an MCP server (Cognis.Studio / Claude Desktop / Cursor)
```

## Built-in demo scenarios

- [`demos/01-basic/`](demos/01-basic/SCENARIO.md)
- [`demos/02-clean/`](demos/02-clean/SCENARIO.md)
- [`demos/03-mixed/`](demos/03-mixed/SCENARIO.md)

## Inspiration / prior art

Built in the spirit of **Foundry gas snapshots / hardhat-gas-reporter**, re-framed for the Cognis approach: single-purpose, self-hostable,
MCP-native, and unified with the rest of the Suite. Missing a credit? Open a PR.

## How it fits the Cognis Neural Suite

`gasprofiler` is one of the **100+ tools** in the [Cognis Neural Suite](https://github.com/cognis-digital).
Every tool ships an MCP server, so [Cognis.Studio](https://cognis.studio) agents can call them as scoped capabilities.

- Design notes: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- Roadmap: [`ROADMAP.md`](ROADMAP.md)

## Contributing

PRs, new rules, and demo scenarios welcome under the collaboration-pull model — see
[CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md).

## License

Source-available under the **Cognis Open Collaboration License (COCL) v1.0** — free for personal,
internal-evaluation, research, and educational use; **commercial / production use requires a license**
(licensing@cognis.digital). See [LICENSE](LICENSE).

## About

**[Cognis Digital](https://cognis.digital)** — Wyoming, USA · *Making Tomorrow Better Today.*
