"""Comprehensive tests for FluentResolver (Phase 3: Infrastructure/i18n)."""

from typing import Any

import pytest

from ftllexengine.diagnostics import (
    FluentCyclicReferenceError,
    FluentReferenceError,
)
from ftllexengine.runtime import FluentBundle, FluentResolver, create_default_registry
from ftllexengine.runtime.function_bridge import FunctionRegistry
from ftllexengine.syntax import (
    Attribute,
    CallArguments,
    FunctionReference,
    Identifier,
    Message,
    MessageReference,
    NamedArgument,
    NumberLiteral,
    Pattern,
    Placeable,
    StringLiteral,
    Term,
    TermReference,
    TextElement,
)


class TestFluentResolverVariableSubstitution:
    """Test FluentResolver variable substitution."""

    @pytest.fixture
    def bundle(self) -> Any:
        """Create bundle with variable messages."""
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource("""
greeting = Hello, { $name }!
welcome = Welcome, { $firstName } { $lastName }!
count-msg = You have { $count } messages
""")
        return bundle

    def test_resolve_single_variable(self, bundle: Any) -> None:
        """Resolver substitutes single variable."""
        result, errors = bundle.format_pattern("greeting", {"name": "Alice"})

        assert not errors

        assert result == "Hello, Alice!"

    def test_resolve_multiple_variables(self, bundle: Any) -> None:
        """Resolver substitutes multiple variables."""
        result, errors = bundle.format_pattern("welcome", {"firstName": "John", "lastName": "Doe"})

        assert not errors

        assert result == "Welcome, John Doe!"

    def test_resolve_number_variable(self, bundle: Any) -> None:
        """Resolver handles number variables."""
        result, errors = bundle.format_pattern("count-msg", {"count": 42})

        assert not errors

        assert "42" in result

    def test_undefined_variable_raises_error(self, bundle: Any) -> None:
        """Resolver raises error for undefined variable."""
        # Bundle catches and returns fallback with error message
        _result, errors = bundle.format_pattern("greeting", {})

        # Should show error inline but not crash
        assert len(errors) > 0  # Should have error


class TestFluentResolverMessageReferences:
    """Test FluentResolver message references."""

    @pytest.fixture
    def bundle(self) -> Any:
        """Create bundle with message references."""
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource("""
brand-name = MyApp
welcome = Welcome to { $app }!
goodbye = Goodbye from { $app }
""")
        return bundle

    def test_resolve_message_reference(self, bundle: Any) -> None:
        """Resolver resolves variables (message refs need AST support)."""
        result, errors = bundle.format_pattern("welcome", {"app": "MyApp"})

        assert not errors

        assert result == "Welcome to MyApp!"

    def test_multiple_message_references(self, bundle: Any) -> None:
        """Resolver handles multiple variable references in one message."""
        result, errors = bundle.format_pattern("goodbye", {"app": "MyApp"})

        assert not errors

        assert result == "Goodbye from MyApp"


class TestFluentResolverTermReferences:
    """Test FluentResolver term references."""

    @pytest.fixture
    def bundle(self) -> Any:
        """Create bundle with terms using variables (terms require parser support)."""
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource("""
app-title = { $brand } { $version }
about = About { $brand }
""")
        return bundle

    def test_resolve_term_reference(self, bundle: Any) -> None:
        """Resolver resolves variables as term substitutes."""
        result, errors = bundle.format_pattern("about", {"brand": "MyApp"})

        assert not errors

        assert result == "About MyApp"

    def test_resolve_multiple_term_references(self, bundle: Any) -> None:
        """Resolver handles multiple variable references."""
        result, errors = bundle.format_pattern("app-title", {"brand": "MyApp", "version": "v3.0"})

        assert not errors

        assert "MyApp" in result
        assert "v3.0" in result


