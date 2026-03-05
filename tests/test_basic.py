from __future__ import annotations

import pytest

import pnmkit as nm


@pytest.mark.smoke
def test_version():
    assert nm.__version__ == "0.0.1"
