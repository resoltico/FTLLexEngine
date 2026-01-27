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
]


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
                if node.value:
                    visit_node(node.value)
                for attr in node.attributes:
                    visit_node(attr)
            case Term():
                features.add("term")
                if node.attributes:
                    features.add("attribute")
                if node.value:
                    visit_node(node.value)
                for attr in node.attributes:
                    visit_node(attr)
            case Comment():
                features.add("comment")
            case Attribute():
                features.add("attribute")
                if node.value:
                    visit_node(node.value)
            case SelectExpression():
                features.add("select_expression")
                visit_node(node.selector)
                for variant in node.variants:
                    # Check for numeric variant keys like [1], [3.14]
                    if isinstance(variant.key, NumberLiteral):
                        features.add("numeric_variant_key")
                    if variant.value:
                        visit_node(variant.value)
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
            case StringLiteral():
                features.add("string_literal")
            case NumberLiteral():
                features.add("number_literal")
            case Placeable():
                if isinstance(node.expression, Placeable):
                    features.add("nested_placeable")
                visit_node(node.expression)
            case TextElement():
                if "\n" in node.value:
                    features.add("multiline_pattern")
            case _:
                pass

        # Recursively visit pattern elements
        if hasattr(node, "elements"):
            for elem in node.elements:
                visit_node(elem)

    for entry in resource.entries:
        visit_node(entry)

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

        # Check for parse errors (junk)
        if junk_count > 0:
            junk_entries = [e for e in resource.entries if isinstance(e, Junk)]
            return SeedAnalysis(
                path=path,
                valid=False,
                error=f"Contains {junk_count} junk entries: {junk_entries[0].content[:50]}...",
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
    report = {
        "status": "pass" if health.invalid_seeds == 0 and health.coverage_percent >= 80 else "warn",
        "total_seeds": health.total_seeds,
        "valid_seeds": health.valid_seeds,
        "invalid_seeds": health.invalid_seeds,
        "duplicate_seeds": health.duplicate_seeds,
        "coverage_percent": round(health.coverage_percent, 1),
        "features_covered": sorted(health.features_covered & set(GRAMMAR_FEATURES)),
        "features_missing": sorted(health.features_missing),
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
