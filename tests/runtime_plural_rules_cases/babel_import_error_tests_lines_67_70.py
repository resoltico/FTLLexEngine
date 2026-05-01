# mypy: ignore-errors
"""Split test cases from tests/test_runtime_plural_rules.py."""

from tests.runtime_plural_rules_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# Babel ImportError Tests (lines 67-70)
# ============================================================================


class TestPluralRulesBabelImportError:
    """Test ImportError path when Babel is not installed (lines 67-70)."""

    def test_select_plural_category_raises_babel_import_error_when_babel_unavailable(
        self,
    ) -> None:
        """select_plural_category raises BabelImportError when Babel unavailable."""
        from ftllexengine.core.babel_compat import (
            BabelImportError,
        )

        # Temporarily hide babel from sys.modules
        babel_module = sys.modules.pop("babel", None)
        babel_core = sys.modules.pop("babel.core", None)
        babel_dates = sys.modules.pop("babel.dates", None)
        babel_numbers = sys.modules.pop("babel.numbers", None)

        # Reset sentinel so _check_babel_available() re-evaluates under the mock
        _bc._babel_available = None

        try:
            with patch.dict(sys.modules, {"babel": None, "babel.core": None}):
                original_import = __import__

                def mock_import_babel(
                    name: str,
                    globals_dict: dict[str, object] | None = None,
                    locals_dict: dict[str, object] | None = None,
                    fromlist: tuple[str, ...] = (),
                    level: int = 0,
                ) -> object:
                    if name == "babel" or name.startswith("babel."):
                        err = ModuleNotFoundError("No module named 'babel'")
                        err.name = "babel"
                        raise err
                    return original_import(name, globals_dict, locals_dict, fromlist, level)

                with patch("builtins.__import__", side_effect=mock_import_babel):
                    with pytest.raises(BabelImportError) as exc_info:
                        select_plural_category(42, "en-US")

                    assert "select_plural_category" in str(exc_info.value)
        finally:
            # Restore babel modules
            if babel_module is not None:
                sys.modules["babel"] = babel_module
            if babel_core is not None:
                sys.modules["babel.core"] = babel_core
            if babel_dates is not None:
                sys.modules["babel.dates"] = babel_dates
            if babel_numbers is not None:
                sys.modules["babel.numbers"] = babel_numbers
            # Reset sentinel so subsequent tests reinitialize with Babel available
            _bc._babel_available = None
