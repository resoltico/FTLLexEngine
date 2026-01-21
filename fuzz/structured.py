#!/usr/bin/env python3
"""Structure-Aware Fuzzer (Atheris).

Generates syntactically plausible FTL using grammar-aware construction,
then applies byte-level mutations. This improves coverage penetration
compared to pure random byte fuzzing.

Built for Python 3.13+ using modern PEPs (695, 585, 563).
"""

from __future__ import annotations

import atexit
import json
import logging
import string
import sys
from typing import Any

# --- PEP 695 Type Aliases (Python 3.13) ---
type FuzzStats = dict[str, int | str]

# Crash-proof reporting: ensure summary is always emitted
_fuzz_stats: FuzzStats = {"status": "incomplete", "iterations": 0, "findings": 0}


def _emit_final_report() -> None:
    """Emit JSON summary on exit (crash-proof reporting)."""
    report = json.dumps(_fuzz_stats)
    print(f"\n[SUMMARY-JSON-BEGIN]{report}[SUMMARY-JSON-END]", file=sys.stderr)


atexit.register(_emit_final_report)

try:
    import atheris
except ImportError:
    print("-" * 80, file=sys.stderr)
    print("ERROR: 'atheris' not found.", file=sys.stderr)
    print("On macOS, install LLVM: brew install llvm", file=sys.stderr)
    print("Then set: export CC=$(brew --prefix llvm)/bin/clang", file=sys.stderr)
    print("And reinstall: uv sync", file=sys.stderr)
    print("See docs/FUZZING_GUIDE.md for details.", file=sys.stderr)
    print("-" * 80, file=sys.stderr)
    sys.exit(1)

# Suppress parser logging during fuzzing
logging.getLogger("ftllexengine").setLevel(logging.CRITICAL)

with atheris.instrument_imports(include=["ftllexengine"]):
    from ftllexengine.syntax.ast import Junk
    from ftllexengine.syntax.parser import FluentParserV1
    from ftllexengine.syntax.serializer import FluentSerializer


class StructuredFuzzError(Exception):
    """Raised when an unexpected exception is detected during structured fuzzing."""


# Exception contract: only these exceptions are acceptable for invalid input
ALLOWED_EXCEPTIONS = (ValueError, RecursionError, MemoryError)

# Character sets for FTL generation per spec: [a-zA-Z][a-zA-Z0-9_-]*
IDENTIFIER_FIRST = string.ascii_letters  # [a-zA-Z]
IDENTIFIER_REST = string.ascii_letters + string.digits + "-_"  # [a-zA-Z0-9_-]
TEXT_CHARS = string.ascii_letters + string.digits + " .,!?'-"
SPECIAL_CHARS = "\t\n\r\x00\x1f\x7f\u200b\ufeff"  # Edge case characters


def generate_identifier(fdp: Any, max_len: int = 20) -> str:
    """Generate a valid FTL identifier using fuzzer decisions."""
    if not fdp.remaining_bytes():
        return "msg"

    first = IDENTIFIER_FIRST[fdp.ConsumeIntInRange(0, len(IDENTIFIER_FIRST) - 1)]
    rest_len = fdp.ConsumeIntInRange(0, max_len)

    rest_chars = []
    for _ in range(rest_len):
        if not fdp.remaining_bytes():
            break
        idx = fdp.ConsumeIntInRange(0, len(IDENTIFIER_REST) - 1)
        rest_chars.append(IDENTIFIER_REST[idx])

    return first + "".join(rest_chars)


def generate_text(fdp: Any, max_len: int = 50) -> str:
    """Generate FTL-safe text content with Unicode support."""
    if not fdp.remaining_bytes():
        return "value"

    length = fdp.ConsumeIntInRange(1, max_len)

    # 30% chance of using full Unicode instead of ASCII-only
    use_unicode = fdp.ConsumeBool() and fdp.ConsumeBool()  # ~25% chance

    if use_unicode and fdp.remaining_bytes() >= length:
        # Use ConsumeUnicodeNoSurrogates for full Unicode coverage
        text = fdp.ConsumeUnicodeNoSurrogates(length)
        # Filter out FTL structural characters
        filtered = "".join(c for c in text if c not in "{}[]*$-.#\n\r")
        return filtered if filtered else "unicode"

    chars = []
    for _ in range(length):
        if not fdp.remaining_bytes():
            break

        # Occasionally inject special characters for edge case testing
        if fdp.ConsumeBool() and fdp.ConsumeBool():
            idx = fdp.ConsumeIntInRange(0, len(SPECIAL_CHARS) - 1)
            chars.append(SPECIAL_CHARS[idx])
        else:
            idx = fdp.ConsumeIntInRange(0, len(TEXT_CHARS) - 1)
            chars.append(TEXT_CHARS[idx])

    return "".join(chars) or "value"


