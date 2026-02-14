"""Absolute final coverage tests for last remaining branches.

Targets specific edge cases that are hard to hit with normal usage:
- PathResourceLoader edge case paths (localization.py:237->243)
- LocaleContext cache double-check pattern (locale_context.py:156)
- Datetime formatting pattern fallback (locale_context.py:384)
- Resolver loop continuation branches (resolver.py:278->274, 438->433)

Python 3.13+.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ftllexengine.diagnostics import FrozenFluentError
from ftllexengine.localization import PathResourceLoader
from ftllexengine.runtime.function_bridge import FunctionRegistry
from ftllexengine.runtime.locale_context import LocaleContext
from ftllexengine.runtime.resolution_context import ResolutionContext
from ftllexengine.runtime.resolver import FluentResolver
from ftllexengine.syntax.ast import (
    Identifier,
    Message,
    Pattern,
    TextElement,
    Variant,
)

# =============================================================================
# LOCALIZATION COVERAGE (Line 237->243)
# =============================================================================


def test_path_resource_loader_fallback_to_cwd():
    """Test PathResourceLoader._resolved_root caching fallback when no static prefix.

    Coverage Target: localization.py:225-237 (__post_init__)

    When base_path starts with {locale}, template_parts[0] will be empty string.
    After rstrip("/\\"), static_prefix will still be empty, so fallback to cwd.
    """
    # Create loader with {locale} at start
    loader = PathResourceLoader("{locale}/data/messages.ftl")

    # Should fall back to cwd since no static prefix before {locale}
    assert loader._resolved_root == Path.cwd().resolve()


# =============================================================================
# LOCALE CONTEXT COVERAGE (Lines 156, 384)
# =============================================================================


@pytest.fixture
def _clean_locale_cache():
    """Clear locale context cache before and after test."""
    LocaleContext.clear_cache()
    yield
    LocaleContext.clear_cache()


@pytest.mark.usefixtures("_clean_locale_cache")
def test_locale_context_cache_concurrent_creation_exact_timing():
    """Test double-check lock pattern with precise timing.

    Coverage Target: locale_context.py:156

    Forces two threads to enter the cache creation path simultaneously,
    ensuring one thread hits the double-check return at line 156.
    """
    # Use barrier to synchronize threads at critical section
    barrier1 = threading.Barrier(2)
    barrier2 = threading.Barrier(2)
    results = []

    def create_with_delay() -> None:
        # Both threads reach here
        barrier1.wait()

        # Both threads try to create
        ctx = LocaleContext.create("test-locale-xyz")
        results.append(ctx)

        # Sync after creation
        barrier2.wait()

    # Execute concurrently
    with ThreadPoolExecutor(max_workers=2) as executor:
        future1 = executor.submit(create_with_delay)
        future2 = executor.submit(create_with_delay)

        future1.result()
        future2.result()

    # Both should get same instance
    assert len(results) == 2
    assert results[0] is results[1]

    # Cache should have exactly one entry
    assert LocaleContext.cache_size() == 1


@pytest.mark.usefixtures("_clean_locale_cache")
def test_locale_context_datetime_pattern_as_string():
    """Test datetime formatting when pattern is string (not DateTimePattern object).

    Coverage Target: locale_context.py:384

    Some locales may have datetime_pattern as a plain string rather than
    a DateTimePattern object with format() method. This tests that fallback.
    """
    # Create context and datetime
    ctx = LocaleContext.create("en-US")
    dt = datetime(2025, 12, 25, 14, 30, 45, tzinfo=UTC)

    # Format with both date and time to trigger datetime_pattern logic
    # This should hit line 378-384, testing both hasattr branches
    result = ctx.format_datetime(dt, date_style="full", time_style="short")

    # Should produce valid formatted output
    assert "2025" in result or "25" in result
    assert ":" in result  # Time component present
    assert len(result) > 10  # Reasonable length for full date + time


# =============================================================================
# RESOLVER COVERAGE (Branches 278->274, 438->433)
# =============================================================================


def test_resolver_pattern_elements_all_text():
    """Test pattern with only TextElements (no Placeables).

    Coverage Target: resolver.py:278->274

    When pattern has only TextElements, the loop iterates without
    entering the Placeable branch, testing the loop continuation.
    """
    pattern = Pattern(
        elements=(
            TextElement(value="Hello "),
            TextElement(value="World"),
            TextElement(value="!"),
        )
    )

    message = Message(id=Identifier(name="test"), value=pattern, attributes=())
    resolver = FluentResolver(
        locale="en",
        messages={"test": message},
        terms={},
        function_registry=FunctionRegistry(),
        use_isolating=False,
    )

    context = ResolutionContext()
    errors: list[FrozenFluentError] = []

    result = resolver._resolve_pattern(pattern, {}, errors, context)

    # All text should be concatenated
    assert result == "Hello World!"
    assert not errors


def test_resolver_variant_matching_identifier_only():
    """Test variant matching with only Identifier keys (no NumberLiterals).

    Coverage Target: resolver.py:438->433

    When all variant keys are Identifiers (no NumberLiterals),
    the NumberLiteral branch is never taken.
    """
    resolver = FluentResolver(
        locale="en",
        messages={},
        terms={},
        function_registry=FunctionRegistry(),
        use_isolating=False,
    )

    # Create variants with only Identifier keys
    variants = [
        Variant(
            key=Identifier(name="male"),
            value=Pattern(elements=(TextElement(value="He"),)),
        ),
        Variant(
            key=Identifier(name="female"),
            value=Pattern(elements=(TextElement(value="She"),)),
        ),
        Variant(
            key=Identifier(name="other"),
            value=Pattern(elements=(TextElement(value="They"),)),
            default=True,
        ),
    ]

    # Test with string selector
    result = resolver._find_exact_variant(variants, "male", "male")
    assert result is not None
    assert result.key.name == "male"  # type: ignore[union-attr]

    # Test with no match - should return None (not enter NumberLiteral branch)
    result_none = resolver._find_exact_variant(variants, "unknown", "unknown")
    assert result_none is None


def test_resolver_empty_pattern_elements():
    """Test pattern resolution with empty elements tuple.

    Coverage: Ensures loop handles empty patterns correctly.
    """
    pattern = Pattern(elements=())

    message = Message(id=Identifier(name="test"), value=pattern, attributes=())
    resolver = FluentResolver(
        locale="en",
        messages={"test": message},
        terms={},
        function_registry=FunctionRegistry(),
        use_isolating=False,
    )

    context = ResolutionContext()
    errors: list[FrozenFluentError] = []

    result = resolver._resolve_pattern(pattern, {}, errors, context)

    # Empty pattern should produce empty string
    assert result == ""
    assert not errors
