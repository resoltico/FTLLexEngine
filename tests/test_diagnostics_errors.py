"""Property-based tests for diagnostics/errors.py: FrozenFluentError.

Covers all invariants of the immutable, content-addressable exception:
- All public properties (message, category, diagnostic, context, content_hash,
  fallback_value, input_value, locale_code, parse_type)
- Content hash computation branches (span, resolution_path, context)
- Mutation protection (__setattr__, __delattr__)
- Sealed type enforcement (__init_subclass__)
- Value semantics (__hash__, __eq__, __repr__)
- verify_integrity() on pristine and constructed variants
- Raise/catch exception behavior

Python 3.13+.
"""

from __future__ import annotations

import contextlib

import pytest
from hypothesis import event, example, given
from hypothesis import strategies as st

from ftllexengine.diagnostics.codes import (
    Diagnostic,
    DiagnosticCode,
    ErrorCategory,
    FrozenErrorContext,
    SourceSpan,
)
from ftllexengine.diagnostics.errors import FrozenFluentError
from ftllexengine.integrity import ImmutabilityViolationError
from tests.strategies.diagnostics import (
    diagnostic_codes,
    diagnostics,
    error_categories,
    frozen_error_contexts,
    source_spans,
)

# ---------------------------------------------------------------------------
# Module-level strategies
# ---------------------------------------------------------------------------

_messages = st.text(min_size=1, max_size=200)
_identifiers = st.from_regex(r"[a-z][a-z0-9_-]{0,19}", fullmatch=True)


# ===========================================================================
# Properties: message, category, context, diagnostic, content_hash
# ===========================================================================


