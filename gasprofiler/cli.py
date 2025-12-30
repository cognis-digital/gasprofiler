"""Command-line interface for GASPROFILER.

Examples
--------
  # Profile a contract and print a per-function gas table
  gasprofiler profile contracts/Token.sol

  # Save a baseline snapshot for CI
  gasprofiler profile contracts/*.sol --out .gas-baseline.json

  # Fail a PR if any function regressed >5% vs the baseline
  gasprofiler check contracts/*.sol --baseline .gas-baseline.json --tolerance 0.05

  # JSON for piping into other tooling
  gasprofiler profile contracts/Token.sol --format json | jq .

Exit codes
----------
  0  success, no findings / no regressions
  1  unbounded-loop findings (profile) or gas regressions (check)
  2  usage / IO error
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

from gasprofiler import TOOL_NAME, TOOL_VERSION
from gasprofiler.core import (
    build_snapshot,
    compare_snapshots,
    load_snapshot,
    snapshot_to_dict,
)


def _expand(patterns: list[str]) -> list[str]:
    files: list[str] = []
    for pat in patterns:
        matched = glob.glob(pat, recursive=True)
        if matched:
            files.extend(sorted(matched))
        elif Path(pat).exists():
            files.append(pat)
    # de-dup preserving order
    seen: set[str] = set()
    out: list[str] = []
    for f in files:
        if f not in seen and f.endswith(".sol"):
            seen.add(f)
            out.append(f)
    return out


def _print_table(snap_dict: dict) -> None:
    funcs = sorted(snap_dict["functions"], key=lambda f: f["estimated_gas"], reverse=True)
    if not funcs:
        print("No functions found.")
        return
    name_w = max(len(f["name"]) for f in funcs)
    name_w = max(name_w, 8)
    print(f"{'FUNCTION':<{name_w}}  {'GAS~':>10}  {'LOOPS':>5}  {'UNBND':>5}  {'SW':>3}  {'SR':>3}  {'CALL':>4}")
    print("-" * (name_w + 42))
    for f in funcs:
        flag = "  <-- UNBOUNDED" if f["unbounded_loops"] else ""
        print(
            f"{f['name']:<{name_w}}  {f['estimated_gas']:>10}  {f['loops']:>5}  "
            f"{f['unbounded_loops']:>5}  {f['storage_writes']:>3}  "
            f"{f['storage_reads']:>3}  {f['external_calls']:>4}{flag}"
        )
    if snap_dict["findings"]:
        print()
        print(f"{len(snap_dict['findings'])} finding(s):")
        for fnd in snap_dict["findings"]:
            print(f"  [{fnd['severity'].upper()}] {fnd['code']} {fnd['function']} (line {fnd['line']}): {fnd['message']}")


def _print_regressions(res: dict) -> None:
    if res["regressions"]:
        print("GAS REGRESSIONS:")
        for r in res["regressions"]:
            print(
                f"  {r['function']}: {r['baseline']} -> {r['current']} "
                f"(+{r['delta']}, +{r['pct'] * 100:.2f}%)"
            )
    if res["improvements"]:
        print("Improvements:")
        for r in res["improvements"]:
            print(
                f"  {r['function']}: {r['baseline']} -> {r['current']} "
                f"({r['delta']}, {r['pct'] * 100:.2f}%)"
            )
    if res["added"]:
        print("New functions:")
        for a in res["added"]:
            print(f"  {a['function']}: {a['gas']}")
    if res["removed"]:
        print("Removed functions: " + ", ".join(res["removed"]))
    if not res["has_regressions"]:
        print("OK: no gas regressions.")


def _cmd_profile(args) -> int:
    files = _expand(args.paths)
    if not files:
        print("error: no .sol files matched", file=sys.stderr)
        return 2
    snap = build_snapshot(files)
    d = snapshot_to_dict(snap)

    if args.out:
        Path(args.out).write_text(json.dumps(d, indent=2), encoding="utf-8")
        if args.format != "json":
            print(f"Wrote snapshot to {args.out} ({len(d['functions'])} functions).")

    if args.format == "json":
        print(json.dumps(d, indent=2))
    elif not args.out:
        _print_table(d)

    # Exit non-zero on unbounded-loop findings so it can gate PRs by itself.
    if not args.no_fail and any(f["severity"] == "error" for f in d["findings"]):
        return 1
    return 0


def _cmd_check(args) -> int:
    files = _expand(args.paths)
    if not files:
        print("error: no .sol files matched", file=sys.stderr)
        return 2
    if not Path(args.baseline).exists():
        print(f"error: baseline not found: {args.baseline}", file=sys.stderr)
        return 2
    baseline = load_snapshot(args.baseline)
    current = build_snapshot(files)
    res = compare_snapshots(baseline, current, tolerance=args.tolerance)
    d = res.to_dict()

    if args.format == "json":
        print(json.dumps(d, indent=2))
    else:
        _print_regressions(d)

    return 1 if res.has_regressions else 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=TOOL_NAME,
        description="Per-function Solidity gas profiler: flags unbounded loops "
        "and gas regressions vs a baseline (forge-snapshot style).",
        epilog=(
            "examples:\n"
            "  gasprofiler profile contracts/Token.sol\n"
            "  gasprofiler profile 'contracts/**/*.sol' --out .gas-baseline.json\n"
            "  gasprofiler check 'contracts/**/*.sol' --baseline .gas-baseline.json --tolerance 0.05\n"
            "  gasprofiler profile contracts/Token.sol --format json | jq .\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--version", action="version", version=f"{TOOL_NAME} {TOOL_VERSION}")
    p.add_argument(
        "--format",
        choices=["table", "json"],
        default="table",
        help="output format (default: table)",
    )
    sub = p.add_subparsers(dest="command", required=True)

    pp = sub.add_parser(
        "profile",
        help="profile contracts and print/save a per-function gas snapshot",
    )
    pp.add_argument("paths", nargs="+", help=".sol files or globs")
    pp.add_argument("--out", help="write snapshot JSON to this path (baseline)")
    pp.add_argument(
        "--no-fail",
        action="store_true",
        help="do not exit non-zero on unbounded-loop findings",
    )
    pp.set_defaults(func=_cmd_profile)

    pc = sub.add_parser(
        "check",
        help="compare contracts against a baseline; exit 1 on regression",
    )
    pc.add_argument("paths", nargs="+", help=".sol files or globs")
    pc.add_argument("--baseline", required=True, help="baseline snapshot JSON")
    pc.add_argument(
        "--tolerance",
        type=float,
        default=0.0,
        help="allowed fractional gas growth before failing (e.g. 0.05 = 5%%)",
    )
    pc.set_defaults(func=_cmd_check)

    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except OSError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
