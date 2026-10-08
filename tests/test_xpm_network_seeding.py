"""Tests for pore network seeding and regression staging operations in pnmkit."""

from __future__ import annotations

import struct
from pathlib import Path

import numpy as np
import pytest
from pnmkit import pnextract, xpm
from pnmkit.network_ops import (
    find_network_files,
    get_xpm_invasion_entry_pressures,
    read_xpm_invasion_entry_file,
    seed_net_to_xpm,
)
from pnmkit.process import which
from pnmkit.runtime import msEnv, MS_INST


def _has_exe(name: str) -> bool:
    ms_bin = str(Path(MS_INST) / "bin") if MS_INST else ""
    path_env = f"{ms_bin}:{msEnv.get('PATH', '')}" if ms_bin else msEnv.get("PATH", "")
    return which(name, path=path_env) is not None


@pytest.fixture
def dummy_network(tmp_path: Path):
    """Create a minimal set of valid dummy network files."""
    net_dir = tmp_path / "seed_net"
    net_dir.mkdir()

    (net_dir / "ref_link1.dat").write_text("1\n 1 1 2 0.04811 1e-5 1e-4 1e-4\n", encoding="utf-8")
    (net_dir / "ref_link2.dat").write_text("1\n 1 1 2 0.0 0.0 0.0 1.0 1.0 1.0\n", encoding="utf-8")
    (net_dir / "ref_node1.dat").write_text("2\n 1 0.0 0.0 0.0 1 1\n 2 1.0 0.0 0.0 1 1\n", encoding="utf-8")
    (net_dir / "ref_node2.dat").write_text(" 1 1e-5 0.04811 1e-12\n 2 1e-5 0.04811 1e-12\n", encoding="utf-8")

    return net_dir


def test_find_network_files_with_prefix(dummy_network: Path):
    source_dir, prefix, matched = find_network_files(dummy_network)
    assert source_dir == dummy_network.resolve()
    assert prefix == "ref"
    assert "_link1.dat" in matched
    assert "_node2.dat" in matched


def test_find_network_files_unprefixed(tmp_path: Path):
    net_dir = tmp_path / "unprefixed_net"
    net_dir.mkdir()
    (net_dir / "_link1.dat").write_text("1\n", encoding="utf-8")
    (net_dir / "_link2.dat").write_text("1\n", encoding="utf-8")
    (net_dir / "_node1.dat").write_text("2\n", encoding="utf-8")
    (net_dir / "_node2.dat").write_text("1\n", encoding="utf-8")

    _source_dir, prefix, matched = find_network_files(net_dir)
    assert prefix == ""
    assert len(matched) >= 4


def test_find_network_files_from_filepath(dummy_network: Path):
    link1_file = dummy_network / "ref_link1.dat"
    source_dir, prefix, matched = find_network_files(link1_file)
    assert source_dir == dummy_network.resolve()
    assert prefix == "ref"
    assert len(matched) >= 4


def test_seed_net_to_xpm_copy(dummy_network: Path, tmp_path: Path):
    target = tmp_path / "target_copy"
    seeded = seed_net_to_xpm(dummy_network, target_dir=target, target_prefix="custom_", mode="copy")

    assert "link1" in seeded
    assert seeded["link1"].is_file()
    assert seeded["link1"].name == "custom__link1.dat"
    assert (target / "custom__node2.dat").is_file()


def test_seed_net_to_xpm_link(dummy_network: Path, tmp_path: Path):
    target = tmp_path / "target_link"
    seed_net_to_xpm(dummy_network, target_dir=target, target_prefix="", mode="link")

    assert (target / "_link1.dat").is_file()
    # Check inode equivalence for hardlink
    assert (target / "_link1.dat").stat().st_ino == (dummy_network / "ref_link1.dat").stat().st_ino


def test_seed_net_to_xpm_velems_synthesis(dummy_network: Path, tmp_path: Path):
    target = tmp_path / "target_velems"
    img_size = (10, 20, 30)
    expected_bytes = (10 + 2) * (20 + 2) * (30 + 2) * 4  # 33792 bytes

    seeded = seed_net_to_xpm(
        dummy_network,
        target_dir=target,
        synthesize_velems=True,
        image_size=img_size,
    )

    assert "VElems" in seeded
    assert seeded["VElems"].is_file()
    assert seeded["VElems"].stat().st_size == expected_bytes