class TestFrozenFluentErrorProperties:
    """Tests for all public property accessors."""

    @given(msg=_messages, cat=error_categories())
    def test_message_property_returns_constructor_arg(
        self, msg: str, cat: ErrorCategory
    ) -> None:
        """PROPERTY: .message returns the string passed to __init__."""
        err = FrozenFluentError(msg, cat)
        assert err.message == msg
        event(f"cat={cat.value}")

    @given(msg=_messages, cat=error_categories())
    def test_category_property_returns_constructor_arg(
        self, msg: str, cat: ErrorCategory
    ) -> None:
        """PROPERTY: .category returns the ErrorCategory passed to __init__."""
        err = FrozenFluentError(msg, cat)
        assert err.category == cat
        event(f"cat={cat.value}")

    @given(msg=_messages, cat=error_categories())
    def test_diagnostic_none_by_default(
        self, msg: str, cat: ErrorCategory
    ) -> None:
        """PROPERTY: .diagnostic is None when not supplied."""
        err = FrozenFluentError(msg, cat)
        assert err.diagnostic is None
        event("diagnostic=absent")

    @given(msg=_messages, cat=error_categories(), diag=diagnostics())
    def test_diagnostic_property_set(
        self, msg: str, cat: ErrorCategory, diag: Diagnostic
    ) -> None:
        """PROPERTY: .diagnostic returns the Diagnostic passed to __init__."""
        err = FrozenFluentError(msg, cat, diagnostic=diag)
        assert err.diagnostic is diag
        event("diagnostic=present")

    @given(msg=_messages, cat=error_categories())
    def test_context_none_by_default(
        self, msg: str, cat: ErrorCategory
    ) -> None:
        """PROPERTY: .context is None when not supplied."""
        err = FrozenFluentError(msg, cat)
        assert err.context is None
        event("context=absent")

    @given(msg=_messages, cat=error_categories(), ctx=frozen_error_contexts())
    def test_context_property_set(
        self, msg: str, cat: ErrorCategory, ctx: FrozenErrorContext
    ) -> None:
        """PROPERTY: .context returns the FrozenErrorContext passed to __init__."""
        err = FrozenFluentError(msg, cat, context=ctx)
        assert err.context is ctx
        event("context=present")

    @given(msg=_messages, cat=error_categories())
    def test_content_hash_is_bytes(
        self, msg: str, cat: ErrorCategory
    ) -> None:
        """PROPERTY: .content_hash is a 16-byte bytes object."""
        err = FrozenFluentError(msg, cat)
        h = err.content_hash
        assert isinstance(h, bytes)
        assert len(h) == 16
        event("content_hash=bytes16")

    @given(msg=_messages, cat=error_categories())
    def test_content_hash_stable(
        self, msg: str, cat: ErrorCategory
    ) -> None:
        """PROPERTY: Two errors with identical content have equal content_hash."""
        e1 = FrozenFluentError(msg, cat)
        e2 = FrozenFluentError(msg, cat)
        assert e1.content_hash == e2.content_hash
        event("outcome=hash_stable")

    @given(msg=_messages, cat=error_categories(), ctx=frozen_error_contexts())
    def test_fallback_value_from_context(
        self, msg: str, cat: ErrorCategory, ctx: FrozenErrorContext
    ) -> None:
        """PROPERTY: .fallback_value returns context.fallback_value when context set."""
        err = FrozenFluentError(msg, cat, context=ctx)
        assert err.fallback_value == ctx.fallback_value
        has_fallback = len(ctx.fallback_value) > 0
        event(f"has_fallback={has_fallback}")

    @given(msg=_messages, cat=error_categories())
    def test_fallback_value_empty_without_context(
        self, msg: str, cat: ErrorCategory
    ) -> None:
        """PROPERTY: .fallback_value returns empty string when context is None."""
        err = FrozenFluentError(msg, cat)
        assert err.fallback_value == ""
        event("fallback=absent")

    @given(msg=_messages, cat=error_categories(), ctx=frozen_error_contexts())
    def test_input_value_from_context(
        self, msg: str, cat: ErrorCategory, ctx: FrozenErrorContext
    ) -> None:
        """PROPERTY: .input_value returns context.input_value when context set."""
        err = FrozenFluentError(msg, cat, context=ctx)
        assert err.input_value == ctx.input_value
        event(f"has_input={len(ctx.input_value) > 0}")

    @given(msg=_messages, cat=error_categories())
    def test_input_value_empty_without_context(
        self, msg: str, cat: ErrorCategory
    ) -> None:
        """PROPERTY: .input_value returns empty string when context is None."""
        err = FrozenFluentError(msg, cat)
        assert err.input_value == ""
        event("input=absent")

    @given(msg=_messages, cat=error_categories(), ctx=frozen_error_contexts())
    def test_locale_code_from_context(
        self, msg: str, cat: ErrorCategory, ctx: FrozenErrorContext
    ) -> None:
        """PROPERTY: .locale_code returns context.locale_code when context set."""
        err = FrozenFluentError(msg, cat, context=ctx)
        assert err.locale_code == ctx.locale_code
        event(f"has_locale={len(ctx.locale_code) > 0}")

    @given(msg=_messages, cat=error_categories())
    def test_locale_code_empty_without_context(
        self, msg: str, cat: ErrorCategory
    ) -> None:
        """PROPERTY: .locale_code returns empty string when context is None."""
        err = FrozenFluentError(msg, cat)
        assert err.locale_code == ""
        event("locale=absent")

    @given(msg=_messages, cat=error_categories(), ctx=frozen_error_contexts())
    def test_parse_type_from_context(
        self, msg: str, cat: ErrorCategory, ctx: FrozenErrorContext
    ) -> None:
        """PROPERTY: .parse_type returns context.parse_type when context set."""
        err = FrozenFluentError(msg, cat, context=ctx)
        assert err.parse_type == ctx.parse_type
        event(f"has_parse_type={len(ctx.parse_type) > 0}")

    @given(msg=_messages, cat=error_categories())
    def test_parse_type_empty_without_context(
        self, msg: str, cat: ErrorCategory
    ) -> None:
        """PROPERTY: .parse_type returns empty string when context is None."""
        err = FrozenFluentError(msg, cat)
        assert err.parse_type == ""
        event("parse_type=absent")


# ===========================================================================
# Content hash: branch coverage for span, resolution_path, and context
# ===========================================================================


