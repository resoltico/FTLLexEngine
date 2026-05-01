# mypy: ignore-errors
"""Split test cases from tests/fuzz/test_localization_property.py."""

from tests.fuzz_localization_property_cases import *  # noqa: F403 - shared split test support

# ---------------------------------------------------------------------------
# Validation edge cases
# ---------------------------------------------------------------------------


class TestValidationEdgeCases:
    """Validation and defensive checks."""

    @given(
        locale=st.sampled_from(["en", "de"]),
        ws=st.sampled_from([" ", "\t", "\n"]),
        position=st.sampled_from(["leading", "trailing"]),
    )
    def test_add_resource_whitespace_locale_rejected(
        self, locale: str, ws: str, position: str,
    ) -> None:
        """add_resource trims locale boundaries and resolves them canonically."""
        event(f"position={position}")
        padded = ws + locale if position == "leading" else locale + ws
        l10n = FluentLocalization([locale])
        l10n.add_resource(padded, "msg = test")
        assert l10n.has_message("msg")
        assert l10n.locales == (normalize_locale(locale),)

    @given(
        locale=st.sampled_from(["en", "de"]),
        invalid_args=st.sampled_from([42, "str", [1, 2], True]),
    )
    def test_format_value_invalid_args_type(
        self, locale: str, invalid_args: int | str | list[int] | bool,
    ) -> None:
        """format_value with non-Mapping args returns error.

        strict=False: invalid-args error returned in tuple, not raised.
        """
        event("outcome=invalid_args")
        l10n = FluentLocalization([locale], strict=False)
        l10n.add_resource(locale, "msg = test")
        result, errors = l10n.format_value(
            "msg", invalid_args,  # type: ignore[arg-type]
        )
        assert result == "{???}"
        assert len(errors) > 0

    @given(
        locale=st.sampled_from(["en", "de"]),
        invalid_attr=st.sampled_from([42, Decimal("3.14"), ["a"], {"k": "v"}]),
    )
    def test_format_pattern_invalid_attribute_type(
        self,
        locale: str,
        invalid_attr: int | Decimal | list[str] | dict[str, str],
    ) -> None:
        """format_pattern with non-str attribute returns error.

        strict=False: invalid-attribute error returned in tuple, not raised.
        """
        event("outcome=invalid_attr")
        l10n = FluentLocalization([locale], strict=False)
        l10n.add_resource(locale, "msg = test\n    .a = v")
        result, errors = l10n.format_pattern(
            "msg", None,
            attribute=invalid_attr,  # type: ignore[arg-type]
        )
        assert result == "{???}"
        assert len(errors) > 0
