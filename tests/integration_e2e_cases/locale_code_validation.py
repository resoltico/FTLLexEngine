# mypy: ignore-errors
"""Split test cases from tests/test_integration_e2e.py."""

from tests.integration_e2e_cases import *  # noqa: F403 - shared split test support

# =============================================================================
# Locale Code Validation
# =============================================================================


class TestLocaleCodeValidation:
    """FluentBundle validates locale codes against BCP 47 format."""

    def test_posix_locale_with_charset_rejected(self) -> None:
        """POSIX locale string with charset suffix is rejected with BCP 47 guidance."""
        with pytest.raises(ValueError, match="Strip charset suffixes"):
            FluentBundle("en_US.UTF-8")

    def test_valid_bcp47_locales_accepted(self) -> None:
        """Valid BCP 47 locale codes are accepted by FluentBundle."""
        for locale in ("en-US", "de-DE", "zh-Hans-CN"):
            bundle = FluentBundle(locale, use_isolating=False)
            bundle.add_resource("hello = Hello")
            result, _ = bundle.format_pattern("hello")
            assert result == "Hello"