class TestContentHashBranches:
    """Tests that exercise all branches in _compute_content_hash."""

    def test_hash_with_span_covered(self) -> None:
        """Hash branch for diagnostic.span is not None is exercised."""
        span = SourceSpan(start=0, end=10, line=1, column=1)
        diag = Diagnostic(
            code=DiagnosticCode.MESSAGE_NOT_FOUND,
            message="test",
            span=span,
        )
        err = FrozenFluentError("test", ErrorCategory.REFERENCE, diagnostic=diag)
        assert len(err.content_hash) == 16
        assert err.verify_integrity()

    @given(
        start=st.integers(min_value=0, max_value=10000),
        length=st.integers(min_value=0, max_value=1000),
        line=st.integers(min_value=1, max_value=9999),
        col=st.integers(min_value=1, max_value=999),
        msg=_messages,
    )
    def test_hash_with_span_property(
        self, start: int, length: int, line: int, col: int, msg: str
    ) -> None:
        """PROPERTY: Hash with diagnostic span is 16 bytes and verifies."""
        span = SourceSpan(start=start, end=start + length, line=line, column=col)
        diag = Diagnostic(
            code=DiagnosticCode.MESSAGE_NOT_FOUND,
            message=msg,
            span=span,
        )
        err = FrozenFluentError(msg, ErrorCategory.REFERENCE, diagnostic=diag)
        assert len(err.content_hash) == 16
        assert err.verify_integrity()
        event(f"span_length={length}")

    def test_hash_with_resolution_path_covered(self) -> None:
        """Hash branch for diagnostic.resolution_path is not None is exercised."""
        diag = Diagnostic(
            code=DiagnosticCode.CYCLIC_REFERENCE,
            message="cycle",
            resolution_path=("msg-a", "msg-b", "msg-a"),
        )
        err = FrozenFluentError("cycle", ErrorCategory.CYCLIC, diagnostic=diag)
        assert len(err.content_hash) == 16
        assert err.verify_integrity()

    @given(
        path=st.lists(_identifiers, min_size=1, max_size=5).map(tuple),
        msg=_messages,
    )
    def test_hash_with_resolution_path_property(
        self, path: tuple[str, ...], msg: str
    ) -> None:
        """PROPERTY: Hash with resolution_path is 16 bytes and verifies."""
        diag = Diagnostic(
            code=DiagnosticCode.CYCLIC_REFERENCE,
            message=msg,
            resolution_path=path,
        )
        err = FrozenFluentError(msg, ErrorCategory.CYCLIC, diagnostic=diag)
        assert len(err.content_hash) == 16
        assert err.verify_integrity()
        event(f"path_len={len(path)}")

    @given(msg=_messages, cat=error_categories(), ctx=frozen_error_contexts())
    def test_hash_with_context_property(
        self, msg: str, cat: ErrorCategory, ctx: FrozenErrorContext
    ) -> None:
        """PROPERTY: Hash with context is 16 bytes and verifies."""
        err = FrozenFluentError(msg, cat, context=ctx)
        assert len(err.content_hash) == 16
        assert err.verify_integrity()
        has_ctx_data = any([
            ctx.input_value,
            ctx.locale_code,
            ctx.parse_type,
            ctx.fallback_value,
        ])
        event(f"has_ctx_data={has_ctx_data}")

    @given(
        msg=_messages,
        cat=error_categories(),
        diag=diagnostics(),
        ctx=frozen_error_contexts(),
    )
    def test_hash_all_fields_combined(
        self,
        msg: str,
        cat: ErrorCategory,
        diag: Diagnostic,
        ctx: FrozenErrorContext,
    ) -> None:
        """PROPERTY: Hash over all optional fields is 16 bytes and verifies."""
        err = FrozenFluentError(msg, cat, diagnostic=diag, context=ctx)
        assert len(err.content_hash) == 16
        assert err.verify_integrity()
        event(f"cat={cat.value}")

    @given(msg1=_messages, msg2=_messages, cat=error_categories())
    def test_different_messages_yield_different_hashes(
        self, msg1: str, msg2: str, cat: ErrorCategory
    ) -> None:
        """PROPERTY: Different messages (almost always) yield different hashes.

        BLAKE2b-128 has negligible collision probability; this is a sanity check.
        We only assert when messages are actually different.
        """
        if msg1 != msg2:
            e1 = FrozenFluentError(msg1, cat)
            e2 = FrozenFluentError(msg2, cat)
            assert e1.content_hash != e2.content_hash
        event("outcome=hash_collision_checked")


