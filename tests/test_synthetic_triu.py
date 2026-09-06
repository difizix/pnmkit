"""Pytest integration tests for synthetic triangular prism benchmark (triu)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from pnmkit import cnflow, mextract, pnextract, snflow, xpm
from pnmkit.network_ops import set_network_equilateral
from pnmkit.runtime import grab_scalar as findf

_tests_dir = str(Path(__file__).parent.resolve())
if _tests_dir not in sys.path:
    sys.path.insert(0, _tests_dir)

from synthetic_triu import (
    _has_exe,
    _make_tringu_image,
    run_triu_benchmark,
)


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
    assert findf(sn_text, keyword="tringu_porosity") == pytest.approx(0.147, rel=0.1)
    assert findf(sn_text, keyword="tringu_permeability") == pytest.approx(1.85e-14, rel=0.2)


@pytest.mark.skipif(not _has_exe("pnextract") or not _has_exe("cnflow"), reason="pnextract or cnflow not found")
def test_triu_cnflow_simulation(tringu_env):
    """Test classical pore network simulation via cnflow."""
    img = tringu_env["img"]
    pnextract(img, {"Overwrite": "true", "OutputName": "tringu"})
    set_network_equilateral("tringu")

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
        "extra_env": {"CNM_DEBUG_PC": "1"},
    }
    ret = cnflow(cn_inp)
    assert ret == 0

    target_dir = tringu_env["dir"]
    res_svg = target_dir / "tringuCN_upscal.svg"
    log_file = target_dir / "tringuCN_cnflow.log"
    assert res_svg.is_file()
    assert log_file.is_file()

    svg = res_svg.read_text() if res_svg.is_file() else log_file.read_text()
    assert findf(svg, "tringuCN_porosity") == pytest.approx(0.147, rel=0.1)
    assert findf(svg, "tringuCN_permeability") == pytest.approx(4.49e-15, rel=0.2)

    log = log_file.read_text()
    assert "Snap off:" in log
    assert "[CNM_DEBUG_PC]" in log


@pytest.mark.skipif(not _has_exe("xpm"), reason="xpm executable not found")
def test_triu_xpm_simulation(tringu_env):
    """Test direct pore scale simulation via xpm."""
    mhd_path = tringu_env["mhd_path"]
    xp_inp = {
        "Overwrite": "true",
        "ImageFile": str(mhd_path),
        "OutputName": "tringuXP",
        "extra_env": {"XPM_WRITE_NET_STATS": "1"},
    }
    ret = xpm(xp_inp)
    assert ret == 0

    target_dir = tringu_env["dir"]
    tsv_file = target_dir / "tringuXP_upscal.tsv"
    log_file = target_dir / "tringuXP_xpm.log"
    assert tsv_file.is_file() or log_file.is_file()

    if tsv_file.is_file():
        tsv = tsv_file.read_text()
        assert findf(tsv, keyword="tringuXP_porosity") == pytest.approx(0.147, rel=0.1)
        assert findf(tsv, keyword="tringuXP_permeability") == pytest.approx(3.71e-15, rel=0.2)

    stats_candidates = list(target_dir.glob("**/network_stats.json"))
    assert len(stats_candidates) > 0, "Expected network_stats.json to be written when XPM_WRITE_NET_STATS is set"
    stats = json.loads(stats_candidates[0].read_text())
    assert stats["num_pores"] == 2
    assert stats["num_throats"] == 3


@pytest.mark.skipif(
    not _has_exe("pnextract") or not _has_exe("cnflow") or not _has_exe("xpm"),
    reason="pnextract, cnflow, or xpm not found",
)
def test_triu_cnm_vs_xpm_benchmark(tringu_env):
    """Integration test: Verify 1:1 match between CNM and XPM on seeded equilateral network."""
    report = run_triu_benchmark(target_dir=tringu_env["dir"], sigma=1.0, contact_angles=(0.0, 30.0, 60.0), verbose=False)
    assert abs(report["diff_phi_pct"]) < 0.2, f"Porosity diff too large: {report['diff_phi_pct']}%"
    assert abs(report["diff_k_pct"]) < 25.0, f"Permeability diff too large: {report['diff_k_pct']}%"
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
