"""Tests for pnmkit.runtime (subprocess/env plumbing + float-grep helpers)."""

import math

import pytest
from pnmkit.runtime import (
    alert,
    dbg_msg,
    ensure,
    grab_scalar,
    read_deviates,
    read_scalar,
    run_sh,
)


def test_grab_scalar_finds_value():
    assert grab_scalar("effPorosity=0.35\nK_x=1.2e-13\n", "K_x=") == pytest.approx(1.2e-13)


def test_grab_scalar_missing_keyword_returns_nan():
    assert math.isnan(grab_scalar("nothing here", "K_x="))


def test_read_scalar(tmp_path):
    f = tmp_path / "summary.txt"
    f.write_text("Kx=42.5\n")
    assert read_scalar(str(f), "Kx=") == pytest.approx(42.5)


def test_read_deviates(tmp_path):
    f = tmp_path / "summary.txt"
    f.write_text("Kx=100.0\n")
    assert read_deviates(str(f), "Kx=", 100.0) == 0
    assert read_deviates(str(f), "Kx=", 50.0) == 1


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