# ===========================================================================
# verify_integrity
# ===========================================================================


class TestVerifyIntegrity:
    """Tests for verify_integrity()."""

    @given(msg=_messages, cat=error_categories())
    def test_verify_integrity_passes_for_pristine_error(
        self, msg: str, cat: ErrorCategory
    ) -> None:
        """PROPERTY: verify_integrity() returns True for freshly constructed errors."""
        err = FrozenFluentError(msg, cat)
        assert err.verify_integrity()
        event(f"cat={cat.value}")

    @given(msg=_messages, cat=error_categories(), ctx=frozen_error_contexts())
    def test_verify_integrity_with_context(
        self, msg: str, cat: ErrorCategory, ctx: FrozenErrorContext
    ) -> None:
        """PROPERTY: verify_integrity() returns True when context supplied."""
        err = FrozenFluentError(msg, cat, context=ctx)
        assert err.verify_integrity()
        event("context=present")

    @given(msg=_messages, cat=error_categories(), diag=diagnostics())
    def test_verify_integrity_with_diagnostic(
        self, msg: str, cat: ErrorCategory, diag: Diagnostic
    ) -> None:
        """PROPERTY: verify_integrity() returns True when diagnostic supplied."""
        err = FrozenFluentError(msg, cat, diagnostic=diag)
        assert err.verify_integrity()
        event("diagnostic=present")


# ===========================================================================
# Mutation protection: __setattr__ and __delattr__
# ===========================================================================


class TestMutationProtection:
    """Tests for immutability enforcement after construction."""

    def test_setattr_raises_after_freeze(self) -> None:
        """__setattr__ raises ImmutabilityViolationError for non-exception attrs."""
        err = FrozenFluentError("msg", ErrorCategory.REFERENCE)
        with pytest.raises(ImmutabilityViolationError):
            err._message = "modified"

    def test_setattr_raises_for_category(self) -> None:
        """__setattr__ raises ImmutabilityViolationError when modifying _category."""
        err = FrozenFluentError("msg", ErrorCategory.REFERENCE)
        with pytest.raises(ImmutabilityViolationError):
            err._category = ErrorCategory.CYCLIC

    def test_setattr_allows_traceback(self) -> None:
        """__setattr__ allows __traceback__ (Python exception propagation)."""
        err = FrozenFluentError("msg", ErrorCategory.REFERENCE)
        # Raising and catching sets __traceback__; must not raise
        try:
            raise err
        except FrozenFluentError:
            pass  # __traceback__ was set by the propagation machinery

    def test_setattr_allows_notes(self) -> None:
        """__setattr__ allows __notes__ (PEP 678 exception notes)."""
        err = FrozenFluentError("msg", ErrorCategory.REFERENCE)
        err.__notes__ = ["additional context"]
        assert err.__notes__ == ["additional context"]

    def test_delattr_raises_unconditionally(self) -> None:
        """__delattr__ always raises ImmutabilityViolationError."""
        err = FrozenFluentError("msg", ErrorCategory.REFERENCE)
        with pytest.raises(ImmutabilityViolationError):
            del err._message

    def test_delattr_raises_for_any_name(self) -> None:
        """__delattr__ raises regardless of the attribute name."""
        err = FrozenFluentError("msg", ErrorCategory.REFERENCE)
        with pytest.raises(ImmutabilityViolationError):
            del err._frozen

    @given(msg=_messages, cat=error_categories())
    def test_content_hash_unchanged_after_attempted_mutation(
        self, msg: str, cat: ErrorCategory
    ) -> None:
        """PROPERTY: content_hash is stable even if mutation is attempted."""
        err = FrozenFluentError(msg, cat)
        original_hash = err.content_hash
        with contextlib.suppress(ImmutabilityViolationError):
            err._message = "tampered"
        assert err.content_hash == original_hash
        assert err.verify_integrity()
        event(f"cat={cat.value}")


# ===========================================================================
# Sealed type: __init_subclass__
# ===========================================================================