def generate_simple_message(fdp: Any) -> str:
    """Generate: msg-id = text value"""
    msg_id = generate_identifier(fdp)
    value = generate_text(fdp)
    return f"{msg_id} = {value}"


def generate_message_with_variable(fdp: Any) -> str:
    """Generate: msg-id = prefix { $var } suffix"""
    msg_id = generate_identifier(fdp)
    var_name = generate_identifier(fdp, max_len=10)
    prefix = generate_text(fdp, max_len=20)
    suffix = generate_text(fdp, max_len=20)
    return f"{msg_id} = {prefix} {{ ${var_name} }} {suffix}"


def generate_term(fdp: Any) -> str:
    """Generate: -term-id = value"""
    term_id = generate_identifier(fdp)
    value = generate_text(fdp)
    return f"-{term_id} = {value}"


def generate_message_with_attribute(fdp: Any) -> str:
    """Generate message with attributes."""
    msg_id = generate_identifier(fdp)
    value = generate_text(fdp)
    attr_name = generate_identifier(fdp, max_len=10)
    attr_value = generate_text(fdp, max_len=30)
    return f"{msg_id} = {value}\n    .{attr_name} = {attr_value}"


def generate_variant_key(fdp: Any) -> str:
    """Generate a variant key (identifier or numeric literal)."""
    if not fdp.remaining_bytes():
        return "other"

    # 40% chance of numeric key (covers plural/ordinal cases)
    if fdp.ConsumeIntInRange(0, 9) < 4:
        # Generate numeric literal
        is_decimal = fdp.ConsumeBool() if fdp.remaining_bytes() else False
        is_negative = fdp.ConsumeBool() if fdp.remaining_bytes() else False

        int_part = fdp.ConsumeIntInRange(0, 999) if fdp.remaining_bytes() else 1

        if is_decimal and fdp.remaining_bytes():
            decimal_part = fdp.ConsumeIntInRange(0, 99)
            num_str = f"{int_part}.{decimal_part:02d}"
        else:
            num_str = str(int_part)

        if is_negative:
            num_str = f"-{num_str}"

        return num_str

    # Generate text identifier key
    return generate_identifier(fdp, max_len=10)


def generate_select_expression(fdp: Any) -> str:
    """Generate message with select expression."""
    msg_id = generate_identifier(fdp)
    var_name = generate_identifier(fdp, max_len=10)

    # Generate 2-4 variants
    num_variants = fdp.ConsumeIntInRange(2, 4) if fdp.remaining_bytes() else 2

    # Randomize default variant position
    default_idx = (
        fdp.ConsumeIntInRange(0, num_variants - 1)
        if fdp.remaining_bytes()
        else num_variants - 1
    )

    variants = []

    for i in range(num_variants):
        if not fdp.remaining_bytes():
            break
        key = generate_variant_key(fdp)
        val = generate_text(fdp, max_len=30)
        prefix = "*" if i == default_idx else " "
        variants.append(f"   {prefix}[{key}] {val}")

    variants_str = "\n".join(variants)
    return f"{msg_id} = {{ ${var_name} ->\n{variants_str}\n}}"


def generate_comment(fdp: Any) -> str:
    """Generate FTL comment."""
    level = fdp.ConsumeIntInRange(1, 3) if fdp.remaining_bytes() else 1
    prefix = "#" * level
    content = generate_text(fdp, max_len=40)
    return f"{prefix} {content}"


def generate_ftl_resource(fdp: Any) -> str:
    """Generate a complete FTL resource with multiple entries."""
    if not fdp.remaining_bytes():
        return "fallback = Fallback value"

    # Decide number of entries (1-10)
    num_entries = fdp.ConsumeIntInRange(1, 10)
    entries = []

    # Entry type generators
    generators = [
        generate_simple_message,
        generate_message_with_variable,
        generate_term,
        generate_message_with_attribute,
        generate_select_expression,
        generate_comment,
    ]

    for _ in range(num_entries):
        if not fdp.remaining_bytes():
            break

        # Pick a generator type
        gen_idx = fdp.ConsumeIntInRange(0, len(generators) - 1)
        generator = generators[gen_idx]

        try:
            entry = generator(fdp)
            entries.append(entry)
        except (IndexError, ValueError):
            break

    return "\n\n".join(entries) if entries else "fallback = Fallback value"


