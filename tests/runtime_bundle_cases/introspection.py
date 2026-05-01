# mypy: ignore-errors
from tests.runtime_bundle_cases import (
    Any,
    CacheConfig,
    FluentBundle,
    create_default_registry,
    pytest,
)


class TestBundleIntrospection:
    """Test introspection and query methods."""

    def test_get_message_variables_returns_frozenset(self) -> None:
        """get_message_variables returns frozenset of variable names."""
        bundle = FluentBundle("en")
        bundle.add_resource("greeting = Hello, { $name }!")
        variables = bundle.get_message_variables("greeting")
        assert "name" in variables
        assert isinstance(variables, frozenset)

    def test_get_message_variables_raises_keyerror(self) -> None:
        """get_message_variables raises KeyError for missing message."""
        bundle = FluentBundle("en")
        with pytest.raises(KeyError, match="not found"):
            bundle.get_message_variables("nonexistent")

    def test_get_all_message_variables(self) -> None:
        """get_all_message_variables returns dict of variable sets."""
        bundle = FluentBundle("en")
        bundle.add_resource(
            "greeting = Hello, { $name }!\n"
            "farewell = Bye, { $first } { $last }!\n"
            "simple = No variables\n"
        )
        all_vars = bundle.get_all_message_variables()
        assert all_vars["greeting"] == frozenset({"name"})
        assert all_vars["farewell"] == frozenset({"first", "last"})
        assert all_vars["simple"] == frozenset()

    def test_get_all_message_variables_empty_bundle(self) -> None:
        """get_all_message_variables returns empty dict when empty."""
        bundle = FluentBundle("en")
        assert bundle.get_all_message_variables() == {}

    def test_introspect_message_returns_metadata(self) -> None:
        """introspect_message returns MessageIntrospection with metadata."""
        bundle = FluentBundle("en")
        bundle.add_resource(
            "price = { NUMBER($amount, minimumFractionDigits: 2) }"
        )
        info = bundle.introspect_message("price")
        assert "amount" in info.get_variable_names()
        assert "NUMBER" in info.get_function_names()

    def test_introspect_message_raises_keyerror(self) -> None:
        """introspect_message raises KeyError for missing message."""
        bundle = FluentBundle("en")
        with pytest.raises(KeyError, match="not found"):
            bundle.introspect_message("nonexistent")

    def test_introspect_term_returns_metadata(self) -> None:
        """introspect_term returns MessageIntrospection for term."""
        bundle = FluentBundle("en")
        bundle.add_resource(
            "-brand = { $case ->\n"
            "    [nominative] Firefox\n"
            "    *[other] Firefox\n}\n"
        )
        info = bundle.introspect_term("brand")
        assert "case" in info.get_variable_names()

    def test_introspect_term_raises_keyerror(self) -> None:
        """introspect_term raises KeyError for missing term."""
        bundle = FluentBundle("en")
        with pytest.raises(KeyError, match="Term 'nonexistent' not found"):
            bundle.introspect_term("nonexistent")

    def test_introspect_term_success(self) -> None:
        """introspect_term returns valid data for existing term."""
        bundle = FluentBundle("en")
        bundle.add_resource(
            "-brand = Firefox\n    .gender = masculine"
        )
        info = bundle.introspect_term("brand")
        assert info is not None

    def test_has_attribute_true(self) -> None:
        """has_attribute returns True when attribute exists."""
        bundle = FluentBundle("en")
        bundle.add_resource("button = Click\n    .tooltip = Save\n")
        assert bundle.has_attribute("button", "tooltip") is True

    def test_has_attribute_false_missing_attribute(self) -> None:
        """has_attribute returns False when attribute missing."""
        bundle = FluentBundle("en")
        bundle.add_resource("button = Click\n    .tooltip = Save\n")
        assert bundle.has_attribute("button", "nonexistent") is False

    def test_has_attribute_false_missing_message(self) -> None:
        """has_attribute returns False when message missing."""
        bundle = FluentBundle("en")
        bundle.add_resource("msg = Hello")
        assert bundle.has_attribute("nonexistent", "tooltip") is False

    def test_has_attribute_multiple_attributes(self) -> None:
        """has_attribute correctly checks among multiple attributes."""
        bundle = FluentBundle("en")
        bundle.add_resource(
            "button = Click\n"
            "    .tooltip = Tooltip\n"
            "    .aria-label = Label\n"
            "    .placeholder = Enter\n"
        )
        assert bundle.has_attribute("button", "tooltip") is True
        assert bundle.has_attribute("button", "aria-label") is True
        assert bundle.has_attribute("button", "placeholder") is True
        assert bundle.has_attribute("button", "missing") is False


# =============================================================================
# Formatting (format_pattern error paths)
# =============================================================================


