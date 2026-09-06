"""Pytest integration tests for synthetic confined sphere layer benchmark (lyrd)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pnmkit import cnflow, mextract, pnextract, snflow, xpm
from pnmkit.runtime import grab_scalar as findf

_tests_dir = str(Path(__file__).parent.resolve())
if _tests_dir not in sys.path:
    sys.path.insert(0, _tests_dir)

from synthetic_lyrd import (
    _has_exe,
    _make_spheres_layer_image,
    run_lyrd_benchmark,
)


@pytest.fixture
def sphelyr_env(tmp_path, monkeypatch):
    """Fixture providing an isolated working directory with generated sphere layers."""
    monkeypatch.chdir(tmp_path)
    img, mhd_path = _make_spheres_layer_image(tmp_path)
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
    assert res_svg.is_file()
    assert log_file.is_file()

    svg = res_svg.read_text() if res_svg.is_file() else log_file.read_text()
    assert findf(svg, "sphelyrRuf_porosity") == pytest.approx(0.0863, rel=0.1)
    assert findf(svg, "sphelyrRuf_permeability") == pytest.approx(3.08e-13, rel=0.2)


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
    assert res_svg.is_file()
    assert log_file.is_file()

    svg = res_svg.read_text() if res_svg.is_file() else log_file.read_text()
    assert findf(svg, "sphelyrCN_porosity") == pytest.approx(0.0867, rel=0.1)
    assert findf(svg, "sphelyrCN_permeability") == pytest.approx(3.58e-13, rel=0.2)


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


@pytest.mark.skipif(
    not _has_exe("pnextract") or not _has_exe("cnflow") or not _has_exe("xpm"),
    reason="pnextract, cnflow, or xpm not found",
)
def test_lyrd_cnm_vs_xpm_benchmark(sphelyr_env):
    """Integration test: Verify CNM vs XPM match on seeded equilateral layered sphere network."""
    report = run_lyrd_benchmark(target_dir=sphelyr_env["dir"], sigma=1.0, contact_angles=(0.0, 30.0, 60.0), verbose=False)
    assert abs(report["diff_phi_pct"]) < 0.1, f"Porosity diff too large: {report['diff_phi_pct']}%"
    assert abs(report["diff_entry_mid_pct"]) < 0.1, f"Mid Entry Pc diff too large: {report['diff_entry_mid_pct']}%"

    xpm_stats = report.get("xpm_radii_stats")
    if xpm_stats:
        cnm_stats = report["radii_stats"]
        assert xpm_stats["num_pores"] == cnm_stats["num_pores"]
        assert xpm_stats["num_throats"] == cnm_stats["num_throats"]
        assert xpm_stats["pore_r_mean"] == pytest.approx(cnm_stats["pore_r_mean"], rel=1e-4)
        assert xpm_stats["throat_r_mean"] == pytest.approx(cnm_stats["throat_r_mean"], rel=1e-4)

    # Corner angle assertions
    cs = report.get("cn_corner_stats", {})
    if cs:
        assert cs["pore_half_ang_arith_deg"] == pytest.approx(30.0, abs=0.5)
        assert cs["throat_half_ang_arith_deg"] == pytest.approx(30.0, abs=0.5)

    # Multi contact angle assertions (Morrow model 1)
    ca_res = {r["theta"]: r for r in report["ca_results"]}
    assert ca_res[0.0]["mid_mech"] == "Snap-off"
    assert abs(ca_res[0.0]["diff_mid_pct"]) < 0.1, f"Snap-off at 0 deg diff: {ca_res[0.0]['diff_mid_pct']}%"
    assert ca_res[30.0]["mid_mech"] == "Snap-off"
    assert abs(ca_res[30.0]["diff_mid_pct"]) < 2.0, f"Snap-off at 30 deg diff: {ca_res[30.0]['diff_mid_pct']}%"
    assert ca_res[60.0]["mid_mech"] == "Cutoff (None)"
    assert ca_res[60.0]["mid_pc_xp"] < 1e-6 or ca_res[60.0]["mid_pc_cn"] < 3e4


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
