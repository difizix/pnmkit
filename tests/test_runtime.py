"""Tests for pnmkit.runtime (subprocess/env plumbing + float-grep helpers)."""

import math

import pytest
from pnmkit.runtime import (
    alert,
    dbg_msg,
    ensure,
    file_float_differs_from,
    grep_float_in_file,
    grep_float_in_str,
    run_sh,
)


def test_grep_float_in_str_finds_value():
    assert grep_float_in_str("effPorosity=0.35\nK_x=1.2e-13\n", "K_x=") == pytest.approx(1.2e-13)


def test_grep_float_in_str_missing_keyword_returns_nan():
    assert math.isnan(grep_float_in_str("nothing here", "K_x="))


def test_grep_float_in_file(tmp_path):
    f = tmp_path / "summary.txt"
    f.write_text("Kx=42.5\n")
    assert grep_float_in_file(str(f), "Kx=") == pytest.approx(42.5)


def test_file_float_differs_from(tmp_path):
    f = tmp_path / "summary.txt"
    f.write_text("Kx=100.0\n")
    assert file_float_differs_from(str(f), "Kx=", 100.0) == 0
    assert file_float_differs_from(str(f), "Kx=", 50.0) == 1


def test_run_sh_success(tmp_path):
    run_sh(str(tmp_path), "echo hello", logfile=None)


def test_run_sh_failure_raises(tmp_path):
    with pytest.raises(RuntimeError):
        run_sh(str(tmp_path), "false", logfile=None)


def test_dbg_msg_with_notrace_returns_minus_one():
    assert dbg_msg("test message", nTrace=0) == -1


def test_ensure_passes_when_ok():
    ensure(True, "should not raise")


def test_alert_raises_with_err():
    with pytest.raises(Exception, match="boom"):
        alert("boom", err=ValueError("cause"))
