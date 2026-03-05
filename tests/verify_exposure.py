from __future__ import annotations

import pnmkit


def test_snflow_exists():
    assert hasattr(pnmkit, "snflow"), "pnmkit does not have snflow"
    print("pnmkit.snflow exists")


def test_snflow_import():
    print("Successfully imported snflow from pnmkit")


if __name__ == "__main__":
    test_snflow_exists()
    test_snflow_import()
    print("All basic availability tests passed!")