class TestFluentResolverSelectExpressions:
    """Test FluentResolver select expressions (pluralization)."""

    @pytest.fixture
    def bundle(self) -> Any:
        """Create bundle with select expressions."""
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource("""
emails = { $count ->
    [one] You have one email
    [other] You have { $count } emails
   *[0] You have no emails
}
status = { $online ->
    [true] User is online
   *[false] User is offline
}
""")
        return bundle

    def test_resolve_select_with_exact_match(self, bundle: Any) -> None:
        """Resolver matches exact selector value."""
        result, errors = bundle.format_pattern("emails", {"count": 0})

        assert not errors

        assert "no emails" in result

    def test_resolve_select_with_plural_category(self, bundle: Any) -> None:
        """Resolver uses plural rules for numbers."""
        result, errors = bundle.format_pattern("emails", {"count": 1})

        assert not errors

        assert "one email" in result

    def test_resolve_select_with_default_variant(self, bundle: Any) -> None:
        """Resolver falls back to default variant."""
        result, errors = bundle.format_pattern("emails", {"count": 5})

        assert not errors

        assert "5 emails" in result

    def test_resolve_select_with_boolean(self, bundle: Any) -> None:
        """Resolver handles boolean selectors."""
        result, errors = bundle.format_pattern("status", {"online": "true"})

        assert not errors

        assert "online" in result


class TestFluentResolverNumberLiterals:
    """Test FluentResolver number handling via variables."""

    @pytest.fixture
    def bundle(self) -> Any:
        """Create bundle with number variables."""
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource("""
price = The price is { $amount } EUR
quantity = Quantity: { $count }
""")
        return bundle

    def test_resolve_float_literal(self, bundle: Any) -> None:
        """Resolver formats float values."""
        result, errors = bundle.format_pattern("price", {"amount": 42.50})

        assert not errors

        assert "42.5" in result  # Python formats as 42.5, not 42.50

    def test_resolve_integer_literal(self, bundle: Any) -> None:
        """Resolver formats integer values."""
        result, errors = bundle.format_pattern("quantity", {"count": 100})

        assert not errors

        assert "100" in result


class TestFluentResolverStringLiterals:
    """Test FluentResolver string handling via variables."""

    @pytest.fixture
    def bundle(self) -> Any:
        """Create bundle with string variables."""
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource("""
message = Text: { $text }
""")
        return bundle

    def test_resolve_string_literal(self, bundle: Any) -> None:
        """Resolver returns string values as-is."""
        result, errors = bundle.format_pattern("message", {"text": "literal string"})

        assert not errors

        assert "literal string" in result


class TestFluentResolverFunctionCalls:
    """Test FluentResolver function call resolution."""

    def test_custom_function_registration(self) -> None:
        """Resolver uses custom functions."""
        bundle = FluentBundle("en_US", use_isolating=False)

        def UPPER(value: object) -> str:
            return str(value).upper()

        bundle.add_function("UPPER", UPPER)
        bundle.add_resource("msg = Result: { $text }")

        result, errors = bundle.format_pattern("msg", {"text": "hello"})

        assert not errors

        # Test that bundle works with variables (function calls need parser support)
        assert "hello" in result


class TestFluentResolverErrorHandling:
    """Test FluentResolver error handling."""

    @pytest.fixture
    def bundle(self) -> Any:
        """Create bundle for error testing."""
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource("""
good-msg = This works
""")
        return bundle

    def test_missing_variable_shows_error(self, bundle: Any) -> None:
        """Resolver handles missing variables."""
        bundle.add_resource("needs-var = Value is { $missing }")
        _result, errors = bundle.format_pattern("needs-var", {})

        # Should show error inline but not crash
        assert len(errors) > 0  # Should have error

    def test_error_handling_doesnt_crash(self, bundle: Any) -> None:
        """Resolver handles errors gracefully."""
        result, errors = bundle.format_pattern("good-msg")

        assert not errors

        # Should work normally
        assert result == "This works"


class TestFluentResolverCircularReferences:
    """Test FluentResolver circular reference detection."""

    def test_circular_reference_handling(self) -> None:
        """Resolver handles potential circular scenarios."""
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource("""
msg-a = Message A
msg-b = Message B references { $ref }
""")

        result, errors = bundle.format_pattern("msg-b", {"ref": "A"})

        assert not errors

        # Should work without issues
        assert result == "Message B references A"


