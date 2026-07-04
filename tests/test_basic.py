from __future__ import annotations

from pathlib import Path

import pytest
import tomllib
from packaging.version import Version

import pnmkit as nm


@pytest.mark.smoke
def test_version():
    with (Path(__file__).parents[1] / "pyproject.toml").open("rb") as f:
        version = tomllib.load(f)["project"]["version"]
    assert nm.__version__ == version.split("-")[0]
    assert version.startswith(nm.__version__)
    assert len(nm.__version__.split(".")) == 3
    assert Version(nm.__version__) >= Version("0.0.2")
