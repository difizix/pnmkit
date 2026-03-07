from __future__ import annotations

import os
from pathlib import Path

import pytest

import image3kit as ik
import pnmkit as nm


@pytest.mark.parametrize("img_name_ext", ["piskel.png", "TPak2D_240x200x1_5um.txt"])
def test_snflow_2d(tmp_path, monkeypatch, img_name_ext):
    # Setup paths
    test_dir = Path(__file__).resolve().parent
    data_dir = test_dir.parent / "data"

    # Logic to find the image file in any subdirectory of tests/data
    img_path = data_dir / img_name_ext
    if not img_path.exists():
        for p in data_dir.rglob(img_name_ext):
            if p.is_file():
                img_path = p
                break

    assert img_path.exists(), f"Reference image {img_name_ext} not found in {data_dir}"
    img_name = img_path.stem

    if tmp_path is None:
        tmp_path = test_dir / "run"
        tmp_path.mkdir(exist_ok=True)

    if monkeypatch is not None:
        monkeypatch.chdir(tmp_path)  # pytest results will be deleted after run
    else:
        os.chdir(tmp_path)

    # 1. Image processing with image3kit
    img = ik.VxlImgU8(img_path)
    img.plotSlice(
        filename=f"{img_name}_2d.png",
        normal_axis="z",
        min_val=0,
        max_val=2,
        color_map="RGB",
    )
    for _ in range(2):
        img.growLabel(0)
    img.voxelSize = (1e-6, 1e-6, 1e-6)
    img.distMapExtrude(offset=0.5, scale=2.0)
    img.plotSlice(
        filename=f"{img_name}3D_mid.png",
        normal_axis="z",
        min_val=0,
        max_val=2,
        color_map="RGB",
    )
    img.write(f"{img_name}3D.mhd")
    assert Path(f"{img_name}3D.mhd").exists()

    # 2. Network extraction with pnmkit
    extract_params = {"OutputName": f"{img_name}3D", "Overwrite": "T", "VoidRange": "0 0"}
    nm.mextract(img, extract_params)
    assert Path(f"{img_name}3D_ms.xmf").exists()  # network file

    # 3. Flow simulation with pnmkit
    base_params = {
        "WaterOil": "0.05",
        "Water": "0.001 1.2 1000.",
        "Oil": "0.001 1000 1000.",
        "UpscaleBox": "0.1 0.9",
        "Cycle1": "0. 1.0E+05 0.05 T T",
        "Cycle2": "1. -5.0E+04 0.05 T T",
        "Cycle3": "0. 1.0E+05 0.05 T T",
        "RandSeed:": "1001",
        "Overwrite": "T",
        "WriteXmf": "1 14 14 14",
        "NetworkFile": f"{img_name}3D_ms.xmf",
        "InitContAng:": "1   0   1   0.25 -1.0  rand  0.",
    }

    cases = [
        ("C30A60",   "3  30  60   0.25 -1.0  rand  0."),
        ("C60A90",   "3  60  90   0.25 -1.0  rand  0."),
        ("C120A150", "3 120 150   0.25 -1.0  rand  0."),
    ]

    for suffix, angle in cases:
        p = base_params.copy()
        name = f"{img_name}XmfNew_{suffix}"

        p["OutputName"] = name
        p["AlterContAng"] = angle
        nm.snflow(p)

        upscal_svg = (
            f"{name}_upscal.svg"  # output rel-perm / pc curve file with embeded data
        )
        assert Path(upscal_svg).exists()

        # ref_svg = ref_dir / upscal_svg # reference file
        # assert ref_svg.exists(), f"Reference file {ref_svg} not found"

        # print(f"Comparing {upscal_svg} with {ref_svg}")
        # nm.DictCompare(upscal_svg, str(ref_svg), 1, "_command") # TODO: copy data


if __name__ == "__main__":
    for img_ext in ["piskel.png", "TPak2D_240x200x1_5um.txt"]:
        print(f"\n--- Running for {img_ext} ---")
        test_snflow_2d(None, None, img_ext)
