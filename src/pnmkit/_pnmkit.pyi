"""

        Pybind11 example plugin
        -----------------------

        .. currentmodule:: scikit_build_example

        .. autosummary::
           :toctree: _generate

           add
           subtract
    
"""
from __future__ import annotations
import typing
__all__: list[str] = ['add', 'subtract']
def add(arg0: typing.SupportsInt | typing.SupportsIndex, arg1: typing.SupportsInt | typing.SupportsIndex) -> int:
    """
            Add two numbers
    
            Some other explanation about the add function.
    """
def subtract(arg0: typing.SupportsInt | typing.SupportsIndex, arg1: typing.SupportsInt | typing.SupportsIndex) -> int:
    """
            Subtract two numbers
    
            Some other explanation about the subtract function.
    """
__version__: str = '0.0.1'