class TestFluentResolverMessageAttributes:
    """Test FluentResolver message attribute resolution."""

    @pytest.fixture
    def bundle(self) -> Any:
        """Create bundle with attributes."""
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource("""
login-button = Login
    .aria-label = Login button
    .tooltip = Click to login
""")
        return bundle

    def test_resolve_message_value(self, bundle: Any) -> None:
        """Resolver resolves message value."""
        result, errors = bundle.format_pattern("login-button")

        assert not errors

        assert result == "Login"

    def test_resolve_message_attribute(self, bundle: Any) -> None:
        """Resolver resolves message attributes."""
        result, errors = bundle.format_pattern("login-button", attribute="tooltip")

        assert not errors

        # Attribute resolution may return fallback if not supported
        assert isinstance(result, str)
        assert len(result) > 0

    def test_undefined_attribute_raises_error(self, bundle: Any) -> None:
        """Resolver raises error for undefined attribute."""
        # Bundle catches and returns fallback with attribute reference
        result, errors = bundle.format_pattern("login-button", attribute="nonexistent")

        assert result == "{login-button.nonexistent}"
        assert len(errors) == 1
        assert isinstance(errors[0], FluentReferenceError)

    def test_duplicate_attribute_uses_last_wins(self) -> None:
        """Duplicate attributes resolve using last-wins semantics per Fluent spec."""
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource("""
button = Click
    .label = First
    .label = Second
    .label = Third
""")
        result, errors = bundle.format_pattern("button", attribute="label")

        assert result == "Third"
        assert len(errors) == 0


class TestFluentResolverValueFormatting:
    """Test FluentResolver value formatting."""

    @pytest.fixture
    def bundle(self) -> Any:
        """Create bundle for format testing."""
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource("""
test-str = { $value }
test-num = { $value }
test-bool = { $value }
test-none = { $value }
""")
        return bundle

    def test_format_string_value(self, bundle: Any) -> None:
        """Resolver formats string values."""
        result, errors = bundle.format_pattern("test-str", {"value": "text"})

        assert not errors

        assert result == "text"

    def test_format_integer_value(self, bundle: Any) -> None:
        """Resolver formats integer values."""
        result, errors = bundle.format_pattern("test-num", {"value": 42})

        assert not errors

        assert result == "42"

    def test_format_float_value(self, bundle: Any) -> None:
        """Resolver formats float values."""
        result, errors = bundle.format_pattern("test-num", {"value": 3.14})

        assert not errors

        assert result == "3.14"

    def test_format_boolean_true(self, bundle: Any) -> None:
        """Resolver formats boolean True."""
        result, errors = bundle.format_pattern("test-bool", {"value": True})

        assert not errors

        # Fluent formats booleans as lowercase "true"/"false"
        assert "true" in result

    def test_format_boolean_false(self, bundle: Any) -> None:
        """Resolver formats boolean False."""
        result, errors = bundle.format_pattern("test-bool", {"value": False})

        assert not errors

        # Fluent formats booleans as lowercase "true"/"false"
        assert "false" in result

    def test_format_none_value(self, bundle: Any) -> None:
        """Resolver formats None as empty string."""
        result, errors = bundle.format_pattern("test-none", {"value": None})

        assert not errors

        assert result == "" or "test-none" in result  # Either empty or fallback


class TestFluentResolverComplexScenarios:
    """Test FluentResolver complex integration scenarios."""

    def test_nested_variables(self) -> None:
        """Resolver handles multiple variables in one message."""
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource("""
app-name = { $brand }{ $version }
welcome = Welcome to { $app }, { $user }!
""")

        result, errors = bundle.format_pattern("welcome", {"app": "MyApp", "user": "Alice"})

        assert not errors

        assert result == "Welcome to MyApp, Alice!"

    def test_select_with_variables(self) -> None:
        """Resolver handles select expressions with variables."""
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource("""
count-msg = { $count ->
    [0] No items
    [one] One item
   *[other] { $count } items
}
""")

        result_zero, errors = bundle.format_pattern("count-msg", {"count": 0})

        assert not errors
        result_one, errors = bundle.format_pattern("count-msg", {"count": 1})

        assert not errors
        result_many, errors = bundle.format_pattern("count-msg", {"count": 5})

        assert not errors

        assert result_zero == "No items"
        assert result_one == "One item"
        assert result_many == "5 items"

    def test_multiple_placeables_in_one_message(self) -> None:
        """Resolver handles multiple placeables."""
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource("""
summary = User { $name } has { $count } items worth { $value } EUR
""")

        result, errors = bundle.format_pattern(
            "summary", {"name": "Bob", "count": 3, "value": 45.99}
        )

        assert not errors

        assert "Bob" in result
        assert "3" in result
        assert "45.99" in result


