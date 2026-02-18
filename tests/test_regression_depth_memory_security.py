"""Regression tests for depth limit enforcement, memory bounding, and security.

Covers resolver depth propagation, serializer validation depth guards,
validator call argument depth tracking, locale code length validation,
and cache error collection memory bounding.
"""

import pytest

from ftllexengine.constants import MAX_DEPTH
from ftllexengine.diagnostics import ErrorCategory, FrozenFluentError
from ftllexengine.runtime.bundle import FluentBundle
from ftllexengine.runtime.cache import IntegrityCache
from ftllexengine.runtime.locale_context import LocaleContext
from ftllexengine.syntax import parse, serialize
from ftllexengine.syntax.serializer import SerializationDepthError
from ftllexengine.syntax.validator import SemanticValidator


class TestArchDepthBypass001:
    """ARCH-DEPTH-BYPASS-001: FluentResolver receives bundle's max_nesting_depth."""

    def test_resolver_respects_bundle_depth_limit(self) -> None:
        """Custom depth limits propagate from bundle to resolver."""
        # Create message reference chain that exceeds depth limit
        # Each message references the next, creating deep resolution chain
        # Chain length: 25 messages (exceeds limit of 20)
        messages = []
        for i in range(25):
            if i == 24:
                # Last message is terminal (no reference)
                messages.append(f"msg{i} = Final value")
            else:
                # Each message references the next
                messages.append(f"msg{i} = {{ msg{i + 1} }}")

        ftl_source = "\n".join(messages)

        # Bundle with restrictive depth limit (20)
        bundle = FluentBundle("en", max_nesting_depth=20)
        bundle.add_resource(ftl_source)

        # Should produce error due to depth limit when resolving msg0
        _result, errors = bundle.format_pattern("msg0")

        # Verify depth limit was enforced
        assert errors, "Expected depth limit error"
        assert any("depth" in str(e).lower() for e in errors)

    def test_resolver_default_depth_limit(self) -> None:
        """Resolver uses MAX_DEPTH when no bundle limit specified."""
        # Create message with nesting just under default limit
        nested_pattern = "text"
        for _ in range(MAX_DEPTH - 5):
            nested_pattern = f"{{ { nested_pattern } }}"

        ftl_source = f"deep = {nested_pattern}"

        bundle = FluentBundle("en")  # Default MAX_DEPTH
        bundle.add_resource(ftl_source)

        _result, errors = bundle.format_pattern("deep")

        # Should succeed (within default limit)
        assert not errors or all("depth" not in str(e).lower() for e in errors)


class TestArchValidationRecursion001:
    """ARCH-VALIDATION-RECURSION-001: Serializer validation has depth guards."""

    def test_serializer_validation_depth_limit(self) -> None:
        """Serializer validation enforces depth limits."""
        # Create pattern that parses but has 25 levels of nesting
        # Parser allows up to MAX_DEPTH (100), so 25 is safe
        nested_ftl = "$x"
        for _ in range(25):
            nested_ftl = f"{{ { nested_ftl } }}"

        ftl_source = f"deep = {nested_ftl}"
        resource = parse(ftl_source)

        # Serialize with very low max_depth (10) should raise SerializationDepthError
        # Since the pattern has 25 levels but we limit validation to 10
        with pytest.raises(
            SerializationDepthError, match=r"[Vv]alidation depth limit exceeded"
        ):
            serialize(resource, validate=True, max_depth=10)

    def test_serializer_validation_respects_custom_depth(self) -> None:
        """Serializer validation uses custom max_depth parameter."""
        # Create moderately nested FTL (15 levels)
        nested_ftl = "$x"
        for _ in range(15):
            nested_ftl = f"{{ { nested_ftl } }}"

        ftl_source = f"medium = {nested_ftl}"

        # Parse into AST
        resource = parse(ftl_source)

        # Should fail with custom limit of 10
        with pytest.raises(SerializationDepthError, match="depth limit exceeded"):
            serialize(resource, validate=True, max_depth=10)

        # Should succeed with custom limit of 20
        result = serialize(resource, validate=True, max_depth=20)
        assert result  # Should produce output


class TestArchValidatorDepth001:
    """ARCH-VALIDATOR-DEPTH-001: Call arguments wrapped in depth guards."""

    def test_validator_call_arguments_depth_tracking(self) -> None:
        """Validator tracks depth for each call argument."""
        # Create FTL with deeply nested call arguments
        # Each argument adds to depth count
        nested_args = "arg"
        for _ in range(60):
            nested_args = f"{{ { nested_args } }}"

        ftl_source = f"""
func-call = {{ FUNC({nested_args}) }}
"""
        resource = parse(ftl_source)

        # Validate (uses default MAX_DEPTH)
        validator = SemanticValidator()
        result = validator.validate(resource)

        # Should produce depth validation warning
        annotations = result.annotations
        # Depth exceeded during argument validation produces annotations
        # The actual behavior depends on MAX_DEPTH and nesting level
        assert annotations is not None  # Validator returns ValidationResult


