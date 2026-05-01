# mypy: ignore-errors
from __future__ import annotations

from typing import Literal

import pytest
from hypothesis import assume, event, given, settings
from hypothesis import strategies as st

from ftllexengine.diagnostics import (
    Diagnostic,
    DiagnosticCode,
    ErrorCategory,
    FrozenErrorContext,
    FrozenFluentError,
    SourceSpan,
)
from tests.strategies.diagnostics import error_categories

# =============================================================================
# Strategies for generating test data
# =============================================================================


@st.composite
def error_messages(draw: st.DrawFn) -> str:
    """Generate valid error messages."""
    return draw(st.text(min_size=1, max_size=200))


@st.composite
def optional_diagnostics(draw: st.DrawFn) -> Diagnostic | None:
    """Generate optional Diagnostic objects."""
    if draw(st.booleans()):
        code = draw(st.sampled_from(list(DiagnosticCode)))
        message = draw(st.text(min_size=1, max_size=100))
        return Diagnostic(code=code, message=message, severity="error")
    return None


@st.composite
def optional_contexts(draw: st.DrawFn) -> FrozenErrorContext | None:
    """Generate optional FrozenErrorContext objects."""
    if draw(st.booleans()):
        return FrozenErrorContext(
            input_value=draw(st.text(min_size=0, max_size=50)),
            locale_code=draw(st.text(min_size=1, max_size=10)),
            parse_type=draw(st.sampled_from(
                ["", "currency", "date", "datetime", "decimal", "number"]
            )),
            fallback_value=draw(st.text(min_size=0, max_size=50)),
        )
    return None


@st.composite
def frozen_fluent_errors(draw: st.DrawFn) -> FrozenFluentError:
    """Generate FrozenFluentError instances."""
    return FrozenFluentError(
        message=draw(error_messages()),
        category=draw(error_categories()),
        diagnostic=draw(optional_diagnostics()),
        context=draw(optional_contexts()),
    )


# =============================================================================
# Content Hash Properties
# =============================================================================



@st.composite
def rich_diagnostics(draw: st.DrawFn) -> Diagnostic:
    """Generate Diagnostic objects with arbitrary optional field population.

    Produces diagnostics with varied combinations of span, hint, help_url,
    function_name, argument_name, type info, ftl_location, severity, and
    resolution_path. Provides broad input diversity for content hash and
    format_error() fuzzing.
    """
    code = draw(st.sampled_from(list(DiagnosticCode)))
    message = draw(st.text(min_size=1, max_size=100))

    has_span = draw(st.booleans())
    span = None
    if has_span:
        start = draw(st.integers(min_value=0, max_value=10000))
        end = draw(
            st.integers(min_value=start, max_value=start + 1000)
        )
        line = draw(st.integers(min_value=1, max_value=5000))
        column = draw(st.integers(min_value=1, max_value=200))
        span = SourceSpan(
            start=start, end=end, line=line, column=column
        )

    opt_str = st.one_of(st.none(), st.text(min_size=1, max_size=80))
    hint = draw(opt_str)
    help_url = draw(opt_str)
    function_name = draw(opt_str)
    argument_name = draw(opt_str)
    expected_type = draw(opt_str)
    received_type = draw(opt_str)
    ftl_location = draw(opt_str)
    severity: Literal["error", "warning"] = draw(
        st.sampled_from(["error", "warning"])
    )

    has_path = draw(st.booleans())
    resolution_path = None
    if has_path:
        path_elems = draw(
            st.lists(
                st.text(min_size=1, max_size=20),
                min_size=0,
                max_size=5,
            )
        )
        resolution_path = tuple(path_elems)

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
        severity=severity,
        resolution_path=resolution_path,
    )