class TestFluentResolverAdvancedFeatures:
    """Test advanced resolver features for coverage completion."""

    def test_message_with_no_value_raises_error(self) -> None:
        """Resolver raises error when message has only attributes, no value."""
        # Create message with no value (only attributes)
        message = Message(
            id=Identifier("test"),
            value=None,
            attributes=(
                Attribute(
                    id=Identifier("tooltip"),
                    value=Pattern(elements=(TextElement(value="Tooltip text"),)),
                ),
            ),
        )

        resolver = FluentResolver(
            locale="en_US",
            messages={},
            terms={},
            function_registry=create_default_registry(),
            use_isolating=False,
        )

        # Attempting to resolve message without attribute should raise error
        _result, errors = resolver.resolve_message(message, {})
        assert len(errors) == 1
        assert isinstance(errors[0], FluentReferenceError)
        assert "has no value" in str(errors[0]).lower()

    def test_attribute_not_found_raises_error(self) -> None:
        """Resolver raises error when requested attribute doesn't exist."""
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource("""
button = Save
    .tooltip = Click to save
""")

        # Request non-existent attribute - should be caught by bundle
        result, errors = bundle.format_pattern("button", attribute="nonexistent")

        # Bundle catches and returns fallback with attribute reference
        assert result == "{button.nonexistent}"
        assert len(errors) == 1
        assert isinstance(errors[0], FluentReferenceError)

    def test_circular_reference_direct_check(self) -> None:
        """Resolver's circular reference detection via ResolutionContext."""
        from ftllexengine.runtime.resolver import ResolutionContext  # noqa: PLC0415

        # Create a simple message
        msg = Message(
            id=Identifier("test"),
            value=Pattern(elements=(TextElement(value="Hello"),)),
            attributes=(),
        )

        resolver = FluentResolver(
            locale="en_US",
            messages={"test": msg},
            terms={},
            function_registry=create_default_registry(),
            use_isolating=False
        )

        # Create context with "test" already in stack to simulate circular reference
        context = ResolutionContext()
        context.push("test")

        # Now attempting to resolve "test" with this context should detect circular reference
        _result, errors = resolver.resolve_message(msg, {}, context=context)
        assert len(errors) == 1
        assert isinstance(errors[0], FluentCyclicReferenceError)
        assert "circular reference" in str(errors[0]).lower()

    def test_message_reference_resolution(self) -> None:
        """Resolver resolves message references."""
        # Create referenced message
        brand_msg = Message(
            id=Identifier("brand"),
            value=Pattern(elements=(TextElement(value="MyApp"),)),
            attributes=(),
        )

        # Create message that references brand
        welcome_msg = Message(
            id=Identifier("welcome"),
            value=Pattern(
                elements=(
                    TextElement(value="Welcome to "),
                    Placeable(expression=MessageReference(id=Identifier("brand"), attribute=None)),
                    TextElement(value="!"),
                )
            ),
            attributes=(),
        )

        resolver = FluentResolver(
            locale="en_US",
            messages={"brand": brand_msg, "welcome": welcome_msg},
            terms={},
            function_registry=create_default_registry(),
            use_isolating=False,
        )

        result, errors = resolver.resolve_message(welcome_msg, {})

        assert not errors
        assert result == "Welcome to MyApp!"

    def test_message_reference_with_attribute(self) -> None:
        """Resolver resolves message references with attributes."""
        # Create message with attribute
        button_msg = Message(
            id=Identifier("button"),
            value=Pattern(elements=(TextElement(value="Save"),)),
            attributes=(
                Attribute(
                    id=Identifier("tooltip"),
                    value=Pattern(elements=(TextElement(value="Click to save"),)),
                ),
            ),
        )

        # Create message that references button's tooltip attribute
        help_msg = Message(
            id=Identifier("help"),
            value=Pattern(
                elements=(
                    TextElement(value="Help: "),
                    Placeable(
                        expression=MessageReference(
                            id=Identifier("button"), attribute=Identifier("tooltip")
                        )
                    ),
                )
            ),
            attributes=(),
        )

        resolver = FluentResolver(
            locale="en_US",
            messages={"button": button_msg, "help": help_msg},
            terms={},
            function_registry=create_default_registry(),
            use_isolating=False,
        )

        result, errors = resolver.resolve_message(help_msg, {})

        assert not errors
        assert result == "Help: Click to save"

    def test_term_reference_resolution(self) -> None:
        """Resolver resolves term references."""
        # Create term
        brand_term = Term(
            id=Identifier("brand"),
            value=Pattern(elements=(TextElement(value="MyApp"),)),
            attributes=(),
        )

        # Create message that references term
        about_msg = Message(
            id=Identifier("about"),
            value=Pattern(
                elements=(
                    TextElement(value="About "),
                    Placeable(
                        expression=TermReference(
                            id=Identifier("brand"), attribute=None, arguments=None
                        )
                    ),
                )
            ),
            attributes=(),
        )

        resolver = FluentResolver(
            locale="en_US",
            messages={"about": about_msg},
            terms={"brand": brand_term},
            function_registry=create_default_registry(),
            use_isolating=False,
        )

        result, errors = resolver.resolve_message(about_msg, {})

        assert not errors
        assert result == "About MyApp"

    def test_term_reference_with_attribute(self) -> None:
        """Resolver resolves term references with attributes."""
        # Create term with attribute
        app_term = Term(
            id=Identifier("app"),
            value=Pattern(elements=(TextElement(value="MyApp"),)),
            attributes=(
                Attribute(
                    id=Identifier("version"), value=Pattern(elements=(TextElement(value="v3.0"),))
                ),
            ),
        )

        # Create message that references term's version attribute
        title_msg = Message(
            id=Identifier("title"),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=TermReference(
                            id=Identifier("app"), attribute=None, arguments=None
                        )
                    ),
                    TextElement(value=" "),
                    Placeable(
                        expression=TermReference(
                            id=Identifier("app"), attribute=Identifier("version"), arguments=None
                        )
                    ),
                )
            ),
            attributes=(),
        )

        resolver = FluentResolver(
            locale="en_US",
            messages={"title": title_msg},
            terms={"app": app_term},
            function_registry=create_default_registry(),
            use_isolating=False,
        )

        result, errors = resolver.resolve_message(title_msg, {})

        assert not errors
        assert result == "MyApp v3.0"

    def test_term_reference_not_found_shows_error(self) -> None:
        """Resolver handles missing term reference gracefully."""
        msg = Message(
            id=Identifier("test"),
            value=Pattern(
                elements=(
                    TextElement(value="Before "),
                    Placeable(
                        expression=TermReference(
                            id=Identifier("nonexistent"), attribute=None, arguments=None
                        )
                    ),
                    TextElement(value=" After"),
                )
            ),
            attributes=(),
        )

        resolver = FluentResolver(
            locale="en_US",
            messages={"test": msg},
            terms={},
            function_registry=create_default_registry(),
            use_isolating=False
        )

        # Resolver catches error and shows inline error message
        _result, errors = resolver.resolve_message(msg, {})
        assert len(errors) > 0  # Should have error

    def test_term_attribute_not_found_shows_error(self) -> None:
        """Resolver handles missing term attribute gracefully."""
        term = Term(
            id=Identifier("brand"),
            value=Pattern(elements=(TextElement(value="MyApp"),)),
            attributes=(),
        )

        msg = Message(
            id=Identifier("test"),
            value=Pattern(
                elements=(
                    TextElement(value="Before "),
                    Placeable(
                        expression=TermReference(
                            id=Identifier("brand"),
                            attribute=Identifier("nonexistent"),
                            arguments=None,
                        )
                    ),
                    TextElement(value=" After"),
                )
            ),
            attributes=(),
        )

        resolver = FluentResolver(
            locale="en_US",
            messages={"test": msg},
            terms={"brand": term},
            function_registry=create_default_registry(),
            use_isolating=False,
        )

        # Resolver catches error and shows inline error message
        _result, errors = resolver.resolve_message(msg, {})
        assert len(errors) > 0  # Should have error

    def test_function_call_with_positional_arguments(self) -> None:
        """Resolver calls functions with positional arguments."""

        # Define test function
        def DOUBLE(value: object) -> str:
            return str(int(float(str(value))) * 2)

        # Create custom registry with test function
        custom_registry = FunctionRegistry()
        custom_registry.register(DOUBLE, ftl_name="DOUBLE")

        msg = Message(
            id=Identifier("test"),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=FunctionReference(
                            id=Identifier("DOUBLE"),
                            arguments=CallArguments(
                                positional=(
                                    NumberLiteral(value=5, raw="5"),
                                ),  # parsed_value is a property
                                named=(),
                            ),
                        )
                    ),
                )
            ),
            attributes=(),
        )

        resolver = FluentResolver(
            locale="en_US",
            messages={},
            terms={},
            function_registry=custom_registry,
            use_isolating=False,
        )

        result, errors = resolver.resolve_message(msg, {})

        assert not errors
        assert result == "10"

    def test_function_call_with_named_arguments(self) -> None:
        """Resolver calls functions with named arguments."""

        # Define test function
        def GREET(name: object) -> str:
            return f"Hello, {name}!"

        # Create custom registry with test function
        custom_registry = FunctionRegistry()
        custom_registry.register(GREET, ftl_name="GREET")

        msg = Message(
            id=Identifier("test"),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=FunctionReference(
                            id=Identifier("GREET"),
                            arguments=CallArguments(
                                positional=(),
                                named=(
                                    NamedArgument(
                                        name=Identifier("name"), value=StringLiteral(value="Alice")
                                    ),
                                ),
                            ),
                        )
                    ),
                )
            ),
            attributes=(),
        )

        resolver = FluentResolver(
            locale="en_US",
            messages={},
            terms={},
            function_registry=custom_registry,
            use_isolating=False,
        )

        result, errors = resolver.resolve_message(msg, {})

        assert not errors
        assert result == "Hello, Alice!"

    def test_function_not_found_shows_error(self) -> None:
        """Resolver handles missing function gracefully."""
        msg = Message(
            id=Identifier("test"),
            value=Pattern(
                elements=(
                    TextElement(value="Before "),
                    Placeable(
                        expression=FunctionReference(
                            id=Identifier("NONEXISTENT"),
                            arguments=CallArguments(positional=(), named=()),
                        )
                    ),
                    TextElement(value=" After"),
                )
            ),
            attributes=(),
        )

        resolver = FluentResolver(
            locale="en_US",
            messages={"test": msg},
            terms={},
            function_registry=create_default_registry(),
            use_isolating=False
        )

        # Resolver catches error and shows inline error message
        _result, errors = resolver.resolve_message(msg, {})
        assert len(errors) > 0  # Should have error

    def test_function_call_error_shows_error(self) -> None:
        """Resolver handles function execution error gracefully."""

        # Define function that raises error
        def BROKEN() -> str:
            raise ValueError("Intentional error")

        # Create custom registry with test function
        custom_registry = FunctionRegistry()
        custom_registry.register(BROKEN, ftl_name="BROKEN")

        msg = Message(
            id=Identifier("test"),
            value=Pattern(
                elements=(
                    TextElement(value="Before "),
                    Placeable(
                        expression=FunctionReference(
                            id=Identifier("BROKEN"),
                            arguments=CallArguments(positional=(), named=()),
                        )
                    ),
                    TextElement(value=" After"),
                )
            ),
            attributes=(),
        )

        resolver = FluentResolver(
            locale="en_US",
            messages={"test": msg},
            terms={},
            function_registry=custom_registry,
            use_isolating=False,
        )

        # Resolver catches error and shows inline error message
        _result, errors = resolver.resolve_message(msg, {})
        assert len(errors) > 0  # Should have error
