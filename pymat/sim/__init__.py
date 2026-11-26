"""pysimu -- pymat's own small Simulink-style simulation engine.

``blocks`` contains the block types, ``diagram`` wires and simulates them, and
``gui`` is the dui block-diagram window opened from pymat's pysimu button.
"""

from .blocks import BLOCK_TYPES, make_block
from .diagram import AlgebraicLoopError, Diagram, SimulationResult, demo_diagram

__all__ = ["BLOCK_TYPES", "make_block", "Diagram", "SimulationResult",
           "AlgebraicLoopError", "demo_diagram", "PysimuWindow"]


def __getattr__(name: str):
    if name == "PysimuWindow":
        from .gui import PysimuWindow
        return PysimuWindow
    raise AttributeError(name)
