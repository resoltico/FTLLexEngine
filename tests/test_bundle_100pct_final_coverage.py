"""Property-based tests for FluentBundle 100% coverage.

Targets specific uncovered lines using Hypothesis with semantic coverage events.
"""

from __future__ import annotations

import pytest
from hypothesis import event, example, given
from hypothesis import strategies as st

from ftllexengine.diagnostics import ErrorCategory
from ftllexengine.integrity import FormattingIntegrityError
from ftllexengine.runtime import FluentBundle
from ftllexengine.runtime.function_bridge import FunctionRegistry
from ftllexengine.runtime.functions import create_default_registry


class TestBundleInitTypeValidation:
    """Test FluentBundle.__init__ type validation for functions parameter."""

    @given(
        invalid_functions=st.one_of(
            st.dictionaries(st.text(min_size=1, max_size=10), st.integers()),
            st.lists(st.text()),
            st.integers(),
            st.text(),
            st.none(),
        )
    )
    def test_init_rejects_non_function_registry(
        self, invalid_functions: object
    ) -> None:
        """FluentBundle.__init__ raises TypeError for non-FunctionRegistry functions.

        Covers lines 307-311: Type validation at API boundary.

        Events emitted:
        - type={TypeName}: Type of invalid object passed
        """
        # Skip None case (valid input)
        if invalid_functions is None:
            event("type=NoneType_valid")
            return

        type_name = type(invalid_functions).__name__
        event(f"type={type_name}")

        with pytest.raises(
            TypeError,
            match="functions must be FunctionRegistry, not",
        ):
            FluentBundle("en_US", functions=invalid_functions)  # type: ignore[arg-type]

    @example(invalid_functions={"NUMBER": lambda x: x})  # dict with valid-looking content
    @example(invalid_functions=[])  # empty list
    @example(invalid_functions=42)  # integer
    @example(invalid_functions="not_a_registry")  # string
    @given(
        invalid_functions=st.one_of(
            st.dictionaries(st.text(min_size=1, max_size=5), st.integers(), min_size=1),
            st.lists(st.integers(), min_size=1),
        )
    )
    def test_init_type_error_message_includes_type_name(
        self, invalid_functions: object
    ) -> None:
        """TypeError message includes the actual type name for debugging.

        Covers lines 307-311: Error message construction.
        """
        type_name = type(invalid_functions).__name__

        with pytest.raises(TypeError) as exc_info:
            FluentBundle("en_US", functions=invalid_functions)  # type: ignore[arg-type]

        assert type_name in str(exc_info.value)
        assert "FunctionRegistry" in str(exc_info.value)
        assert "create_default_registry" in str(exc_info.value)


class TestBundlePropertyGetters:
    """Test FluentBundle property getters for complete coverage."""

    @given(
        max_expansion_size=st.integers(min_value=1000, max_value=10_000_000),
        locale=st.sampled_from(["en_US", "de_DE", "lv_LV", "ja_JP"]),
    )
    def test_max_expansion_size_property_getter(
        self, max_expansion_size: int, locale: str
    ) -> None:
        """FluentBundle.max_expansion_size property returns configured value.

        Covers line 616: Property getter for max_expansion_size.

        Events emitted:
        - boundary={category}: Boundary value category
        """
        # Emit boundary event
        if max_expansion_size < 10_000:
            event("boundary=small")
        elif max_expansion_size > 1_000_000:
            event("boundary=large")
        else:
            event("boundary=medium")

        bundle = FluentBundle(locale, max_expansion_size=max_expansion_size)

        assert bundle.max_expansion_size == max_expansion_size

    @given(
        locale=st.sampled_from(["en", "de", "lv", "pl", "ar", "ja"]),
        provide_custom_registry=st.booleans(),
    )
    def test_function_registry_property_getter(
        self, locale: str, provide_custom_registry: bool
    ) -> None:
        """FluentBundle.function_registry property returns registry.

        Covers line 634: Property getter for function_registry.

        Events emitted:
        - registry_type={shared|custom}: Registry source
        """
        if provide_custom_registry:
            event("registry_type=custom")
            custom_registry = create_default_registry()
            bundle = FluentBundle(locale, functions=custom_registry)
        else:
            event("registry_type=shared")
            bundle = FluentBundle(locale)

        registry = bundle.function_registry

        assert isinstance(registry, FunctionRegistry)
        # Verify registry is functional
        assert "NUMBER" in registry


