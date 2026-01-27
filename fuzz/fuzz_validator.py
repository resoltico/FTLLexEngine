#!/usr/bin/env python3
# FUZZ_PLUGIN_HEADER_START
# FUZZ_PLUGIN: validator - Semantic Validator Unit
# Intentional: This header is intentionally placed for dynamic plugin discovery.
# CRITICAL: DO NOT REMOVE THIS HEADER - REQUIRED FOR FUZZ_ATHERIS.SH
# FUZZ_PLUGIN_HEADER_END
"""Semantic Validator Unit Fuzzer (Atheris).

Targets: ftllexengine.syntax.validator.SemanticValidator
Tests the semantic check engine with synthetically constructed (and potentially illegal) AST nodes.
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
    from ftllexengine.syntax.validator import SemanticValidator

def generate_risky_node(fdp: Any) -> ast.Entry:
    """Generate AST nodes that might trigger semantic violations."""
    choice = fdp.ConsumeIntInRange(0, 3)

    if choice == 0: # Term without value (Illegal)
        return ast.Term(
            id=ast.Identifier("term"),
            value=None, # type: ignore[arg-type]
            attributes=()
        )
    if choice == 1: # Select without default (Illegal)
        return ast.Message(
            id=ast.Identifier("msg"),
            value=ast.Pattern(elements=(
                ast.Placeable(expression=ast.SelectExpression(
                    selector=ast.VariableReference(ast.Identifier("var")),
                    variants=(ast.Variant(ast.Identifier("one"), ast.Pattern(())),)
                )),
            )),
            attributes=()
        )
    if choice == 2: # Named arg duplicate (Illegal)
        args = ast.CallArguments(
            positional=(),
            named=(
                ast.NamedArgument(ast.Identifier("dup"), ast.StringLiteral("1")),
                ast.NamedArgument(ast.Identifier("dup"), ast.StringLiteral("2")),
            )
        )
        return ast.Message(
            id=ast.Identifier("msg"),
            value=ast.Pattern(elements=(
                ast.Placeable(expression=ast.FunctionReference(ast.Identifier("FUNC"), args)),
            )),
            attributes=()
        )

    return ast.Comment(content="valid", type=ast.CommentType.COMMENT)

def test_one_input(data: bytes) -> None:
    """Atheris entry point: Test semantic validator with synthetically constructed AST nodes."""
    _fuzz_stats["iterations"] = int(_fuzz_stats["iterations"]) + 1
    _fuzz_stats["status"] = "running"

    fdp = atheris.FuzzedDataProvider(data)

    # 1. Setup Resource
    try:
        nodes = [generate_risky_node(fdp) for _ in range(3)]
        root = ast.Resource(entries=tuple(nodes))
    except Exception:  # pylint: disable=broad-exception-caught # Fuzzer: skip invalid AST generation
        return

    # 2. Validate
    # This must NEVER crash, only return annotations.
    validator = SemanticValidator()
    try:
        res = validator.validate(root)
        _ = res.is_valid
        _ = res.annotations
    except Exception:  # pylint: disable=broad-exception-caught # Fuzzer: record any unexpected exception as finding
        _fuzz_stats["findings"] = int(_fuzz_stats["findings"]) + 1
        raise

if __name__ == "__main__":
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()
