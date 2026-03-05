from __future__ import annotations

import pnmkit


def test_pnmkit_imported():
    assert "Xdmf" in dir(pnmkit)
    assert "stepData" in dir(pnmkit)
    assert "Input" in dir(pnmkit)
