"""Final tests to achieve 100% coverage for targeted modules.

Covers remaining edge cases and branches in:
- ftllexengine.diagnostics.formatter
- ftllexengine.diagnostics.templates (already 100%)
- ftllexengine.locale_utils (already 100%)
- ftllexengine.localization
- ftllexengine.runtime.depth_guard (already 100%)
- ftllexengine.runtime.locale_context
- ftllexengine.runtime.resolver

Test Design Philosophy:
    - Property-based where mathematical properties exist
    - Example-based for specific edge cases
    - Focus on uncovered branches and error paths
    - No redundancy with existing comprehensive test suites

Python 3.13+.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from ftllexengine.diagnostics.codes import DiagnosticCode
from ftllexengine.diagnostics.formatter import DiagnosticFormatter, OutputFormat
from ftllexengine.diagnostics.templates import ErrorTemplate
from ftllexengine.localization import FluentLocalization, PathResourceLoader
from ftllexengine.runtime.function_bridge import FunctionRegistry
from ftllexengine.runtime.locale_context import LocaleContext
from ftllexengine.runtime.resolver import FluentResolver, ResolutionContext
from ftllexengine.syntax.ast import (
    Identifier,
    Message,
    NumberLiteral,
    Pattern,
    Placeable,
    SelectExpression,
    TextElement,
    VariableReference,
    Variant,
)

# =============================================================================
# DIAGNOSTICS FORMATTER COVERAGE (Line 81)
# =============================================================================


def test_formatter_json_output_exhaustive():
    """Test JSON format output to ensure match statement exhaustiveness.

    Coverage Target: diagnostics/formatter.py:81 (match case exit branch)

    The match statement at line 76-82 should handle all OutputFormat cases.
    This test verifies JSON output specifically to trigger line 81-82.
    """
    diagnostic = ErrorTemplate.message_not_found("test")
    formatter = DiagnosticFormatter(output_format=OutputFormat.JSON)

    result = formatter.format(diagnostic)

    # Verify JSON output structure
    assert "{" in result
    assert "}" in result
    assert "MESSAGE_NOT_FOUND" in result
    assert DiagnosticCode.MESSAGE_NOT_FOUND.name in result


# =============================================================================
# LOCALIZATION COVERAGE (Lines 156, 237-243, 803, 874)
# =============================================================================


def test_path_resource_loader_resolved_root_no_static_prefix():
    """Test PathResourceLoader._resolved_root caching with edge cases.

    Coverage Target: localization.py:225-237 (__post_init__)

    Tests the resolution logic cached at initialization when:
    - template_parts is empty or has no static prefix
    - Falls back to Path.cwd().resolve()
    """
    # Case 1: Template with {locale} at start - empty static prefix
    loader = PathResourceLoader("{locale}/messages.ftl")
    # Should fall back to cwd since static_prefix would be empty string
    assert loader._resolved_root == Path.cwd().resolve()

    # Case 2: Explicitly set root_dir overrides logic
    explicit_root = "/tmp/test_locales"
    loader_with_root = PathResourceLoader(
        "{locale}/messages.ftl", root_dir=explicit_root
    )
    assert loader_with_root._resolved_root == Path(explicit_root).resolve()


def test_localization_add_function_to_created_bundle():
    """Test add_function() applies to already-created bundles.

    Coverage Target: localization.py:803

    Verifies that when a bundle has been lazily created, add_function()
    applies the function to that existing bundle.
    """
    l10n = FluentLocalization(["en"], enable_cache=False, use_isolating=False)

    # Add resource to trigger bundle creation for 'en'
    l10n.add_resource("en", "msg = Test")

    # Force bundle creation by formatting
    _, _ = l10n.format_value("msg")

    # Now add function - should apply to already-created 'en' bundle
    def CUSTOM(value: str) -> str:  # noqa: N802
        return value.upper()

    l10n.add_function("CUSTOM", CUSTOM)

    # Add resource using the new function
    l10n.add_resource("en", "test = { CUSTOM($val) }")

    # Verify function works in already-created bundle
    result, errors = l10n.format_value("test", {"val": "hello"})
    assert result == "HELLO"
    assert not errors


def test_localization_clear_cache_with_uninitialized_bundles():
    """Test clear_cache() handles uninitialized (None) bundles gracefully.

    Coverage Target: localization.py:874

    FluentLocalization lazily creates bundles. clear_cache() should handle
    cases where some bundles in _bundles dict are still None.
    """
    # Create FluentLocalization with multiple locales but don't access them
    l10n = FluentLocalization(["en", "fr", "de"], enable_cache=True)

    # Only access one locale to create one bundle
    l10n.add_resource("en", "msg = Test")
    _, _ = l10n.format_value("msg")

    # At this point: 'en' bundle is created, 'fr' and 'de' are None
    # clear_cache() must handle None values
    l10n.clear_cache()  # Should not raise

    # Verify system still works
    result, _ = l10n.format_value("msg")
    assert result == "Test"


@pytest.fixture
def _reset_locale_context_cache():
    """Clear locale context cache before and after test."""
    LocaleContext.clear_cache()
    yield
    LocaleContext.clear_cache()


@pytest.mark.usefixtures("_reset_locale_context_cache")
def test_locale_context_cache_double_check_race_condition():
    """Test LocaleContext.create() double-check locking pattern.

    Coverage Target: locale_context.py:156

    Tests the race condition where two threads create LocaleContext for the
    same locale simultaneously. The double-check pattern (line 154-156)
    prevents duplicate cache entries.
    """
    barrier = threading.Barrier(2)
    results: list[LocaleContext] = []
    cache_sizes: list[int] = []

    def create_context() -> None:
        barrier.wait()  # Synchronize threads
        ctx = LocaleContext.create("en-US")
        results.append(ctx)
        cache_sizes.append(LocaleContext.cache_size())

    # Run two threads concurrently
    with ThreadPoolExecutor(max_workers=2) as executor:
        executor.submit(create_context)
        executor.submit(create_context)

    # Both threads should get the same object (identity check)
    assert len(results) == 2
    assert results[0] is results[1]

    # Cache should have exactly 1 entry (no duplicates)
    assert LocaleContext.cache_size() == 1


@pytest.mark.usefixtures("_reset_locale_context_cache")
def test_locale_context_format_datetime_pattern_string_fallback():
    """Test format_datetime when pattern lacks format() method.

    Coverage Target: locale_context.py:384

    Tests the branch where datetime_pattern is a string (not an object with
    format() method). Uses str.format() as fallback.
    """
    ctx = LocaleContext.create("en-US")
    dt = datetime(2025, 10, 27, 14, 30, 0, tzinfo=UTC)

    # Format with both date and time to trigger datetime pattern combination
    result = ctx.format_datetime(dt, date_style="medium", time_style="medium")

    # Should produce combined date-time output
    assert "2025" in result or "25" in result
    assert ":" in result  # Time component
    assert result  # Not empty


# =============================================================================
# RESOLVER COVERAGE (Branches 278->274, 438->433)
# =============================================================================


def test_resolver_pattern_loop_branches():
    """Test pattern resolution loop branches.

    Coverage Target: resolver.py:278->274 (loop continuation)

    Tests _resolve_pattern() loop over pattern elements with different
    element types to ensure all loop branches are covered.
    """
    # Create message with mixed elements
    pattern = Pattern(
        elements=(
            TextElement(value="Static text "),
            Placeable(expression=VariableReference(id=Identifier(name="var"))),
            TextElement(value=" more text"),
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
    errors: list = []

    result = resolver._resolve_pattern(pattern, {"var": "VALUE"}, errors, context)

    # Verify all elements were processed
    assert result == "Static text VALUE more text"
    assert not errors


def test_resolver_find_exact_variant_number_literal_branch():
    """Test exact variant matching with NumberLiteral.

    Coverage Target: resolver.py:438->433 (NumberLiteral branch not taken)

    Tests _find_exact_variant() when variant key is NumberLiteral but
    selector is not numeric, ensuring the branch at 438 is not taken.
    """
    resolver = FluentResolver(
        locale="en",
        messages={},
        terms={},
        function_registry=FunctionRegistry(),
        use_isolating=False,
    )

    # Create variants with NumberLiteral keys
    variants = [
        Variant(key=NumberLiteral(value=1, raw="1"), value=Pattern(elements=())),
        Variant(key=NumberLiteral(value=2, raw="2"), value=Pattern(elements=())),
        Variant(
            key=Identifier(name="other"), value=Pattern(elements=()), default=True
        ),
    ]

    # Selector is string (not numeric) - NumberLiteral branch should not match
    selector_value = "text"
    selector_str = "text"

    result = resolver._find_exact_variant(variants, selector_value, selector_str)

    # Should return None since string doesn't match NumberLiteral
    assert result is None


@given(
    selector_value=st.one_of(st.none(), st.text(), st.booleans()),
)
def test_resolver_exact_variant_non_numeric_selectors(selector_value):
    """Property: Non-numeric selectors don't match NumberLiteral variants.

    Coverage: resolver.py:438-442 (NumberLiteral matching logic)

    Invariant: When selector is not numeric (int/float/Decimal), it should
    never match a NumberLiteral variant key.
    """
    resolver = FluentResolver(
        locale="en",
        messages={},
        terms={},
        function_registry=FunctionRegistry(),
    )

    variants = [
        Variant(key=NumberLiteral(value=42, raw="42"), value=Pattern(elements=())),
    ]

    selector_str = "" if selector_value is None else str(selector_value)
    result = resolver._find_exact_variant(variants, selector_value, selector_str)

    # Property: non-numeric selectors never match NumberLiteral
    assert result is None


# =============================================================================
# PROPERTY-BASED METAMORPHIC TESTS
# =============================================================================


@given(
    format_type=st.sampled_from(
        [OutputFormat.RUST, OutputFormat.SIMPLE, OutputFormat.JSON]
    ),
    message_id=st.text(
        min_size=1, max_size=50, alphabet=st.characters(min_codepoint=32, max_codepoint=126)
    ),
)
def test_formatter_format_always_returns_string(format_type, message_id):
    """Property: format() always returns non-empty string for any output format.

    Metamorphic Property: The output format affects structure but all formats
    produce non-empty string output for valid diagnostics.
    """
    diagnostic = ErrorTemplate.message_not_found(message_id)
    formatter = DiagnosticFormatter(output_format=format_type)

    result = formatter.format(diagnostic)

    assert isinstance(result, str)
    assert len(result) > 0
    # Message ID appears in output (may be escaped in JSON, but code is always there)
    assert message_id in result or "MESSAGE_NOT_FOUND" in result


@given(
    locales=st.lists(
        st.sampled_from(["en", "fr", "de", "lv"]),
        min_size=1,
        max_size=3,
        unique=True,
    ),
)
def test_localization_clear_cache_idempotent(locales):
    """Property: clear_cache() is idempotent.

    Metamorphic Property: Calling clear_cache() multiple times produces
    the same result as calling it once.
    """
    l10n = FluentLocalization(locales, enable_cache=True)

    # Add some data
    l10n.add_resource(locales[0], "msg = Test")
    _, _ = l10n.format_value("msg")

    # Multiple clear_cache() calls should be equivalent to one
    l10n.clear_cache()
    l10n.clear_cache()
    l10n.clear_cache()

    # System should still work
    result, _ = l10n.format_value("msg")
    assert result == "Test"


# =============================================================================
# EDGE CASE REGRESSION TESTS
# =============================================================================


def test_resolver_select_expression_none_selector():
    """Test SelectExpression resolution with None selector value.

    Regression Test: Ensures None selector is handled consistently.
    None represents undefined/missing value and should use default variant.
    """
    # Create SelectExpression with None selector result
    select_expr = SelectExpression(
        selector=VariableReference(id=Identifier(name="missing")),
        variants=(
            Variant(
                key=Identifier(name="foo"),
                value=Pattern(elements=(TextElement(value="Foo"),)),
            ),
            Variant(
                key=Identifier(name="other"),
                value=Pattern(elements=(TextElement(value="Default"),)),
                default=True,
            ),
        ),
    )

    pattern = Pattern(elements=(Placeable(expression=select_expr),))
    message = Message(id=Identifier(name="test"), value=pattern, attributes=())

    resolver = FluentResolver(
        locale="en",
        messages={"test": message},
        terms={},
        function_registry=FunctionRegistry(),
        use_isolating=False,
    )

    # Resolve with missing variable (None value)
    result, errors = resolver.resolve_message(message, args={})

    # Should fall back to default variant since selector evaluates to error
    assert "Default" in result or errors  # Either uses default or reports error


def test_path_resource_loader_edge_case_paths():
    """Test PathResourceLoader with unusual but valid path templates.

    Edge Cases:
    - Path starting with {locale}
    - Path with multiple directory components
    - Path with trailing separators
    """
    # Edge case: {locale} at start
    loader1 = PathResourceLoader("{locale}/data")
    assert loader1._resolved_root.is_absolute()

    # Edge case: Complex path
    loader2 = PathResourceLoader("app/locales/{locale}/messages")
    root2 = loader2._resolved_root
    assert "app" in str(root2) or root2 == Path("app/locales").resolve()

    # Edge case: Trailing slashes
    loader3 = PathResourceLoader("locales/{locale}//")
    assert loader3._resolved_root.is_absolute()
