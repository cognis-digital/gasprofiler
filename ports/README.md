# Ports of gasprofiler

The same scan logic, ported across languages so you can drop gasprofiler into any stack
or ship a single static binary. All ports share the rule IDs and JSON output shape.

| Language | Path | Run |
|---|---|---|
| Python (reference) | `../gasprofiler/` | `gasprofiler scan .` |
| JavaScript / Node | `javascript/` | `node ports/javascript/index.js .` |
| Go | `go/` | `cd ports/go && go run . ..` |
| Rust | `rust/` | `cd ports/rust && cargo run -- ..` |

Contributions of additional ports (Ruby, C#, Bun, Deno, WASM) are welcome — see ../CONTRIBUTING.md.
