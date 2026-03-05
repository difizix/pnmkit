"""

        pnmkit network extraction and simulation
        ---------------------------------------

        .. currentmodule:: pnmkit

        .. autosummary::
           :toctree: _generate

           Input, shared with image3kit
           mextract
           snflow

"""
from __future__ import annotations

import typing

from image3kit._core.sirun import Input

__all__: list[str] = ['DictCompare', 'Input', 'Xdmf', 'Xdml', 'mextract', 'snflow', 'stepData']
class Xdmf:
    def __getitem__(self, arg0: typing.SupportsInt | typing.SupportsIndex) -> list[stepData]:
        ...
    def __init__(self, arg0: str, arg1: str) -> None:
        ...
    def readXmf(self, arg0: str) -> None:
        ...
    def writeAll(self, arg0: str) -> None:
        ...
class Xdml(Xdmf):
    def __init__(self, arg0: str) -> None:
        ...
class stepData:
    @property
    def elemData3_(self) -> dict:
        ...
    @property
    def elemDataI_(self) -> dict:
        ...
    @property
    def elemData_(self) -> dict:
        ...
    @property
    def nodeData3_(self) -> dict:
        ...
    @property
    def nodeDataI_(self) -> dict:
        ...
    @property
    def nodeData_(self) -> dict:
        ...
def DictCompare(dic1Nam: str, dic2Nam: str, sever: typing.SupportsInt | typing.SupportsIndex = 1, ignor: str = '') -> bool:
    """
    Compare two input files
    """
def mextract(image: typing.Any, config: dict = {}, verbose: bool = False) -> int:
    """
    Extract network from voxelImage or filename
    """
def snflow(inp: dict) -> Xdml:
    """
    Run network model stages
    """
__version__: str = '0.0.1'