@pytest.mark.fuzz
class TestRichDiagnosticHashProperties:
    """Content hash integrity with fully-populated diagnostic fields.

    Exercises hash computation paths for all diagnostic optional fields
    (span, hint, help_url, function_name, resolution_path, etc.)
    that are unreachable with the basic optional_diagnostics strategy.
    """

    @given(
        message=error_messages(),
        category=error_categories(),
        diagnostic=rich_diagnostics(),
        context=optional_contexts(),
    )
    @settings(max_examples=200)
    def test_hash_determinism_rich_diagnostics(
        self,
        message: str,
        category: ErrorCategory,
        diagnostic: Diagnostic,
        context: FrozenErrorContext | None,
    ) -> None:
        """Property: Hash is deterministic with fully-populated diagnostics."""
        error1 = FrozenFluentError(
            message, category, diagnostic, context
        )
        error2 = FrozenFluentError(
            message, category, diagnostic, context
        )

        has_span = diagnostic.span is not None
        has_path = diagnostic.resolution_path is not None
        n_opt = sum(
            1
            for f in (
                diagnostic.hint,
                diagnostic.help_url,
                diagnostic.function_name,
                diagnostic.argument_name,
                diagnostic.expected_type,
                diagnostic.received_type,
                diagnostic.ftl_location,
            )
            if f is not None
        )
        event(f"has_span={has_span}")
        event(f"has_resolution_path={has_path}")
        event(f"optional_field_count={n_opt}")
        event(f"severity={diagnostic.severity}")

        assert error1.content_hash == error2.content_hash
        assert error1 == error2
        assert error1.verify_integrity()
        event("outcome=rich_hash_determinism")

    @given(
        message=error_messages(),
        category=error_categories(),
        diagnostic=rich_diagnostics(),
    )
    @settings(max_examples=200)
    def test_rich_diagnostic_integrity(
        self,
        message: str,
        category: ErrorCategory,
        diagnostic: Diagnostic,
    ) -> None:
        """Property: verify_integrity() passes for all diagnostic variants."""
        error = FrozenFluentError(message, category, diagnostic)

        has_span = diagnostic.span is not None
        has_path = diagnostic.resolution_path is not None
        event(f"has_span={has_span}")
        event(f"has_resolution_path={has_path}")
        event(f"severity={diagnostic.severity}")
        event(f"code={diagnostic.code.name}")

        assert error.verify_integrity()
        assert len(error.content_hash) == 16
        event("outcome=rich_integrity_verified")

    @given(
        message=error_messages(),
        category=error_categories(),
        diagnostic=rich_diagnostics(),
    )
    @settings(max_examples=100)
    def test_rich_diagnostic_repr_contains_fields(
        self,
        message: str,
        category: ErrorCategory,
        diagnostic: Diagnostic,
    ) -> None:
        """Property: repr includes all constructor args for rich diagnostics."""
        error = FrozenFluentError(message, category, diagnostic)
        r = repr(error)

        assert "FrozenFluentError" in r
        assert "message=" in r
        assert "category=" in r
        assert "diagnostic=" in r
        event(f"code={diagnostic.code.name}")
        event("outcome=rich_repr_valid")

_TEST_CONTROL_TRANSLATE = str.maketrans(
    {c: f"\\x{c:02x}" for c in range(0x20)}
    | {0x7F: "\\x7f", 0x1B: "\\x1b", 0x0D: "\\r", 0x0A: "\\n", 0x09: "\\t"}
)

def _escape_control_chars(text: str) -> str:
    """Mirror DiagnosticFormatter._escape_control_chars for test assertions."""
    return text.translate(_TEST_CONTROL_TRANSLATE)

