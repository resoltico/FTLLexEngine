"""Graph analysis facade for public dependency helpers.

The implementation lives in ``ftllexengine.core.reference_graph`` so lower
layers can use the same algorithms without importing the higher-level analysis
package. This module remains the stable public namespace for callers and keeps
module-level compatibility for monkeypatch-based tests.
"""

from __future__ import annotations

import ftllexengine.core.reference_graph as _core_graph
from ftllexengine.constants import (
    MAX_DETECTED_CYCLES as _DEFAULT_MAX_DETECTED_CYCLES,
)
from ftllexengine.constants import (
    MAX_GRAPH_DFS_STACK as _DEFAULT_MAX_GRAPH_DFS_STACK,
)

MAX_DETECTED_CYCLES = _DEFAULT_MAX_DETECTED_CYCLES
MAX_GRAPH_DFS_STACK = _DEFAULT_MAX_GRAPH_DFS_STACK

__all__ = [
    "MAX_DETECTED_CYCLES",
    "MAX_GRAPH_DFS_STACK",
    "_canonicalize_cycle",
    "detect_cycles",
    "entry_dependency_set",
    "make_cycle_key",
]


def entry_dependency_set(
    message_refs: frozenset[str],
    term_refs: frozenset[str],
) -> frozenset[str]:
    """Build a namespace-prefixed dependency set from reference sets."""
    return _core_graph.entry_dependency_set(message_refs, term_refs)


def make_cycle_key(cycle: list[str] | tuple[str, ...]) -> str:
    """Create a canonical display key from a cycle path."""
    return _core_graph.make_cycle_key(cycle)


def _canonicalize_cycle(cycle: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    """Canonicalize a cycle path for compatibility callers and fuzzers."""
    return _core_graph.canonicalize_cycle(cycle)


def detect_cycles(dependencies: dict[str, set[str]]) -> list[list[str]]:
    """Detect cycles while honoring monkeypatched module-level limits."""
    original_max_cycles = _core_graph.MAX_DETECTED_CYCLES
    original_max_stack = _core_graph.MAX_GRAPH_DFS_STACK
    _core_graph.MAX_DETECTED_CYCLES = MAX_DETECTED_CYCLES
    _core_graph.MAX_GRAPH_DFS_STACK = MAX_GRAPH_DFS_STACK
    try:
        return _core_graph.detect_cycles(dependencies)
    finally:
        _core_graph.MAX_DETECTED_CYCLES = original_max_cycles
        _core_graph.MAX_GRAPH_DFS_STACK = original_max_stack