class TestSealedType:
    """Tests for subclassing prevention."""

    def test_subclassing_raises_type_error(self) -> None:
        """__init_subclass__ raises TypeError when subclassing is attempted."""
        with pytest.raises(TypeError, match="cannot be subclassed"):

            class _SubError(  # type: ignore[misc]  # pylint: disable=subclassed-final-class
                FrozenFluentError
            ):
                pass

    def test_subclassing_message_mentions_error_category(self) -> None:
        """TypeError message directs user to ErrorCategory."""
        with pytest.raises(TypeError) as exc_info:

            class _AnotherSubError(  # type: ignore[misc]  # pylint: disable=subclassed-final-class
                FrozenFluentError
            ):
                pass

        assert "ErrorCategory" in str(exc_info.value)


# ===========================================================================
# Value semantics: __hash__, __eq__, __repr__
# ===========================================================================


class TestValueSemantics:
    """Tests for __hash__, __eq__, and __repr__."""

    @given(msg=_messages, cat=error_categories())
    def test_hash_is_integer(self, msg: str, cat: ErrorCategory) -> None:
        """PROPERTY: hash() returns a Python integer."""
        err = FrozenFluentError(msg, cat)
        h = hash(err)
        assert isinstance(h, int)
        event(f"cat={cat.value}")

    @given(msg=_messages, cat=error_categories())
    def test_equal_errors_have_same_hash(
        self, msg: str, cat: ErrorCategory
    ) -> None:
        """PROPERTY: Equal errors (same content) have equal hash values."""
        e1 = FrozenFluentError(msg, cat)
        e2 = FrozenFluentError(msg, cat)
        assert e1 == e2
        assert hash(e1) == hash(e2)
        event("outcome=equal")

    @given(
        msg1=_messages,
        msg2=_messages,
        cat=error_categories(),
    )
    def test_different_messages_are_not_equal(
        self, msg1: str, msg2: str, cat: ErrorCategory
    ) -> None:
        """PROPERTY: Errors with different messages compare not-equal."""
        if msg1 != msg2:
            e1 = FrozenFluentError(msg1, cat)
            e2 = FrozenFluentError(msg2, cat)
            assert e1 != e2
        event("outcome=inequality_checked")

    @given(msg=_messages)
    def test_different_categories_are_not_equal(self, msg: str) -> None:
        """PROPERTY: Errors with different categories compare not-equal."""
        cats = list(ErrorCategory)
        if len(cats) >= 2:
            e1 = FrozenFluentError(msg, cats[0])
            e2 = FrozenFluentError(msg, cats[1])
            assert e1 != e2
        event("outcome=category_differs")

    @given(msg=_messages, cat=error_categories())
    def test_eq_returns_not_implemented_for_non_error(
        self, msg: str, cat: ErrorCategory
    ) -> None:
        """PROPERTY: __eq__ returns NotImplemented for non-FrozenFluentError."""
        err = FrozenFluentError(msg, cat)
        # Call __eq__ directly to inspect the return value, not the operator result.
        # The == operator masks NotImplemented via reflected __eq__ fallback.
        result = err.__eq__("not an error")  # pylint: disable=unnecessary-dunder-call
        assert result is NotImplemented
        event("outcome=not_implemented")

    @given(msg=_messages, cat=error_categories())
    def test_repr_contains_message(self, msg: str, cat: ErrorCategory) -> None:
        """PROPERTY: repr() contains the error message."""
        err = FrozenFluentError(msg, cat)
        r = repr(err)
        assert isinstance(r, str)
        assert "FrozenFluentError" in r
        assert repr(msg) in r
        event(f"cat={cat.value}")

    @given(msg=_messages, cat=error_categories())
    def test_repr_contains_category(self, msg: str, cat: ErrorCategory) -> None:
        """PROPERTY: repr() contains the error category."""
        err = FrozenFluentError(msg, cat)
        assert cat.value in repr(err)
        event(f"cat={cat.value}")

    @given(msg=_messages, cat=error_categories())
    def test_usable_in_set(self, msg: str, cat: ErrorCategory) -> None:
        """PROPERTY: FrozenFluentError instances are usable in sets (hashable)."""
        e1 = FrozenFluentError(msg, cat)
        e2 = FrozenFluentError(msg, cat)
        s = {e1, e2}
        # Equal errors (same content) collapse to one entry in the set
        assert len(s) == 1
        event("outcome=set_dedup")

    @given(msg=_messages, cat=error_categories())
    def test_usable_as_dict_key(self, msg: str, cat: ErrorCategory) -> None:
        """PROPERTY: FrozenFluentError instances are usable as dict keys."""
        err = FrozenFluentError(msg, cat)
        d = {err: "value"}
        assert d[err] == "value"
        event("outcome=dict_key")


