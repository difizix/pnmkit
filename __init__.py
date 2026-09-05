"""PNMKit: Pore Network Modeling Toolkit.

Architecture & API Boundary:
- Public top-level exports in this module are strictly limited to simulation
  runner wrappers (`cnflow`, `pnextract`, `pnflow`, `scalor`, `skelor`, `xpm`).
- Domain network transformations, seeding, format conversions, and geometry
  modifications reside in `pnmkit.network_ops`.
- Transient execution parameters (e.g. environment variables) are passed via
  the `extra_env` key in configuration/keyword dictionaries (`kwrds`/`config`)
  and popped by backend runners before file serialization.
"""

from __future__ import annotations

from ._pnmkit import cnflow, pnextract, pnflow, scalor, skelor, xpm

# Aliases
mextract = skelor
snextract = skelor
snflow = scalor

__all__ = [
    "cnflow",
    "mextract",
    "pnextract",
    "pnflow",
    "scalor",
    "skelor",
    "snextract",
    "snflow",
    "xpm",
]
