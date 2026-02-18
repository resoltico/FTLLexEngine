"""Graph analysis utilities for FTL resource validation.

Provides algorithms for dependency analysis and cycle detection in
message/term reference graphs.

Python 3.13+.
"""

from .graph import detect_cycles, entry_dependency_set, make_cycle_key

__all__ = [
    "detect_cycles",
    "entry_dependency_set",
    "make_cycle_key",
]
