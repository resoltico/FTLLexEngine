#!/usr/bin/env python3
# FUZZ_PLUGIN_HEADER_START
# FUZZ_PLUGIN: visitor - AST Visitor & Transformer
# Intentional: This header is intentionally placed for dynamic plugin discovery.
# CRITICAL: DO NOT REMOVE THIS HEADER - REQUIRED FOR FUZZ_ATHERIS.SH
# FUZZ_PLUGIN_HEADER_END
"""AST Visitor & Transformer Fuzzer (Atheris).

Targets: ftllexengine.syntax.visitor
Tests the base visitor and transformer logic with synthetically constructed ASTs.
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
    from ftllexengine.syntax import ast
    from ftllexengine.syntax.visitor import ASTTransformer, ASTVisitor

def generate_random_node(fdp: Any, depth: int) -> ast.Entry:
    """Generate valid random entry nodes for visitor testing."""
    if depth > 3:
        # Terminal: create a simple Comment
        return ast.Comment(
            content=fdp.ConsumeUnicodeNoSurrogates(20),
            type=fdp.PickValueInList([ast.CommentType.COMMENT, ast.CommentType.GROUP])
        )

    # Create Message or Term with random complexity
    msg_id = ast.Identifier(name=f"msg{depth}")
    text_elem = ast.TextElement(value=fdp.ConsumeUnicodeNoSurrogates(30))

    if fdp.ConsumeBool():
        # Simple message with text only
        value = ast.Pattern(elements=(text_elem,))
        return ast.Message(id=msg_id, value=value, attributes=())

    # Message with placeable
    var_ref = ast.VariableReference(id=ast.Identifier("x"))
    placeable = ast.Placeable(expression=var_ref)
    pattern_with_placeable = ast.Pattern(elements=(text_elem, placeable))
    return ast.Message(id=msg_id, value=pattern_with_placeable, attributes=())

def test_one_input(data: bytes) -> None:
    """Atheris entry point: Test AST visitor and transformer with random nodes."""
    _fuzz_stats["iterations"] = int(_fuzz_stats["iterations"]) + 1
    _fuzz_stats["status"] = "running"

    fdp = atheris.FuzzedDataProvider(data)

    # 1. Generate Synthetic AST
    try:
        root = ast.Resource(entries=(generate_random_node(fdp, 0),))
    except Exception:  # pylint: disable=broad-exception-caught # Fuzzer: skip invalid AST generation
        return

    # 2. Test Base Visitor
    visitor = ASTVisitor()
    try:
        visitor.visit(root)
    except Exception:  # pylint: disable=broad-exception-caught # Fuzzer: record any visitor crash as finding
        _fuzz_stats["findings"] = int(_fuzz_stats["findings"]) + 1
        raise

    # 3. Test Transformer
    transformer = ASTTransformer()
    try:
        transformer.transform(root)
    except Exception:  # pylint: disable=broad-exception-caught # Fuzzer: record any transformer crash as finding
        _fuzz_stats["findings"] = int(_fuzz_stats["findings"]) + 1
        raise

if __name__ == "__main__":
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()
