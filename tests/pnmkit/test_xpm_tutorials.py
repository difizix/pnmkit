
from __future__ import annotations

import os
import shutil
import subprocess
from contextlib import chdir
from pathlib import Path

import pytest

import pnmkit as nm
from pnmkit.msmodels import FlowSim, VoxImg, mSN, sSN
from pnmkit.xpm_utils import xpm_json_to_mhd

# config_paths = sorted(Path("xpm/files/tutorials").glob("tutorial*/config*.json"), reverse=True)
config_paths = sorted(Path("xpm/files/tutorials").glob("tutorial1/config*.json"), reverse=True)


# @pytest.mark.skip(reason="Skipping long-running XPM tutorial test")
@pytest.mark.integration
@pytest.mark.parametrize("config_path", config_paths, ids=lambda p: p.name)
def test_xpmtutorials_xpm(tmp_path, monkeypatch, config_path):

    rel_config = config_path.relative_to("xpm/files/tutorials")

    config_path = Path(config_path).absolute()
    config_path = config_path.resolve()

    # copy to run directory
    src_images = Path("xpm/files/images").absolute()
    src_tutorials = Path("xpm/files/tutorials").absolute()

    if monkeypatch is not None:  # monkeypatch is used by pytest, os.chdir is used by fab/local runs
        monkeypatch.chdir(tmp_path)
    else:
        os.chdir(tmp_path)

    run_xpmtut = Path("XPM") # tutorial run directory
    run_images = Path("images")

    run_xpmtut.mkdir(parents=True, exist_ok=True)
    run_images.mkdir(parents=True, exist_ok=True)
    Path("XPM/pnextract").mkdir(exist_ok=True)

    shutil.copytree(src_tutorials, run_xpmtut, dirs_exist_ok=True)
    shutil.copytree(src_images, run_images, dirs_exist_ok=True)

    xpm_json_to_mhd(config_path, run_images)

    print(f"  Processing {rel_config} in {run_xpmtut}...")
    env = os.environ.copy()
    # the executables are generated using `make dev`, `make all` puts them in the .venv/bin directory:
    env["PATH"] = str(Path("build/install/bin").absolute()) + ":" + env.get("PATH", "")
    env["LD_LIBRARY_PATH"] = str(Path("build/install/lib").absolute()) + ":" + env.get("LD_LIBRARY_PATH", "")
    env["HWLOC_COMPONENTS"] = "-gl"

    subprocess.run(["xpm", "-G", str(rel_config)], cwd=run_xpmtut, env=env, check=True)


@pytest.mark.integration
@pytest.mark.parametrize("config_path", config_paths, ids=lambda p: p.name)
def test_xpmtutorials_snm(tmp_path, monkeypatch, config_path):

    config_path = Path(config_path).absolute()
    config_path = config_path.resolve()

    if monkeypatch is not None:  # monkeypatch is used by pytest, os.chdir is used by fab/local runs
        monkeypatch.chdir(tmp_path)
    else:
        os.chdir(tmp_path)

    ske_dir = Path("SKE")
    snf_dir = Path("SNF")
    ske_dir.mkdir(parents=True, exist_ok=True)
    snf_dir.mkdir(parents=True, exist_ok=True)
    mhd_path = xpm_json_to_mhd(config_path, ske_dir)
    with chdir(ske_dir):
        img_name = mhd_path.stem
        extract_params = {"OutputName": img_name, "Overwrite": "T", "VoidRange": "0 0"}
        name_mhd = Path(mhd_path).name
        nm.mextract(name_mhd, extract_params)
        assert Path(f"{img_name}_ms.xmf").exists(), "Network extraction failed"

    with chdir(snf_dir):
        # FIXME these depend on `mtd`
        img = VoxImg(img_name)

        CA = [30, 50]
        Swi = 0.
        tag = f"C{CA[0]}A{CA[1]}Swi{Swi}"
        inpt = {
            "UpscaleBox": "0.2 0.9",
            "Cycle1":       f"{Swi} 1.0E+05 0.05 T T",
            "Cycle2":        "1. -1.0E+05 0.05 T T",
            "Cycle3":        "0. 1.0E+05 0.05 T T",
            "Cycle1_BC":     "T F F T DP 1. 1.",
            "Cycle2_BC":     "T F F T DP 1. 1.",
            "Cycle3_BC":     "T F F T DP 1. 1.",
            "InitContAng":   "1   0    10   -0.2 -3.  rand 0.",
            "AlterContAng": f"4  {CA[0]} {CA[1]}  -0.2 -3.  rand 0.",
            "Overwrite":     "T"
        }
        sim = FlowSim(tag, f"Swi={Swi}, CA={CA[0]}-{CA[1]}", img, mSN, sSN, inpt.copy())
        sim.resSuffix = tag


        ret = sim.runSim("TestThread", forceRun=True) # runXNFlow or runXPM
        assert ret == 0, f"Simulation failed for {sim.tag}" # ideally the runSim shall throw an exception instead for debugging


if __name__ == "__main__":
    exc = None
    Path("run/xnmtutorials").mkdir(parents=True, exist_ok=True)

    for config_path in config_paths: # SNM
        test_xpmtutorials_snm("run/xnmtutorials", None, config_path)

    for config_path in config_paths: # XPM
        try:
            test_xpmtutorials_xpm("run", None, config_path)
        except Exception as e:
            print(f"Error occurred: {e}")
            print(f"Temporary directory kept for debugging: {config_path}")
            exc = e
    if exc is not None:
        raise exc
