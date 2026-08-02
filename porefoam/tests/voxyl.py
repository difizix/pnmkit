#!/usr/bin/env python3
"""Synthetic voxel cylinder generator for porefoam two-phase test cases.

Replaces voxyl.mhd by creating an 18x24x24 voxel cylinder image using image3kit.
"""

from __future__ import annotations

from pathlib import Path

import image3kit as ik


def create_cylinder(output_file: str | Path | None = None) -> ik.VxlImgU8:
    """Create synthetic cylinder voxel image (18 x 24 x 24 voxels, 1 um spacing)."""
    img = ik.VxlImgU8((18, 24, 24))
    img.replace_range(0, 255, 1)
    img.spacing = ik.dbl3(2, 2, 2)
    img.paint(ik.cylinder((0, 12, 12), (18, 12, 12), 6, 0))
    img.spacing = ik.dbl3(1e-6, 1e-6, 1e-6)
    img.print_info()

    poro = img.porosity()
    assert 0.05 < poro < 0.5, f"Unexpected porosity {poro}"

    if output_file is not None:
        img.write(str(output_file))

    return img


if __name__ == "__main__":
    create_cylinder("voxyl.mhd")
