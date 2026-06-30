"""Synthetic sphere layer benchmark integration tests (lyrd).

Procedural geometry: 2 layers of spheres confined by planes with random surface noise.
Executables tested: skelor (mextract), pnextract, scalor (snflow), cnflow, xpm.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from pnmkit import cnflow, mextract, pnextract, snflow, xpm
from pnmkit.process import grep_float_in_str_list as findf
from pnmkit.runtime import msEnv


def _has_exe(app: str) -> bool:
    """Check if the given executable is found in msEnv PATH or system PATH."""
    return shutil.which(app, path=msEnv.get("PATH", "")) is not None


def _make_layered_image(target_dir: Path):
    """Generate the synthetic confined sphere layer image."""
    image3kit = pytest.importorskip("image3kit")
    VxlImgU8 = image3kit.VxlImgU8
    sphere = image3kit.sphere
    cube = image3kit.cube
    dbl3 = image3kit.dbl3
    int3 = image3kit.int3

    img = VxlImgU8((160, 92, 80), 0)
    img.spacing = dbl3(0.5, 0.5, 0.5)
    img.paint(sphere((3, 6, 0), 23, 1))
    img.paint(sphere((3, 6, 40), 23, 1))
    img.paint(sphere((40, 6, 0), 23, 1))
    img.paint(sphere((40, 6, 40), 23, 1))
    img.paint(sphere((77, 6, 0), 23, 1))
    img.paint(sphere((77, 6, 40), 23, 1))
    img.paint(sphere((3, -6, 0), 30, 1))
    img.paint(sphere((3, -6, 40), 30, 1))
    img.paint(sphere((40, -6, 0), 30, 1))
    img.paint(sphere((40, -6, 40), 30, 1))
    img.paint(sphere((77, -6, 0), 30, 1))
    img.paint(sphere((77, -6, 40), 30, 1))
    img.paint(cube((0, 0, 0), (80, 6, 40), 1))
    img.paint(cube((0, 25, 0), (80, 21, 40), 2))
    img.spacing = dbl3(1e-6, 1e-6, 1e-6)
    img.crop(int3(20, 0, 0), int3(140, 92, 80))
    img.add_surf_noise(1 << 2, 1 << 2, 12, 12)
    img.grow_box(2)
    img.mode6(1)
    img.mode6(1)
    img.shrink_box(2)
    img.grow_box(2)
    for _ in range(10):
        img.mode6(2)
    img.shrink_box(2)

    mhd_path = target_dir / "sphelyrRuf.mhd"
    img.write(str(mhd_path))
    return img, mhd_path


@pytest.fixture
def sphelyr_env(tmp_path, monkeypatch):
    """Fixture providing an isolated working directory with generated sphere layers."""
    monkeypatch.chdir(tmp_path)
    img, mhd_path = _make_layered_image(tmp_path)
    return {"img": img, "mhd_path": mhd_path, "dir": tmp_path}


@pytest.mark.skipif(not _has_exe("skelor"), reason="skelor executable not found")
def test_lyrd_skelor_extraction(sphelyr_env):
    """Test medial-surface extraction on layered spheres via skelor (mextract)."""
    img = sphelyr_env["img"]
    ret = mextract(
        img,
        {
            "multiDir": "true",
            "Overwrite": "true",
            "write_bSurf": "true",
            "OutputName": "sphelyr",
        },
        verbose=False,
    )
    assert ret == 0

    target_dir = sphelyr_env["dir"]
    ms_xmf = target_dir / "sphelyr_ms.xmf"
    assert ms_xmf.is_file(), f"Expected {ms_xmf} to exist"


@pytest.mark.skipif(not _has_exe("pnextract"), reason="pnextract executable not found")
def test_lyrd_pnextract_extraction(sphelyr_env):
    """Test maximal-ball extraction on layered spheres via pnextract."""
    img = sphelyr_env["img"]
    ret = pnextract(
        img,
        {
            "Overwrite": "true",
            "OutputName": "sphelyr",
        },
        verbose=False,
    )
    assert ret == 0

    target_dir = sphelyr_env["dir"]
    link1 = target_dir / "sphelyr_link1.dat"
    node1 = target_dir / "sphelyr_node1.dat"
    assert link1.is_file(), f"Expected {link1} to exist"
    assert node1.is_file(), f"Expected {node1} to exist"


@pytest.mark.skipif(not _has_exe("skelor") or not _has_exe("scalor"), reason="skelor or scalor not found")
def test_lyrd_scalor_simulation(sphelyr_env):
    """Test scalor two-phase displacement simulation on extracted sphere network."""
    img = sphelyr_env["img"]
    mextract(img, {"multiDir": "true", "Overwrite": "true", "write_bSurf": "true", "OutputName": "sphelyr"})

    base_inp = {
        "WaterOil": "0.05",
        "Water": "0.001 1.2 1000.",
        "Oil": "0.001 1000 1000.",
        "Cycle1": "0. 5.0E+05 0.05 T T",
        "Cycle2": "1. -5.0E+04 0.05 T T",
        "Cycle3": "0. 1.0E+05 0.05 T T",
        "InitContAng": "1 0 1 0.25 -1.0 rand 0.",
        "RandSeed": "1001",
        "Overwrite": "true",
        "WriteStats": "T",
        "verbose": "T",
        "WriteXmf": "1 15 15 15",
        "maxPcRandness": "0.",
        "maxRcRandness": "0.",
        "KEY": "VAL 0.5",
        "UpscaleBox": "0 1",
    }

    inp_ruf = dict(base_inp)
    inp_ruf["NetworkFile"] = "sphelyr_ms.xmf"
    inp_ruf["OutputName"] = "sphelyrRuf"
    inp_ruf["oldAlg"] = "false"
    ret = snflow(inp_ruf)
    assert ret == 0

    target_dir = sphelyr_env["dir"]
    res_svg = target_dir / "sphelyrRuf_upscal.svg"
    log_file = target_dir / "sphelyrRuf_scalor.log"
    assert res_svg.is_file() and log_file.is_file()

    svg = res_svg.read_text() if res_svg.is_file() else log_file.read_text()
    assert findf(svg, "sphelyrRuf_porosity") == pytest.approx(0.0863, rel=0.1)
    assert findf(svg, "sphelyrRuf_permeability") == pytest.approx(3.08e-13, rel=0.2)

    log = log_file.read_text()
    assert "Pc: 1.62e+05" in log
    assert "End of cycle 2" in log


@pytest.mark.skipif(not _has_exe("pnextract") or not _has_exe("cnflow"), reason="pnextract or cnflow not found")
def test_lyrd_cnflow_simulation(sphelyr_env):
    """Test cnflow simulation on extracted layered spheres."""
    img = sphelyr_env["img"]
    pnextract(img, {"Overwrite": "true", "OutputName": "sphelyr"})

    inp_cn = {
        "Overwrite": "true",
        "NETWORK": "F sphelyr",
        "OutputName": "sphelyrCN",
        "WaterOil": "0.05",
        "Water": "0.001 1.2 1000.",
        "Oil": "0.001 1000 1000.",
        "Cycle1": "0. 1.0E+05 0.05 T T",
        "Cycle2": "1. -5.0E+04 0.05 T T",
        "InitContAng": "1 0 1 0.25 -1.0 rand 0.",
        "RandSeed": "1001",
    }
    ret = cnflow(inp_cn)
    assert ret == 0

    target_dir = sphelyr_env["dir"]
    res_svg = target_dir / "sphelyrCN_upscal.svg"
    log_file = target_dir / "sphelyrCN_cnflow.log"
    assert res_svg.is_file() and log_file.is_file()

    svg = res_svg.read_text() if res_svg.is_file() else log_file.read_text()
    assert findf(svg, "sphelyrCN_porosity") == pytest.approx(0.0867, rel=0.1)
    assert findf(svg, "sphelyrCN_permeability") == pytest.approx(3.58e-13, rel=0.2)

    log = log_file.read_text()
    assert "Drainage" in log
    assert "Imbibition" in log


@pytest.mark.skipif(not _has_exe("xpm"), reason="xpm executable not found")
def test_lyrd_xpm_simulation(sphelyr_env):
    """Test direct xpm simulation on layered spheres."""
    mhd_path = sphelyr_env["mhd_path"]
    inp_xp = {
        "Overwrite": "true",
        "ImageFile": str(mhd_path),
        "OutputName": "sphelyrXP",
    }
    ret = xpm(inp_xp)
    assert ret == 0

    target_dir = sphelyr_env["dir"]
    tsv_file = target_dir / "sphelyrXP_upscal.tsv"
    log_file = target_dir / "sphelyrXP_xpm.log"
    assert tsv_file.is_file() or log_file.is_file()

    if tsv_file.is_file():
        tsv = tsv_file.read_text()
        assert findf(tsv, "sphelyrXP_porosity") == pytest.approx(0.0867, rel=0.1)
        assert findf(tsv, "sphelyrXP_permeability") == pytest.approx(2.76e-13, rel=0.2)