class TestBundleCommentHandling:
    """Test FluentBundle handling of Comment entries in resources."""

    @given(
        num_comments=st.integers(min_value=1, max_value=10),
        comment_style=st.sampled_from(["single", "double", "triple"]),
    )
    def test_add_resource_with_comments_logs_debug(
        self, num_comments: int, comment_style: str
    ) -> None:
        """FluentBundle._register_resource handles Comment entries.

        Covers line 941->943: Comment case branch in match statement.

        Events emitted:
        - comment_count={n}: Number of comments in resource
        - comment_style={type}: Style of comment marker
        """
        event(f"comment_count={num_comments}")
        event(f"comment_style={comment_style}")

        # Build FTL source with standalone comment lines (produces Comment entries)
        ftl_lines = []
        comment_marker = {
            "single": "#",
            "double": "##",
            "triple": "###",
        }[comment_style]

        for i in range(num_comments):
            # Standalone comment lines produce Comment AST entries
            ftl_lines.append(f"{comment_marker} Comment line {i}")

        # Add a valid message after comments
        ftl_lines.append("")  # Blank line
        ftl_lines.append("msg = Hello")

        ftl_source = "\n".join(ftl_lines)

        bundle = FluentBundle("en_US")
        junk = bundle.add_resource(ftl_source)

        # Comments are ignored (not errors)
        assert len(junk) == 0
        assert bundle.has_message("msg")

    @example(num_standalone=1)
    @example(num_standalone=3)
    @example(num_standalone=10)
    @given(num_standalone=st.integers(min_value=1, max_value=20))
    def test_comments_do_not_create_junk_entries(self, num_standalone: int) -> None:
        """Comments are skipped during resource registration without creating Junk.

        Covers line 941->943: Comment case processing.

        Events emitted:
        - standalone_comments={n}: Number of standalone comment lines
        """
        event(f"standalone_comments={num_standalone}")

        # Build FTL source with standalone comment lines
        ftl_lines = ["### Section Header"]
        for i in range(num_standalone):
            ftl_lines.append(f"# Comment line {i}")

        ftl_lines.append("")  # Blank line
        ftl_lines.append("message = Value")
        ftl_lines.append("## Trailing section comment")

        ftl_source = "\n".join(ftl_lines)

        bundle = FluentBundle("en_US")
        junk = bundle.add_resource(ftl_source)

        assert len(junk) == 0  # Comments don't create Junk
        assert bundle.has_message("message")


class TestBundleStrictModeCacheInteraction:
    """Test FluentBundle strict mode with cached error results."""

    @given(
        locale=st.sampled_from(["en", "de", "lv", "pl"]),
        missing_var_name=st.text(
            alphabet=st.characters(
                min_codepoint=ord("a"), max_codepoint=ord("z")
            ),
            min_size=1,
            max_size=20,
        ),
    )
    def test_strict_mode_raises_on_cached_error_result(
        self, locale: str, missing_var_name: str
    ) -> None:
        """FluentBundle strict mode raises FormattingIntegrityError on cached errors.

        Covers line 1218: Strict mode check for cached entries with errors.

        Events emitted:
        - cache_hit_type={error|success}: Type of cached result
        """
        bundle = FluentBundle(locale, strict=True, enable_cache=True)

        # Create a message with a variable reference
        bundle.add_resource(f"msg = Hello {{ ${missing_var_name} }}")

        # First call: cache miss, raises FormattingIntegrityError
        with pytest.raises(FormattingIntegrityError) as exc_info_1:
            bundle.format_pattern("msg", {})

        event("cache_hit_type=error")

        assert exc_info_1.value.message_id == "msg"
        assert len(exc_info_1.value.fluent_errors) == 1
        assert (
            exc_info_1.value.fluent_errors[0].category == ErrorCategory.REFERENCE
        )

        # Second call: cache hit with error, should still raise
        with pytest.raises(FormattingIntegrityError) as exc_info_2:
            bundle.format_pattern("msg", {})

        # Verify same error structure (from cache)
        assert exc_info_2.value.message_id == "msg"
        assert len(exc_info_2.value.fluent_errors) == 1

    @given(
        locale=st.sampled_from(["en_US", "de_DE", "lv_LV"]),
        message_text=st.text(
            alphabet=st.characters(
                min_codepoint=ord("A"),
                max_codepoint=ord("z"),
                blacklist_categories=("Cc", "Cs"),
            ),
            min_size=1,
            max_size=50,
        ),
    )
    def test_strict_mode_cache_hit_without_errors_succeeds(
        self, locale: str, message_text: str
    ) -> None:
        """FluentBundle strict mode with cached success result returns normally.

        Covers line 1218: Branch not taken when cached entry has no errors.

        Events emitted:
        - cache_hit_type=success: Cached result without errors
        """
        # Filter to valid FTL message text (strip problematic chars)
        safe_text = "".join(
            c for c in message_text if c.isprintable() and c not in "{}#"
        ).strip()

        # Fallback to simple text if filtering resulted in empty string
        if not safe_text:
            safe_text = "Hello"

        bundle = FluentBundle(locale, strict=True, enable_cache=True)
        bundle.add_resource(f"msg = {safe_text}")

        # First call: cache miss
        result1, errors1 = bundle.format_pattern("msg")
        assert result1 == safe_text
        assert errors1 == ()

        event("cache_hit_type=success")

        # Second call: cache hit (no errors, should not raise)
        result2, errors2 = bundle.format_pattern("msg")
        assert result2 == safe_text
        assert errors2 == ()