@pytest.mark.fuzz
class TestDiagnosticFormatProperties:
    """Property tests for Diagnostic.format_error() output correctness.

    Tests the Rust-inspired diagnostic formatting in codes.py, ensuring
    all field combinations produce well-structured output.
    """

    @given(diagnostic=rich_diagnostics())
    @settings(max_examples=200)
    def test_format_error_nonempty(
        self, diagnostic: Diagnostic
    ) -> None:
        """Property: format_error() always returns non-empty string."""
        formatted = diagnostic.format_error()
        assert isinstance(formatted, str)
        assert len(formatted) > 0
        event(f"has_span={diagnostic.span is not None}")
        event(f"severity={diagnostic.severity}")
        event("outcome=format_nonempty")

    @given(diagnostic=rich_diagnostics())
    @settings(max_examples=200)
    def test_format_error_contains_message(
        self, diagnostic: Diagnostic
    ) -> None:
        """Property: format_error() always contains the escaped diagnostic message."""
        formatted = diagnostic.format_error()
        assert _escape_control_chars(diagnostic.message) in formatted
        event(f"code={diagnostic.code.name}")
        event("outcome=format_contains_message")

    @given(diagnostic=rich_diagnostics())
    @settings(max_examples=200)
    def test_format_error_contains_code_name(
        self, diagnostic: Diagnostic
    ) -> None:
        """Property: format_error() always contains the diagnostic code name."""
        formatted = diagnostic.format_error()
        assert diagnostic.code.name in formatted
        event(f"code={diagnostic.code.name}")

    @given(diagnostic=rich_diagnostics())
    @settings(max_examples=200)
    def test_format_error_severity_prefix(
        self, diagnostic: Diagnostic
    ) -> None:
        """Property: format_error() starts with correct severity prefix."""
        formatted = diagnostic.format_error()
        if diagnostic.severity == "warning":
            assert formatted.startswith("warning[")
            event("severity=warning")
        else:
            assert formatted.startswith("error[")
            event("severity=error")

    @given(diagnostic=rich_diagnostics())
    @settings(max_examples=200)
    def test_format_error_location_dispatch(
        self, diagnostic: Diagnostic
    ) -> None:
        """Property: format_error() dispatches location correctly.

        Span takes precedence over ftl_location. When neither is
        present, no location line appears.
        """
        formatted = diagnostic.format_error()
        if diagnostic.span is not None:
            line_str = f"line {diagnostic.span.line}"
            col_str = f"column {diagnostic.span.column}"
            assert line_str in formatted
            assert col_str in formatted
            event("location=span")
        elif diagnostic.ftl_location is not None:
            assert _escape_control_chars(diagnostic.ftl_location) in formatted
            event("location=ftl_location")
        else:
            assert "-->" not in formatted
            event("location=none")

    @given(diagnostic=rich_diagnostics())
    @settings(max_examples=200)
    def test_format_error_optional_field_inclusion(
        self, diagnostic: Diagnostic
    ) -> None:
        """Property: format_error() includes all present optional fields."""
        formatted = diagnostic.format_error()

        if diagnostic.function_name:
            escaped_fn = _escape_control_chars(diagnostic.function_name)
            fn_line = f"function: {escaped_fn}"
            assert fn_line in formatted
            event("has_function=True")
        else:
            event("has_function=False")

        if diagnostic.argument_name:
            escaped_arg = _escape_control_chars(diagnostic.argument_name)
            arg_line = f"argument: {escaped_arg}"
            assert arg_line in formatted

        if diagnostic.expected_type:
            escaped_exp = _escape_control_chars(diagnostic.expected_type)
            exp_line = f"expected: {escaped_exp}"
            assert exp_line in formatted

        if diagnostic.received_type:
            escaped_rcv = _escape_control_chars(diagnostic.received_type)
            rcv_line = f"received: {escaped_rcv}"
            assert rcv_line in formatted

        if diagnostic.resolution_path:
            path_str = " -> ".join(diagnostic.resolution_path)
            escaped_path = _escape_control_chars(path_str)
            assert escaped_path in formatted
            path_len = len(diagnostic.resolution_path)
            event(f"path_len={path_len}")

        if diagnostic.hint:
            escaped_hint = _escape_control_chars(diagnostic.hint)
            hint_line = f"help: {escaped_hint}"
            assert hint_line in formatted
            event("has_hint=True")
        else:
            event("has_hint=False")

        if diagnostic.help_url:
            escaped_url = _escape_control_chars(diagnostic.help_url)
            url_line = f"note: see {escaped_url}"
            assert url_line in formatted

    @given(diagnostic=rich_diagnostics())
    @settings(max_examples=100)
    def test_format_error_idempotent(
        self, diagnostic: Diagnostic
    ) -> None:
        """Property: format_error() is idempotent."""
        result1 = diagnostic.format_error()
        result2 = diagnostic.format_error()
        assert result1 == result2
        event(f"code={diagnostic.code.name}")
        event("outcome=format_idempotent")

def _make_diag_with_field(
    field: str, val: str
) -> Diagnostic:
    """Build a Diagnostic with exactly one optional string field set."""
    return Diagnostic(
        code=DiagnosticCode.FUNCTION_FAILED,
        message="base",
        hint=val if field == "hint" else None,
        help_url=val if field == "help_url" else None,
        function_name=(
            val if field == "function_name" else None
        ),
        argument_name=(
            val if field == "argument_name" else None
        ),
        expected_type=(
            val if field == "expected_type" else None
        ),
        received_type=(
            val if field == "received_type" else None
        ),
        ftl_location=(
            val if field == "ftl_location" else None
        ),
    )

_OPTIONAL_DIAG_FIELDS = [
    "hint",
    "help_url",
    "function_name",
    "argument_name",
    "expected_type",
    "received_type",
    "ftl_location",
]

