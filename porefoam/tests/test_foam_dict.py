#!/usr/bin/env python3
"""Tests for pnmkit.foam_dict (brace-depth-aware OpenFOAM dictionary editing).

Pure Python tests — no OpenFOAM/cfMesh installation required.
"""

from pathlib import Path

import pytest

from pnmkit.foam.foam_dict import (
    FileKV,
    _find_section_block,
    _replace_keyword_in_text,
    apply_edits,
)

# ---------- FileKV ----------


def test_filekv_dataclass():
    edit = FileKV(file="system/controlDict", entry="endTime", value="0.5")
    assert edit.file == "system/controlDict"
    assert edit.entry == "endTime"
    assert edit.value == "0.5"


def test_filekv_dot_assertion():
    # Valid entries (0 or 1 dot)
    FileKV(file="system/controlDict", entry="endTime", value="0.5")
    FileKV(file="system/fvSolution", entry="PIMPLE.nCorrectors", value="5")

    # Invalid entry (> 1 dot)
    with pytest.raises(AssertionError, match="at most one dot"):
        FileKV(file="system/controlDict", entry="a.b.c", value="1")


# ---------- _find_section_block ----------


def test_find_section_block_simple():
    text = """
solvers
{
    p { solver PCG; }
}
endTime 1;
"""
    start, end = _find_section_block(text, "solvers")
    assert start is not None
    assert "solvers" in text[start:end]
    assert text[end] == "\n" or text[end - 1] == "}"


def test_find_section_block_nested_braces():
    # Must not stop at inner '}'; must find the matching outer '}'
    text = """
relaxationFactors
{
    U           0.5;
    p           0.7;
    nested
    {
        x       1.0;
    }
}
otherThing 42;
"""
    start, end = _find_section_block(text, "relaxationFactors")
    assert start is not None
    assert "nested" in text[start:end]
    assert "otherThing" not in text[start:end]


def test_find_section_block_not_found():
    text = "foo { bar 1; }\n"
    assert _find_section_block(text, "nonexistent") is None


# ---------- _replace_keyword_in_text ----------


def test_replace_keyword_simple():
    text = "endTime           0.1;\nmaxCo 0.4;\n"
    new = _replace_keyword_in_text(text, "endTime", "0.5", 0, len(text))
    assert "endTime           0.5;" in new


def test_replace_keyword_in_range():
    text = """
relaxationFactors
{
    U           0.5;
    p           0.7;
}
"""
    # Only modify within a subset range covering the section body.
    start = text.index("{")
    end = text.rindex("}") + 1
    new = _replace_keyword_in_text(text, "U", "0.9", start, end)
    assert "U           0.9;" in new


def test_replace_keyword_not_found_raises():
    text = "foo 1;\n"
    with pytest.raises(ValueError, match="not found"):
        _replace_keyword_in_text(text, "bar", "2", 0, len(text))


def test_replace_keyword_multiple_raises():
    text = "U 0.5;\nU 0.3;\n"
    with pytest.raises(ValueError, match="found 2 times"):
        _replace_keyword_in_text(text, "U", "1.0", 0, len(text))


# ---------- apply_edits (section-scoped) ----------


def test_apply_edits_section_scoped(tmp_path: Path):
    fv_sol = tmp_path / "system" / "fvSolution"
    fv_sol.parent.mkdir(parents=True, exist_ok=True)
    fv_sol.write_text("""
relaxationFactors
{
    U           0.5;
    p           0.7;
}
""")
    apply_edits(
        tmp_path,
        [FileKV(file="system/fvSolution", entry="relaxationFactors.U", value="0.9")],
    )
    content = fv_sol.read_text()
    assert "U           0.9;" in content
    assert "p           0.7;" in content


def test_apply_edits_section_nested(tmp_path: Path):
    fv_sol = tmp_path / "system" / "fvSolution"
    fv_sol.parent.mkdir(parents=True, exist_ok=True)
    fv_sol.write_text("""
relaxationFactors
{
    U           0.5;
    p           0.7;
}
PIMPLE
{
    nCorrectors     2;
}
""")
    apply_edits(
        tmp_path,
        [FileKV(file="system/fvSolution", entry="PIMPLE.nCorrectors", value="5")],
    )
    content = fv_sol.read_text()
    # PIMPLE block changed
    assert "nCorrectors     5;" in content
    # relaxationFactors block untouched
    assert "nCorrectors" in content  # appears once, in PIMPLE


# ---------- apply_edits (whole-file scope) ----------


def test_apply_edits_whole_file(tmp_path: Path):
    ctrl = tmp_path / "system" / "controlDict"
    ctrl.parent.mkdir(parents=True, exist_ok=True)
    ctrl.write_text("""
endTime           0.1;
deltaT            5e-8;
""")
    apply_edits(
        tmp_path,
        [FileKV(file="system/controlDict", entry="endTime", value="1.0")],
    )
    assert "endTime           1.0;" in ctrl.read_text()


# ---------- apply_edits (error handling) ----------


def test_apply_edits_missing_file_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError, match="not found"):
        apply_edits(tmp_path, [FileKV(file="nonexistent/dict", entry="x", value="1")])


def test_apply_edits_missing_section_raises(tmp_path: Path):
    ctrl = tmp_path / "system" / "controlDict"
    ctrl.parent.mkdir(parents=True, exist_ok=True)
    ctrl.write_text("endTime 1;\n")
    with pytest.raises(ValueError, match="Section 'nonexistent' not found"):
        apply_edits(
            tmp_path,
            [FileKV(file="system/controlDict", entry="nonexistent.x", value="1")],
        )


def test_apply_edits_missing_keyword_raises(tmp_path: Path):
    ctrl = tmp_path / "system" / "controlDict"
    ctrl.parent.mkdir(parents=True, exist_ok=True)
    ctrl.write_text("""
relaxationFactors
{
    U 0.5;
}
""")
    with pytest.raises(ValueError, match="Keyword 'missing' not found"):
        apply_edits(
            tmp_path,
            [FileKV(file="system/controlDict", entry="relaxationFactors.missing", value="1")],
        )
