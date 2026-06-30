"""Tests for pnmkit.process (result-file parsing + solver orchestration)."""

from unittest.mock import patch

import pytest
from pnmkit.process import (
    grep_fixed_list_in_file,
    grep_float_in_str_list,
    grep_sub_keys_in_str,
    nil_fn,
    read_file,
    run_ske,
    run_xnflow,
    set_pnm_keyword_vals,
)


def test_nil_fn_returns_zero():
    assert nil_fn(1, 2, foo="bar") == 0


def test_grep_float_in_str_list():
    assert grep_float_in_str_list("Gavg: 1.0 2.0 3.0\n", keyword="Gavg", skipLines=1) == pytest.approx(2.0)


def test_grep_fixed_list_in_file(tmp_path):
    f = tmp_path / "vxlImage.mhd"
    f.write_text("DimSize = 100.0 200.0 300.0\n")
    vals = grep_fixed_list_in_file(3, str(f), "DimSize")
    assert vals == pytest.approx([100.0, 200.0, 300.0])


def test_grep_sub_keys_in_str():
    lines = "cycle 1\neP4:0.1\neP4:0.2\n;\n"
    vals = grep_sub_keys_in_str(lines, keyword="cycle 1", midkey="eP4:", endKy=";")
    assert vals == pytest.approx([0.1, 0.2])


def test_read_file_roundtrip(tmp_path):
    f = tmp_path / "xxx.dbg"
    f.write_text("hello\n")
    assert read_file(str(f)) == "hello\n"


def test_read_file_missing_returns_empty():
    assert read_file("/nonexistent/path.dbg") == ""


def test_set_pnm_keyword_vals_writes_new_keyword(tmp_path):
    case_inp = tmp_path / "case.inp"
    set_pnm_keyword_vals(kwrds={"Foo": "1.0"}, caseInp=str(case_inp), lines="")
    content = case_inp.read_text()
    assert "Foo" in content
    assert "1.0" in content


@patch("pnmkit.process.which", return_value="/usr/bin/skelor")
@patch("pnmkit.process.subprocess.Popen")
def test_run_ske_skips_when_log_exists(mock_popen, _mock_which, tmp_path):
    res_dir = tmp_path / "SKE"
    res_dir.mkdir()
    (res_dir / "img.log").write_text("done\n")
    ret = run_ske(kwrds={}, bNam="img", resDir=str(res_dir), netDir=str(tmp_path), forceRun=False)
    assert ret == 0
    mock_popen.assert_not_called()


@patch("pnmkit.process.which", return_value="/usr/bin/scalor")
@patch("pnmkit.process.subprocess.Popen")
def test_run_xnflow_skips_when_log_exists(mock_popen, _mock_which, tmp_path):
    res_dir = tmp_path / "resultsSNM"
    res_dir.mkdir()
    (res_dir / "net_scalor.log").write_text("done\n")
    ret = run_xnflow(kwrds={"NetworkFile": "net.xmf", "OutputName": "net"}, netnam="net", resDir=str(res_dir), netDir=str(tmp_path), forceRun=False)
    assert ret == 0
    mock_popen.assert_not_called()
