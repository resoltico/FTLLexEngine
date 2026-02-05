"""Tests for LocaleContext direct construction guard.

Achieves 100% coverage by testing the __post_init__ validation that prevents
direct construction without using factory methods.

Python 3.13+.
"""

from __future__ import annotations

import pytest
from babel import Locale

from ftllexengine.runtime.locale_context import LocaleContext


class TestLocaleContextDirectConstructionGuard:
    """Test __post_init__ validation prevents direct construction (lines 120-127)."""

    def test_direct_construction_without_token_raises_typeerror(self) -> None:
        """Direct construction without factory token raises TypeError (line 127).

        LocaleContext requires using create() or create_or_raise() factory methods.
        Direct construction via __init__ is blocked by __post_init__ validation.
        """
        babel_locale = Locale.parse("en_US")

        # Attempt direct construction without factory token
        with pytest.raises(TypeError) as exc_info:
            LocaleContext(
                locale_code="en-US",
                _babel_locale=babel_locale,
                # Missing _factory_token or wrong token triggers error
            )

        # Verify error message guides user to factory methods
        error_msg = str(exc_info.value)
        assert "LocaleContext.create()" in error_msg
        assert "LocaleContext.create_or_raise()" in error_msg
        assert "direct construction" in error_msg

    def test_direct_construction_with_wrong_token_raises_typeerror(self) -> None:
        """Direct construction with invalid token raises TypeError (line 122->127).

        Even if a token is provided, it must be the exact sentinel object.
        """
        babel_locale = Locale.parse("en_US")

        # Attempt with wrong token object
        wrong_token = object()

        with pytest.raises(TypeError) as exc_info:
            LocaleContext(
                locale_code="en-US",
                _babel_locale=babel_locale,
                _factory_token=wrong_token,
            )

        error_msg = str(exc_info.value)
        assert "LocaleContext.create()" in error_msg

    def test_direct_construction_with_none_token_raises_typeerror(self) -> None:
        """Direct construction with None token raises TypeError.

        None is the default value, so omitting _factory_token uses None.
        """
        babel_locale = Locale.parse("en_US")

        with pytest.raises(TypeError) as exc_info:
            LocaleContext(
                locale_code="en-US",
                _babel_locale=babel_locale,
                _factory_token=None,
            )

        error_msg = str(exc_info.value)
        assert "LocaleContext.create()" in error_msg
        assert "direct construction" in error_msg

    def test_factory_methods_work_correctly(self) -> None:
        """Factory methods bypass __post_init__ guard successfully.

        This validates that the factory token mechanism works correctly.
        """
        # Both factory methods should succeed
        ctx1 = LocaleContext.create("en-US")
        assert isinstance(ctx1, LocaleContext)
        # Note: locale_code may be normalized (en_US) due to caching
        assert ctx1.locale_code in {"en-US", "en_US"}

        ctx2 = LocaleContext.create_or_raise("de-DE")
        assert isinstance(ctx2, LocaleContext)
        # Note: locale_code may be normalized (de_DE) due to caching
        assert ctx2.locale_code in {"de-DE", "de_DE"}