@pytest.mark.fuzz
class TestHashCollisionResistanceProperties:
    """Advanced collision resistance for _compute_content_hash.

    Tests three structural integrity mechanisms:
    1. Length-prefix prevents field boundary ambiguity
    2. Each optional diagnostic field independently affects hash
    3. Section markers prevent diagnostic/context presence collisions
    """

    @given(
        a=st.text(min_size=2, max_size=50),
        b=st.text(min_size=1, max_size=50),
    )
    @settings(max_examples=200)
    def test_length_prefix_prevents_boundary_collision(
        self, a: str, b: str
    ) -> None:
        """Property: Shifting one char across field boundary changes hash.

        _hash_string uses 4-byte length prefix so ("ab","cd") and
        ("a","bcd") produce different digests even though the raw
        bytes concatenate identically without the prefix.

        Events emitted:
        - a_len={n}: Length of first field
        - b_len={n}: Length of second field
        - outcome=length_prefix_collision_prevented
        """
        # Shift last char of 'a' into 'b'
        a_shifted = a[:-1]
        b_shifted = a[-1] + b

        ctx1 = FrozenErrorContext(
            input_value=a,
            locale_code=b,
            parse_type="date",
            fallback_value="f",
        )
        ctx2 = FrozenErrorContext(
            input_value=a_shifted,
            locale_code=b_shifted,
            parse_type="date",
            fallback_value="f",
        )

        error1 = FrozenFluentError(
            "msg", ErrorCategory.REFERENCE, context=ctx1
        )
        error2 = FrozenFluentError(
            "msg", ErrorCategory.REFERENCE, context=ctx2
        )

        event(f"a_len={len(a)}")
        event(f"b_len={len(b)}")
        assert error1.content_hash != error2.content_hash
        event("outcome=length_prefix_collision_prevented")

    @given(
        field=st.sampled_from(_OPTIONAL_DIAG_FIELDS),
        val1=st.text(min_size=1, max_size=50),
        val2=st.text(min_size=1, max_size=50),
    )
    @settings(max_examples=200)
    def test_each_optional_field_affects_hash(
        self, field: str, val1: str, val2: str
    ) -> None:
        """Property: Changing any single optional field changes the hash.

        Each of the 7 optional string fields in Diagnostic (hint,
        help_url, function_name, argument_name, expected_type,
        received_type, ftl_location) must independently affect the
        content hash.

        Events emitted:
        - field={name}: Which field was varied
        - outcome=field_sensitivity_verified
        """
        assume(val1 != val2)
        event(f"field={field}")

        diag1 = _make_diag_with_field(field, val1)
        diag2 = _make_diag_with_field(field, val2)

        e1 = FrozenFluentError(
            "m", ErrorCategory.RESOLUTION, diagnostic=diag1
        )
        e2 = FrozenFluentError(
            "m", ErrorCategory.RESOLUTION, diagnostic=diag2
        )

        assert e1.content_hash != e2.content_hash
        event("outcome=field_sensitivity_verified")

    @given(
        field=st.sampled_from(_OPTIONAL_DIAG_FIELDS),
        val=st.text(min_size=1, max_size=50),
    )
    @settings(max_examples=100)
    def test_none_vs_present_field_affects_hash(
        self, field: str, val: str
    ) -> None:
        """Property: None vs present for any optional field changes hash.

        The hash uses b"\\x00NONE" sentinel for absent fields. A
        present field must always produce a different hash than the
        sentinel.

        Events emitted:
        - field={name}: Which field was toggled
        - outcome=none_vs_present_verified
        """
        event(f"field={field}")

        diag_with = _make_diag_with_field(field, val)
        diag_without = Diagnostic(
            code=DiagnosticCode.FUNCTION_FAILED,
            message="base",
        )

        e1 = FrozenFluentError(
            "m", ErrorCategory.RESOLUTION, diagnostic=diag_with
        )
        e2 = FrozenFluentError(
            "m", ErrorCategory.RESOLUTION, diagnostic=diag_without
        )

        assert e1.content_hash != e2.content_hash
        event("outcome=none_vs_present_verified")

    @given(
        message=error_messages(),
        category=error_categories(),
    )
    @settings(max_examples=100)
    def test_section_markers_prevent_presence_collision(
        self, message: str, category: ErrorCategory
    ) -> None:
        """Property: All 4 diagnostic/context presence permutations differ.

        Section markers (\\x01DIAG/\\x00NODIAG, \\x01CTX/\\x00NOCTX)
        ensure that errors with different combinations of diagnostic
        and context presence always produce different hashes.

        Events emitted:
        - category={name}: Error category
        - outcome=section_markers_verified
        """
        event(f"category={category.name}")

        diag = Diagnostic(
            code=DiagnosticCode.MESSAGE_NOT_FOUND,
            message="diag msg",
        )
        ctx = FrozenErrorContext(input_value="ctx val")

        # All 4 presence permutations
        e_nn = FrozenFluentError(message, category)
        e_dn = FrozenFluentError(
            message, category, diagnostic=diag
        )
        e_nc = FrozenFluentError(
            message, category, context=ctx
        )
        e_dc = FrozenFluentError(
            message, category, diagnostic=diag, context=ctx
        )

        hashes = {
            e_nn.content_hash,
            e_dn.content_hash,
            e_nc.content_hash,
            e_dc.content_hash,
        }
        assert len(hashes) == 4
        event("outcome=section_markers_verified")
