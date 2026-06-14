"""Core gas-profiling engine for GASPROFILER.

The engine performs a lightweight static analysis of Solidity source. It does
NOT compile or run the EVM (that would require external tooling); instead it
estimates a *relative* gas cost per function by counting gas-relevant
operations using EVM-derived constants, and it detects unbounded-loop patterns
that cause real-world gas blowups and out-of-gas reverts.

The estimates are deterministic, so they make an excellent baseline for
regression gating in CI: what matters for a PR gate is the *delta* between two
runs of the same analyzer, not absolute precision.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Iterable

TOOL_NAME = "gasprofiler"
TOOL_VERSION = "0.1.0"

# ---------------------------------------------------------------------------
# Gas cost model (EVM-derived approximate constants, post-Berlin-ish).
# These are intentionally coarse — used for relative scoring, not billing.
# ---------------------------------------------------------------------------
GAS = {
    "base": 21000 // 100,   # scaled function entry overhead
    "sstore_set": 20000,    # cold storage write (zero -> non-zero)
    "sstore_reset": 5000,   # storage write (non-zero -> non-zero)
    "sload": 2100,          # cold storage read
    "mstore": 3,
    "call": 2600,           # external call (cold account)
    "create": 32000,
    "log": 750,             # event emission base
    "keccak": 30,
    "arith": 3,
}

# A loop body is multiplied by this when we cannot prove a constant bound.
UNBOUNDED_LOOP_MULTIPLIER = 16

# Regex toolbox -------------------------------------------------------------
_COMMENT_BLOCK = re.compile(r"/\*.*?\*/", re.DOTALL)
_COMMENT_LINE = re.compile(r"//[^\n]*")
# function NAME ( ... ) <modifiers> { ... }  — capture name + signature start.
_FUNC_RE = re.compile(
    r"\bfunction\s+([A-Za-z_]\w*)\s*\(([^)]*)\)",
    re.DOTALL,
)
_FOR_WHILE_RE = re.compile(r"\b(for|while)\b\s*\(")
# .length used as a loop bound => iterates over a dynamic collection.
_LENGTH_BOUND_RE = re.compile(r"<\s*[A-Za-z_]\w*(?:\[[^\]]*\])?\.length\b")
_CONST_BOUND_RE = re.compile(r"<\s*(\d+)\b")


@dataclass
class Finding:
    """A flagged issue (e.g. an unbounded loop)."""
    function: str
    severity: str  # "warning" | "error"
    code: str
    message: str
    line: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class FunctionProfile:
    name: str
    signature: str
    estimated_gas: int
    loops: int
    unbounded_loops: int
    storage_writes: int
    storage_reads: int
    external_calls: int
    line: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Snapshot:
    source: str
    functions: list[FunctionProfile] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)

    def gas_map(self) -> dict[str, int]:
        return {f.name: f.estimated_gas for f in self.functions}


@dataclass
class RegressionResult:
    regressions: list[dict] = field(default_factory=list)
    improvements: list[dict] = field(default_factory=list)
    added: list[dict] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)

    @property
    def has_regressions(self) -> bool:
        return bool(self.regressions)

    def to_dict(self) -> dict:
        return {
            "regressions": self.regressions,
            "improvements": self.improvements,
            "added": self.added,
            "removed": self.removed,
            "has_regressions": self.has_regressions,
        }


# ---------------------------------------------------------------------------
# Source preparation
# ---------------------------------------------------------------------------
def _strip_comments(src: str) -> str:
    """Remove comments while preserving newline count for line numbers."""
    def _blank(m: re.Match) -> str:
        return "\n" * m.group(0).count("\n")

    src = _COMMENT_BLOCK.sub(_blank, src)
    src = _COMMENT_LINE.sub("", src)
    return src


def _extract_body(src: str, open_brace_idx: int) -> tuple[str, int]:
    """Return the balanced { ... } body starting at open_brace_idx and the
    index just past the closing brace."""
    depth = 0
    i = open_brace_idx
    n = len(src)
    while i < n:
        c = src[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return src[open_brace_idx + 1 : i], i + 1
        i += 1
    # Unbalanced — return the rest.
    return src[open_brace_idx + 1 :], n


def _line_of(src: str, idx: int) -> int:
    return src.count("\n", 0, idx) + 1


# ---------------------------------------------------------------------------
# Loop analysis
# ---------------------------------------------------------------------------
def _analyze_loops(body: str) -> tuple[int, int, list[tuple[int, str]]]:
    """Find loops in a function body.

    Returns (total_loops, unbounded_loops, [(offset_in_body, kind)]) where kind
    is 'unbounded' or 'bounded'.
    """
    loops = 0
    unbounded = 0
    detail: list[tuple[int, str]] = []
    for m in _FOR_WHILE_RE.finditer(body):
        loops += 1
        # Grab the loop header up to the matching ')'.
        start = m.end() - 1  # at '('
        depth = 0
        j = start
        while j < len(body):
            if body[j] == "(":
                depth += 1
            elif body[j] == ")":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        header = body[start : j + 1]
        kind = "bounded"
        if m.group(1) == "while":
            # while loops are bounded only if comparing to a constant.
            if not _CONST_BOUND_RE.search(header):
                kind = "unbounded"
        else:  # for
            if _LENGTH_BOUND_RE.search(header):
                kind = "unbounded"
            elif not _CONST_BOUND_RE.search(header):
                kind = "unbounded"
        if kind == "unbounded":
            unbounded += 1
        detail.append((m.start(), kind))
    return loops, unbounded, detail


def _count_ops(body: str) -> dict[str, int]:
    """Count gas-relevant operations in a body string."""
    counts = {
        "storage_writes": 0,
        "storage_reads": 0,
        "external_calls": 0,
        "events": 0,
        "keccak": 0,
    }
    # Storage writes: assignments to state-looking lvalues. Heuristic: an '='
    # not part of '==','!=','<=','>=','=>' on a non-memory identifier.
    for m in re.finditer(r"[^=!<>]=[^=]", body):
        counts["storage_writes"] += 1
    # mapping/array index reads + member reads (rough proxy for SLOAD).
    counts["storage_reads"] += len(re.findall(r"\w+\[[^\]]+\]", body))
    # external calls
    counts["external_calls"] += len(re.findall(r"\.(call|delegatecall|staticcall|transfer|send)\s*[\({]", body))
    counts["external_calls"] += len(re.findall(r"\b[A-Z]\w*\([^)]*\)\.", body))
    counts["events"] += len(re.findall(r"\bemit\s+\w+", body))
    counts["keccak"] += len(re.findall(r"\bkeccak256\s*\(", body))
    return counts


def _estimate_gas(body: str, loop_detail: list[tuple[int, str]], counts: dict) -> int:
    """Estimate relative gas for a function body.

    Strategy: compute a flat operation cost for the whole body, then add an
    extra cost for loop bodies (bounded loops weighted modestly, unbounded
    loops weighted heavily) to surface scaling risk.
    """
    flat = GAS["base"]
    flat += counts["storage_writes"] * GAS["sstore_reset"]
    flat += counts["storage_reads"] * GAS["sload"]
    flat += counts["external_calls"] * GAS["call"]
    flat += counts["events"] * GAS["log"]
    flat += counts["keccak"] * GAS["keccak"]
    # arithmetic / control flow proxy
    flat += len(re.findall(r"[+\-*/%]", body)) * GAS["arith"]

    loop_penalty = 0
    for _, kind in loop_detail:
        mult = UNBOUNDED_LOOP_MULTIPLIER if kind == "unbounded" else 4
        # The loop body roughly re-pays storage/call costs per iteration; we
        # approximate by re-charging a fraction of the flat storage cost.
        per_iter = GAS["sload"] + GAS["sstore_reset"]
        loop_penalty += per_iter * mult
    return flat + loop_penalty


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def profile_source(src: str, source_name: str = "<string>") -> Snapshot:
    """Analyze Solidity source text and return a Snapshot."""
    clean = _strip_comments(src)
    functions: list[FunctionProfile] = []
    findings: list[Finding] = []

    for fm in _FUNC_RE.finditer(clean):
        name = fm.group(1)
        params = " ".join(fm.group(2).split())
        signature = f"{name}({params})"
        # Find the body opening brace after the signature (skip modifiers).
        brace = clean.find("{", fm.end())
        semi = clean.find(";", fm.end())
        if brace == -1 or (semi != -1 and semi < brace):
            # Interface / abstract function declaration (no body) — skip.
            continue
        body, _ = _extract_body(clean, brace)
        func_line = _line_of(clean, fm.start())

        loops, unbounded, loop_detail = _analyze_loops(body)
        counts = _count_ops(body)
        gas = _estimate_gas(body, loop_detail, counts)

        functions.append(
            FunctionProfile(
                name=name,
                signature=signature,
                estimated_gas=gas,
                loops=loops,
                unbounded_loops=unbounded,
                storage_writes=counts["storage_writes"],
                storage_reads=counts["storage_reads"],
                external_calls=counts["external_calls"],
                line=func_line,
            )
        )

        for off, kind in loop_detail:
            if kind == "unbounded":
                findings.append(
                    Finding(
                        function=name,
                        severity="error",
                        code="UNBOUNDED_LOOP",
                        message=(
                            "Loop has no constant bound (iterates over dynamic "
                            "data); gas cost scales with input/state and may "
                            "hit the block gas limit / revert."
                        ),
                        line=func_line + body.count("\n", 0, off),
                    )
                )

    return Snapshot(source=source_name, functions=functions, findings=findings)


def profile_path(path: str | Path) -> Snapshot:
    """Profile a single .sol file path.

    Raises
    ------
    OSError
        If the file cannot be read.
    ValueError
        If the file is not valid UTF-8 text.
    """
    p = Path(path)
    try:
        src = p.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(
            f"{p}: file is not valid UTF-8 and cannot be parsed as Solidity"
        ) from exc
    return profile_source(src, source_name=str(p))


def build_snapshot(paths: Iterable[str | Path]) -> Snapshot:
    """Profile one or more .sol files, merged into a single snapshot.

    Function names are namespaced by file (file::function) to avoid collisions.
    """
    merged = Snapshot(source="<multi>")
    for path in paths:
        p = Path(path)
        snap = profile_path(p)
        prefix = p.name
        for fn in snap.functions:
            fn = FunctionProfile(**fn.to_dict())
            fn.name = f"{prefix}::{fn.name}"
            merged.functions.append(fn)
        for fd in snap.findings:
            fd = Finding(**fd.to_dict())
            fd.function = f"{prefix}::{fd.function}"
            merged.findings.append(fd)
    return merged


def snapshot_to_dict(snap: Snapshot) -> dict:
    return {
        "source": snap.source,
        "functions": [f.to_dict() for f in snap.functions],
        "findings": [f.to_dict() for f in snap.findings],
    }


def load_snapshot(path: str | Path) -> Snapshot:
    """Load a snapshot previously written as JSON.

    Raises
    ------
    ValueError
        If the file is not valid JSON or the top-level structure is not a dict.
    KeyError / TypeError
        Propagated with a descriptive prefix when a record is missing required
        fields or has fields of the wrong type.
    """
    raw = Path(path).read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"baseline is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(
            f"baseline JSON must be an object, got {type(data).__name__}"
        )
    snap = Snapshot(source=data.get("source", "<unknown>"))
    _FUNCTION_FIELDS = {
        "name", "signature", "estimated_gas", "loops",
        "unbounded_loops", "storage_writes", "storage_reads",
        "external_calls", "line",
    }
    _FINDING_FIELDS = {"function", "severity", "code", "message", "line"}
    for i, f in enumerate(data.get("functions", [])):
        if not isinstance(f, dict):
            raise ValueError(
                f"baseline functions[{i}] must be an object, "
                f"got {type(f).__name__}"
            )
        missing = _FUNCTION_FIELDS - f.keys()
        if missing:
            raise ValueError(
                f"baseline functions[{i}] is missing required fields: "
                + ", ".join(sorted(missing))
            )
        try:
            snap.functions.append(FunctionProfile(**f))
        except TypeError as exc:
            raise ValueError(
                f"baseline functions[{i}] has wrong field types: {exc}"
            ) from exc
    for i, f in enumerate(data.get("findings", [])):
        if not isinstance(f, dict):
            raise ValueError(
                f"baseline findings[{i}] must be an object, "
                f"got {type(f).__name__}"
            )
        missing = _FINDING_FIELDS - f.keys()
        if missing:
            raise ValueError(
                f"baseline findings[{i}] is missing required fields: "
                + ", ".join(sorted(missing))
            )
        try:
            snap.findings.append(Finding(**f))
        except TypeError as exc:
            raise ValueError(
                f"baseline findings[{i}] has wrong field types: {exc}"
            ) from exc
    return snap


def compare_snapshots(
    baseline: Snapshot, current: Snapshot, tolerance: float = 0.0
) -> RegressionResult:
    """Compare current against baseline. A function is a regression if its gas
    grew by more than `tolerance` (fractional, e.g. 0.05 = 5%).
    """
    res = RegressionResult()
    base = baseline.gas_map()
    cur = current.gas_map()

    for name, cur_gas in cur.items():
        if name not in base:
            res.added.append({"function": name, "gas": cur_gas})
            continue
        base_gas = base[name]
        delta = cur_gas - base_gas
        pct = (delta / base_gas) if base_gas else (1.0 if delta else 0.0)
        entry = {
            "function": name,
            "baseline": base_gas,
            "current": cur_gas,
            "delta": delta,
            "pct": round(pct, 4),
        }
        if pct > tolerance:
            res.regressions.append(entry)
        elif delta < 0:
            res.improvements.append(entry)

    for name in base:
        if name not in cur:
            res.removed.append(name)

    res.regressions.sort(key=lambda e: e["delta"], reverse=True)
    res.improvements.sort(key=lambda e: e["delta"])
    return res
