"""Property-based tests for diagnostics/templates.py: ErrorTemplate.

Comprehensive Hypothesis coverage for all ErrorTemplate factory methods.
Each factory is tested for:
- Code assignment (correct DiagnosticCode)
- Message content (relevant identifiers appear in message)
- Diagnostic structure (hint, help_url, function_name etc. where applicable)
- No crashes on arbitrary valid inputs

Python 3.13+.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import ClassVar

from hypothesis import event, given
from hypothesis import strategies as st

from ftllexengine.diagnostics.codes import Diagnostic, DiagnosticCode
from ftllexengine.diagnostics.templates import ErrorTemplate

# ---------------------------------------------------------------------------
# Shared strategies
# ---------------------------------------------------------------------------

_identifiers = st.from_regex(r"[a-z][a-z0-9_-]{0,19}", fullmatch=True)
_short_text = st.text(min_size=1, max_size=60)
_locale_codes = st.from_regex(r"[a-z]{2,3}(_[A-Z]{2,3})?", fullmatch=True)
_symbols = st.text(
    st.characters(categories=("L", "S", "N")),
    min_size=1,
    max_size=5,
)
_amounts = st.from_regex(r"[0-9]{1,10}(\.[0-9]{1,4})?", fullmatch=True)
_currency_codes = st.from_regex(r"[A-Z]{3}", fullmatch=True)
_function_names = st.sampled_from(["NUMBER", "DATETIME", "CURRENCY", "PERCENT"])
_positive_ints = st.integers(min_value=1, max_value=100)


# ===========================================================================
# Reference errors (1000-1099)
# ===========================================================================


class TestReferenceTemplates:
    """Templates for reference errors."""

    @given(msg_id=_identifiers)
    def test_message_not_found(self, msg_id: str) -> None:
        """message_not_found embeds the ID and uses MESSAGE_NOT_FOUND code."""
        d = ErrorTemplate.message_not_found(msg_id)
        assert isinstance(d, Diagnostic)
        assert d.code == DiagnosticCode.MESSAGE_NOT_FOUND
        assert msg_id in d.message
        assert d.hint is not None
        assert d.help_url is not None
        event("template=message_not_found")

    @given(attr=_identifiers, msg_id=_identifiers)
    def test_attribute_not_found(self, attr: str, msg_id: str) -> None:
        """attribute_not_found embeds both names and uses ATTRIBUTE_NOT_FOUND."""
        d = ErrorTemplate.attribute_not_found(attr, msg_id)
        assert d.code == DiagnosticCode.ATTRIBUTE_NOT_FOUND
        assert attr in d.message
        assert msg_id in d.message
        assert d.hint is not None
        event("template=attribute_not_found")

    @given(term_id=_identifiers)
    def test_term_not_found(self, term_id: str) -> None:
        """term_not_found embeds the term ID and uses TERM_NOT_FOUND."""
        d = ErrorTemplate.term_not_found(term_id)
        assert d.code == DiagnosticCode.TERM_NOT_FOUND
        assert term_id in d.message
        assert d.hint is not None
        event("template=term_not_found")

    @given(attr=_identifiers, term_id=_identifiers)
    def test_term_attribute_not_found(self, attr: str, term_id: str) -> None:
        """term_attribute_not_found embeds both names and uses TERM_ATTRIBUTE_NOT_FOUND."""
        d = ErrorTemplate.term_attribute_not_found(attr, term_id)
        assert d.code == DiagnosticCode.TERM_ATTRIBUTE_NOT_FOUND
        assert attr in d.message
        assert term_id in d.message
        assert d.hint is not None
        event("template=term_attribute_not_found")

    @given(term=_identifiers, count=_positive_ints)
    def test_term_positional_args_ignored_singular(
        self, term: str, count: int
    ) -> None:
        """term_positional_args_ignored embeds name and count."""
        d = ErrorTemplate.term_positional_args_ignored(term, count)
        assert d.code == DiagnosticCode.TERM_POSITIONAL_ARGS_IGNORED
        assert term in d.message
        assert str(count) in d.message
        assert d.hint is not None
        singular = count == 1
        event(f"singular={singular}")

    def test_term_positional_args_singular_form(self) -> None:
        """term_positional_args_ignored uses singular 'argument' for the positional count=1."""
        d = ErrorTemplate.term_positional_args_ignored("brand", 1)
        assert d.hint is not None
        # "1 positional argument" (singular) — "named arguments" is always plural as a concept
        assert "1 positional argument" in d.hint
        assert "1 positional arguments" not in d.hint

    def test_term_positional_args_plural_form(self) -> None:
        """term_positional_args_ignored uses plural 'arguments' for count>1."""
        d = ErrorTemplate.term_positional_args_ignored("brand", 3)
        assert d.hint is not None
        assert "3 positional arguments" in d.hint

    @given(var=_identifiers)
    def test_variable_not_provided(self, var: str) -> None:
        """variable_not_provided embeds the variable name."""
        d = ErrorTemplate.variable_not_provided(var)
        assert d.code == DiagnosticCode.VARIABLE_NOT_PROVIDED
        assert var in d.message
        assert d.hint is not None
        event("template=variable_not_provided")

    @given(var=_identifiers, path=st.lists(_identifiers, min_size=1, max_size=4).map(tuple))
    def test_variable_not_provided_with_resolution_path(
        self, var: str, path: tuple[str, ...]
    ) -> None:
        """variable_not_provided accepts optional resolution_path."""
        d = ErrorTemplate.variable_not_provided(var, resolution_path=path)
        assert d.code == DiagnosticCode.VARIABLE_NOT_PROVIDED
        assert d.resolution_path == path
        event(f"path_len={len(path)}")

    @given(msg_id=_identifiers)
    def test_message_no_value(self, msg_id: str) -> None:
        """message_no_value embeds the ID and uses MESSAGE_NO_VALUE."""
        d = ErrorTemplate.message_no_value(msg_id)
        assert d.code == DiagnosticCode.MESSAGE_NO_VALUE
        assert msg_id in d.message
        assert d.hint is not None
        event("template=message_no_value")


# ===========================================================================
# Resolution errors (2000-2999)
# ===========================================================================


class TestResolutionTemplates:
    """Templates for resolution errors."""

    @given(path=st.lists(_identifiers, min_size=2, max_size=6))
    def test_cyclic_reference(self, path: list[str]) -> None:
        """cyclic_reference embeds the full path and uses CYCLIC_REFERENCE."""
        d = ErrorTemplate.cyclic_reference(path)
        assert d.code == DiagnosticCode.CYCLIC_REFERENCE
        for node in path:
            assert node in d.message
        assert "circular" in d.message.lower() or "cycle" in d.message.lower()
        event(f"path_len={len(path)}")

    @given(msg_id=_identifiers, max_depth=st.integers(min_value=1, max_value=1000))
    def test_max_depth_exceeded(self, msg_id: str, max_depth: int) -> None:
        """max_depth_exceeded embeds the message ID and depth."""
        d = ErrorTemplate.max_depth_exceeded(msg_id, max_depth)
        assert d.code == DiagnosticCode.MAX_DEPTH_EXCEEDED
        assert msg_id in d.message
        assert str(max_depth) in d.message
        assert d.hint is not None
        event(f"depth={max_depth}")

    @given(max_depth=st.integers(min_value=1, max_value=1000))
    def test_depth_exceeded(self, max_depth: int) -> None:
        """depth_exceeded embeds the depth limit."""
        d = ErrorTemplate.depth_exceeded(max_depth)
        assert d.code == DiagnosticCode.MAX_DEPTH_EXCEEDED
        assert str(max_depth) in d.message
        assert d.hint is not None
        event(f"depth={max_depth}")

    @given(
        total=st.integers(min_value=1, max_value=10_000_000),
        limit=st.integers(min_value=1, max_value=10_000_000),
    )
    def test_expansion_budget_exceeded(self, total: int, limit: int) -> None:
        """expansion_budget_exceeded embeds total and limit."""
        d = ErrorTemplate.expansion_budget_exceeded(total, limit)
        assert d.code == DiagnosticCode.EXPANSION_BUDGET_EXCEEDED
        assert str(total) in d.message
        assert str(limit) in d.message
        assert d.hint is not None
        event(f"ratio={'over' if total > limit else 'under'}")

    def test_no_variants(self) -> None:
        """no_variants produces NO_VARIANTS diagnostic with hint."""
        d = ErrorTemplate.no_variants()
        assert d.code == DiagnosticCode.NO_VARIANTS
        assert len(d.message) > 0
        assert d.hint is not None

    @given(fn=_function_names)
    def test_function_not_found(self, fn: str) -> None:
        """function_not_found embeds the function name."""
        d = ErrorTemplate.function_not_found(fn)
        assert d.code == DiagnosticCode.FUNCTION_NOT_FOUND
        assert fn in d.message
        assert d.hint is not None
        event(f"fn={fn}")

    @given(fn=_function_names, reason=_short_text)
    def test_function_failed(self, fn: str, reason: str) -> None:
        """function_failed embeds function name and reason."""
        d = ErrorTemplate.function_failed(fn, reason)
        assert d.code == DiagnosticCode.FUNCTION_FAILED
        assert fn in d.message
        assert reason in d.message
        assert d.function_name == fn
        event(f"fn={fn}")

    @given(fn=_function_names, value=_short_text, reason=_short_text)
    def test_formatting_failed(self, fn: str, value: str, reason: str) -> None:
        """formatting_failed embeds function name, value, and reason."""
        d = ErrorTemplate.formatting_failed(fn, value, reason)
        assert d.code == DiagnosticCode.FORMATTING_FAILED
        assert fn in d.message
        assert value in d.message
        assert reason in d.message
        assert d.function_name == fn
        event(f"fn={fn}")

    @given(
        fn=_function_names,
        expected=_positive_ints,
        received=_positive_ints,
    )
    def test_function_arity_mismatch(
        self, fn: str, expected: int, received: int
    ) -> None:
        """function_arity_mismatch embeds expected and received counts."""
        d = ErrorTemplate.function_arity_mismatch(fn, expected, received)
        assert d.code == DiagnosticCode.FUNCTION_ARITY_MISMATCH
        assert str(expected) in d.message
        assert str(received) in d.message
        assert d.function_name == fn
        event(f"fn={fn}")

    @given(
        fn=_function_names,
        arg=_identifiers,
        expected=_short_text,
        received=_short_text,
    )
    def test_type_mismatch(
        self, fn: str, arg: str, expected: str, received: str
    ) -> None:
        """type_mismatch embeds types and argument name."""
        d = ErrorTemplate.type_mismatch(fn, arg, expected, received)
        assert d.code == DiagnosticCode.TYPE_MISMATCH
        assert d.function_name == fn
        assert d.argument_name == arg
        assert d.expected_type == expected
        assert d.received_type == received
        event(f"fn={fn}")

    @given(
        fn=_function_names,
        arg=_identifiers,
        reason=_short_text,
    )
    def test_invalid_argument(self, fn: str, arg: str, reason: str) -> None:
        """invalid_argument embeds argument name and reason."""
        d = ErrorTemplate.invalid_argument(fn, arg, reason)
        assert d.code == DiagnosticCode.INVALID_ARGUMENT
        assert fn in d.message
        assert arg in d.message
        assert reason in d.message
        assert d.function_name == fn
        assert d.argument_name == arg
        event(f"fn={fn}")

    @given(fn=_function_names, arg=_identifiers)
    def test_argument_required(self, fn: str, arg: str) -> None:
        """argument_required embeds function name and argument name."""
        d = ErrorTemplate.argument_required(fn, arg)
        assert d.code == DiagnosticCode.ARGUMENT_REQUIRED
        assert fn in d.message
        assert arg in d.message
        assert d.function_name == fn
        assert d.argument_name == arg
        event(f"fn={fn}")

    @given(fn=_function_names, pattern=_short_text, reason=_short_text)
    def test_pattern_invalid(
        self, fn: str, pattern: str, reason: str
    ) -> None:
        """pattern_invalid embeds reason and sets argument_name='pattern'."""
        d = ErrorTemplate.pattern_invalid(fn, pattern, reason)
        assert d.code == DiagnosticCode.PATTERN_INVALID
        assert reason in d.message
        assert d.function_name == fn
        assert d.argument_name == "pattern"
        event(f"fn={fn}")

    @given(expr_type=_short_text)
    def test_unknown_expression(self, expr_type: str) -> None:
        """unknown_expression embeds the expression type name."""
        d = ErrorTemplate.unknown_expression(expr_type)
        assert d.code == DiagnosticCode.UNKNOWN_EXPRESSION
        assert expr_type in d.message
        assert d.hint is not None
        event("template=unknown_expression")

    def test_plural_support_unavailable(self) -> None:
        """plural_support_unavailable produces PLURAL_SUPPORT_UNAVAILABLE."""
        d = ErrorTemplate.plural_support_unavailable()
        assert d.code == DiagnosticCode.PLURAL_SUPPORT_UNAVAILABLE
        assert "babel" in d.message.lower() or "plural" in d.message.lower()
        assert d.hint is not None


# ===========================================================================
# Syntax errors (3000-3999)
# ===========================================================================


class TestSyntaxTemplates:
    """Templates for syntax errors."""

    @given(pos=st.integers(min_value=0, max_value=100000))
    def test_unexpected_eof(self, pos: int) -> None:
        """unexpected_eof embeds the position."""
        d = ErrorTemplate.unexpected_eof(pos)
        assert d.code == DiagnosticCode.UNEXPECTED_EOF
        assert str(pos) in d.message
        assert d.hint is not None
        event(f"pos={pos}")


# ===========================================================================
# Parsing errors (4000-4999) - bi-directional localization
# ===========================================================================


class TestParsingTemplates:
    """Templates for bi-directional parsing errors."""

    @given(val=_short_text, locale=_locale_codes, reason=_short_text)
    def test_parse_decimal_failed(
        self, val: str, locale: str, reason: str
    ) -> None:
        """parse_decimal_failed embeds value, locale, and reason."""
        d = ErrorTemplate.parse_decimal_failed(val, locale, reason)
        assert d.code == DiagnosticCode.PARSE_DECIMAL_FAILED
        assert val in d.message
        assert locale in d.message
        assert reason in d.message
        event("template=parse_decimal_failed")

    @given(val=_short_text, locale=_locale_codes, reason=_short_text)
    def test_parse_date_failed(
        self, val: str, locale: str, reason: str
    ) -> None:
        """parse_date_failed embeds value, locale, and reason."""
        d = ErrorTemplate.parse_date_failed(val, locale, reason)
        assert d.code == DiagnosticCode.PARSE_DATE_FAILED
        assert val in d.message
        assert locale in d.message
        assert reason in d.message
        assert "ISO 8601" in d.hint  # type: ignore[operator]
        event("template=parse_date_failed")

    @given(val=_short_text, locale=_locale_codes, reason=_short_text)
    def test_parse_datetime_failed(
        self, val: str, locale: str, reason: str
    ) -> None:
        """parse_datetime_failed embeds value, locale, and reason."""
        d = ErrorTemplate.parse_datetime_failed(val, locale, reason)
        assert d.code == DiagnosticCode.PARSE_DATETIME_FAILED
        assert val in d.message
        assert locale in d.message
        assert reason in d.message
        event("template=parse_datetime_failed")

    @given(val=_short_text, locale=_locale_codes, reason=_short_text)
    def test_parse_currency_failed(
        self, val: str, locale: str, reason: str
    ) -> None:
        """parse_currency_failed embeds value, locale, and reason."""
        d = ErrorTemplate.parse_currency_failed(val, locale, reason)
        assert d.code == DiagnosticCode.PARSE_CURRENCY_FAILED
        assert val in d.message
        assert locale in d.message
        assert reason in d.message
        event("template=parse_currency_failed")

    @given(locale=_locale_codes)
    def test_parse_locale_unknown(self, locale: str) -> None:
        """parse_locale_unknown embeds the locale code."""
        d = ErrorTemplate.parse_locale_unknown(locale)
        assert d.code == DiagnosticCode.PARSE_LOCALE_UNKNOWN
        assert locale in d.message
        assert d.hint is not None
        event("template=parse_locale_unknown")

    @given(symbol=_symbols, val=_short_text)
    def test_parse_currency_ambiguous(
        self, symbol: str, val: str
    ) -> None:
        """parse_currency_ambiguous embeds symbol and full value."""
        d = ErrorTemplate.parse_currency_ambiguous(symbol, val)
        assert d.code == DiagnosticCode.PARSE_CURRENCY_AMBIGUOUS
        assert symbol in d.message
        assert d.hint is not None
        event("template=parse_currency_ambiguous")

    @given(symbol=_symbols, val=_short_text)
    def test_parse_currency_symbol_unknown(
        self, symbol: str, val: str
    ) -> None:
        """parse_currency_symbol_unknown embeds symbol."""
        d = ErrorTemplate.parse_currency_symbol_unknown(symbol, val)
        assert d.code == DiagnosticCode.PARSE_CURRENCY_SYMBOL_UNKNOWN
        assert symbol in d.message
        assert d.hint is not None
        event("template=parse_currency_symbol_unknown")

    @given(code=_currency_codes, val=_short_text)
    def test_parse_currency_code_invalid(
        self, code: str, val: str
    ) -> None:
        """parse_currency_code_invalid embeds the 3-letter ISO code."""
        d = ErrorTemplate.parse_currency_code_invalid(code, val)
        assert d.code == DiagnosticCode.PARSE_CURRENCY_CODE_INVALID
        assert code in d.message
        assert d.hint is not None
        event("template=parse_currency_code_invalid")

    @given(amount=_amounts, val=_short_text, reason=_short_text)
    def test_parse_amount_invalid(
        self, amount: str, val: str, reason: str
    ) -> None:
        """parse_amount_invalid embeds amount, value, and reason."""
        d = ErrorTemplate.parse_amount_invalid(amount, val, reason)
        assert d.code == DiagnosticCode.PARSE_AMOUNT_INVALID
        assert amount in d.message
        assert reason in d.message
        assert d.hint is not None
        event("template=parse_amount_invalid")


# ===========================================================================
# Structural invariants across all templates
# ===========================================================================


class TestTemplateStructuralInvariants:
    """Cross-cutting invariants that all templates must satisfy."""

    _all_factories: ClassVar[list[Callable[[], Diagnostic]]] = [
        lambda: ErrorTemplate.message_not_found("msg"),
        lambda: ErrorTemplate.attribute_not_found("attr", "msg"),
        lambda: ErrorTemplate.term_not_found("term"),
        lambda: ErrorTemplate.term_attribute_not_found("attr", "term"),
        lambda: ErrorTemplate.term_positional_args_ignored("term", 2),
        ErrorTemplate.plural_support_unavailable,
        lambda: ErrorTemplate.variable_not_provided("var"),
        lambda: ErrorTemplate.message_no_value("msg"),
        lambda: ErrorTemplate.cyclic_reference(["a", "b"]),
        lambda: ErrorTemplate.max_depth_exceeded("msg", 10),
        lambda: ErrorTemplate.depth_exceeded(50),
        lambda: ErrorTemplate.expansion_budget_exceeded(200, 100),
        ErrorTemplate.no_variants,
        lambda: ErrorTemplate.function_not_found("NUMBER"),
        lambda: ErrorTemplate.function_failed("NUMBER", "invalid"),
        lambda: ErrorTemplate.formatting_failed("NUMBER", "x", "reason"),
        lambda: ErrorTemplate.function_arity_mismatch("NUMBER", 1, 2),
        lambda: ErrorTemplate.type_mismatch("NUMBER", "val", "Number", "String"),
        lambda: ErrorTemplate.invalid_argument("NUMBER", "val", "reason"),
        lambda: ErrorTemplate.argument_required("NUMBER", "val"),
        lambda: ErrorTemplate.pattern_invalid("NUMBER", "#,##0", "syntax"),
        lambda: ErrorTemplate.unknown_expression("FooExpr"),
        lambda: ErrorTemplate.unexpected_eof(42),
        lambda: ErrorTemplate.parse_decimal_failed("abc", "de_DE", "invalid"),
        lambda: ErrorTemplate.parse_date_failed("abc", "en_US", "invalid"),
        lambda: ErrorTemplate.parse_datetime_failed("abc", "en_US", "invalid"),
        lambda: ErrorTemplate.parse_currency_failed("abc", "en_US", "invalid"),
        lambda: ErrorTemplate.parse_locale_unknown("xx_XX"),
        lambda: ErrorTemplate.parse_currency_ambiguous("$", "$10"),
        lambda: ErrorTemplate.parse_currency_symbol_unknown("@", "@10"),
        lambda: ErrorTemplate.parse_currency_code_invalid("XYZ", "XYZ 10"),
        lambda: ErrorTemplate.parse_amount_invalid("abc", "USD abc", "NaN"),
    ]

    def test_all_templates_return_diagnostic(self) -> None:
        """Every factory method returns a Diagnostic instance."""
        for factory in self._all_factories:
            d = factory()
            assert isinstance(d, Diagnostic), f"Expected Diagnostic, got {type(d)}"

    def test_all_templates_have_nonempty_message(self) -> None:
        """Every template produces a non-empty message."""
        for factory in self._all_factories:
            d = factory()
            assert len(d.message) > 0, f"Empty message from {factory}"

    def test_all_templates_have_valid_code(self) -> None:
        """Every template has a valid DiagnosticCode member."""
        for factory in self._all_factories:
            d = factory()
            assert isinstance(d.code, DiagnosticCode), f"Invalid code from {factory}"

    def test_all_templates_span_is_none(self) -> None:
        """Templates never pre-populate span (it is set by callers)."""
        for factory in self._all_factories:
            d = factory()
            assert d.span is None, f"Unexpected span from {factory}"


# ============================================================================
# CURRENCY SYMBOL UNKNOWN TEMPLATE COVERAGE
# ============================================================================


class TestDiagnosticsTemplatesCoverage:
    """Coverage for ErrorTemplate.parse_currency_symbol_unknown factory."""

    def test_parse_currency_symbol_unknown_template(self) -> None:
        """parse_currency_symbol_unknown produces correct diagnostic structure."""
        diagnostic = ErrorTemplate.parse_currency_symbol_unknown("XYZ", "XYZ100.50")

        assert diagnostic.code == DiagnosticCode.PARSE_CURRENCY_SYMBOL_UNKNOWN
        assert "Unknown currency symbol" in diagnostic.message
        assert "XYZ" in diagnostic.message
        assert diagnostic.hint is not None
