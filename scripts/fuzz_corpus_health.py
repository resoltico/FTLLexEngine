#!/usr/bin/env python3
"""Corpus Health Checker.

Validates seed corpus, computes coverage metrics, and reports issues.

Usage:
    uv run python scripts/corpus-health.py
    uv run python scripts/corpus-health.py --json
    uv run python scripts/corpus-health.py --dedupe
    uv run python scripts/corpus-health.py --coverage
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ftllexengine.syntax.ast import (  # pylint: disable=C0413
    Attribute,
    Comment,
    FunctionReference,
    Junk,
    Message,
    MessageReference,
    NumberLiteral,
    Placeable,
    SelectExpression,
    StringLiteral,
    Term,
    TermReference,
    TextElement,
    VariableReference,
)
from ftllexengine.syntax.parser import FluentParserV1  # pylint: disable=C0413

if TYPE_CHECKING:
    from ftllexengine.syntax.ast import Resource

SEEDS_DIR = Path(__file__).parent.parent / "fuzz" / "seeds"

# Grammar features we want to cover
GRAMMAR_FEATURES = [
    "message",
    "term",
    "comment",
    "attribute",
    "select_expression",
    "variable_reference",
    "message_reference",
    "term_reference",
    "term_arguments",       # -term(arg: value)
    "function_call",
    "string_literal",
    "number_literal",
    "numeric_variant_key",  # [1], [3.14]
    "multiline_pattern",
    "nested_placeable",
    # Advanced features
    "deep_nesting",
    "complex_selector",
    "empty_message",
    "attribute_only",
    "large_numbers",
    "special_chars",
    "whitespace_variants",
    "mixed_references",
    "nested_selects",
    "function_chaining",
    "term_with_attributes",
    "long_identifiers",
    "many_attributes",
    "error_recovery",
]

# Suggestions for missing features
FEATURE_SUGGESTIONS = {
    "term_arguments": (
        "Add a seed with term references that include arguments: "
        "{-term-name(arg: 'value')}"
    ),
    "function_call": "Add a seed with function calls: {FUNCTION(arg)}",
    "select_expression": (
        "Add a seed with select expressions: {$var ->\n  [value1] Result 1\n "
        "*[other] Default}"
    ),
    "attribute": (
        "Add a seed with message/term attributes: message = Value\n    "
        ".attr = Attribute value"
    ),
    "comment": "Add a seed with comments: # This is a comment\nmessage = Value",
    "variable_reference": "Add a seed with variable references: message = {$variable}",
    "message_reference": "Add a seed with message references: message = {other-message}",
    "term_reference": "Add a seed with term references: message = {-term-name}",
    "string_literal": "Add a seed with string literals: message = {'string value'}",
    "number_literal": "Add a seed with number literals: message = {123}",
    "numeric_variant_key": (
        "Add a seed with numeric variant keys: {$var ->\n  [1] One\n "
        "*[other] Other}"
    ),
    "multiline_pattern": (
        "Add a seed with multiline patterns: message =\n    Line 1\n    Line 2"
    ),
    "nested_placeable": "Add a seed with nested placeables: message = {{{'nested'}}}",
    # Advanced features
    "deep_nesting": "Add deeply nested placeables: message = {{{{{{'very nested'}}}}}}",
    "complex_selector": (
        "Add complex selectors with many variants: {$var ->\n  [a] One\n  "
        "[b] Two\n  [c] Three\n *[other] Default}"
    ),
    "empty_message": "Add empty messages: empty-msg =\nempty-term =",
    "attribute_only": (
        "Add messages/terms with only attributes: msg =\n    .attr1 = Value1\n"
        "    .attr2 = Value2"
    ),
    "large_numbers": "Add large numbers: big-num = {12345678901234567890}",
    "special_chars": (
        "Add special characters in identifiers: msg_with_underscores = Value\n"
        "msg-with-dashes = Value"
    ),
    "whitespace_variants": (
        "Add various whitespace patterns: msg = {'  spaced  '}\n    "
        ".attr = {'\t\ttabbed\t\t'}"
    ),
    "mixed_references": (
        "Add mixed references: complex = {$var} and {other-msg} with "
        "{-term(arg: 'val')}"
    ),
    "nested_selects": (
        "Add nested select expressions: nested = {$outer ->\n  [a] {$inner ->\n"
        "    [x] Result\n   *[y] Default}\n *[b] Outer default}"
    ),
    "function_chaining": (
        "Add chained function calls: chained = {NUMBER(NUMBER($value, "
        "minimumFractionDigits: 0), minimumFractionDigits: 2)}"
    ),
    "term_with_attributes": (
        "Add terms with attributes: -term = Value\n    .attr = Term attribute"
    ),
    "long_identifiers": (
        "Add very long identifiers: very_long_message_identifier_that_tests_"
        "limits = {'Long id'}"
    ),
    "many_attributes": (
        "Add messages/terms with many attributes: multi =\n    .a = 1\n    "
        ".b = 2\n    .c = 3\n    .d = 4\n    .e = 5"
    ),
    "error_recovery": (
        "Add malformed content that should produce junk entries: message = "
        "{unclosed\nincomplete = {missing}"
    ),
}


@dataclass
class SeedAnalysis:
    """Analysis result for a single seed file."""

    path: Path
    valid: bool
    error: str | None = None
    features: set[str] = field(default_factory=set)
    message_count: int = 0
    term_count: int = 0
    junk_count: int = 0
    content_hash: str = ""


@dataclass
class CorpusHealth:
    """Overall corpus health report."""

    total_seeds: int = 0
    valid_seeds: int = 0
    invalid_seeds: int = 0
    duplicate_seeds: int = 0
    features_covered: set[str] = field(default_factory=set)
    features_missing: set[str] = field(default_factory=set)
    coverage_percent: float = 0.0
    issues: list[str] = field(default_factory=list)
    analyses: list[SeedAnalysis] = field(default_factory=list)
    duplicates: list[tuple[Path, Path]] = field(default_factory=list)


def extract_features(resource: Resource) -> set[str]:  # noqa: PLR0915
    """Extract grammar features used in a resource."""
    features: set[str] = set()

    # Visitor dispatch for AST node types - inherently needs many branches
    def visit_node(node: object) -> None:  # noqa: PLR0912, PLR0915
        match node:
            case Message():
                features.add("message")
                if node.attributes:
                    features.add("attribute")
                    if len(node.attributes) > 3:
                        features.add("many_attributes")
                if node.value and node.value.elements:  # Check if pattern has actual content
                    visit_node(node.value)
                else:
                    features.add("empty_message")
                for attr in node.attributes:
                    visit_node(attr)
                if node.attributes and (not node.value or not node.value.elements):
                    features.add("attribute_only")
            case Term():
                features.add("term")
                if node.attributes:
                    features.add("attribute")
                    features.add("term_with_attributes")
                    if len(node.attributes) > 3:
                        features.add("many_attributes")
                if node.value and node.value.elements:  # Check if pattern has actual content
                    visit_node(node.value)
                else:
                    features.add("empty_message")
                for attr in node.attributes:
                    visit_node(attr)
                if node.attributes and (not node.value or not node.value.elements):
                    features.add("attribute_only")
            case Comment():
                features.add("comment")
            case Attribute():
                features.add("attribute")
                if node.value:
                    visit_node(node.value)
            case SelectExpression():
                features.add("select_expression")
                visit_node(node.selector)
                variant_count = len(node.variants)
                if variant_count > 3:
                    features.add("complex_selector")
                for variant in node.variants:
                    # Check for numeric variant keys like [1], [3.14]
                    if isinstance(variant.key, NumberLiteral):
                        features.add("numeric_variant_key")
                    if variant.value:
                        visit_node(variant.value)
                # Check for nested selects
                nested_found = False
                for variant in node.variants:
                    if variant.value and hasattr(variant.value, "elements"):
                        for elem in variant.value.elements:
                            if (
                                isinstance(elem, Placeable) and
                                isinstance(elem.expression, SelectExpression)
                            ):
                                nested_found = True
                                break
                        if nested_found:
                            break
                if nested_found:
                    features.add("nested_selects")
            case VariableReference():
                features.add("variable_reference")
            case MessageReference():
                features.add("message_reference")
            case TermReference():
                features.add("term_reference")
                if node.arguments is not None:
                    features.add("term_arguments")
            case FunctionReference():
                features.add("function_call")
                # Check for function chaining
                if node.arguments:
                    for pos_arg in node.arguments.positional:
                        if isinstance(pos_arg, FunctionReference):
                            features.add("function_chaining")
                            break
                    if "function_chaining" not in features:  # Only check named if not already found
                        for named_arg in node.arguments.named:
                            if isinstance(named_arg.value, FunctionReference):
                                features.add("function_chaining")
                                break
            case StringLiteral():
                features.add("string_literal")
                value = node.value

                if len(value) > 50:
                    features.add("long_identifiers")  # Approximation for long content
                if "  " in value or "\t" in value:
                    features.add("whitespace_variants")
            case NumberLiteral():
                features.add("number_literal")
                try:
                    num_val = float(node.value)
                    if num_val > 1000000:
                        features.add("large_numbers")
                except ValueError:
                    pass
            case Placeable():
                expr = node.expression
                if isinstance(expr, Placeable):
                    features.add("nested_placeable")
                    # Check for deep nesting
                    depth = 1
                    current: Placeable = expr
                    while isinstance(current.expression, Placeable):
                        depth += 1
                        current = current.expression
                    if depth > 3:
                        features.add("deep_nesting")
                visit_node(expr)
            case TextElement():
                if "\n" in node.value:
                    features.add("multiline_pattern")
                if "  " in node.value or "\t" in node.value:
                    features.add("whitespace_variants")
            case _:
                pass

        # Check for mixed references and special chars in identifiers
        if hasattr(node, "id"):
            ident = node.id.name if hasattr(node.id, "name") else str(node.id)

            if "_" in ident or "-" in ident:
                features.add("special_chars")
            if len(ident) > 30:
                features.add("long_identifiers")

        # Recursively visit pattern elements
        if hasattr(node, "elements"):
            for elem in node.elements:
                visit_node(elem)

    for entry in resource.entries:
        visit_node(entry)

    # Check for mixed references across the resource
    has_var = "variable_reference" in features
    has_msg = "message_reference" in features
    has_term = "term_reference" in features
    if has_var and (has_msg or has_term):
        features.add("mixed_references")

    # Check for error recovery (junk entries)
    junk_count = sum(1 for e in resource.entries if isinstance(e, Junk))
    if junk_count > 0:
        features.add("error_recovery")

    return features


def analyze_seed(path: Path, parser: FluentParserV1) -> SeedAnalysis:
    """Analyze a single seed file."""
    try:
        content = path.read_text(encoding="utf-8")
        content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]

        resource = parser.parse(content)

        # Count entry types
        message_count = sum(1 for e in resource.entries if isinstance(e, Message))
        term_count = sum(1 for e in resource.entries if isinstance(e, Term))
        junk_count = sum(1 for e in resource.entries if isinstance(e, Junk))

        # Check for parse errors (junk) - but junk is expected for error_recovery testing
        if junk_count > 0:
            # For error_recovery feature, junk entries are actually the desired behavior
            # So this seed is valid if it parsed successfully
            features = extract_features(resource)
            return SeedAnalysis(
                path=path,
                valid=True,  # Changed from False - junk entries are expected for error recovery
                features=features,
                message_count=message_count,
                term_count=term_count,
                junk_count=junk_count,
                content_hash=content_hash,
            )

        # Check for empty resources
        if message_count == 0 and term_count == 0:
            return SeedAnalysis(
                path=path,
                valid=False,
                error="No messages or terms found",
                content_hash=content_hash,
            )

        features = extract_features(resource)

        return SeedAnalysis(
            path=path,
            valid=True,
            features=features,
            message_count=message_count,
            term_count=term_count,
            junk_count=junk_count,
            content_hash=content_hash,
        )

    except (OSError, UnicodeDecodeError, ValueError) as e:
        return SeedAnalysis(
            path=path,
            valid=False,
            error=f"Parse error: {e}",
        )


def check_corpus_health(seeds_dir: Path) -> CorpusHealth:
    """Check health of the entire seed corpus."""
    health = CorpusHealth()
    parser = FluentParserV1()

    # Find all seed files
    seed_files = sorted(seeds_dir.glob("*.ftl"))
    health.total_seeds = len(seed_files)

    if health.total_seeds == 0:
        health.issues.append("No seed files found in corpus")
        health.features_missing = set(GRAMMAR_FEATURES)
        return health

    # Analyze each seed
    hash_to_path: dict[str, Path] = {}

    for seed_file in seed_files:
        analysis = analyze_seed(seed_file, parser)
        health.analyses.append(analysis)

        if analysis.valid:
            health.valid_seeds += 1
            health.features_covered.update(analysis.features)

            # Check for duplicates
            if analysis.content_hash in hash_to_path:
                health.duplicate_seeds += 1
                health.duplicates.append((hash_to_path[analysis.content_hash], seed_file))
            else:
                hash_to_path[analysis.content_hash] = seed_file
        else:
            health.invalid_seeds += 1
            health.issues.append(f"{seed_file.name}: {analysis.error}")
            # Still include features from partially valid seeds
            if analysis.features:
                health.features_covered.update(analysis.features)

    # Calculate coverage
    health.features_missing = set(GRAMMAR_FEATURES) - health.features_covered
    covered = len(health.features_covered & set(GRAMMAR_FEATURES))
    total = len(GRAMMAR_FEATURES)
    health.coverage_percent = (covered / total) * 100 if total > 0 else 0.0

    # Add warnings
    if health.coverage_percent < 80:
        health.issues.append(
            f"Coverage below 80%: {health.coverage_percent:.1f}% "
            f"(missing: {', '.join(sorted(health.features_missing))})"
        )

    if health.duplicate_seeds > 0:
        health.issues.append(f"{health.duplicate_seeds} duplicate seed(s) found")

    return health


def print_human_report(health: CorpusHealth) -> None:
    """Print human-readable health report."""
    print()
    print("=" * 60)
    print("Seed Corpus Health Report")
    print("=" * 60)
    print()

    # Summary
    print(f"Total seeds:     {health.total_seeds}")
    print(f"Valid seeds:     {health.valid_seeds}")
    print(f"Invalid seeds:   {health.invalid_seeds}")
    print(f"Duplicates:      {health.duplicate_seeds}")
    print()

    # Coverage
    print(f"Grammar Feature Coverage: {health.coverage_percent:.1f}%")
    print(f"  Covered:  {', '.join(sorted(health.features_covered & set(GRAMMAR_FEATURES)))}")
    if health.features_missing:
        print(f"  Missing:  {', '.join(sorted(health.features_missing))}")
        print()
        print("Suggestions for missing features:")
        for feature in sorted(health.features_missing):
            if feature in FEATURE_SUGGESTIONS:
                print(f"  - {feature}: {FEATURE_SUGGESTIONS[feature]}")
    print()

    # Issues
    if health.issues:
        print("Issues:")
        for issue in health.issues:
            print(f"  - {issue}")
        print()

    # Duplicates detail
    if health.duplicates:
        print("Duplicate pairs:")
        for orig, dup in health.duplicates:
            print(f"  {orig.name} == {dup.name}")
        print()

    # Status
    print("=" * 60)
    if health.invalid_seeds == 0 and health.coverage_percent >= 80:
        print("[PASS] Corpus is healthy.")
    else:
        print("[WARN] Corpus needs attention.")
    print("=" * 60)


def print_json_report(health: CorpusHealth) -> None:
    """Print JSON health report."""
    suggestions = {}
    for feature in health.features_missing:
        if feature in FEATURE_SUGGESTIONS:
            suggestions[feature] = FEATURE_SUGGESTIONS[feature]

    report = {
        "status": "pass" if health.invalid_seeds == 0 and health.coverage_percent >= 80 else "warn",
        "total_seeds": health.total_seeds,
        "valid_seeds": health.valid_seeds,
        "invalid_seeds": health.invalid_seeds,
        "duplicate_seeds": health.duplicate_seeds,
        "coverage_percent": round(health.coverage_percent, 1),
        "features_covered": sorted(health.features_covered & set(GRAMMAR_FEATURES)),
        "features_missing": sorted(health.features_missing),
        "feature_suggestions": suggestions,
        "issues": health.issues,
        "duplicates": [[str(a), str(b)] for a, b in health.duplicates],
    }
    print(json.dumps(report, indent=2))


def print_coverage_report(health: CorpusHealth) -> None:
    """Print detailed coverage report."""
    print()
    print("=" * 60)
    print("Grammar Feature Coverage Detail")
    print("=" * 60)
    print()

    # Count which seeds cover each feature
    feature_counts: Counter[str] = Counter()
    feature_files: dict[str, list[str]] = {f: [] for f in GRAMMAR_FEATURES}

    for analysis in health.analyses:
        if analysis.valid:
            for feature in analysis.features:
                if feature in GRAMMAR_FEATURES:
                    feature_counts[feature] += 1
                    feature_files[feature].append(analysis.path.name)

    # Print table
    print(f"{'Feature':<25} {'Count':>6}  Files")
    print("-" * 60)

    for feature in sorted(GRAMMAR_FEATURES):
        count = feature_counts[feature]
        files = feature_files[feature][:3]  # Show up to 3 files
        files_str = ", ".join(files)
        if len(feature_files[feature]) > 3:
            files_str += f" (+{len(feature_files[feature]) - 3} more)"

        status = "[OK]" if count > 0 else "[MISSING]"
        print(f"{feature:<25} {count:>6}  {status} {files_str}")

    print()


def dedupe_corpus(_seeds_dir: Path, health: CorpusHealth, dry_run: bool = True) -> None:
    """Remove duplicate seeds from corpus."""
    if not health.duplicates:
        print("No duplicates to remove.")
        return

    print()
    print("=" * 60)
    print("Deduplication" + (" (dry run)" if dry_run else ""))
    print("=" * 60)
    print()

    for orig, dup in health.duplicates:
        if dry_run:
            print(f"Would remove: {dup.name} (duplicate of {orig.name})")
        else:
            dup.unlink()
            print(f"Removed: {dup.name} (duplicate of {orig.name})")

    print()
    if dry_run:
        print("Run with --dedupe --execute to actually remove duplicates.")


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Check seed corpus health")
    parser.add_argument("--json", action="store_true", help="Output JSON report")
    parser.add_argument("--coverage", action="store_true", help="Show detailed coverage report")
    parser.add_argument("--dedupe", action="store_true", help="Show duplicate removal plan")
    parser.add_argument(
        "--execute", action="store_true", help="Actually execute dedupe (with --dedupe)"
    )
    args = parser.parse_args()

    if not SEEDS_DIR.exists():
        if args.json:
            print('{"status":"error","error":"Seeds directory does not exist"}')
        else:
            print(f"[ERROR] Seeds directory does not exist: {SEEDS_DIR}")
        sys.exit(2)

    health = check_corpus_health(SEEDS_DIR)

    if args.dedupe:
        dedupe_corpus(SEEDS_DIR, health, dry_run=not args.execute)
    elif args.coverage:
        print_coverage_report(health)
    elif args.json:
        print_json_report(health)
    else:
        print_human_report(health)

    # Exit code based on health
    if health.invalid_seeds > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
