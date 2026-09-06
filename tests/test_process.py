"""Tests for pnmkit.process (result-file parsing + solver orchestration)."""

from unittest.mock import patch

import pytest
from pnmkit.process import (
    grab_array,
    grab_list,
    grab_scalar_sub,
    nil_fn,
    read_array,
    read_file,
    read_list,
    run_ske,
    run_xnflow,
    write_pnm_input,
)


def test_nil_fn_returns_zero():
    assert nil_fn(1, 2, foo="bar") == 0


def test_grab_array():
    assert grab_array(3, "Gavg: 1.0 2.0 3.0\n", keyword="Gavg") == pytest.approx([1.0, 2.0, 3.0])
    assert grab_array(2, "Gavg: 1.0 2.0 3.0\n", keyword="Gavg", skip=1) == pytest.approx([2.0, 3.0])
    assert grab_array(4, "Gavg: 1.0 2.0\n", keyword="Gavg") == pytest.approx([1.0, 2.0, 0.0, 0.0])


def test_read_array(tmp_path):
    f = tmp_path / "vxlImage.mhd"
    f.write_text("DimSize = 100.0 200.0 300.0\n")
    vals = read_array(3, str(f), "DimSize")
    assert vals == pytest.approx([100.0, 200.0, 300.0])


def test_grab_list():
    assert grab_list("Values: 1.5 2.5 3.5 4.5 ;\n", keyword="Values", endKy=";") == pytest.approx([1.5, 2.5, 3.5, 4.5])
    assert grab_list("Values: 1.5 2.5 3.5 4.5 ;\n", keyword="Values", endKy=";", skip=2) == pytest.approx([3.5, 4.5])
    assert grab_list("1.0 2.0 3.0") == pytest.approx([1.0, 2.0, 3.0])
    assert grab_list("") == []


def test_read_list(tmp_path):
    f = tmp_path / "list_data.txt"
    f.write_text("MyList: 10.0 20.0 30.0 ;\n")
    assert read_list(f, keyword="MyList", endKy=";") == pytest.approx([10.0, 20.0, 30.0])


def test_grab_scalar_sub():
    lines = "cycle 1\neP4:0.1\neP4:0.2\n;\n"
    vals = grab_scalar_sub(lines, keyword="cycle 1", midkey="eP4:", endKy=";")
    assert vals == pytest.approx([0.1, 0.2])


def test_read_file_roundtrip(tmp_path):
    f = tmp_path / "xxx.dbg"
    f.write_text("hello\n")
    assert read_file(str(f)) == "hello\n"


def test_read_file_missing_returns_empty():
    assert read_file("/nonexistent/path.dbg") == ""


def test_write_pnm_input_writes_new_keyword(tmp_path):
    case_inp = tmp_path / "case.inp"
    write_pnm_input(kwrds={"Foo": "1.0"}, caseInp=str(case_inp), lines="")
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