def test_pnextract_with_network_seed(dummy_network: Path, tmp_path: Path, monkeypatch):
    """Test that pnextract bypasses extraction when NetworkSeed is specified."""
    run_dir = tmp_path / "pnextract_seed_run"
    run_dir.mkdir()
    monkeypatch.chdir(run_dir)

    cfg = {
        "NetworkSeed": str(dummy_network),
        "OutputName": "seeded_out",
    }
    ret = pnextract(None, cfg)
    assert ret == 0
    assert (run_dir / "seeded_out_link1.dat").is_file()
    assert (run_dir / "seeded_out_node1.dat").is_file()


def test_read_invasion_entry_binary(tmp_path: Path):
    """Test reading synthetic binary invasion entry files."""
    test_bin = tmp_path / "invasion_entry_rc_primary.bin"
    count = 4
    hdr = struct.pack("<IIIIQ", 0x31455249, 1, 0, 0, count)
    radii = np.array([1e-5, 2e-5, 0.0, 5e-6], dtype=np.float32)
    with test_bin.open("wb") as f:
        f.write(hdr)
        radii.tofile(f)

    data = read_xpm_invasion_entry_file(test_bin)
    assert data["magic"] == 0x31455249
    assert data["version"] == 1
    assert data["cycle"] == 0
    assert data["element_count"] == 4
    assert np.allclose(data["r_cap"], radii)

    pressures = get_xpm_invasion_entry_pressures(test_bin, sigma=0.03, pore_count=2)
    assert pressures["pore_pc"][0] == pytest.approx(0.03 / 1e-5)
    assert pressures["pore_pc"][1] == pytest.approx(0.03 / 2e-5)
    assert pressures["throat_pc"][0] == 0.0  # uninvaded
    assert pressures["throat_pc"][1] == pytest.approx(0.03 / 5e-6)


@pytest.mark.skipif(not _has_exe("xpm") or not _has_exe("pnextract"), reason="xpm or pnextract not found")
def test_xpm_with_network_seed(tmp_path: Path, monkeypatch):
    """End-to-end regression test: verify XPM simulation runs with a pre-seeded network."""
    image3kit = pytest.importorskip("image3kit")
    VxlImgU8 = image3kit.VxlImgU8
    triangular = image3kit.triangular
    dbl3 = image3kit.dbl3

    # Step 1: Create seed network directory with pnextract
    seed_dir = tmp_path / "seed_run"
    seed_dir.mkdir()
    monkeypatch.chdir(seed_dir)

    img = VxlImgU8((120, 30, 33), 1)
    img.paint(triangular((0, 28, 16), L1=15, L2=15, h=16, Lt=30, ch=4, val=0))
    img.spacing = dbl3(5e-7, 5e-7, 5e-7)
    seed_mhd = seed_dir / "tringu.mhd"
    img.write(str(seed_mhd))

    pnextract(img, {"Overwrite": "true", "OutputName": "tringu"})
    assert (seed_dir / "tringu_link1.dat").is_file()

    # Step 2: In a separate clean directory, run XPM specifying NetworkSeed
    work_dir = tmp_path / "work_run"
    work_dir.mkdir()
    monkeypatch.chdir(work_dir)

    work_mhd = work_dir / "tringu.mhd"
    img.write(str(work_mhd))

    xp_inp = {
        "Overwrite": "true",
        "ImageFile": str(work_mhd),
        "NetworkSeed": str(seed_dir),
        "OutputName": "tringu_seeded_xp",
    }
    ret = xpm(xp_inp)
    assert ret == 0

    log_file = work_dir / "tringu_seeded_xp_xpm.log"
    tsv_file = work_dir / "tringu_seeded_xp_upscal.tsv"
    assert log_file.is_file() or tsv_file.is_file()

    # Verify log indicates using cached network seeded by pnmkit
    if log_file.is_file():
        log_content = log_file.read_text()
        assert "using cached network" in log_content

    # Step 3: Verify XPM generated binary invasion entry files and pnmkit parses them
    res_dir = work_dir / "results"
    pri_data = get_xpm_invasion_entry_pressures(res_dir, cycle="primary", sigma=0.03, pore_count=2)
    assert pri_data["element_count"] == 5
    assert (pri_data["pc"] > 0).all()

    sec_data = get_xpm_invasion_entry_pressures(res_dir, cycle="secondary", sigma=0.03, pore_count=2)
    assert sec_data["element_count"] == 5
    assert (sec_data["throat_pc"] > 0).any()