def _verify_semantic_invariants(source: str, result: Any) -> None:
    """Verify semantic invariants that don't cause crashes but indicate logic bugs."""
    # Check 1: Non-corrupted input should produce entries
    if (
        "corruption" not in source[:50]
        and len(result.entries) == 0
        and len(source.strip()) > 10
    ):
        # Suspicious: non-trivial input produced empty AST
        _fuzz_stats["findings"] = int(_fuzz_stats["findings"]) + 1
        msg = f"Empty AST for non-trivial input: {source[:100]!r}"
        raise AssertionError(msg)

    # Check 2: Round-trip consistency for valid parses (no junk)
    if not any(isinstance(e, Junk) for e in result.entries):
        serializer = FluentSerializer()
        parser = FluentParserV1()
        try:
            serialized = serializer.serialize(result)
            reparsed = parser.parse(serialized)

            # Entry count should match
            if len(result.entries) != len(reparsed.entries):
                _fuzz_stats["findings"] = int(_fuzz_stats["findings"]) + 1
                msg = (
                    f"Round-trip entry count mismatch: "
                    f"{len(result.entries)} -> {len(reparsed.entries)}"
                )
                raise AssertionError(msg)
        except ALLOWED_EXCEPTIONS:
            pass  # Serialization may fail for edge cases


def test_one_input(data: bytes) -> None:
    """Atheris entry point: generate structured FTL and detect crashes."""
    _fuzz_stats["iterations"] = int(_fuzz_stats["iterations"]) + 1
    _fuzz_stats["status"] = "running"

    fdp = atheris.FuzzedDataProvider(data)

    # Generate structured FTL using fuzzer-guided decisions
    source = generate_ftl_resource(fdp)

    # Optionally apply raw byte corruption to test parser robustness
    if fdp.remaining_bytes() and fdp.ConsumeBool() and len(source) > 0:
        # Corrupt a random position in the generated FTL
        pos = fdp.ConsumeIntInRange(0, len(source) - 1)
        corruption = fdp.ConsumeUnicodeNoSurrogates(min(3, fdp.remaining_bytes()))
        source = source[:pos] + corruption + source[pos + 1 :]

    parser = FluentParserV1(max_source_size=1024 * 1024, max_nesting_depth=100)

    try:
        result = parser.parse(source)
        _verify_semantic_invariants(source, result)

    except ALLOWED_EXCEPTIONS:
        pass  # Expected for invalid/corrupted input
    except AssertionError:
        raise  # Propagate semantic invariant failures
    except Exception as e:
        # Unexpected exception - this is a finding
        _fuzz_stats["findings"] = int(_fuzz_stats["findings"]) + 1
        _fuzz_stats["status"] = "finding"

        print("\n" + "=" * 80)
        print("[FINDING] STABILITY BREACH DETECTED (Structure-Aware)")
        print("=" * 80)
        print(f"Exception Type: {type(e).__module__}.{type(e).__name__}")
        print(f"Error Message:  {e}")
        print(f"Input Preview:  {source[:200]!r}...")
        print("-" * 80)
        print("NEXT STEPS:")
        print("  1. Reproduce:  ./scripts/fuzz.sh --repro .fuzz_corpus/crash_*")
        print("  2. Create test: Use tests/test_parser_survivability.py as template")
        print("  3. Fix & Verify: Resolve the crash and confirm with --repro")
        print("=" * 80)

        msg = f"{type(e).__name__}: {e}"
        raise StructuredFuzzError(msg) from e


def main() -> None:
    """Run the structure-aware fuzzer."""
    print("\n" + "=" * 80)
    print("Fluent Structure-Aware Fuzzer (Python 3.13 Edition)")
    print("=" * 80)
    print("Strategy: Generate valid FTL scaffolds, then mutate")
    print("Contract: Only ValueError, RecursionError, MemoryError allowed")
    print("Stopping: Press Ctrl+C at any time (findings auto-saved)")
    print("=" * 80 + "\n")

    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
