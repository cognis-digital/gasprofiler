"""Tests for hardening additions: bad input, edge cases, and error paths."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from gasprofiler.core import (
    TOOL_NAME,
    TOOL_VERSION,
    load_snapshot,
    profile_path,
    profile_source,
    compare_snapshots,
    snapshot_to_dict,
)
from gasprofiler.cli import main

REPO = Path(__file__).resolve().parents[1]
DEMO = REPO / "demos" / "01-basic" / "Airdrop.sol"


# ---------------------------------------------------------------------------
# core.py: TOOL_NAME / TOOL_VERSION constants are present
# ---------------------------------------------------------------------------

def test_tool_name_and_version_in_core():
    assert TOOL_NAME == "gasprofiler"
    assert isinstance(TOOL_VERSION, str)
    assert TOOL_VERSION.count(".") >= 1


# ---------------------------------------------------------------------------
# core.py: load_snapshot — malformed / invalid JSON
# ---------------------------------------------------------------------------

def test_load_snapshot_invalid_json(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{ not valid json }", encoding="utf-8")
    with pytest.raises(ValueError, match="not valid JSON"):
        load_snapshot(bad)


def test_load_snapshot_json_not_object(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(ValueError, match="must be an object"):
        load_snapshot(bad)


def test_load_snapshot_function_missing_fields(tmp_path):
    snap = tmp_path / "snap.json"
    # Write a snapshot with a function entry that is missing required fields.
    data = {
        "source": "<test>",
        "functions": [{"name": "foo"}],  # missing all other required fields
        "findings": [],
    }
    snap.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="missing required fields"):
        load_snapshot(snap)


def test_load_snapshot_roundtrip_valid(tmp_path):
    """A valid snapshot written by snapshot_to_dict should round-trip cleanly."""
    snap = profile_source(
        "contract C { function f() external { uint x = 1; } }"
    )
    d = snapshot_to_dict(snap)
    out = tmp_path / "snap.json"
    out.write_text(json.dumps(d), encoding="utf-8")
    loaded = load_snapshot(out)
    assert len(loaded.functions) == len(snap.functions)
    assert loaded.functions[0].name == snap.functions[0].name


# ---------------------------------------------------------------------------
# core.py: profile_path — binary / non-UTF-8 file
# ---------------------------------------------------------------------------

def test_profile_path_binary_file(tmp_path):
    bad = tmp_path / "binary.sol"
    bad.write_bytes(bytes(range(256)))
    with pytest.raises(ValueError, match="not valid UTF-8"):
        profile_path(bad)


# ---------------------------------------------------------------------------
# core.py: edge cases — empty source, zero functions, zero-division in compare
# ---------------------------------------------------------------------------

def test_profile_source_empty_string():
    snap = profile_source("")
    assert snap.functions == []
    assert snap.findings == []


def test_compare_snapshots_base_gas_zero():
    """compare_snapshots must not raise ZeroDivisionError when baseline gas is 0."""
    base = profile_source(
        "contract C { function f() external { } }"
    )
    cur = profile_source(
        "contract C { function f() external { uint x = 1; } }"
    )
    # Force baseline gas to 0 directly to exercise the guard.
    base.functions[0].estimated_gas = 0
    res = compare_snapshots(base, cur, tolerance=0.0)
    # Should not raise; the function will be treated as a regression.
    assert isinstance(res.has_regressions, bool)


def test_compare_snapshots_empty_baseline():
    src = "contract C { function f() external { uint x = 1; } }"
    base = profile_source("")  # no functions
    cur = profile_source(src)
    res = compare_snapshots(base, cur, tolerance=0.0)
    assert not res.has_regressions
    assert any(a["function"] == "f" for a in res.added)


# ---------------------------------------------------------------------------
# cli.py: --tolerance validation
# ---------------------------------------------------------------------------

def test_cli_check_negative_tolerance(tmp_path):
    base = tmp_path / "base.json"
    main(["profile", str(DEMO), "--out", str(base), "--no-fail"])
    rc = main([
        "check", str(DEMO),
        "--baseline", str(base),
        "--tolerance", "-0.1",
    ])
    assert rc == 2


# ---------------------------------------------------------------------------
# cli.py: malformed baseline JSON triggers exit 2
# ---------------------------------------------------------------------------

def test_cli_check_malformed_baseline(tmp_path):
    bad = tmp_path / "bad_baseline.json"
    bad.write_text("not json at all", encoding="utf-8")
    rc = main([
        "check", str(DEMO),
        "--baseline", str(bad),
    ])
    assert rc == 2


# ---------------------------------------------------------------------------
# cli.py: --out to a non-existent directory exits 2
# ---------------------------------------------------------------------------

def test_cli_profile_out_missing_dir(tmp_path):
    rc = main([
        "profile", str(DEMO),
        "--out", str(tmp_path / "nonexistent_subdir" / "snap.json"),
    ])
    assert rc == 2