# ===========================================================================
# Exception behavior: raise / catch
# ===========================================================================


class TestExceptionBehavior:
    """Tests for raise/catch as a Python exception."""

    @given(msg=_messages, cat=error_categories())
    def test_can_be_raised_and_caught(
        self, msg: str, cat: ErrorCategory
    ) -> None:
        """PROPERTY: FrozenFluentError can be raised and caught."""
        caught: FrozenFluentError | None = None
        try:
            raise FrozenFluentError(msg, cat)
        except FrozenFluentError as e:
            caught = e
        assert caught is not None
        assert caught.message == msg
        assert caught.category == cat
        event(f"cat={cat.value}")

    @given(msg=_messages, cat=error_categories())
    def test_str_matches_message(self, msg: str, cat: ErrorCategory) -> None:
        """PROPERTY: str(error) equals the constructor message argument."""
        err = FrozenFluentError(msg, cat)
        assert str(err) == msg
        event(f"msg_len={len(msg)}")

    @given(msg=_messages, cat=error_categories())
    def test_is_base_exception_subclass(
        self, msg: str, cat: ErrorCategory
    ) -> None:
        """PROPERTY: FrozenFluentError is catchable as Exception."""
        caught: Exception | None = None
        try:
            raise FrozenFluentError(msg, cat)
        except Exception as e:
            caught = e
        assert isinstance(caught, FrozenFluentError)
        event(f"cat={cat.value}")


# ===========================================================================
# Promoted examples from edge-case discovery
# ===========================================================================


class TestEdgeCases:
    """Promoted edge cases from exploratory testing."""

    @example(msg="", cat=ErrorCategory.REFERENCE)
    @given(msg=st.just(""), cat=error_categories())
    def test_empty_message_permitted(
        self, msg: str, cat: ErrorCategory
    ) -> None:
        """Empty string message is accepted and stored faithfully."""
        err = FrozenFluentError(msg, cat)
        assert err.message == ""
        assert err.verify_integrity()
        event("edge=empty_message")

    def test_context_with_all_fields_populated(self) -> None:
        """FrozenFluentError with fully-populated FrozenErrorContext."""
        ctx = FrozenErrorContext(
            input_value="1.234,56",
            locale_code="de_DE",
            parse_type="decimal",
            fallback_value="0",
        )
        err = FrozenFluentError(
            "parse failed",
            ErrorCategory.PARSE,
            context=ctx,
        )
        assert err.input_value == "1.234,56"
        assert err.locale_code == "de_DE"
        assert err.parse_type == "decimal"
        assert err.fallback_value == "0"
        assert err.verify_integrity()

    def test_diagnostic_with_span_and_resolution_path(self) -> None:
        """FrozenFluentError with diagnostic carrying both span and resolution_path."""
        span = SourceSpan(start=5, end=15, line=2, column=6)
        diag = Diagnostic(
            code=DiagnosticCode.CYCLIC_REFERENCE,
            message="cycle: a -> b -> a",
            span=span,
            resolution_path=("a", "b", "a"),
        )
        err = FrozenFluentError(
            "cycle: a -> b -> a",
            ErrorCategory.CYCLIC,
            diagnostic=diag,
        )
        assert err.diagnostic is diag
        assert err.verify_integrity()

    @given(
        code=diagnostic_codes(),
        msg=_messages,
        span=source_spans(),
    )
    def test_diagnostic_with_arbitrary_span(
        self,
        code: DiagnosticCode,
        msg: str,
        span: SourceSpan,
    ) -> None:
        """PROPERTY: Arbitrary span in diagnostic hashes and verifies correctly."""
        diag = Diagnostic(code=code, message=msg, span=span)
        err = FrozenFluentError(msg, ErrorCategory.REFERENCE, diagnostic=diag)
        assert err.verify_integrity()
        event(f"code_range={'ref' if code.value < 2000 else 'other'}")
