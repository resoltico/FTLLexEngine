# mypy: ignore-errors
"""Split test cases from tests/test_parsing_dates.py."""

from tests.parsing_dates_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# _babel_to_strptime: Timezone Token Handling
# ============================================================================


class TestBabelToStrptimeTimezoneToken:
    """Test _babel_to_strptime timezone token handling."""

    def test_timezone_z(self) -> None:
        """Timezone token 'z' is removed from pattern."""
        pattern, has_era = _babel_to_strptime("d MMM y HH:mm z")
        assert has_era is False
        assert "z" not in pattern

    def test_timezone_zzzz(self) -> None:
        """Timezone token 'zzzz' is removed."""
        pattern, has_era = _babel_to_strptime(
            "MMMM d, y 'at' h:mm a zzzz"
        )
        assert has_era is False
        assert "zzzz" not in pattern

    def test_timezone_v(self) -> None:
        """Timezone token 'v' is removed."""
        pattern, has_era = _babel_to_strptime("d MMM y HH:mm v")
        assert has_era is False
        assert "v" not in pattern

    def test_timezone_vvvv(self) -> None:
        """Timezone token 'vvvv' is removed."""
        pattern, has_era = _babel_to_strptime("d MMM y HH:mm vvvv")
        assert has_era is False
        assert "vvvv" not in pattern

    def test_timezone_o(self) -> None:
        """Timezone token 'O' is removed."""
        pattern, has_era = _babel_to_strptime("d MMM y HH:mm O")
        assert has_era is False
        assert "O" not in pattern

    def test_both_era_and_timezone(self) -> None:
        """Both era and timezone tokens handled correctly."""
        pattern, has_era = _babel_to_strptime("d MMM y G HH:mm z")
        assert has_era is True
        assert "G" not in pattern
        assert "z" not in pattern

    def test_none_token_fallthrough(self) -> None:
        """None-mapped token that is not era is silently dropped."""
        from ftllexengine.parsing import dates as dates_module

        original_map = dates_module._BABEL_TOKEN_MAP.copy()
        modified_map = original_map.copy()
        modified_map["QQQ"] = None

        with patch.object(
            dates_module, "_BABEL_TOKEN_MAP", modified_map
        ):
            pattern, has_era = _babel_to_strptime(
                "d MMM y QQQ HH:mm"
            )
            assert has_era is False
            assert "QQQ" not in pattern

    def test_zzzz_localized_gmt_skipped(self) -> None:
        """ZZZZ (localized GMT) is skipped entirely."""
        pattern, has_era = _babel_to_strptime("d MMM y HH:mm ZZZZ")
        assert has_era is False
        assert "ZZZZ" not in pattern
        assert "%z" not in pattern

    def test_trailing_whitespace_normalized(self) -> None:
        """Trailing whitespace from skipped tokens is stripped."""
        pattern, has_era = _babel_to_strptime("HH:mm zzzz")
        assert has_era is False
        assert pattern == "%H:%M"

    def test_multiple_trailing_spaces_normalized(self) -> None:
        """Multiple trailing spaces from skipped tokens stripped."""
        pattern, has_era = _babel_to_strptime("HH:mm   zzzz")
        assert has_era is False
        assert pattern == "%H:%M"