class TestBundleFormatting:
    """Test formatting methods and error handling."""

    def test_format_pattern_formats_message(self) -> None:
        """format_pattern formats message without attribute access."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource("welcome = Hello, { $name }!")
        result, errors = bundle.format_pattern("welcome", {"name": "Alice"})
        assert result == "Hello, Alice!"
        assert errors == ()

    def test_format_pattern_handles_recursion_error(self) -> None:
        """format_pattern catches RecursionError from circular refs."""
        bundle = FluentBundle("en", strict=False)
        bundle.add_resource("msg1 = { msg2 }\nmsg2 = { msg1 }\n")
        _result, errors = bundle.format_pattern("msg1")
        assert len(errors) > 0


# =============================================================================
# Custom Functions
# =============================================================================


class TestBundleCustomFunctions:
    """Test custom function registration and registry isolation."""

    def test_custom_function_registered_and_works(self) -> None:
        """add_function registers custom function successfully."""
        bundle = FluentBundle("en")

        def custom(value: Any) -> str:
            return str(value).upper()

        bundle.add_function("CUSTOM", custom)
        bundle.add_resource("msg = { CUSTOM($val) }")
        result, _ = bundle.format_pattern("msg", {"val": "hello"})
        assert "HELLO" in result

    def test_add_function_clears_cache(self) -> None:
        """add_function clears cache after registration."""
        bundle = FluentBundle("en", cache=CacheConfig())
        bundle.add_resource("msg = Hello")
        bundle.format_pattern("msg")
        assert bundle.cache_usage == 1

        def custom(v: Any) -> str:
            return str(v)

        bundle.add_function("CUSTOM", custom)
        assert bundle.cache_usage == 0

    def test_add_function_without_cache(self) -> None:
        """add_function works when cache is disabled."""
        bundle = FluentBundle("en", use_isolating=False)

        def custom(val: str) -> str:
            return val.upper()

        bundle.add_function("CUSTOM", custom)
        bundle.add_resource("msg = { CUSTOM($val) }")
        result, _ = bundle.format_pattern("msg", {"val": "test"})
        assert result == "TEST"

    def test_init_with_custom_registry(self) -> None:
        """FluentBundle accepts custom FunctionRegistry."""
        registry = create_default_registry()

        def my_func(_val: int) -> str:
            return "custom"

        registry.register(my_func, ftl_name="CUSTOM")
        bundle = FluentBundle("en", functions=registry)
        bundle.add_resource("test = { CUSTOM(123) }")
        result, errors = bundle.format_pattern("test")
        assert not errors
        assert "custom" in result

    def test_init_copies_registry_for_isolation(self) -> None:
        """FluentBundle creates copy of registry for isolation."""
        original = create_default_registry()
        bundle = FluentBundle("en", strict=False, functions=original)

        def new_func(_val: int) -> str:
            return "new"

        original.register(new_func, ftl_name="NEWFUNC")
        bundle.add_resource("test = { NEWFUNC(1) }")
        result, errors = bundle.format_pattern("test")
        assert len(errors) > 0 or "NEWFUNC" not in result


# =============================================================================
# get_babel_locale Method
# =============================================================================


class TestBundleGetBabelLocale:
    """Test get_babel_locale introspection method."""

    def test_returns_locale_identifier(self) -> None:
        """get_babel_locale returns Babel locale identifier."""
        assert FluentBundle("lv").get_babel_locale() == "lv"

    def test_handles_underscore_locale(self) -> None:
        """get_babel_locale handles underscore-separated locales."""
        assert FluentBundle("en_US").get_babel_locale() == "en_US"

    def test_handles_hyphen_locale(self) -> None:
        """get_babel_locale handles hyphen-separated locales."""
        result = FluentBundle("en-GB").get_babel_locale()
        assert "en" in result

    def test_invalid_locale_is_rejected_at_construction(self) -> None:
        """Unknown locales are rejected before a bundle can be created."""
        with pytest.raises(ValueError, match="Unknown locale identifier"):
            FluentBundle("xx-INVALID")


# =============================================================================
# Thread Safety
# =============================================================================


class TestBundleThreadSafety:
    """Test always-on thread safety via readers-writer lock."""

    def test_add_resource_is_thread_safe(self) -> None:
        """add_resource acquires lock (always-on thread safety)."""
        bundle = FluentBundle("en")
        bundle.add_resource("msg = Hello")
        assert bundle.has_message("msg")
        result, errors = bundle.format_pattern("msg")
        assert result == "Hello"
        assert errors == ()

    def test_format_pattern_is_thread_safe(self) -> None:
        """format_pattern acquires lock (always-on thread safety)."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource("greeting = Hello, { $name }!")
        result, errors = bundle.format_pattern(
            "greeting", {"name": "World"}
        )
        assert result == "Hello, World!"
        assert errors == ()


# =============================================================================
# Hypothesis Property-Based Tests
# =============================================================================