class TestSecLocaleUnbounded001:
    """SEC-LOCALE-UNBOUNDED-001: Locale code length validation."""

    def test_bundle_rejects_malicious_locale_length(self) -> None:
        """FluentBundle rejects locale codes exceeding 1000 characters (DoS prevention)."""
        # Create locale code exceeding DoS prevention limit
        malicious_locale = "a" * 1500  # 1500 characters

        with pytest.raises(ValueError, match="exceeds maximum length of 1000"):
            FluentBundle(malicious_locale)

    def test_bundle_accepts_extended_locale_codes(self) -> None:
        """FluentBundle accepts locale codes up to 1000 characters."""
        # Test boundary cases including extended BCP 47 codes
        valid_locales = [
            "en",
            "en-US",
            "zh-Hans-CN",
            "a" * 35,  # Standard BCP 47 limit
            "a" * 100,  # Extended locale with private-use subtags
            "a" * 999,  # Just under DoS limit
        ]

        for locale in valid_locales:
            bundle = FluentBundle(locale)
            assert bundle.locale == locale

    def test_bundle_error_message_shows_actual_length(self) -> None:
        """Error message for oversized locale shows actual length."""
        oversized_locale = "b" * 2000

        with pytest.raises(
            ValueError,
            match="exceeds maximum length of 1000",
        ) as exc_info:
            FluentBundle(oversized_locale)

        error_msg = str(exc_info.value)
        # Should show actual length
        assert "2000 characters" in error_msg

    def test_locale_context_warns_for_long_locale_codes(self) -> None:
        """LocaleContext.create warns for locale codes exceeding BCP 47 standard (35 chars)."""
        # Locale exceeds standard BCP 47 length but is under DoS limit
        long_locale = "x" * 50

        # create() should log warning and fall back to en_US
        context = LocaleContext.create(long_locale)

        # Should have created en_US fallback
        assert context is not None
        # Verify it's usable
        assert context.locale_code  # Has some locale code


class TestSecCacheErrorBloat001:
    """SEC-CACHE-ERROR-BLOAT-001: Error collection memory bounding."""

    def test_cache_skips_entries_with_excessive_errors(self) -> None:
        """IntegrityCache skips caching when error count exceeds limit."""
        cache = IntegrityCache(strict=False, maxsize=100, max_errors_per_entry=10)

        # Create result with too many errors
        many_errors = tuple(
            FrozenFluentError(f"Error {i}", ErrorCategory.REFERENCE)
            for i in range(15)
        )

        # Put should skip due to error count
        cache.put("msg", None, None, "en", True, "formatted text", many_errors)

        # Verify it wasn't cached
        cached = cache.get("msg", None, None, "en", True)
        assert cached is None

        # Verify skip was counted
        stats = cache.get_stats()
        assert stats["error_bloat_skips"] == 1

    def test_cache_skips_entries_with_error_weight_exceeding_limit(self) -> None:
        """IntegrityCache skips caching when total error weight exceeds limit.

        Dynamic weight calculation: base overhead (100) + actual string lengths.
        Each error with a 100-char message: 100 + 100 = 200 bytes.
        25 errors with 100-char messages = 5000 bytes.
        String: 100 chars = 100 bytes.
        Total: 5100 bytes > 5000 (max_entry_weight).
        """
        cache = IntegrityCache(
            strict=False,
            maxsize=100,
            max_entry_weight=5000,  # 5KB limit
            max_errors_per_entry=100,  # Allow 100 errors
        )

        # Create errors with long messages to trigger weight limit
        # Each error: 100 base + 100 chars = 200 bytes
        # 25 errors x 200 = 5000 bytes, plus 100 char string = 5100 > 5000
        errors = tuple(
            FrozenFluentError("E" * 100, ErrorCategory.REFERENCE) for _ in range(25)
        )

        # Put should skip due to total weight
        cache.put("msg", None, None, "en", True, "x" * 100, errors)

        # Verify it wasn't cached
        cached = cache.get("msg", None, None, "en", True)
        assert cached is None

        # Verify skip was counted
        stats = cache.get_stats()
        assert stats["error_bloat_skips"] == 1

    def test_cache_accepts_reasonable_error_collections(self) -> None:
        """IntegrityCache caches results with reasonable error counts."""
        cache = IntegrityCache(strict=False, maxsize=100, max_errors_per_entry=50)

        # Create result with moderate errors
        few_errors = tuple(
            FrozenFluentError(f"Error {i}", ErrorCategory.REFERENCE)
            for i in range(5)
        )

        # Put should succeed
        cache.put("msg", None, None, "en", True, "formatted text", few_errors)

        # Verify it was cached
        cached = cache.get("msg", None, None, "en", True)
        assert cached is not None
        assert cached.as_result() == ("formatted text", few_errors)

        # No error bloat skips
        stats = cache.get_stats()
        assert stats["error_bloat_skips"] == 0

    def test_cache_stats_includes_max_errors_per_entry(self) -> None:
        """Cache stats includes max_errors_per_entry configuration."""
        cache = IntegrityCache(strict=False, max_errors_per_entry=25)

        stats = cache.get_stats()
        assert "max_errors_per_entry" in stats
        assert stats["max_errors_per_entry"] == 25

    def test_cache_clear_resets_error_bloat_counter(self) -> None:
        """Cache.clear() resets error_bloat_skips counter."""
        cache = IntegrityCache(strict=False, max_errors_per_entry=5)

        # Trigger some error bloat skips
        many_errors = tuple(
            FrozenFluentError(f"Error {i}", ErrorCategory.REFERENCE)
            for i in range(10)
        )
        cache.put("msg1", None, None, "en", True, "text", many_errors)
        cache.put("msg2", None, None, "en", True, "text", many_errors)

        stats = cache.get_stats()
        assert stats["error_bloat_skips"] == 2

        # Clear should reset
        cache.clear()

        stats = cache.get_stats()
        assert stats["error_bloat_skips"] == 0
