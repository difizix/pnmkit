"""Voxel image processing helpers (Phase 3a — image3kit integration).

Provides:
- convert_voxel_image(src, dst, dtype, threshold=None)
- make_alpha_field(corners_mhd, alpha_mhd, threshold)
- find_image_file(stem, directory) / rewrite_mhd_header(path, ...): generic
  .mhd-header editing and by-stem image lookup, shared by porefoam1f_case.py
  and porefoam2f_case.py (no porefoam-solver-specific logic).

Maps onto image3kit's pybind11 bindings (VxlImgXX.hpp: read_from_header, write,
threshold101). Falls back to invoking standalone `voxelImageProcPy` exe via
FoamCase.run_app if image3kit is unavailable or bindings incomplete.
"""

import re
from pathlib import Path

from . import runtime as rt
from .foam_case import FoamCase


def find_image_file(
    stem: str,
    directory: Path | str,
    extensions: tuple[str, ...] = (".mhd", ".nhdr", ".tif", ".am", ".mhd.gz", ".nhdr.gz"),
) -> Path | None:
    """Find an image file for a given stem, checking extensions in order."""
    directory = Path(directory)
    for ext in extensions:
        candidate = directory / f"{stem}{ext}"
        if candidate.exists():
            return candidate
    return None


def rewrite_mhd_header(
    path: Path | str,
    *,
    unit: float | None = None,
    element_data_file: str | None = None,
    append_text: str | None = None,
) -> None:
    """Rewrite an .mhd header in place: substitute Unit=/ElementDataFile=, append text.

    Args:
        path: Path to the .mhd file to modify in place.
        unit: If given, replaces the `Unit = ...` line with this physical voxel size.
        element_data_file: If given, replaces the `ElementDataFile = ...` line.
        append_text: If given, appended verbatim to the end of the file.
    """
    path = Path(path)
    text = path.read_text()
    if unit is not None:
        text = re.sub(r"Unit = .*", f"Unit = {unit}", text)
    if element_data_file is not None:
        text = re.sub(
            r"^ElementDataFile\s*=\s*.*",
            f"ElementDataFile = {element_data_file}",
            text,
            flags=re.MULTILINE,
        )
    if append_text:
        text += append_text
    path.write_text(text)


def convert_voxel_image(
    src: str,
    dst: str,
    dtype: str | None = None,
    threshold: str | None = None,
    case: FoamCase | None = None,
) -> None:
    """Convert a voxel image from one format to another.

    Reproduces two common bash patterns:
    1. Plain dtype cast: `voxelImageProcPy src.mhd "" dst.mhd`
    2. Threshold-based conversion: used for initial saturation fields

    Args:
        src: Source image file (.mhd).
        dst: Destination image file (.mhd).
        dtype: Target data type (e.g. "UChar", "Float32"). If None, preserves original.
        threshold: Optional threshold specification (e.g. "120 2000").
        case: Optional FoamCase for fallback to external exe path.
    """
    # Try image3kit first.
    try:
        import image3kit as ik
        try:
            img = ik.read_from_header(src)
            if threshold is not None:
                parts = threshold.split()
                if len(parts) == 2:
                    lo, hi = float(parts[0]), float(parts[1])
                    img = img.threshold101(lo, hi)
            if dtype is not None:
                # image3kit should have a dtype conversion method; if not, fall back.
                if hasattr(img, "convert"):
                    img = img.convert(dtype)
                else:
                    msg = "image3kit missing convert()"
                    raise AttributeError(msg)
            img.write(dst)
            rt.disp(f"Converted {src} → {dst} (dtype={dtype}, threshold={threshold}) via image3kit")
            return
        except Exception as e:
            rt.disp(f"image3kit convert failed ({e}), falling back to voxelImageProcPy exe")
    except ImportError as e:
        rt.disp(f"⚠️ image3kit is not found, falling back to voxelImageProcPy")

    # Fallback: external voxelImageProcPy executable.
    cmd_args = [src, "-o", dst]
    if dtype is not None:
        cmd_args.append(dtype)
    if threshold is not None:
        # threshold is typically added as a line in the .mhd header before processing.
        # For the fallback exe, we modify the header inline.

        with open(src) as f:
            header_text = f.read()
        header_text += f"threshold {threshold}\n"
        with open(src, "w") as f:
            f.write(header_text)

    if case is not None:
        case.run_app("voxelImageProcPy", cmd_args)
    else:
        rt.run_sh(".", f"voxelImageProcPy {' '.join(cmd_args)}")


def make_alpha_field(
    corners_mhd: str,
    alpha_mhd: str,
    threshold: str = "120 2000",
    unit: float = 5e-6,
    case: FoamCase | None = None,
) -> None:
    """Create an alpha1 saturation field from a corners skeleton image.

    Reproduces the pattern from AllRunImageTwoPhase_spack:359-364:
    1. Replace Unit = ... in corners_mhd with physical scale.
    2. Append threshold line.
    3. Run voxelImageProcPy corners.mhd -o alpha1.mhd UChar.

    Args:
        corners_mhd: Source corners skeleton image (.mhd).
        alpha_mhd: Destination alpha field (.mhd).
        threshold: Threshold specification string.
        unit: Physical voxel size in meters.
        case: Optional FoamCase for fallback exe path.
    """
    rewrite_mhd_header(corners_mhd, unit=unit, append_text=f"threshold {threshold}\n")

    # Convert to alpha field (UChar).
    convert_voxel_image(corners_mhd, alpha_mhd, dtype="UChar", case=case)


def grow_alpha_field(
    alpha_mhd: str,
    n_grow: int,
    invert: bool = False,
    case: FoamCase | None = None,
) -> None:
    """Grow/shrink an alpha field using voxelAlphaFieldToFoam.

    Args:
        alpha_mhd: Alpha field image (.mhd).
        n_grow: Number of voxel layers to grow (positive) or shrink (negative).
        invert: If True, invert the alpha field.
        case: FoamCase for running the exe.
    """
    if case is None:
        msg = "FoamCase required for grow_alpha_field (uses voxelAlphaFieldToFoam exe)"
        raise ValueError(msg)

    args = [alpha_mhd, "-nGrowAlpha", str(n_grow)]
    if invert:
        args.append("-invertAlpha")
    case.run_app("voxelAlphaFieldToFoam", args)
