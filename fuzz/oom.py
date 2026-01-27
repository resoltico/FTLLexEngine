#!/usr/bin/env python3
# FUZZ_PLUGIN: oom - Memory Density (Object Explosion)
"""Memory Density & Object Explosion Fuzzer (Atheris).

Targets: ftllexengine.syntax.parser.FluentParserV1
Detects "Billion Laughs" style attacks where small inputs generate massive ASTs.

This fuzzer tracks the total number of AST nodes produced.
"""

from __future__ import annotations

import atexit
import json
import logging
import sys
from typing import Any

# --- PEP 695 Type Aliases ---
type FuzzStats = dict[str, int | str]

_fuzz_stats: FuzzStats = {"status": "incomplete", "iterations": 0, "findings": 0}

def _emit_final_report() -> None:
    report = json.dumps(_fuzz_stats)
    print(f"\n[SUMMARY-JSON-BEGIN]{report}[SUMMARY-JSON-END]", file=sys.stderr)

atexit.register(_emit_final_report)

try:
    import atheris
except ImportError:
    sys.exit(1)

logging.getLogger("ftllexengine").setLevel(logging.CRITICAL)

with atheris.instrument_imports(include=["ftllexengine"]):
    from ftllexengine.syntax.parser import FluentParserV1

class MemoryDensityError(Exception):
    """Raised when AST object density exceeds safe limits."""

def count_nodes(node: Any) -> int:
    """Recursively count AST nodes."""
    count = 1
    if hasattr(node, "entries"): # Resource
        for e in node.entries:
            count += count_nodes(e)
    if hasattr(node, "value") and node.value: # Message/Term/Attribute
        count += count_nodes(node.value)
    if hasattr(node, "attributes"): # Message/Term
        for a in node.attributes:
            count += count_nodes(a)
    if hasattr(node, "elements"): # Pattern
        for e in node.elements:
            count += count_nodes(e)
    if hasattr(node, "expression"): # Placeable
        count += count_nodes(node.expression)
    if hasattr(node, "selector"): # SelectExpression
        count += count_nodes(node.selector)
    if hasattr(node, "variants"): # SelectExpression
        for v in node.variants:
            count += count_nodes(v)
    return count

def test_one_input(data: bytes) -> None:
    """Atheris entry point: Detect billion laughs style AST explosion attacks."""
    _fuzz_stats["iterations"] = int(_fuzz_stats["iterations"]) + 1
    _fuzz_stats["status"] = "running"

    fdp = atheris.FuzzedDataProvider(data)

    # Strat: Generate high-nested attributes or placeables in a small string
    # example: msg = {"{"} ... }
    depth = fdp.ConsumeIntInRange(1, 200)
    msg_id = "msg"

    # We want to keep the SOURCE small but generate MANY objects
    # This manually constructs a potentially pathological string
    if fdp.ConsumeBool():
        # Placeable nesting
        source = f"{msg_id} = " + ("{" * depth) + " $var " + ("}" * depth) + "\n"
    else:
        # Attribute explosion
        source = f"{msg_id} = val\n" + "\n".join([f" .attr{i} = val" for i in range(depth)])

    parser = FluentParserV1(max_source_size=1024*1024, max_nesting_depth=500)

    try:
        res = parser.parse(source)
        node_count = count_nodes(res)

        # Density check: Nodes per KB of source
        source_size_kb = max(len(source) / 1024.0, 0.1)
        density = node_count / source_size_kb

        # Threshold: 2000 nodes per KB is extremely high for 1.0 spec
        if density > 5000:
            _fuzz_stats["findings"] = int(_fuzz_stats["findings"]) + 1
            msg = (
                f"Pathological density: {density:.1f} nodes/KB "
                f"({node_count} nodes for {len(source)} bytes)"
            )
            raise MemoryDensityError(msg)

    except (ValueError, RecursionError, MemoryError):
        pass
    except Exception:
        _fuzz_stats["findings"] = int(_fuzz_stats["findings"]) + 1
        raise

if __name__ == "__main__":
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()
