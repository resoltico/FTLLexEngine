"""Graph analysis utilities for FTL resource validation.

Provides algorithms for dependency analysis and cycle detection in
message/term reference graphs.

Python 3.13+.
"""

from .graph import build_dependency_graph, detect_cycles

__all__ = [
    "build_dependency_graph",
    "detect_cycles",
]
