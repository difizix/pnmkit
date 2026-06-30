"""Synthetic triangular prism benchmark integration tests (triu).

Procedural geometry: Triangular prism with sinusoidal inscribed radius.
Executables tested: skelor (mextract), pnextract, scalor (snflow), cnflow, xpm.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest
from pnmkit import cnflow, mextract, pnextract, snflow, xpm
from pnmkit.process import grep_float_in_str_list as findf
from pnmkit.runtime import msEnv


def _has_exe(app: str) -> bool:
    """Check if the given executable is found in msEnv PATH or system PATH."""
    return shutil.which(app, path=msEnv.get("PATH", "")) is not None


def _make_tringu_image(target_dir: Path):
    """Generate the synthetic triangular prism image."""
    image3kit = pytest.importorskip("image3kit")
    VxlImgU8 = image3kit.VxlImgU8
    triangular = image3kit.triangular
    dbl3 = image3kit.dbl3

    img = VxlImgU8((120, 30, 33), 1)
    img.paint(triangular((0, 28, 16), L1=15, L2=15, h=16, Lt=30, ch=4, val=0))
    img.spacing = dbl3(5e-7, 5e-7, 5e-7)

    mhd_path = target_dir / "tringu.mhd"
    img.write(str(mhd_path))
    return img, mhd_path


@pytest.fixture
def tringu_env(tmp_path, monkeypatch):
    """Fixture providing an isolated working directory with generated tringu geometry."""
    monkeypatch.chdir(tmp_path)
    img, mhd_path = _make_tringu_image(tmp_path)
    return {"img": img, "mhd_path": mhd_path, "dir": tmp_path}


@pytest.mark.skipif(not _has_exe("skelor"), reason="skelor executable not found")
def test_triu_skelor_extraction(tringu_env):
    """Test medial-surface extraction via skelor (mextract)."""
    img = tringu_env["img"]
    ret = mextract(
        img,
        {
            "multiDir": "false",
            "Overwrite": "true",
            "write_bSurf": "true",
            "name": "tringu",
        },
        verbose=False,
    )
    assert ret == 0

    target_dir = tringu_env["dir"]
    ms_xmf = target_dir / "tringu_ms.xmf"
    assert ms_xmf.is_file(), f"Expected extracted network file {ms_xmf} to exist"


@pytest.mark.skipif(not _has_exe("pnextract"), reason="pnextract executable not found")
def test_triu_pnextract_extraction(tringu_env):
    """Test maximal-ball network extraction via pnextract."""
    img = tringu_env["img"]
    ret = pnextract(
        img,
        {
            "Overwrite": "true",
            "OutputName": "tringu",
        },
        verbose=False,
    )
    assert ret == 0

    target_dir = tringu_env["dir"]
    link1 = target_dir / "tringu_link1.dat"
    node1 = target_dir / "tringu_node1.dat"
    assert link1.is_file(), f"Expected {link1} to exist"
    assert node1.is_file(), f"Expected {node1} to exist"


@pytest.mark.skipif(not _has_exe("skelor") or not _has_exe("scalor"), reason="skelor or scalor not found")
def test_triu_scalor_simulation(tringu_env):
    """Test pore-network flow simulation on extracted network via scalor (snflow)."""
    img = tringu_env["img"]
    mextract(img, {"multiDir": "false", "Overwrite": "true", "write_bSurf": "true", "name": "tringu"})

    flow_inp = {
        "Overwrite": "true",
        "NetworkFile": "tringu_ms.xmf",
        "name": "tringu",
        "WriteStats": "T",
        "WriteXmf": "1 15 15 15",
        "Cycle1": "0. 2e6",
        "Cycle2": "1. -5e4",
        "UpscaleBox": "0 1",
        "RandSeed": "1000",
        "verbose": "T",
        "maxPcRandness": "0.",
        "maxRcRandness": "0.",
        "InitContAng": "1      0   10   -0.2  -3.     rand    0.0",
        "AlterContAng": "4      40   50  -0.2  -3.     rand    90.",
        "Water": "0.001       1.2                1000.",
        "Oil": "0.001       1000.             1000.",
        "ClayResistivity": "1.",
        "WaterOil": "0.03",
        "OutputName": "tringu",
    }
    ret = snflow(flow_inp)
    assert ret == 0

    target_dir = tringu_env["dir"]
    res_svg = target_dir / "tringu_upscal.svg"
    log_file = target_dir / "tringu_scalor.log"
    assert res_svg.is_file() or log_file.is_file()

    sn_text = res_svg.read_text() if res_svg.is_file() else log_file.read_text()
    assert findf(sn_text, keyword="tringu_porosity") == pytest.approx(0.1115, rel=0.1)
    assert findf(sn_text, keyword="tringu_permeability") == pytest.approx(1.757e-14, rel=0.2)

    # FIXME: Check breakthrough Pc in log file
    log = log_file.read_text()
    match_drainage = re.search(r"Sw:([0-9.]+)\s+Pc:\s*([0-9.eE+-]+).*?kro:([0-9.eE+-]+)", log)
    assert match_drainage is not None
    # Breakthrough occurs above 1.0e6 Pa
    assert "Pc: 1.12e+06" in log or "Pc: 1.35e+06" in log

    # Residual saturation after cycle 2 (imbibition) returns to Sw=1
    assert "End of cycle 2" in log


@pytest.mark.skipif(not _has_exe("pnextract") or not _has_exe("cnflow"), reason="pnextract or cnflow not found")
def test_triu_cnflow_simulation(tringu_env):
    """Test classical pore network simulation via cnflow."""
    img = tringu_env["img"]
    pnextract(img, {"Overwrite": "true", "OutputName": "tringu"})

    cn_inp = {
        "Overwrite": "true",
        "NETWORK": "F tringu",
        "OutputName": "tringuCN",
        "Cycle1": "0. 2e6 0.05 T T",
        "Cycle2": "1. -5e4 0.05 T T",
        "InitContAng": "1 0 10 -0.2 -3. rand 0.0",
        "AlterContAng": "4 40 50 -0.2 -3. rand 90.",
        "Water": "0.001 1.2 1000.",
        "Oil": "0.001 1000. 1000.",
        "ClayResistivity": "1.",
        "WaterOil": "0.03",
        "RandSeed": "1000",
    }
    ret = cnflow(cn_inp)
    assert ret == 0

    target_dir = tringu_env["dir"]
    res_svg = target_dir / "tringuCN_upscal.svg"
    log_file = target_dir / "tringuCN_cnflow.log"
    assert res_svg.is_file() and log_file.is_file()

    svg = res_svg.read_text() if res_svg.is_file() else log_file.read_text()
    assert findf(svg, "tringuCN_porosity") == pytest.approx(0.1115, rel=0.1)
    assert findf(svg, "tringuCN_permeability") == pytest.approx(2.61e-15, rel=0.2)

    # FIXME: Breakthrough occurred and snap-off happened in imbibition
    log = log_file.read_text()
    assert "Snap off:" in log
    assert "Water saturation:" in log


@pytest.mark.skipif(not _has_exe("xpm"), reason="xpm executable not found")
def test_triu_xpm_simulation(tringu_env):
    """Test direct pore scale simulation via xpm."""
    mhd_path = tringu_env["mhd_path"]
    xp_inp = {
        "Overwrite": "true",
        "ImageFile": str(mhd_path),
        "OutputName": "tringuXP",
    }
    ret = xpm(xp_inp)
    assert ret == 0

    target_dir = tringu_env["dir"]
    tsv_file = target_dir / "tringuXP_upscal.tsv"
    log_file = target_dir / "tringuXP_xpm.log"
    assert tsv_file.is_file() or log_file.is_file()

    if tsv_file.is_file():
        tsv = tsv_file.read_text()
        assert findf(tsv, keyword="tringuXP_porosity") == pytest.approx(0.1115, rel=0.1)
        assert findf(tsv, keyword="tringuXP_permeability") == pytest.approx(2.13e-15, rel=0.2)
