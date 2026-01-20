"""Comprehensive property-based tests for diagnostics/codes.py module.

Tests all data structures and enumerations in the diagnostics codes module
using Hypothesis for property-based testing to achieve 100% coverage.

Tested components:
- ErrorCategory enum
- FrozenErrorContext dataclass
- DiagnosticCode enum
- SourceSpan dataclass
- Diagnostic dataclass and format_error() method

Properties tested:
- Immutability (frozen dataclasses)
- Construction with all field combinations
- Enum exhaustiveness and value uniqueness
- Format idempotence and consistency
- Branch coverage for all format_error() paths

Python 3.13+.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from ftllexengine.diagnostics.codes import (
    Diagnostic,
    DiagnosticCode,
    ErrorCategory,
    FrozenErrorContext,
    SourceSpan,
)

# ============================================================================
# HYPOTHESIS STRATEGIES
# ============================================================================


@st.composite
def source_span_strategy(draw: st.DrawFn) -> SourceSpan:
    """Generate arbitrary SourceSpan instances."""
    start = draw(st.integers(min_value=0, max_value=100000))
    end = draw(st.integers(min_value=start, max_value=start + 10000))
    line = draw(st.integers(min_value=1, max_value=10000))
    column = draw(st.integers(min_value=1, max_value=1000))
    return SourceSpan(start=start, end=end, line=line, column=column)


@st.composite
def frozen_error_context_strategy(draw: st.DrawFn) -> FrozenErrorContext:
    """Generate arbitrary FrozenErrorContext instances."""
    input_value = draw(st.text(min_size=0, max_size=100))
    locale_code = draw(st.text(min_size=0, max_size=20))
    parse_type = draw(st.text(min_size=0, max_size=20))
    fallback_value = draw(st.text(min_size=0, max_size=100))
    return FrozenErrorContext(
        input_value=input_value,
        locale_code=locale_code,
        parse_type=parse_type,
        fallback_value=fallback_value,
    )


@st.composite
def diagnostic_strategy(draw: st.DrawFn) -> Diagnostic:
    """Generate arbitrary Diagnostic instances with all possible field combinations."""
    code = draw(st.sampled_from(list(DiagnosticCode)))
    message = draw(st.text(min_size=1, max_size=200))
    span = draw(st.none() | source_span_strategy())
    hint = draw(st.none() | st.text(min_size=1, max_size=100))
    help_url = draw(st.none() | st.text(min_size=1, max_size=100))
    function_name = draw(st.none() | st.text(min_size=1, max_size=50))
    argument_name = draw(st.none() | st.text(min_size=1, max_size=50))
    expected_type = draw(st.none() | st.text(min_size=1, max_size=50))
    received_type = draw(st.none() | st.text(min_size=1, max_size=50))
    ftl_location = draw(st.none() | st.text(min_size=1, max_size=100))
    severity = draw(st.sampled_from(["error", "warning"]))
    resolution_path = draw(
        st.none()
        | st.lists(st.text(min_size=1, max_size=30), min_size=1, max_size=10).map(tuple)
    )

    return Diagnostic(
        code=code,
        message=message,
        span=span,
        hint=hint,
        help_url=help_url,
        function_name=function_name,
        argument_name=argument_name,
        expected_type=expected_type,
        received_type=received_type,
        ftl_location=ftl_location,
        severity=severity,  # type: ignore[arg-type]
        resolution_path=resolution_path,
    )


# ============================================================================
# PROPERTY TESTS: ErrorCategory
# ============================================================================


class TestErrorCategoryEnum:
    """Property-based tests for ErrorCategory enum."""

    def test_all_error_categories_defined(self) -> None:
        """All expected ErrorCategory values are defined."""
        assert ErrorCategory.REFERENCE.value == "reference"
        assert ErrorCategory.RESOLUTION.value == "resolution"
        assert ErrorCategory.CYCLIC.value == "cyclic"
        assert ErrorCategory.PARSE.value == "parse"
        assert ErrorCategory.FORMATTING.value == "formatting"

    def test_error_category_values_unique(self) -> None:
        """PROPERTY: All ErrorCategory values are unique."""
        values = [category.value for category in ErrorCategory]
        assert len(values) == len(set(values))

    def test_error_category_exhaustive(self) -> None:
        """All expected ErrorCategory members exist."""
        category_values = {c.value for c in ErrorCategory}
        expected = {"reference", "resolution", "cyclic", "parse", "formatting"}
        assert category_values == expected

    @given(category=st.sampled_from(list(ErrorCategory)))
    def test_error_category_value_is_string(self, category: ErrorCategory) -> None:
        """PROPERTY: All ErrorCategory values are strings."""
        assert isinstance(category.value, str)
        assert len(category.value) > 0


# ============================================================================
# PROPERTY TESTS: FrozenErrorContext
# ============================================================================


class TestFrozenErrorContextDataclass:
    """Property-based tests for FrozenErrorContext dataclass."""

    def test_frozen_error_context_default_construction(self) -> None:
        """FrozenErrorContext can be constructed with defaults."""
        context = FrozenErrorContext()
        assert context.input_value == ""
        assert context.locale_code == ""
        assert context.parse_type == ""
        assert context.fallback_value == ""

    @given(context=frozen_error_context_strategy())
    def test_frozen_error_context_immutable(self, context: FrozenErrorContext) -> None:
        """PROPERTY: FrozenErrorContext instances are immutable (frozen)."""
        try:
            context.input_value = "modified"  # type: ignore[misc]
            msg = "Expected FrozenInstanceError"
            raise AssertionError(msg)
        except AttributeError:
            pass

    @given(context=frozen_error_context_strategy())
    def test_frozen_error_context_preserves_fields(
        self, context: FrozenErrorContext
    ) -> None:
        """PROPERTY: FrozenErrorContext preserves all field values."""
        # All fields should be strings
        assert isinstance(context.input_value, str)
        assert isinstance(context.locale_code, str)
        assert isinstance(context.parse_type, str)
        assert isinstance(context.fallback_value, str)

    @given(
        input_value=st.text(max_size=100),
        locale_code=st.text(max_size=20),
        parse_type=st.text(max_size=20),
        fallback_value=st.text(max_size=100),
    )
    def test_frozen_error_context_construction_with_values(
        self,
        input_value: str,
        locale_code: str,
        parse_type: str,
        fallback_value: str,
    ) -> None:
        """PROPERTY: FrozenErrorContext construction preserves all arguments."""
        context = FrozenErrorContext(
            input_value=input_value,
            locale_code=locale_code,
            parse_type=parse_type,
            fallback_value=fallback_value,
        )
        assert context.input_value == input_value
        assert context.locale_code == locale_code
        assert context.parse_type == parse_type
        assert context.fallback_value == fallback_value


# ============================================================================
# PROPERTY TESTS: DiagnosticCode
# ============================================================================


class TestDiagnosticCodeEnum:
    """Property-based tests for DiagnosticCode enum."""

    def test_diagnostic_code_values_unique(self) -> None:
        """PROPERTY: All DiagnosticCode values are unique."""
        values = [code.value for code in DiagnosticCode]
        assert len(values) == len(set(values))

    @given(code=st.sampled_from(list(DiagnosticCode)))
    def test_diagnostic_code_value_is_integer(self, code: DiagnosticCode) -> None:
        """PROPERTY: All DiagnosticCode values are integers."""
        assert isinstance(code.value, int)
        assert code.value > 0

    def test_reference_error_codes_in_range(self) -> None:
        """Reference error codes are in 1000-1999 range."""
        reference_codes = [
            DiagnosticCode.MESSAGE_NOT_FOUND,
            DiagnosticCode.ATTRIBUTE_NOT_FOUND,
            DiagnosticCode.TERM_NOT_FOUND,
            DiagnosticCode.TERM_ATTRIBUTE_NOT_FOUND,
            DiagnosticCode.VARIABLE_NOT_PROVIDED,
            DiagnosticCode.MESSAGE_NO_VALUE,
        ]
        for code in reference_codes:
            assert 1000 <= code.value < 2000

    def test_resolution_error_codes_in_range(self) -> None:
        """Resolution error codes are in 2000-2999 range."""
        resolution_codes = [
            DiagnosticCode.CYCLIC_REFERENCE,
            DiagnosticCode.MAX_DEPTH_EXCEEDED,
            DiagnosticCode.NO_VARIANTS,
            DiagnosticCode.FUNCTION_NOT_FOUND,
            DiagnosticCode.FUNCTION_FAILED,
            DiagnosticCode.UNKNOWN_EXPRESSION,
            DiagnosticCode.TYPE_MISMATCH,
            DiagnosticCode.INVALID_ARGUMENT,
            DiagnosticCode.ARGUMENT_REQUIRED,
            DiagnosticCode.PATTERN_INVALID,
            DiagnosticCode.FUNCTION_ARITY_MISMATCH,
            DiagnosticCode.TERM_POSITIONAL_ARGS_IGNORED,
            DiagnosticCode.PLURAL_SUPPORT_UNAVAILABLE,
            DiagnosticCode.FORMATTING_FAILED,
        ]
        for code in resolution_codes:
            assert 2000 <= code.value < 3000

    def test_syntax_error_codes_in_range(self) -> None:
        """Syntax error codes are in 3000-3999 range."""
        syntax_codes = [
            DiagnosticCode.UNEXPECTED_EOF,
            DiagnosticCode.INVALID_CHARACTER,
            DiagnosticCode.EXPECTED_TOKEN,
            DiagnosticCode.PARSE_JUNK,
            DiagnosticCode.PARSE_NESTING_DEPTH_EXCEEDED,
        ]
        for code in syntax_codes:
            assert 3000 <= code.value < 4000

    def test_parsing_error_codes_in_range(self) -> None:
        """Parsing error codes are in 4000-4999 range."""
        parsing_codes = [
            DiagnosticCode.PARSE_NUMBER_FAILED,
            DiagnosticCode.PARSE_DECIMAL_FAILED,
            DiagnosticCode.PARSE_DATE_FAILED,
            DiagnosticCode.PARSE_DATETIME_FAILED,
            DiagnosticCode.PARSE_CURRENCY_FAILED,
            DiagnosticCode.PARSE_LOCALE_UNKNOWN,
            DiagnosticCode.PARSE_CURRENCY_AMBIGUOUS,
            DiagnosticCode.PARSE_CURRENCY_SYMBOL_UNKNOWN,
            DiagnosticCode.PARSE_AMOUNT_INVALID,
            DiagnosticCode.PARSE_CURRENCY_CODE_INVALID,
        ]
        for code in parsing_codes:
            assert 4000 <= code.value < 5000

    def test_validation_error_codes_in_range(self) -> None:
        """Validation error codes are in 5000-5099 range."""
        validation_codes = [
            DiagnosticCode.VALIDATION_TERM_NO_VALUE,
            DiagnosticCode.VALIDATION_SELECT_NO_DEFAULT,
            DiagnosticCode.VALIDATION_SELECT_NO_VARIANTS,
            DiagnosticCode.VALIDATION_VARIANT_DUPLICATE,
            DiagnosticCode.VALIDATION_NAMED_ARG_DUPLICATE,
        ]
        for code in validation_codes:
            assert 5000 <= code.value < 5100

    def test_validation_warning_codes_in_range(self) -> None:
        """Validation warning codes are in 5100-5199 range."""
        warning_codes = [
            DiagnosticCode.VALIDATION_PARSE_ERROR,
            DiagnosticCode.VALIDATION_CRITICAL_PARSE_ERROR,
            DiagnosticCode.VALIDATION_DUPLICATE_ID,
            DiagnosticCode.VALIDATION_NO_VALUE_OR_ATTRS,
            DiagnosticCode.VALIDATION_UNDEFINED_REFERENCE,
            DiagnosticCode.VALIDATION_CIRCULAR_REFERENCE,
            DiagnosticCode.VALIDATION_CHAIN_DEPTH_EXCEEDED,
            DiagnosticCode.VALIDATION_DUPLICATE_ATTRIBUTE,
            DiagnosticCode.VALIDATION_SHADOW_WARNING,
            DiagnosticCode.VALIDATION_TERM_POSITIONAL_ARGS,
        ]
        for code in warning_codes:
            assert 5100 <= code.value < 5200


# ============================================================================
# PROPERTY TESTS: SourceSpan
# ============================================================================


class TestSourceSpanDataclass:
    """Property-based tests for SourceSpan dataclass."""

    @given(span=source_span_strategy())
    def test_source_span_immutable(self, span: SourceSpan) -> None:
        """PROPERTY: SourceSpan instances are immutable (frozen)."""
        try:
            span.start = 999  # type: ignore[misc]
            msg = "Expected FrozenInstanceError"
            raise AssertionError(msg)
        except AttributeError:
            pass

    @given(span=source_span_strategy())
    def test_source_span_preserves_fields(self, span: SourceSpan) -> None:
        """PROPERTY: SourceSpan preserves all field values."""
        assert isinstance(span.start, int)
        assert isinstance(span.end, int)
        assert isinstance(span.line, int)
        assert isinstance(span.column, int)
        assert span.start >= 0
        assert span.end >= span.start
        assert span.line >= 1
        assert span.column >= 1

    @given(
        start=st.integers(min_value=0, max_value=10000),
        length=st.integers(min_value=0, max_value=1000),
        line=st.integers(min_value=1, max_value=1000),
        column=st.integers(min_value=1, max_value=200),
    )
    def test_source_span_construction(
        self, start: int, length: int, line: int, column: int
    ) -> None:
        """PROPERTY: SourceSpan construction preserves all arguments."""
        end = start + length
        span = SourceSpan(start=start, end=end, line=line, column=column)
        assert span.start == start
        assert span.end == end
        assert span.line == line
        assert span.column == column


# ============================================================================
# PROPERTY TESTS: Diagnostic
# ============================================================================


class TestDiagnosticDataclass:
    """Property-based tests for Diagnostic dataclass."""

    @given(diagnostic=diagnostic_strategy())
    def test_diagnostic_immutable(self, diagnostic: Diagnostic) -> None:
        """PROPERTY: Diagnostic instances are immutable (frozen)."""
        try:
            diagnostic.message = "modified"  # type: ignore[misc]
            msg = "Expected FrozenInstanceError"
            raise AssertionError(msg)
        except AttributeError:
            pass

    @given(diagnostic=diagnostic_strategy())
    def test_diagnostic_preserves_code_and_message(
        self, diagnostic: Diagnostic
    ) -> None:
        """PROPERTY: Diagnostic preserves code and message fields."""
        assert isinstance(diagnostic.code, DiagnosticCode)
        assert isinstance(diagnostic.message, str)
        assert len(diagnostic.message) > 0

    @given(diagnostic=diagnostic_strategy())
    def test_diagnostic_format_error_is_idempotent(
        self, diagnostic: Diagnostic
    ) -> None:
        """PROPERTY: format_error() is idempotent (same output on repeated calls)."""
        first = diagnostic.format_error()
        second = diagnostic.format_error()
        assert first == second

    @given(diagnostic=diagnostic_strategy())
    def test_diagnostic_format_error_contains_code(
        self, diagnostic: Diagnostic
    ) -> None:
        """PROPERTY: Formatted diagnostic contains error code name."""
        formatted = diagnostic.format_error()
        assert diagnostic.code.name in formatted

    @given(diagnostic=diagnostic_strategy())
    def test_diagnostic_format_error_contains_message(
        self, diagnostic: Diagnostic
    ) -> None:
        """PROPERTY: Formatted diagnostic contains error message."""
        formatted = diagnostic.format_error()
        assert diagnostic.message in formatted

    @given(diagnostic=diagnostic_strategy())
    def test_diagnostic_format_error_nonempty(self, diagnostic: Diagnostic) -> None:
        """PROPERTY: format_error() always returns non-empty string."""
        formatted = diagnostic.format_error()
        assert isinstance(formatted, str)
        assert len(formatted) > 0

    @given(
        code=st.sampled_from(list(DiagnosticCode)),
        message=st.text(min_size=1, max_size=100),
    )
    def test_diagnostic_minimal_construction(
        self, code: DiagnosticCode, message: str
    ) -> None:
        """PROPERTY: Diagnostic can be constructed with minimal fields."""
        diagnostic = Diagnostic(code=code, message=message)
        assert diagnostic.code == code
        assert diagnostic.message == message
        assert diagnostic.span is None
        assert diagnostic.hint is None
        assert diagnostic.help_url is None
        assert diagnostic.severity == "error"


# ============================================================================
# UNIT TESTS: Diagnostic.format_error() Branch Coverage
# ============================================================================


class TestDiagnosticFormatErrorBranches:
    """Unit tests for Diagnostic.format_error() to cover all branches."""

    def test_format_error_with_span(self) -> None:
        """format_error() includes span location when present."""
        span = SourceSpan(start=10, end=20, line=5, column=10)
        diagnostic = Diagnostic(
            code=DiagnosticCode.MESSAGE_NOT_FOUND,
            message="Message 'hello' not found",
            span=span,
        )

        result = diagnostic.format_error()

        assert "error[MESSAGE_NOT_FOUND]: Message 'hello' not found" in result
        assert "--> line 5, column 10" in result

    def test_format_error_with_ftl_location_no_span(self) -> None:
        """format_error() uses ftl_location when span is None (line 223)."""
        diagnostic = Diagnostic(
            code=DiagnosticCode.MESSAGE_NOT_FOUND,
            message="Message 'hello' not found",
            ftl_location="main.ftl:42",
        )

        result = diagnostic.format_error()

        assert "error[MESSAGE_NOT_FOUND]: Message 'hello' not found" in result
        assert "--> main.ftl:42" in result

    def test_format_error_with_function_name(self) -> None:
        """format_error() includes function_name when present (line 226)."""
        diagnostic = Diagnostic(
            code=DiagnosticCode.FUNCTION_FAILED,
            message="Function failed",
            function_name="NUMBER",
        )

        result = diagnostic.format_error()

        assert "error[FUNCTION_FAILED]: Function failed" in result
        assert "= function: NUMBER" in result

    def test_format_error_with_argument_name(self) -> None:
        """format_error() includes argument_name when present (line 229)."""
        diagnostic = Diagnostic(
            code=DiagnosticCode.TYPE_MISMATCH,
            message="Type mismatch",
            argument_name="value",
        )

        result = diagnostic.format_error()

        assert "error[TYPE_MISMATCH]: Type mismatch" in result
        assert "= argument: value" in result

    def test_format_error_with_expected_type(self) -> None:
        """format_error() includes expected_type when present (line 232)."""
        diagnostic = Diagnostic(
            code=DiagnosticCode.TYPE_MISMATCH,
            message="Type mismatch",
            expected_type="Number",
        )

        result = diagnostic.format_error()

        assert "error[TYPE_MISMATCH]: Type mismatch" in result
        assert "= expected: Number" in result

    def test_format_error_with_received_type(self) -> None:
        """format_error() includes received_type when present (line 235)."""
        diagnostic = Diagnostic(
            code=DiagnosticCode.TYPE_MISMATCH,
            message="Type mismatch",
            received_type="String",
        )

        result = diagnostic.format_error()

        assert "error[TYPE_MISMATCH]: Type mismatch" in result
        assert "= received: String" in result

    def test_format_error_with_resolution_path(self) -> None:
        """format_error() includes resolution_path when present (lines 238-239)."""
        diagnostic = Diagnostic(
            code=DiagnosticCode.CYCLIC_REFERENCE,
            message="Circular reference detected",
            resolution_path=("message1", "term1", "message2"),
        )

        result = diagnostic.format_error()

        assert "error[CYCLIC_REFERENCE]: Circular reference detected" in result
        assert "= resolution path: message1 -> term1 -> message2" in result

    def test_format_error_with_hint(self) -> None:
        """format_error() includes hint when present."""
        diagnostic = Diagnostic(
            code=DiagnosticCode.VARIABLE_NOT_PROVIDED,
            message="Variable 'name' not provided",
            hint="Check that the variable is passed in args",
        )

        result = diagnostic.format_error()

        assert "error[VARIABLE_NOT_PROVIDED]: Variable 'name' not provided" in result
        assert "= help: Check that the variable is passed in args" in result

    def test_format_error_with_help_url(self) -> None:
        """format_error() includes help_url when present."""
        diagnostic = Diagnostic(
            code=DiagnosticCode.TERM_NOT_FOUND,
            message="Term '-brand' not found",
            help_url="https://projectfluent.org/fluent/guide/terms.html",
        )

        result = diagnostic.format_error()

        assert "error[TERM_NOT_FOUND]: Term '-brand' not found" in result
        assert "= note: see https://projectfluent.org/fluent/guide/terms.html" in result

    def test_format_error_warning_severity(self) -> None:
        """format_error() uses 'warning' prefix for warning severity."""
        diagnostic = Diagnostic(
            code=DiagnosticCode.MESSAGE_NOT_FOUND,
            message="Message 'hello' not found",
            severity="warning",
        )

        result = diagnostic.format_error()

        assert "warning[MESSAGE_NOT_FOUND]: Message 'hello' not found" in result

    def test_format_error_all_optional_fields(self) -> None:
        """format_error() handles all optional fields together."""
        span = SourceSpan(start=10, end=20, line=5, column=10)
        diagnostic = Diagnostic(
            code=DiagnosticCode.TYPE_MISMATCH,
            message="Type mismatch in NUMBER()",
            span=span,
            hint="Convert value to Number",
            help_url="https://projectfluent.org/fluent/guide/functions.html",
            function_name="NUMBER",
            argument_name="value",
            expected_type="Number",
            received_type="String",
            ftl_location="ui.ftl:509",
            resolution_path=("msg1", "term1"),
        )

        result = diagnostic.format_error()

        assert "error[TYPE_MISMATCH]: Type mismatch in NUMBER()" in result
        assert "  --> line 5, column 10" in result
        assert "  = function: NUMBER" in result
        assert "  = argument: value" in result
        assert "  = expected: Number" in result
        assert "  = received: String" in result
        assert "  = resolution path: msg1 -> term1" in result
        assert "  = help: Convert value to Number" in result
        assert "  = note: see https://projectfluent.org/fluent/guide/functions.html" in result

    def test_format_error_minimal(self) -> None:
        """format_error() with only required fields."""
        diagnostic = Diagnostic(
            code=DiagnosticCode.UNKNOWN_EXPRESSION,
            message="Unknown expression type",
        )

        result = diagnostic.format_error()

        assert "error[UNKNOWN_EXPRESSION]: Unknown expression type" in result
        assert "-->" not in result
        assert "= help:" not in result
        assert "= note:" not in result
        assert "= function:" not in result
        assert "= argument:" not in result
        assert "= expected:" not in result
        assert "= received:" not in result
        assert "= resolution path:" not in result
