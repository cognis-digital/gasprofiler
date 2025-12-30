"""Smoke tests for GASPROFILER. No network. Runs against the bundled demo."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from gasprofiler import TOOL_NAME, TOOL_VERSION
from gasprofiler.core import (
    build_snapshot,
    compare_snapshots,
    profile_path,
    profile_source,
    snapshot_to_dict,
)
from gasprofiler.cli import main

REPO = Path(__file__).resolve().parents[1]
DEMO = REPO / "demos" / "01-basic" / "Airdrop.sol"


def test_metadata():
    assert TOOL_NAME == "gasprofiler"
    assert TOOL_VERSION.count(".") == 2


def test_demo_exists():
    assert DEMO.exists()


def test_profile_finds_functions():
    snap = profile_path(DEMO)
    names = {f.name for f in snap.functions}
    # public state-var getters are not functions; these are the declared ones
    assert {"setOwner", "seedFirstFive", "distribute", "clearAll"} <= names
    # constructor has no `function` keyword -> not parsed as a function
    assert "constructor" not in names


def test_unbounded_loops_detected():
    snap = profile_path(DEMO)
    by_name = {f.name: f for f in snap.functions}
    assert by_name["distribute"].unbounded_loops == 1
    assert by_name["clearAll"].unbounded_loops == 1
    # the fixed `i < 5` loop is bounded
    assert by_name["seedFirstFive"].loops == 1
    assert by_name["seedFirstFive"].unbounded_loops == 0
    # no-loop function
    assert by_name["setOwner"].loops == 0

    codes = {fd.code for fd in snap.findings}
    assert "UNBOUNDED_LOOP" in codes
    assert any(fd.severity == "error" for fd in snap.findings)


def test_unbounded_costs_more_than_bounded():
    snap = profile_path(DEMO)
    by_name = {f.name: f for f in snap.functions}
    # The unbounded distribute loop should be estimated as more expensive
    # than the cheap single-write setOwner.
    assert by_name["distribute"].estimated_gas > by_name["setOwner"].estimated_gas


def test_interface_declaration_is_skipped():
    src = "interface I { function foo() external returns (uint256); }"
    snap = profile_source(src)
    assert snap.functions == []


def test_comment_with_loop_is_ignored():
    src = (
        "contract C {\n"
        "  // for (uint i = 0; i < x.length; i++) {}\n"
        "  function f() external { uint a = 1; }\n"
        "}\n"
    )
    snap = profile_source(src)
    f = snap.functions[0]
    assert f.loops == 0
    assert f.unbounded_loops == 0


def test_regression_detection():
    base = profile_source(
        "contract C { function f() external { x = 1; } }"
    )
    # current version adds an unbounded loop -> more gas
    cur = profile_source(
        "contract C { function f() external { "
        "for (uint i = 0; i < arr.length; i++) { x = 1; } } }"
    )
    res = compare_snapshots(base, cur, tolerance=0.05)
    assert res.has_regressions
    assert any(r["function"] == "f" for r in res.regressions)
    assert res.regressions[0]["delta"] > 0


def test_no_regression_when_identical():
    src = "contract C { function f() external { x = 1; } }"
    res = compare_snapshots(profile_source(src), profile_source(src), tolerance=0.0)
    assert not res.has_regressions
    assert res.improvements == []


def test_improvement_detected():
    base = profile_source(
        "contract C { function f() external { "
        "for (uint i = 0; i < arr.length; i++) { x = 1; } } }"
    )
    cur = profile_source("contract C { function f() external { x = 1; } }")
    res = compare_snapshots(base, cur, tolerance=0.0)
    assert not res.has_regressions
    assert any(i["function"] == "f" for i in res.improvements)


def test_snapshot_roundtrip():
    snap = profile_path(DEMO)
    d = snapshot_to_dict(snap)
    s = json.dumps(d)
    back = json.loads(s)
    assert back["functions"]
    assert "findings" in back


def test_cli_profile_exit_code_on_findings():
    # Demo has unbounded loops -> exit 1
    rc = main(["profile", str(DEMO), "--format", "json"])
    assert rc == 1


def test_cli_profile_no_fail_flag():
    rc = main(["profile", str(DEMO), "--no-fail", "--format", "json"])
    assert rc == 0


def test_cli_check_no_regression(tmp_path):
    base = tmp_path / "base.json"
    main(["profile", str(DEMO), "--out", str(base), "--no-fail"])
    rc = main(["check", str(DEMO), "--baseline", str(base), "--tolerance", "0.05"])
    assert rc == 0


def test_cli_check_missing_baseline():
    rc = main(["check", str(DEMO), "--baseline", "does_not_exist.json"])
    assert rc == 2


def test_cli_no_match():
    rc = main(["profile", "nonexistent_dir/*.sol"])
    assert rc == 2


def test_module_entrypoint_runs():
    proc = subprocess.run(
        [sys.executable, "-m", "gasprofiler", "--version"],
        capture_output=True,
        text=True,
        cwd=str(REPO),
    )
    assert proc.returncode == 0
    assert "gasprofiler" in proc.stdout
